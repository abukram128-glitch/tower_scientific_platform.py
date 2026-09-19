# ============================================================================
# 🔐 tawor_auth.py — مصادقة JWT احترافية للتطبيق و API
# ============================================================================
import os
import sqlite3
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ─── مكتبات JWT ───
try:
    from jose import JWTError, jwt
    JOSE_AVAILABLE = True
except ImportError:
    JOSE_AVAILABLE = False

try:
    from passlib.context import CryptContext
    PWD_CTX = CryptContext(schemes=["bcrypt"], deprecated="auto")
    PASSLIB_AVAILABLE = True
except ImportError:
    PASSLIB_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────
# الإعدادات (من متغيرات البيئة)
# ─────────────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("TAWOR_JWT_SECRET",
                        secrets.token_urlsafe(64))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("TAWOR_JWT_EXPIRE_MIN", "1440"))  # 24 ساعة


class AuthCore:
    """جوهر المصادقة: تشفير، تحقق، إصدار توكن، قراءة توكن."""

    @staticmethod
    def hash_password(password: str) -> str:
        if PASSLIB_AVAILABLE:
            return PWD_CTX.hash(password)
        # fallback آمن نسبياً
        salt = secrets.token_hex(16)
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"sha256${salt}${h}"

    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        if not hashed:
            return False
        if hashed.startswith("sha256$"):
            try:
                _, salt, h = hashed.split("$", 2)
                return hashlib.sha256(
                    (salt + password).encode()).hexdigest() == h
            except Exception:
                return False
        if PASSLIB_AVAILABLE:
            try:
                return PWD_CTX.verify(password, hashed)
            except Exception:
                return False
        return False

    @staticmethod
    def create_access_token(data: dict,
                             expires_delta: Optional[timedelta] = None) -> str:
        if not JOSE_AVAILABLE:
            raise RuntimeError("pip install python-jose[cryptography]")
        to_encode = data.copy()
        expire = datetime.utcnow() + (
            expires_delta or
            timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire, "iat": datetime.utcnow()})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Dict:
        if not JOSE_AVAILABLE:
            raise RuntimeError("pip install python-jose[cryptography]")
        try:
            return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="توكن غير صالح أو منتهي",
                headers={"WWW-Authenticate": "Bearer"})


# ─────────────────────────────────────────────────────────────────────────
# قاعدة بيانات المستخدمين للـ API (مشتركة مع Streamlit)
# ─────────────────────────────────────────────────────────────────────────
class APIAuthDB:
    DB_PATH = os.getenv("TAWOR_DB_PATH",
                         "tawor_user_data/tawor_api.db")

    @staticmethod
    def _conn():
        os.makedirs(os.path.dirname(APIAuthDB.DB_PATH), exist_ok=True)
        return sqlite3.connect(APIAuthDB.DB_PATH)

    @staticmethod
    def init():
        conn = APIAuthDB._conn()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS api_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'breeder',
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            last_login TEXT,
            api_key TEXT UNIQUE)''')
        c.execute('''CREATE TABLE IF NOT EXISTS formula_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, action TEXT, formula_id TEXT,
            ip TEXT, user_agent TEXT, created_at TEXT)''')
        conn.commit()
        conn.close()

    @staticmethod
    def create_user(username: str, password: str, email: str = "",
                     role: str = "breeder") -> Dict:
        conn = APIAuthDB._conn()
        c = conn.cursor()
        try:
            api_key = secrets.token_urlsafe(32)
            c.execute(
                "INSERT INTO api_users "
                "(username, email, password_hash, role, "
                "created_at, api_key) VALUES (?,?,?,?,?,?)",
                (username, email or None,
                 AuthCore.hash_password(password),
                 role, datetime.utcnow().isoformat(), api_key))
            conn.commit()
            uid = c.lastrowid
            return {"id": uid, "username": username, "role": role,
                    "api_key": api_key}
        except sqlite3.IntegrityError:
            raise HTTPException(400, "اسم المستخدم موجود مسبقاً")
        finally:
            conn.close()

    @staticmethod
    def authenticate(username: str, password: str) -> Optional[Dict]:
        conn = APIAuthDB._conn()
        c = conn.cursor()
        try:
            row = c.execute(
                "SELECT id, username, email, password_hash, role, "
                "is_active FROM api_users WHERE username=?",
                (username,)).fetchone()
        finally:
            conn.close()
        if not row or not row[5]:
            return None
        if not AuthCore.verify_password(password, row[3]):
            return None
        # تحديث آخر تسجيل دخول
        conn = APIAuthDB._conn()
        c = conn.cursor()
        c.execute("UPDATE api_users SET last_login=? WHERE id=?",
                   (datetime.utcnow().isoformat(), row[0]))
        conn.commit()
        conn.close()
        return {"id": row[0], "username": row[1], "email": row[2],
                "role": row[4]}

    @staticmethod
    def get_by_api_key(api_key: str) -> Optional[Dict]:
        conn = APIAuthDB._conn()
        c = conn.cursor()
        try:
            row = c.execute(
                "SELECT id, username, email, role, is_active "
                "FROM api_users WHERE api_key=?",
                (api_key,)).fetchone()
        finally:
            conn.close()
        if not row or not row[4]:
            return None
        return {"id": row[0], "username": row[1], "email": row[2],
                "role": row[3]}

    @staticmethod
    def audit(user_id: int, action: str, formula_id: str = "",
               ip: str = "", ua: str = ""):
        conn = APIAuthDB._conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO formula_audit "
            "(user_id, action, formula_id, ip, user_agent, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, action, formula_id, ip, ua,
             datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()


APIAuthDB.init()


# ─────────────────────────────────────────────────────────────────────────
# FastAPI Dependencies
# ─────────────────────────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Dict:
    """يتحقق من التوكن (Bearer) أو API Key (يبدأ بـ 'ApiKey ')."""
    if not creds:
        # جرّب هيدر API Key التقليدي
        raise HTTPException(401, "التوكن مطلوب",
            headers={"WWW-Authenticate": "Bearer"})

    token = creds.credentials
    # API Key مباشر؟
    if token.startswith("twk_"):
        user = APIAuthDB.get_by_api_key(token)
        if user:
            return user
        raise HTTPException(401, "API Key غير صالح")

    # JWT
    payload = AuthCore.decode_token(token)
    if "sub" not in payload:
        raise HTTPException(401, "توكن غير صالح")
    return {"id": int(payload["sub"]),
            "username": payload.get("username", ""),
            "role": payload.get("role", "breeder")}


def require_role(*roles: str):
    """Factory لتقييد الوصول بأدوار محددة."""
    def _checker(user: Dict = Depends(get_current_user)) -> Dict:
        if user.get("role") not in roles and user.get("role") != "owner":
            raise HTTPException(403, "لا تملك صلاحية هذه العملية")
        return user
    return _checker


def create_initial_admin():
    """ينشئ admin افتراضي إن لم يوجد."""
    conn = APIAuthDB._conn()
    c = conn.cursor()
    row = c.execute("SELECT id FROM api_users WHERE username='admin'"
                     ).fetchone()
    conn.close()
    if not row:
        admin_pass = os.getenv("TAWOR_ADMIN_PASS",
                                secrets.token_urlsafe(12))
        u = APIAuthDB.create_user("admin", admin_pass,
                                   "admin@tawornology.com", "owner")
        print(f"🔑 تم إنشاء admin — كلمة المرور: {admin_pass}")
        print(f"🔑 API Key: {u['api_key']}")
        return u
    return None
