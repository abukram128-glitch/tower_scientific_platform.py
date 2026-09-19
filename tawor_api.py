# ============================================================================
# 🌐 tawor_api.py — Tawornology API v19.5 (JWT + WhatsApp + Audit)
# uvicorn tawor_api:app --host 0.0.0.0 --port 8502
# ============================================================================
import asyncio, json, sqlite3, secrets, time, os, hashlib, hmac
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import (FastAPI, HTTPException, Query, Depends,
                      BackgroundTasks, Request)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import numpy as np

# ─── الوحدات الداخلية ───
from tawor_auth import (AuthCore, APIAuthDB, get_current_user,
                         require_role, create_initial_admin)
from tawor_webhook import WhatsAppNotifier   # ← من الملف 3


app = FastAPI(
    title="🌾 Tawornology API",
    version="19.5.0",
    description="واجهة برمجية آمنة بـ JWT — تكوين، حفظ، تنبؤ",
    docs_url="/docs", redoc_url="/redoc",
    openapi_tags=[
        {"name": "عام", "description": "فحص الحالة والبيانات العامة"},
        {"name": "مصادقة", "description": "تسجيل ودخول وإدارة JWT"},
        {"name": "التكوين", "description": "تكوين الخلطات (يتطلب توكن)"},
        {"name": "المكتبة", "description": "حفظ/استرجاع الخلطات"},
        {"name": "التحليلات", "description": "حساسية، مونت كارلو، تنبؤ"},
    ])

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])

# ─── تحميل محرك التكوين (نفس السابق) ───
try:
    from tawor_engine import formulate_feed, STANDARD_VALUES, \
                             BIG_FEEDS_LIBRARY, MarketPriceEngine, \
                             sensitivity_analysis, monte_carlo_cost, \
                             pareto_frontier, shadow_prices
    ENGINE_LOADED = True
except ImportError:
    ENGINE_LOADED = False
    print("⚠️ tawor_engine.py غير موجود — استخرج دوال التكوين إليه")


# ─────────────────────────────────────────────────────────────────────────
# نماذج Pydantic
# ─────────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    email: str = ""
    role: str = "breeder"

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]

class FormulationRequest(BaseModel):
    animal_type: str
    stage: str
    ingredients: List[str] = Field(..., min_length=3)
    prices: Optional[Dict[str, float]] = None
    use_cp_basis: bool = False

class SaveFormulaRequest(BaseModel):
    formula_name: str
    breed: str = ""
    requester: str = ""
    notes: str = ""
    result: Dict[str, Any]
    send_whatsapp: bool = False
    whatsapp_to: Optional[str] = None

class WhatsAppRequest(BaseModel):
    to_phone: str
    message: str


# ─────────────────────────────────────────────────────────────────────────
# 🟢 نقاط عامة
# ─────────────────────────────────────────────────────────────────────────
@app.get("/", tags=["عام"])
def root():
    return {"service": "Tawornology API", "version": "19.5",
            "engine": "✅" if ENGINE_LOADED else "❌",
            "auth": "JWT + API Key"}

@app.get("/health", tags=["عام"])
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(),
            "engine_loaded": ENGINE_LOADED,
            "jwt_ready": True}

@app.on_event("startup")
def startup():
    create_initial_admin()


# ─────────────────────────────────────────────────────────────────────────
# 🔐 المصادقة
# ─────────────────────────────────────────────────────────────────────────
@app.post("/auth/register", tags=["مصادقة"],
           response_model=Dict[str, Any])
def register(req: RegisterRequest):
    u = APIAuthDB.create_user(req.username, req.password,
                                req.email, req.role)
    APIAuthDB.audit(u["id"], "register")
    return {"success": True, "user_id": u["id"],
            "username": u["username"], "role": u["role"],
            "api_key": u["api_key"]}


@app.post("/auth/login", tags=["مصادقة"],
           response_model=TokenResponse)
def login(req: LoginRequest):
    user = APIAuthDB.authenticate(req.username, req.password)
    if not user:
        raise HTTPException(401, "بيانات خاطئة")
    token = AuthCore.create_access_token({
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"]})
    APIAuthDB.audit(user["id"], "login")
    return TokenResponse(
        access_token=token,
        expires_in=1440 * 60,
        user={"id": user["id"], "username": user["username"],
              "role": user["role"]})


@app.get("/auth/me", tags=["مصادقة"])
def me(user: Dict = Depends(get_current_user)):
    return user


# ─────────────────────────────────────────────────────────────────────────
# 🧬 التكوين (محمي)
# ─────────────────────────────────────────────────────────────────────────
@app.post("/formulate", tags=["التكوين"])
def api_formulate(req: FormulationRequest,
                   user: Dict = Depends(get_current_user)):
    if not ENGINE_LOADED:
        raise HTTPException(503, "المحرك غير متوفر")
    t0 = time.time()
    result = formulate_feed(
        req.animal_type, req.stage, req.ingredients,
        prices=req.prices, use_cp_basis=req.use_cp_basis)
    result["_raw"] = None
    result["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
    APIAuthDB.audit(user["id"], "formulate",
                     result.get("message", "")[:50])
    return result


@app.post("/formulate/stream", tags=["التكوين"])
async def api_formulate_stream(req: FormulationRequest,
                                 user: Dict = Depends(get_current_user)):
    async def gen():
        steps = [("🔍 التحقق", 0.05), ("📥 تحضير المواد", 0.15),
                 ("🧮 بناء المصفوفات", 0.30),
                 ("⚙️ Linear Programming", 0.60),
                 ("📊 الأملاح والألياف", 0.80),
                 ("🔬 التقييم", 0.92), ("✅ اكتمل", 1.00)]
        for label, p in steps:
            yield f"data: {json.dumps({'step': label, 'progress': p}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.12)
        try:
            r = formulate_feed(req.animal_type, req.stage,
                                req.ingredients, prices=req.prices,
                                use_cp_basis=req.use_cp_basis)
            r["_raw"] = None
            yield f"data: {json.dumps({'result': r}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────────────────────
# 📚 المكتبة (محمي + WhatsApp)
# ─────────────────────────────────────────────────────────────────────────
@app.post("/formulas/save", tags=["المكتبة"])
def api_save_formula(req: SaveFormulaRequest,
                       background: BackgroundTasks,
                       user: Dict = Depends(get_current_user)):
    db_path = os.getenv("TAWOR_DB_PATH",
                         "tawor_user_data/tawor_api.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS feed_formulas (
        formula_id TEXT PRIMARY KEY, formula_name TEXT, animal_type TEXT,
        breed TEXT, stage TEXT, target_dp REAL, target_se REAL,
        ingredients TEXT, total_cost REAL, cost_per_ton REAL,
        created_by TEXT, created_date TEXT, is_approved INTEGER DEFAULT 0,
        usage_count INTEGER DEFAULT 0, requester_name TEXT)''')

    fid = secrets.token_hex(16)
    res = req.result
    c.execute("INSERT INTO feed_formulas VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (fid, req.formula_name, res.get("animal_type", ""),
         req.breed, res.get("stage", ""),
         res.get("totals", {}).get("target_DP", 0),
         res.get("totals", {}).get("target_SE", 0),
         json.dumps(res, ensure_ascii=False),
         res.get("cost_per_ton", 0) * 1000,
         res.get("cost_per_ton", 0),
         user["username"], datetime.utcnow().isoformat(),
         0, 0, req.requester))
    conn.commit()
    conn.close()
    APIAuthDB.audit(user["id"], "save_formula", fid)

    # ═══ إرسال WhatsApp في الخلفية ═══
    wa_status = "معطّل"
    if req.send_whatsapp and req.whatsapp_to:
        notifier = WhatsAppNotifier()
        if notifier.enabled:
            formula_txt = "\n".join(
                f"• {k}: {v:.2f}%" for k, v in
                res.get("formula", {}).items())
            msg = (f"🌾 *خلطة جديدة*\n"
                    f"الاسم: {req.formula_name}\n"
                    f"الحيوان: {res.get('animal_type','')}\n"
                    f"المرحلة: {res.get('stage','')}\n"
                    f"💰 ${res.get('cost_per_ton',0):.2f}/طن\n\n"
                    f"*المكونات:*\n{formula_txt}")
            background.add_task(notifier.send_text,
                                 req.whatsapp_to, msg)
            wa_status = "قيد الإرسال"
        else:
            wa_status = "غير مُهيّأ"

    return {"success": True, "formula_id": fid,
            "whatsapp_status": wa_status,
            "message": f"✅ تم الحفظ: {req.formula_name}"}


@app.get("/formulas", tags=["المكتبة"])
def api_list_formulas(limit: int = Query(100, ge=1, le=1000),
                        user: Dict = Depends(get_current_user)):
    db_path = os.getenv("TAWOR_DB_PATH",
                         "tawor_user_data/tawor_api.db")
    if not os.path.exists(db_path):
        return {"formulas": [], "count": 0}
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT formula_id, formula_name, animal_type, stage, "
            "cost_per_ton, created_by, created_date "
            "FROM feed_formulas ORDER BY created_date DESC LIMIT ?",
            (limit,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    return {"count": len(rows), "formulas": [{
        "formula_id": r[0], "formula_name": r[1], "animal_type": r[2],
        "stage": r[3], "cost_per_ton": r[4], "created_by": r[5],
        "created_date": r[6]} for r in rows]}


@app.get("/formulas/{formula_id}", tags=["المكتبة"])
def api_get_formula(formula_id: str,
                     user: Dict = Depends(get_current_user)):
    db_path = os.getenv("TAWOR_DB_PATH",
                         "tawor_user_data/tawor_api.db")
    if not os.path.exists(db_path):
        raise HTTPException(404, "لا توجد قاعدة بيانات")
    conn = sqlite3.connect(db_path)
    r = conn.execute("SELECT * FROM feed_formulas WHERE formula_id=?",
                      (formula_id,)).fetchone()
    conn.close()
    if not r:
        raise HTTPException(404, "غير موجودة")
    try:
        payload = json.loads(r[8])
    except Exception:
        payload = {}
    return {"formula_id": r[0], "formula_name": r[1],
            "animal_type": r[2], "breed": r[3], "stage": r[4],
            "payload": payload, "cost_per_ton": r[10],
            "created_by": r[11], "created_date": r[12]}


@app.delete("/formulas/{formula_id}", tags=["المكتبة"])
def api_delete_formula(formula_id: str,
                         user: Dict = Depends(
                             require_role("owner", "specialist"))):
    db_path = os.getenv("TAWOR_DB_PATH",
                         "tawor_user_data/tawor_api.db")
    if not os.path.exists(db_path):
        raise HTTPException(404, "لا توجد قاعدة بيانات")
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM feed_formulas WHERE formula_id=?",
                  (formula_id,))
    conn.commit()
    conn.close()
    APIAuthDB.audit(user["id"], "delete_formula", formula_id)
    return {"success": True}


# ─────────────────────────────────────────────────────────────────────────
# 📲 WhatsApp مباشر
# ─────────────────────────────────────────────────────────────────────────
@app.post("/whatsapp/send", tags=["عام"])
def api_send_whatsapp(req: WhatsAppRequest,
                        user: Dict = Depends(get_current_user)):
    notifier = WhatsAppNotifier()
    if not notifier.enabled:
        raise HTTPException(503, "خدمة واتساب غير مُهيّأة")
    ok, msg = notifier.send_text(req.to_phone, req.message)
    return {"success": ok, "message": msg}


# ─────────────────────────────────────────────────────────────────────────
# 📈 التنبؤ
# ─────────────────────────────────────────────────────────────────────────
@app.post("/predict", tags=["التحليلات"])
def api_predict(ingredient_name: str, days_ahead: int = 7,
                 user: Dict = Depends(get_current_user)):
    db_path = os.getenv("TAWOR_DB_PATH",
                         "tawor_user_data/tawor_api.db")
    if not os.path.exists(db_path):
        return {"prediction": None}
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT price FROM price_history WHERE ingredient_name=? "
            "ORDER BY record_date DESC LIMIT 30",
            (ingredient_name,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    if len(rows) < 5:
        return {"prediction": None, "message": "بيانات غير كافية"}
    prices = [r[0] for r in rows]
    w = np.arange(1, len(prices) + 1)
    wavg = float(np.average(prices, weights=w))
    trend = float((prices[0] - prices[-1]) / len(prices))
    pred = max(0, wavg + trend * days_ahead)
    return {"current_price": prices[0],
            "prediction": round(pred, 2),
            "trend": "up" if trend > 0 else "down" if trend < 0 else "stable"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("tawor_api:app", host="0.0.0.0", port=8502)
