# ============================================================================
# 🌾 تاور نولجي Tawornology v19.6 — الملف الرئيسي المُدمج
# ============================================================================
# المشرف: الاختصاصي م. عبد القادر إسماعيل تاور - اختصاصي تغذية الحيوان
# ============================================================================

import streamlit as st
import numpy as np
import pandas as pd
import json, os, base64, secrets, io, sqlite3, warnings, re, random
import urllib.parse, hashlib, hmac, smtplib
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ─── استيراد محرك التكوين ───
from tawor_engine import (
    STANDARD_VALUES, BIG_FEEDS_LIBRARY, FLAT_FEED_DB,
    MINERALS_FIBER_DB, MINERAL_FIBER_STANDARDS, EXCHANGE_RATES,
    MarketPriceEngine, calculate_minerals_fibers,
    evaluate_against_standard, get_ideal_ca_p_ratio,
    formulate_feed, sensitivity_analysis, monte_carlo_cost,
    pareto_frontier, shadow_prices)

# ─── استيراد الوحدات المساعدة ───
from tawor_modules import ExcelExporter, FormulaLibrary
from tawor_admin_dashboard import render_admin_dashboard

# ─── مكتبات بصرية ───
from scipy.optimize import linprog
from sklearn.linear_model import LinearRegression
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ─── PDF ───
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white
from reportlab.platypus import (Table, TableStyle, Paragraph, Spacer,
                                 Image, SimpleDocTemplate, PageBreak)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
import arabic_reshaper
from bidi.algorithm import get_display
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

warnings.filterwarnings('ignore')

try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    GTTS_AVAILABLE = False


# =====================================================================
# إعدادات الصفحة
# =====================================================================
st.set_page_config(
    page_title="تاور نولجي Tawornology v19.6",
    page_icon="🌾", layout="wide",
    initial_sidebar_state="collapsed")


# =====================================================================
# معالج النص العربي
# =====================================================================
def ar(text) -> str:
    if text is None:
        return ""
    s = str(text)
    if not s.strip():
        return s
    try:
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


@st.cache_resource
def _setup_matplotlib_arabic() -> str:
    candidates = [
        "Amiri-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf"]
    chosen = "DejaVu Sans"
    for p in candidates:
        if os.path.exists(p):
            try:
                fm.fontManager.addfont(p)
                chosen = fm.FontProperties(fname=p).get_name()
                break
            except Exception:
                continue
    plt.rcParams['font.family'] = chosen
    plt.rcParams['axes.unicode_minus'] = False
    return chosen


_MAT_FONT = _setup_matplotlib_arabic()


# =====================================================================
# دوال المستخدم
# =====================================================================
def get_current_user_name() -> str:
    user = st.session_state.get("user") or {}
    return user.get("full_name", "مستخدم غير معروف")


def get_current_user_role() -> str:
    return st.session_state.get("user_role", "public")


def get_or_create_device_id() -> str:
    if "device_id" not in st.session_state:
        st.session_state["device_id"] = secrets.token_hex(16)
    return st.session_state["device_id"]


# =====================================================================
# أكواد الدخول
# =====================================================================
CODES_DB = {
    "202687": {"role": "owner",
               "name": "الاختصاصي م. عبد القادر إسماعيل تاور", "level": 3},
    "2020": {"role": "specialist", "name": "المختص والزملاء", "level": 2},
    "2024": {"role": "veterinarian", "name": "الطبيب البيطري", "level": 2},
    "2025": {"role": "nutritionist", "name": "أخصائي التغذية", "level": 2},
    "2026": {"role": "breeder", "name": "المربي", "level": 1}}


def validate_access_code(input_code: str):
    if not input_code:
        return None
    clean = input_code.strip()
    if len(clean) < 4:
        return None
    for stored_code, data in CODES_DB.items():
        try:
            if hmac.compare_digest(clean, stored_code):
                return data
        except Exception:
            continue
    return None


# =====================================================================
# البريد والواتساب
# =====================================================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "abukram128@gmail.com"
OWNER_EMAIL = "abukram128@gmail.com"
WHATSAPP_NUMBER = "+249123533489"

if "email_password" not in st.session_state:
    try:
        st.session_state["email_password"] = st.secrets["email"]["password"]
    except Exception:
        st.session_state["email_password"] = None

PHOTO_OPTIONS = ("14686.jpg", "1000069464.jpg", "14686.JPG", "1000069464.JPG")


@st.cache_data(ttl=3600)
def get_image_base64(paths_tuple: tuple):
    for path in paths_tuple:
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode()
            except Exception:
                pass
    return None


img_base64 = get_image_base64(PHOTO_OPTIONS)


# =====================================================================
# الصوت
# =====================================================================
@st.cache_data(ttl=3600)
def tts_base64(text, lang="ar"):
    if not GTTS_AVAILABLE or not text:
        return None
    try:
        tts = gTTS(text=text, lang=lang, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode()
    except Exception:
        return None


def play_audio_b64(audio_b64):
    if audio_b64:
        st.components.v1.html(
            f'<audio autoplay><source src="data:audio/mp3;base64,'
            f'{audio_b64}" type="audio/mpeg"></audio>', height=0)
        return True
    return False


def voice_guide(message, lang="ar"):
    if not GTTS_AVAILABLE or not message:
        return
    b64 = tts_base64(message, lang)
    if b64:
        play_audio_b64(b64)


def voice_welcome(role):
    msgs = {
        "owner": "مرحباً بك، أيها الاختصاصي م. عبد القادر إسماعيل تاور.",
        "specialist": "مرحباً أيها المختص.",
        "veterinarian": "مرحباً أيها الطبيب البيطري.",
        "nutritionist": "مرحباً أيها أخصائي التغذية.",
        "breeder": "مرحباً أيها المربي.",
        "public": "مرحباً بك زائراً."}
    voice_guide(msgs.get(role, "مرحباً بك."))


def send_code_to_email(receiver_email):
    if receiver_email.strip().lower() != OWNER_EMAIL.strip().lower():
        return False, "❌ الإرسال مسموح فقط للبريد: " + OWNER_EMAIL
    if not st.session_state.get("email_password"):
        return False, "⚠️ يرجى إعداد كلمة مرور البريد."
    try:
        with open(__file__, "r", encoding="utf-8") as f:
            code_content = f.read()
    except Exception:
        code_content = "# تعذر قراءة الكود"
    file_hash = hashlib.md5(code_content.encode()).hexdigest()
    msg = __import__("email.mime.multipart", fromlist=["MIMEMultipart"])\
        .MIMEMultipart()
    from email.mime.text import MIMEText
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email
    msg['Subject'] = "🌾 السورس كود - تاور نولجي v19.6"
    body = f"السلام عليكم،\nالتوقيع: {file_hash}"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    att = MIMEText(code_content, 'plain', 'utf-8')
    att.add_header('Content-Disposition', 'attachment',
                    filename="tawornology_main.py")
    msg.attach(att)
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, st.session_state["email_password"])
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        return True, "✅ تم الإرسال إلى " + receiver_email
    except Exception as e:
        return False, f"❌ فشل الإرسال: {str(e)}"


# =====================================================================
# قاعدة البيانات
# =====================================================================
class UserIsolatedDB:
    _DATA_DIR = "tawor_user_data"

    @staticmethod
    def _ensure_dir():
        os.makedirs(UserIsolatedDB._DATA_DIR, exist_ok=True)

    @staticmethod
    def get_db_path() -> str:
        UserIsolatedDB._ensure_dir()
        user = st.session_state.get("user") or {}
        uid = (user.get("user_id") or
               st.session_state.get("device_id") or "guest_device")
        safe = re.sub(r'[^a-zA-Z0-9_\-]', '', str(uid))[:40] or "guest"
        return os.path.join(UserIsolatedDB._DATA_DIR, f"tawor_{safe}.db")


class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = UserIsolatedDB.get_db_path()
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY, username TEXT UNIQUE,
            password_hash TEXT, role TEXT, full_name TEXT, email TEXT,
            phone TEXT, specialty TEXT, experience_years INTEGER,
            created_date TEXT, last_login TEXT,
            is_active INTEGER DEFAULT 1, is_public INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS feed_formulas (
            formula_id TEXT PRIMARY KEY, formula_name TEXT,
            animal_type TEXT, breed TEXT, stage TEXT,
            target_dp REAL, target_se REAL, ingredients TEXT,
            total_cost REAL, cost_per_ton REAL, created_by TEXT,
            created_date TEXT, is_approved INTEGER DEFAULT 0,
            usage_count INTEGER DEFAULT 0, requester_name TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS price_history (
            record_id TEXT PRIMARY KEY, ingredient_name TEXT, price REAL,
            currency TEXT, country TEXT, city TEXT, record_date TEXT,
            recorded_by TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS lab_results (
            result_id TEXT PRIMARY KEY, sample_name TEXT,
            sample_type TEXT, cp REAL, dc REAL, se REAL, ndf REAL,
            adf REAL, ee REAL, ash REAL, moisture REAL,
            analysis_date TEXT, analyzed_by TEXT, notes TEXT,
            image_path TEXT, requester_name TEXT, calcium REAL,
            phosphorus REAL, sodium REAL, potassium REAL,
            magnesium REAL, chlorine REAL, sulfur REAL,
            crude_fiber REAL)''')
        conn.commit()
        conn.close()

    def execute_query(self, query, params=()):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        result = c.execute(query, params)
        conn.commit()
        data = result.fetchall()
        conn.close()
        return data

    def insert_record(self, table, data):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        cols = ', '.join(data.keys())
        ph = ', '.join(['?' for _ in data])
        c.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})",
                  list(data.values()))
        conn.commit()
        conn.close()
        return True

    def update_record(self, table, data, condition):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        set_cl = ', '.join([f"{k}=?" for k in data.keys()])
        where = ' AND '.join([f"{k}=?" for k in condition.keys()])
        c.execute(f"UPDATE {table} SET {set_cl} WHERE {where}",
                  list(data.values()) + list(condition.values()))
        conn.commit()
        conn.close()
        return True


@st.cache_resource
def get_db_manager() -> DatabaseManager:
    return DatabaseManager()


def seed_price_history_if_empty():
    try:
        db = get_db_manager()
        count = db.execute_query("SELECT COUNT(*) FROM price_history")[0][0]
        if count > 0:
            return
        base_prices = {
            "ذرة صفراء": 230.0, "كسب فول صويا 44%": 440.0,
            "نخالة قمح (ردة)": 150.0, "شعير مطحون": 210.0,
            "كسب عباد الشمس 36%": 310.0,
            "أمباز الفول السوداني (كسب)": 460.0,
            "مسحوق أسماك (Fishmeal 60%)": 850.0,
            "الحجر الجيري (بودرة بلاط)": 40.0,
            "فوسفات ثنائي الكالسيوم (DCP)": 280.0,
            "ملح الطعام": 30.0}
        rng = random.Random(42)
        for ing, base in base_prices.items():
            for d in range(30, 0, -1):
                dt = (datetime.now() - timedelta(days=d)).isoformat()
                noise = rng.uniform(-0.05, 0.05)
                trend = (30 - d) * 0.003
                price = base * (1 + noise + trend)
                db.insert_record('price_history', {
                    'record_id': secrets.token_hex(16),
                    'ingredient_name': ing, 'price': round(price, 2),
                    'currency': 'USD', 'country': 'السودان',
                    'city': 'الخرطوم', 'record_date': dt,
                    'recorded_by': 'system'})
    except Exception:
        pass


# =====================================================================
# المصادقة
# =====================================================================
class AuthManager:
    def __init__(self):
        self.db = get_db_manager()
        self._create_default_users()
        self._create_public_user()

    def _create_default_users(self):
        defaults = [
            ('admin', 'admin123', 'owner',
             'الاختصاصي م. عبد القادر إسماعيل تاور',
             'admin@tawornology.com', '+249123456789', 'تغذية حيوان', 10),
            ('specialist', 'spec123', 'specialist', 'المختص العام',
             'spec@tawornology.com', '+249123456788', 'تغذية', 8)]
        for u, p, r, fn, e, ph, sp, exp in defaults:
            exist = self.db.execute_query(
                "SELECT * FROM users WHERE username=?", (u,))
            if not exist:
                self.create_user(u, p, r, fn, e, ph, sp, exp)

    def _create_public_user(self):
        exist = self.db.execute_query(
            "SELECT * FROM users WHERE username='public'")
        if not exist:
            self.create_user('public', 'public123', 'public', 'زائر',
                             'public@tawornology.com', '+249123456780',
                             'عام', 0)
            self.db.update_record('users', {'is_public': 1},
                                   {'username': 'public'})

    def create_user(self, username, password, role, full_name, email,
                    phone, specialty="", experience=0):
        uid = secrets.token_hex(16)
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        self.db.insert_record('users', {
            'user_id': uid, 'username': username, 'password_hash': pwd_hash,
            'role': role, 'full_name': full_name, 'email': email,
            'phone': phone, 'specialty': specialty,
            'experience_years': experience,
            'created_date': datetime.now().isoformat(), 'last_login': '',
            'is_active': 1, 'is_public': 1 if role == 'public' else 0})
        return uid

    def authenticate(self, username, password):
        rows = self.db.execute_query(
            "SELECT * FROM users WHERE username=? AND is_active=1",
            (username,))
        if not rows:
            return None
        u = rows[0]
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        if u[2] != pwd_hash:
            return None
        self.db.update_record('users',
            {'last_login': datetime.now().isoformat()}, {'user_id': u[0]})
        return {'user_id': u[0], 'username': u[1], 'role': u[3],
                'full_name': u[4], 'email': u[5], 'phone': u[6],
                'specialty': u[7], 'experience_years': u[8]}

    def login_public(self):
        rows = self.db.execute_query(
            "SELECT * FROM users WHERE username='public' AND is_active=1")
        if rows:
            u = rows[0]
            return {'user_id': u[0], 'username': u[1], 'role': 'public',
                    'full_name': 'زائر', 'email': u[5], 'phone': u[6],
                    'specialty': 'عام', 'experience_years': 0}
        self._create_public_user()
        return self.login_public()


# =====================================================================
# مولد PDF
# =====================================================================
@st.cache_resource
def download_arabic_font():
    font_path = "Amiri-Regular.ttf"
    if os.path.exists(font_path):
        return font_path
    for f in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "C:/Windows/Fonts/arial.ttf"]:
        if os.path.exists(f):
            return f
    return None


def ensure_arabic_font():
    fp = download_arabic_font()
    if fp and os.path.exists(fp):
        try:
            pdfmetrics.registerFont(TTFont('ArabicFont', fp))
            return 'ArabicFont'
        except Exception:
            pass
    try:
        pdfmetrics.registerFont(TTFont('ArabicFont', 'Helvetica'))
    except Exception:
        pass
    return 'Helvetica'


class ProfessionalPDFGenerator:
    def __init__(self):
        self.font_name = ensure_arabic_font()
        self.styles = self._create_styles()

    def _create_styles(self):
        s = {}
        s['title'] = ParagraphStyle('title', fontName=self.font_name,
            fontSize=22, alignment=TA_CENTER,
            textColor=HexColor('#1b5e20'), spaceAfter=12, leading=28)
        s['subtitle'] = ParagraphStyle('subtitle', fontName=self.font_name,
            fontSize=15, alignment=TA_CENTER,
            textColor=HexColor('#2e7d32'), spaceAfter=10, leading=20)
        s['heading'] = ParagraphStyle('heading', fontName=self.font_name,
            fontSize=13, alignment=TA_RIGHT,
            textColor=HexColor('#1b5e20'), spaceAfter=8, leading=18)
        s['body'] = ParagraphStyle('body', fontName=self.font_name,
            fontSize=11, alignment=TA_RIGHT,
            textColor=HexColor('#333333'), spaceAfter=5, leading=16)
        s['footer'] = ParagraphStyle('footer', fontName=self.font_name,
            fontSize=8, alignment=TA_CENTER,
            textColor=HexColor('#999999'), spaceAfter=0, leading=10)
        return s

    def _p(self, text, style='body'):
        return Paragraph(ar(str(text)),
                          self.styles.get(style, self.styles['body']))

    def _bismala(self, story):
        style = ParagraphStyle('bismala', fontName=self.font_name,
            fontSize=22, alignment=TA_CENTER,
            textColor=HexColor('#1b5e20'), spaceAfter=6, leading=30)
        story.append(Paragraph(ar("﷽"), style))
        story.append(Spacer(1, 6))
        bar = Table([[""]], colWidths=[520], rowHeights=[6])
        bar.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), HexColor('#2e7d32'))]))
        story.append(bar)
        story.append(Spacer(1, 12))
        return story

    def _section(self, story, text, color_hex):
        style = ParagraphStyle('sec', fontName=self.font_name,
            fontSize=13, alignment=TA_CENTER, textColor=white,
            backColor=HexColor(color_hex),
            borderPadding=(8, 12, 8, 12), leading=20)
        story.append(Paragraph(ar(text), style))
        story.append(Spacer(1, 8))
        return story

    def _table(self, rows, color_hex, widths=None):
        if widths is None:
            widths = [110, 90, 90, 90, 120]
        t = Table(rows, colWidths=widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), HexColor(color_hex)),
            ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#bdbdbd')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [HexColor('#f9f9f9'), HexColor('#ffffff')]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        return t

    def _recommendations(self, mf_eval):
        recs = []
        if not mf_eval:
            return ["لا توجد معايير للمقارنة."]
        for key, ev in mf_eval.items():
            st_ = ev.get("status", "neutral")
            dev = ev.get("deviation", 0)
            if st_ == "high":
                recs.append(f"🔺 {key} مرتفع ({dev:+.1f}%)")
            elif st_ == "low":
                recs.append(f"🔻 {key} منخفض ({dev:+.1f}%)")
        return recs[:10] if recs else ["✅ جميع القيم ضمن النطاق القياسي"]

    def _bar_chart(self, story, computed, standard, keys):
        try:
            ck = [k for k in keys if k in standard]
            if not ck:
                return
            fig, ax = plt.subplots(figsize=(7, 4))
            x = np.arange(len(ck))
            w = 0.35
            ax.bar(x - w/2, [computed.get(k, 0) for k in ck],
                   w, label=ar('المحسوب'), color='#2e7d32')
            ax.bar(x + w/2, [standard.get(k, 0) for k in ck],
                   w, label=ar('القياسي'), color='#1565C0')
            ax.set_xticks(x); ax.set_xticklabels(ck, fontsize=10)
            ax.set_title(ar('مقارنة الأملاح والألياف'),
                          fontsize=12, fontweight='bold')
            ax.legend(loc='upper right', fontsize=9,
                       prop={'family': _MAT_FONT})
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            plt.tight_layout()
            buf = io.BytesIO()
            plt.savefig(buf, format='png', dpi=130,
                        bbox_inches='tight', facecolor='white')
            plt.close()
            buf.seek(0)
            story.append(Spacer(1, 10))
            story.append(Image(buf, width=440, height=250))
        except Exception:
            pass

    def _signature(self, story, requester=""):
        story.append(Spacer(1, 20))
        story.append(self._p("مع خالص التحية والتقدير،"))
        sign = ParagraphStyle('sign', fontName=self.font_name,
            fontSize=12, alignment=TA_RIGHT,
            textColor=HexColor('#c62828'), spaceAfter=4, leading=18)
        story.append(Paragraph(ar(
            "الاختصاصي م. عبد القادر إسماعيل تاور - "
            "اختصاصي تغذية الحيوان"), sign))
        if requester:
            story.append(self._p(f"طالب العلفة: {requester}"))
        story.append(Spacer(1, 12))
        story.append(self._p(
            "🌾 تاور نولجي Tawornology v19.6 © 2026", 'footer'))

    def generate_comprehensive_report(self, formula, target_dp, breed, cost,
                                       city, local_cost, local_sym,
                                       computed_se, user_name,
                                       requester_name="", standard=None,
                                       include_charts=True, extra_info=None,
                                       mineral_data=None, mf_standard=None,
                                       mf_evaluation=None, ratios=None):
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=45,
            leftMargin=45, topMargin=25, bottomMargin=35)
        story = []
        story = self._bismala(story)
        story.append(self._p("🌾 تاور نولجي Tawornology العلمية", 'title'))
        story.append(self._p("📄 تقرير فني شامل - v19.6", 'subtitle'))
        story.append(Spacer(1, 10))

        info = [
            [ar("👨‍💻 المشرف"),
             ar("الاختصاصي م. عبد القادر إسماعيل تاور")],
            [ar("👤 طالب العلفة"), ar(requester_name or 'غير محدد')],
            [ar("🐾 الفصيل"), ar(breed)],
            [ar("📌 الموقع"), ar(city)],
            [ar("📅 التاريخ"),
             ar(datetime.now().strftime('%Y-%m-%d %H:%M'))]]
        it = Table(info, colWidths=[140, 360])
        it.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), HexColor('#e8f5e9')),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, -1), self.font_name),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#a5d6a7')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
        story.append(it)
        story.append(Spacer(1, 15))

        story = self._section(story, "📋 المقادير المعتمدة لطن واحد",
                                '#2e7d32')
        rows = [[ar('المكون'), ar('النسبة %'), ar('كجم/طن')]]
        for ing, pct in formula.items():
            rows.append([ar(ing), f'{pct:.2f}%', f'{pct*10:.1f}'])
        story.append(self._table(rows, '#2e7d32', [220, 130, 130]))

        if mineral_data and mf_standard:
            story.append(PageBreak())
            story = self._section(story, "🧂 تحليل الأملاح", '#00838f')
            names = {"Ca": "كالسيوم", "P": "فسفور", "Na": "صوديوم",
                      "K": "بوتاسيوم", "Mg": "مغنيسيوم", "Cl": "كلور",
                      "S": "كبريت"}
            rows = [[ar('المعدن'), ar('المحسوب %'), ar('القياسي %'),
                     ar('الانحراف %'), ar('التقييم')]]
            for key, name in names.items():
                if key in mf_standard:
                    ev = mf_evaluation.get(key, {})
                    rows.append([ar(f"{name} ({key})"),
                        f"{ev.get('calculated', 0):.3f}",
                        f"{ev.get('standard', 0):.3f}",
                        f"{ev.get('deviation', 0):+.1f}",
                        ev.get("grade", "-")])
            story.append(self._table(rows, '#00838f'))
            story.append(Spacer(1, 15))

            story = self._section(story, "🌾 تحليل الألياف", '#6a1b9a')
            fn = {"NDF": "NDF", "ADF": "ADF", "CF": "CF", "Ash": "رماد"}
            rows = [[ar('نوع الليف'), ar('المحسوب %'), ar('القياسي %'),
                     ar('الانحراف %'), ar('التقييم')]]
            for key, name in fn.items():
                if key in mf_standard:
                    ev = mf_evaluation.get(key, {})
                    rows.append([ar(name),
                        f"{ev.get('calculated', 0):.2f}",
                        f"{ev.get('standard', 0):.2f}",
                        f"{ev.get('deviation', 0):+.1f}",
                        ev.get("grade", "-")])
            story.append(self._table(rows, '#6a1b9a'))

            if include_charts:
                self._bar_chart(story, mineral_data, mf_standard,
                    ["Ca", "P", "Na", "K", "Mg", "NDF", "ADF", "CF"])

            if ratios:
                story.append(Spacer(1, 12))
                story = self._section(story, "⚖️ النسب والتوصيات", '#c62828')
                ca_p = ratios.get("Ca_P_ratio", 0)
                k_na = ratios.get("K_Na_ratio", 0)
                story.append(self._p(f"• Ca : P = {ca_p:.2f}"))
                story.append(self._p(f"• K : Na = {k_na:.2f}"))
                for r in self._recommendations(mf_evaluation):
                    story.append(self._p(f"• {r}"))

        self._signature(story, requester_name)
        doc.build(story)
        buf.seek(0)
        return buf.getvalue()


pdf_generator = ProfessionalPDFGenerator()


# =====================================================================
# التنبؤ بالأسعار
# =====================================================================
class PricePredictor:
    def __init__(self):
        self.db = get_db_manager()

    def get_price_trend(self, ingredient_name, days=30):
        rows = self.db.execute_query(
            "SELECT * FROM price_history WHERE ingredient_name=? "
            "ORDER BY record_date DESC LIMIT ?", (ingredient_name, days))
        if len(rows) < 3:
            return {'trend': 'stable', 'change_percent': 0,
                    'volatility': 0, 'current_price': 0}
        prices = [r[2] for r in rows]
        x = np.array(range(len(prices))).reshape(-1, 1)
        y = np.array(prices)
        model = LinearRegression()
        model.fit(x, y)
        slope = model.coef_[0]
        change = ((prices[0] - prices[-1]) / prices[-1] * 100
                  if prices[-1] > 0 else 0)
        trend = ('up' if slope > 0.5
                 else 'down' if slope < -0.5 else 'stable')
        return {'trend': trend, 'change_percent': change,
                'volatility': np.std(prices) / np.mean(prices)
                if np.mean(prices) > 0 else 0,
                'current_price': prices[0]}

    def predict_price(self, ingredient_name, days_ahead=7):
        rows = self.db.execute_query(
            "SELECT price FROM price_history WHERE ingredient_name=? "
            "ORDER BY record_date DESC LIMIT 30", (ingredient_name,))
        if len(rows) < 5:
            return {'prediction': None, 'confidence': 0,
                    'current_price': None, 'trend': 'stable'}
        prices = [r[0] for r in rows]
        weights = np.array(range(1, len(prices) + 1))
        weighted_avg = np.average(prices, weights=weights)
        trend = ((prices[0] - prices[-1]) / len(prices)
                 if len(prices) > 1 else 0)
        pred = weighted_avg + (trend * days_ahead)
        return {'prediction': max(0, pred),
                'confidence': min(1, len(prices) / 30),
                'current_price': prices[0] if prices else None,
                'trend': self.get_price_trend(ingredient_name)['trend']}


# =====================================================================
# المخزون
# =====================================================================
class InventoryManager:
    @staticmethod
    def initialize_inventory():
        if "inventory" not in st.session_state:
            st.session_state["inventory"] = {}
            for cat_name, items in BIG_FEEDS_LIBRARY.items():
                for ing in items:
                    st.session_state["inventory"][ing] = {
                        "quantity": 25.0, "min_threshold": 5.0,
                        "unit": "طن"}

    @staticmethod
    def check_stock_levels():
        warns = {}
        for item, data in st.session_state["inventory"].items():
            qty = data if isinstance(data, (int, float)) else data["quantity"]
            thr = (5.0 if isinstance(data, (int, float))
                   else data.get("min_threshold", 5.0))
            if qty <= 0:
                warns[item] = {"status": "نفذ المخزون",
                                "level": "critical"}
            elif qty < thr:
                warns[item] = {"status": "منخفض", "level": "warning"}
        return warns

    @staticmethod
    def get_stock_summary():
        total = len(st.session_state["inventory"])
        qty = sum(d["quantity"] if isinstance(d, dict) else d
                  for d in st.session_state["inventory"].values())
        low = sum(1 for d in st.session_state["inventory"].values()
                  if (d["quantity"] if isinstance(d, dict) else d)
                  < (d.get("min_threshold", 5.0)
                     if isinstance(d, dict) else 5.0))
        return {"total_items": total, "total_quantity": qty,
                "low_stock": low}


InventoryManager.initialize_inventory()


ANIMAL_IMAGES_RESOURCES = {
    "عام": "https://images.unsplash.com/photo-1500382017468-9049fed747ef?w=1600"}


# =====================================================================
# State الافتراضي
# =====================================================================
defaults = {
    "approved": False, "user_role": None, "login_welcome_shown": False,
    "login_attempts": 0, "last_login_time": None, "session_token": None,
    "analysis_results": None,
    "analysis_animal": "غير محدد", "analysis_stage": "غير محدد",
    "daily_production_log": [], "dose_reminders": [],
    "active_formula": {}, "active_cp_tag": 12.0, "active_se_tag": 65.0,
    "active_animal_img": ANIMAL_IMAGES_RESOURCES["عام"],
    "active_stage_title": "إنتاج عام", "computed_ton_cost": 280.0,
    "lab_sample": None, "lab_sample_name": "", "lab_cp": 0.0,
    "lab_dc": 0.0, "lab_se": 0.0, "lab_ndf": 0.0, "lab_adf": 0.0,
    "lab_ee": 0.0, "lab_ash": 0.0, "lab_moisture": 0.0,
    "lab_notes": "", "lab_ca": 0.0, "lab_p": 0.0, "lab_na": 0.0,
    "lab_k": 0.0, "user": None, "device_id": None,
    "shared_comments":
        "• [توجيه الاختصاصي]: يرجى من جميع الزملاء إضافة تعليقاتهم.\n",
    "broiler_farms": {},
    "global_livestock_prices": {
        "عجول تسمين هولشتاين ($)": 1350.0,
        "أبقار كنانة محلية ($)": 900.0,
        "ضأن وستيرلنغ ($)": 180.0,
        "ماعز نوبي ($)": 130.0,
        "خيول عربية أصيلة ($)": 4500.0,
        "إبل عربية ($)": 2500.0,
        "كتكوت لاحم ($)": 0.65},
    "global_products_prices": {
        "كيلو لحم بقري ($)": 7.50, "كيلو لحم ضأن ($)": 9.00,
        "كيلو لحم دجاج ($)": 3.80, "طبق بيض 30 بيضة ($)": 4.20,
        "لتر حليب خام ($)": 0.90, "لتر حليب إبل ($)": 1.50},
    "afs_library": [],
    "afs_last_result": None,
    "afs_sens_data": None,
    "afs_mc_data": None,
    "afs_pareto_data": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

get_or_create_device_id()
seed_price_history_if_empty()


# =====================================================================
# عرض الجداول العربية
# =====================================================================
def show_arabic_table(rows, color="#2e7d32", widths=None):
    if not rows:
        st.info("لا توجد بيانات.")
        return
    ncols = len(rows[0])
    if widths is None:
        widths = [f"{100/ncols:.1f}%" for _ in range(ncols)]
    html = f"""
    <div dir="rtl" style="overflow-x:auto; margin:12px 0;">
    <table style="width:100%; border-collapse:collapse;
                  font-family:'Cairo','Tajawal',sans-serif;
                  direction:rtl; text-align:right; font-size:0.92rem;
                  box-shadow:0 4px 20px rgba(0,0,0,0.08);
                  border-radius:12px; overflow:hidden;">
        <thead><tr style="background:linear-gradient(135deg,{color},{color}dd);
                        color:white; font-weight:700;">"""
    for i, h in enumerate(rows[0]):
        html += (f'<th style="padding:12px 14px; text-align:center; '
                  f'width:{widths[i] if i < len(widths) else "auto"};">'
                  f'{h}</th>')
    html += "</tr></thead><tbody>"
    for r_idx, row in enumerate(rows[1:]):
        bg = "#ffffff" if r_idx % 2 == 0 else "#f8faf8"
        html += f'<tr style="background:{bg};">'
        for i, cell in enumerate(row):
            align = "right" if i == 0 else "center"
            cs = str(cell)
            tc = "#333"
            if "✅" in cs or "ممتاز" in cs:
                tc = "#2e7d32"
            elif "⚠️" in cs or "مرتفع" in cs:
                tc = "#c62828"
            elif "🔻" in cs or "منخفض" in cs:
                tc = "#e65100"
            html += (f'<td style="padding:10px 14px; text-align:{align}; '
                      f'color:{tc}; border-bottom:1px solid #e8ece8; '
                      f'font-weight:{"600" if i == 0 else "400"};">'
                      f'{cell}</td>')
        html += "</tr>"
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)


# =====================================================================
# CSS
# =====================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap');
* { font-family: 'Cairo', 'Tajawal', sans-serif; }
html, body, [data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 50%, #f5f7fa 100%);
    background-attachment: fixed;
}
.main-box {
    background: rgba(255,255,255,0.92); padding: 35px; border-radius: 24px;
    box-shadow: 0 25px 70px rgba(0,0,0,0.15); backdrop-filter: blur(15px);
    margin-bottom: 35px;
}
.section-title {
    color: #1b5e20; border-right: 6px solid #2e7d32; padding-right: 18px;
    text-align: right; font-size: 1.7rem; font-weight: 700;
    margin: 30px 0 25px 0;
    background: linear-gradient(to left, rgba(46,125,50,0.12), transparent);
    padding: 14px 22px; border-radius: 14px;
}
.metric-card {
    background: white; padding: 22px; border-radius: 18px;
    box-shadow: 0 6px 30px rgba(0,0,0,0.08); text-align: center;
}
.metric-card .number {
    font-size: 2.2rem; font-weight: 900; color: #1b5e20; margin: 5px 0;
}
.metric-card .label { font-size: 0.95rem; color: #666; font-weight: 600; }
.warning-card {
    background: linear-gradient(135deg, #fff3e0, #ffe0b2);
    padding: 15px; border-radius: 12px;
    border-right: 5px solid #f57c00;
    margin-bottom: 15px; direction: rtl; text-align: right;
    color: #e65100 !important;
}
.profile-img-style {
    width: 160px; height: 160px; border-radius: 50%; object-fit: cover;
    border: 4px solid #d4af37; box-shadow: 0 10px 30px rgba(0,0,0,0.2);
}
</style>
""", unsafe_allow_html=True)


# =====================================================================
# شريط الدعاء
# =====================================================================
def render_dua_bar():
    st.markdown("""
    <style>
    @keyframes scrollDuaLR {
        0% { transform: translateX(-100%); opacity: 0.2; }
        50% { opacity: 1; }
        100% { transform: translateX(100%); opacity: 0.2; }
    }
    .dua-container {
        background: linear-gradient(90deg,#0d1b2a,#1a237e,#4a148c,#1a237e,#0d1b2a);
        background-size: 300% 300%;
        padding: 20px 0; border-radius: 20px; margin-bottom: 15px;
        overflow: hidden; border: 3px solid #ffd700;
        text-align: center; direction: rtl; color: #ffd700;
        font-weight: 800; font-size: 1.3rem;
    }
    .dua-track {
        display: inline-block; white-space: nowrap;
        animation: scrollDuaLR 30s linear infinite;
        padding: 0 30px;
    }
    .dua-static {
        background: linear-gradient(90deg,#1b2a4a,#2a1b4a,#1b2a4a);
        padding: 12px 20px; border-radius: 12px;
        text-align: center; color: #e1bee7;
        font-size: 1rem; font-weight: 700;
        border: 2px solid #ffd700; direction: rtl;
        margin-bottom: 20px;
    }
    </style>
    <div class="dua-container">
        <div class="dua-track">
            ❤️ اللهم اغفر لإسماعيل تاور وابتسام وارحمهما ❤️
        </div>
    </div>
    <div class="dua-static">
        🕊️ اللهم اغفر لإسماعيل تاور وابتسام وارحمهما 🕊️
    </div>
    """, unsafe_allow_html=True)


# =====================================================================
# دالة عرض تحليل الأملاح والألياف
# =====================================================================
def render_mineral_fiber_analysis(formula_results, animal_type, stage,
                                    requester_name=""):
    mf_result = calculate_minerals_fibers(formula_results)
    computed = mf_result["values"]
    ratios = mf_result["ratios"]
    mf_std = MINERAL_FIBER_STANDARDS.get(animal_type, {}).get(stage, {})
    mf_eval = (evaluate_against_standard(computed, mf_std)
               if mf_std else {})

    tab_min, tab_fib, tab_rat = st.tabs(
        ["🧂 الأملاح", "🌾 الألياف", "⚖️ النسب"])

    with tab_min:
        items = [("Ca", "كالسيوم (Ca)"), ("P", "فسفور (P)"),
                 ("Na", "صوديوم (Na)"), ("K", "بوتاسيوم (K)"),
                 ("Mg", "مغنيسيوم (Mg)"), ("Cl", "كلور (Cl)"),
                 ("S", "كبريت (S)")]
        rows = [["المعدن", "المحسوب %", "القياسي %",
                 "الانحراف %", "التقييم"]]
        for key, name in items:
            calc = computed.get(key, 0.0)
            std = mf_std.get(key)
            if std is not None:
                ev = mf_eval.get(key, {})
                rows.append([name, f"{calc:.3f}", f"{std:.3f}",
                              f"{ev.get('deviation', 0):+.1f}%",
                              ev.get("grade", "-")])
            else:
                rows.append([name, f"{calc:.3f}", "-", "-", "-"])
        show_arabic_table(rows, "#00838f",
                          ["30%", "16%", "16%", "18%", "20%"])

    with tab_fib:
        items = [("NDF", "ألياف متعادلة (NDF)"),
                 ("ADF", "ألياف حمضية (ADF)"),
                 ("CF", "ألياف خام (CF)"), ("Ash", "رماد (Ash)")]
        rows = [["نوع الليف", "المحسوب %", "القياسي %",
                 "الانحراف %", "التقييم"]]
        for key, name in items:
            calc = computed.get(key, 0.0)
            std = mf_std.get(key)
            if std is not None:
                ev = mf_eval.get(key, {})
                rows.append([name, f"{calc:.2f}", f"{std:.2f}",
                              f"{ev.get('deviation', 0):+.1f}%",
                              ev.get("grade", "-")])
            else:
                rows.append([name, f"{calc:.2f}", "-", "-", "-"])
        show_arabic_table(rows, "#6a1b9a",
                          ["34%", "16%", "16%", "18%", "16%"])

    with tab_rat:
        ca_p = ratios.get("Ca_P_ratio", 0)
        k_na = ratios.get("K_Na_ratio", 0)
        ideal = get_ideal_ca_p_ratio(animal_type)
        rows = [["النسبة", "القيمة", "المثالي", "الحالة"]]
        ca_s = ("✅ ممتاز" if abs(ca_p - ideal) <= 0.3
                else "⚠️ يحتاج تحسين" if abs(ca_p - ideal) <= 0.6
                else "❌ خارج النطاق")
        k_s = ("✅ ممتاز" if 2.5 <= k_na <= 4.0
               else "⚠️ يحتاج تحسين")
        rows.append(["Ca : P", f"{ca_p:.2f}", f"≈ {ideal:.1f}", ca_s])
        rows.append(["K : Na", f"{k_na:.2f}", "≈ 3.0", k_s])
        show_arabic_table(rows, "#c62828",
                          ["25%", "20%", "25%", "30%"])

    if mf_std:
        keys = [k for k in ["Ca", "P", "Na", "K", "Mg", "NDF", "ADF", "CF"]
                if k in mf_std]
        if keys:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=keys, y=[computed.get(k, 0) for k in keys],
                name="المحسوب", marker_color="#2e7d32"))
            fig.add_trace(go.Bar(
                x=keys, y=[mf_std.get(k, 0) for k in keys],
                name="القياسي", marker_color="#1565C0"))
            fig.update_layout(
                title="مقارنة الأملاح والألياف مع المعايير",
                barmode="group",
                font=dict(family="Cairo, Tajawal, sans-serif", size=12),
                height=400)
            st.plotly_chart(fig, use_container_width=True)

    if mf_eval:
        st.markdown("#### 📌 التوصيات الذكية")
        for rec in pdf_generator._recommendations(mf_eval):
            st.info(f"• {rec}")

    return mf_result, mf_std, mf_eval, ratios


# =====================================================================
# شاشة الدخول
# =====================================================================
MAX_LOGIN = 5
LOCKOUT = 300

if st.session_state.get("user") and \
        st.session_state["user"].get("role") == "owner" and \
        st.session_state.get("session_token"):
    st.session_state["approved"] = True

if not st.session_state.get("approved", False):
    render_dua_bar()
    if st.session_state.get("login_attempts", 0) >= MAX_LOGIN:
        if st.session_state.get("last_login_time"):
            dt = (datetime.now() -
                  st.session_state["last_login_time"]).seconds
            if dt < LOCKOUT:
                st.error(f"🔒 قفل مؤقت. المحاولة بعد {LOCKOUT - dt} ثانية")
                st.stop()
            else:
                st.session_state["login_attempts"] = 0

    st.markdown('<div class="main-box" style="max-width:550px; '
                'margin:80px auto; direction:rtl;">', unsafe_allow_html=True)
    if img_base64:
        st.markdown(
            f'<img src="data:image/jpeg;base64,{img_base64}" '
            f'style="width:100px; height:100px; border-radius:50%; '
            f'border:3px solid #d4af37; display:block; margin:0 auto;">',
            unsafe_allow_html=True)
    st.markdown(
        "<h2 style='color:#1a237e; text-align:center;'>"
        "🌾 تاور نولجي Tawornology</h2>",
        unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#555;'>"
                "للإنتاج الحيواني وتركيب الأعلاف - v19.6</p>",
                unsafe_allow_html=True)

    if st.button("👤 دخول كزائر", type="primary", use_container_width=True):
        auth = AuthManager()
        user = auth.login_public()
        if user:
            st.session_state["approved"] = True
            st.session_state["user_role"] = "public"
            st.session_state["login_welcome_shown"] = False
            st.session_state["last_login_time"] = datetime.now()
            st.session_state["session_token"] = secrets.token_urlsafe(32)
            st.session_state["user"] = user
            st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)
    opt = st.radio("طريقة الدخول:",
                    ["كود سري", "اسم المستخدم"], horizontal=True)

    if opt == "كود سري":
        code = st.text_input("🔑 الكود:", type="password")
        if st.button("دخول 🔓", type="secondary",
                      use_container_width=True):
            ud = validate_access_code(code)
            if ud:
                st.session_state["approved"] = True
                st.session_state["user_role"] = ud["role"]
                st.session_state["login_welcome_shown"] = False
                st.session_state["last_login_time"] = datetime.now()
                st.session_state["session_token"] = secrets.token_urlsafe(32)
                st.session_state["user"] = {
                    "full_name": ud["name"], "role": ud["role"],
                    "user_id": f"code_{ud['role']}"}
                st.rerun()
            else:
                st.session_state["login_attempts"] = \
                    st.session_state.get("login_attempts", 0) + 1
                st.error(f"❌ كود خاطئ! متبقي "
                          f"{MAX_LOGIN - st.session_state['login_attempts']}")
    else:
        un = st.text_input("👤 المستخدم")
        pw = st.text_input("🔑 كلمة المرور", type="password")
        if st.button("دخول 🔓", type="primary", use_container_width=True):
            auth = AuthManager()
            user = auth.authenticate(un, pw)
            if user:
                st.session_state["approved"] = True
                st.session_state["user_role"] = user['role']
                st.session_state["login_welcome_shown"] = False
                st.session_state["last_login_time"] = datetime.now()
                st.session_state["session_token"] = secrets.token_urlsafe(32)
                st.session_state["user"] = user
                st.rerun()
            else:
                st.session_state["login_attempts"] = \
                    st.session_state.get("login_attempts", 0) + 1
                st.error(f"❌ خطأ! متبقي "
                          f"{MAX_LOGIN - st.session_state['login_attempts']}")
        st.caption("💡 admin / admin123")
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# =====================================================================
# الترحيب
# =====================================================================
if not st.session_state.get("login_welcome_shown"):
    role_msgs = {
        "owner": "👑 مرحباً، الاختصاصي م. عبد القادر",
        "specialist": "🔬 أهلاً بالمختصين",
        "veterinarian": "💊 أهلاً بالطبيب",
        "nutritionist": "🧬 أهلاً بأخصائي التغذية",
        "breeder": "🌾 أهلاً بالمربي",
        "public": "👤 مرحباً زائراً"}
    st.toast(role_msgs.get(st.session_state.get("user_role"), "مرحباً"),
             icon="🌾")
    voice_welcome(st.session_state.get("user_role", "public"))
    st.session_state["login_welcome_shown"] = True

render_dua_bar()

# =====================================================================
# الواجهة الرئيسية
# =====================================================================
st.markdown('<div class="main-box">', unsafe_allow_html=True)

c_logout, c_status = st.columns([0.7, 0.3])
with c_status:
    rnames = {"owner": "المالك 👑", "specialist": "المختص 👨‍🔬",
              "veterinarian": "الطبيب 💊",
              "nutritionist": "التغذية 🧬",
              "breeder": "المربي 🌾", "public": "زائر 👤"}
    st.markdown(f"""
    <div style='text-align:left; background:linear-gradient(135deg,#f5f5f5,#e0e0e0);
                padding:14px; border-radius:14px;'>
        <div style='font-weight:700;'>{get_current_user_name()}</div>
        <div style='font-size:0.85rem; color:#555;'>
            {rnames.get(get_current_user_role(), "مستخدم")}</div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🚪 خروج", use_container_width=True):
        keep = ["inventory", "email_password", "device_id"]
        for k in list(st.session_state.keys()):
            if k not in keep:
                del st.session_state[k]
        st.session_state["approved"] = False
        st.rerun()

c1, c2 = st.columns([0.2, 0.8])
with c1:
    src = (f"data:image/jpeg;base64,{img_base64}"
           if img_base64 else ANIMAL_IMAGES_RESOURCES["عام"])
    st.markdown(f'<img src="{src}" class="profile-img-style">',
                 unsafe_allow_html=True)
with c2:
    st.markdown("<h1 style='color:#1a237e; text-align:right;'>"
                "🌾 تاور نولجي Tawornology</h1>",
                unsafe_allow_html=True)
    st.markdown("<p style='color:#1565C0; text-align:right; "
                "font-size:1.2rem;'>"
                "للإنتاج الحيواني وتركيب الأعلاف - v19.6</p>",
                unsafe_allow_html=True)
    st.markdown("<h3 style='color:#c62828; text-align:right;'>"
                "الاختصاصي م. عبد القادر إسماعيل تاور</h3>",
                unsafe_allow_html=True)

st.markdown("<hr style='border-top:3px solid #2e7d32;'>",
             unsafe_allow_html=True)

# لوحة تحكم
st.markdown("### 📊 لوحة التحكم")
cs = InventoryManager.get_stock_summary()
c1, c2, c3, c4 = st.columns(4)
c1.markdown(f"<div class='metric-card'><div class='number'>"
             f"{cs['total_items']}</div><div class='label'>"
             f"إجمالي المواد</div></div>", unsafe_allow_html=True)
c2.markdown(f"<div class='metric-card'><div class='number'>"
             f"{cs['total_quantity']:.1f}</div><div class='label'>"
             f"المخزون (طن)</div></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='metric-card'><div class='number'>"
             f"{cs['low_stock']}</div><div class='label'>"
             f"مواد منخفضة</div></div>", unsafe_allow_html=True)
c4.markdown(f"<div class='metric-card'><div class='number'>"
             f"{len(st.session_state.get('broiler_farms', {}))}</div>"
             f"<div class='label'>مزارع</div></div>",
             unsafe_allow_html=True)
st.markdown("---")


# =====================================================================
# القائمة الرئيسية للتبويبات
# =====================================================================
tab_titles = [
    "🐾 القطاع الحيواني", "🚀 وحدة متقدمة", "📚 مكتبة الخلطات",
    "🧪 المختبر الذكي", "🔬 المختبر المتقدم", "🐔 إدارة المزارع",
    "🍼 بدائل الحليب", "💊 منبه الجرعات", "📊 بورصة الأسعار",
    "🏭 المستودعات", "📈 الإنتاج اليومي", "🔔 التنبيهات",
    "📈 التحليلات", "💬 التعليقات", "📚 المراجع", "🌐 واجهة API"]

if st.session_state.get("user_role") == "owner":
    tab_titles.extend(["📧 إرسال الكود", "📊 لوحة الإدارة"])

tabs = st.tabs(tab_titles)


# ═══════════════════════════════════════════════════════════
# 🐾 0: القطاع الحيواني — التكوين المباشر
# ═══════════════════════════════════════════════════════════
with tabs[0]:
    st.markdown('<div class="section-title">🐾 القطاع الحيواني</div>',
                 unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        animal = st.selectbox("الفصيل:",
            list(STANDARD_VALUES.keys()), key="main_animal")
    with c2:
        stage = st.selectbox("المرحلة:",
            list(STANDARD_VALUES.get(animal, {}).keys()),
            key=f"main_stage_{animal}")
    with c3:
        basis = st.radio("نظام البروتين:",
            ["DP (مهضوم)", "CP (خام)"], horizontal=True,
            key="main_basis")

    std_preview = STANDARD_VALUES.get(animal, {}).get(stage, {})
    if std_preview:
        m1, m2, m3 = st.columns(3)
        m1.metric("🎯 DP قياسي", f"{std_preview.get('DP', 0):.2f}%")
        m2.metric("⚡ SE قياسي", f"{std_preview.get('SE', 0):.2f}")
        m3.metric("📊 CP قياسي", f"{std_preview.get('CP', 0):.2f}%")

    # طالب العلف
    requester = st.text_input("👤 اسم طالب العلف:",
        placeholder="أدخل اسم المربي", key="main_req")

    # الموقع
    st.markdown("#### 🌍 الموقع الجغرافي")
    lc1, lc2 = st.columns(2)
    with lc1:
        country = st.selectbox("الدولة:",
            ["السودان", "LIBYA", "مصر", "دولار أمريكي"],
            key="main_country")
    with lc2:
        city = st.text_input("المدينة:", value="الخرطوم", key="main_city")

    # اختيار المواد
    with st.expander("🌾 اختر المواد المتاحة", expanded=True):
        ac1, ac2 = st.columns(2)
        with ac1:
            if st.button("✅ توصيات النظام", key="main_def",
                          use_container_width=True):
                dmap = {
                    "أبقار": ["ذرة صفراء", "شعير مطحون",
                              "نخالة قمح (ردة)", "كسب فول صويا 44%",
                              "أمباز الفول السوداني (كسب)",
                              "البرسيم الجاف (الدريس)",
                              "مركزات خيول ومجترات"],
                    "أغنام": ["ذرة صفراء", "شعير مطحون",
                              "نخالة قمح (ردة)", "كسب فول صويا 44%",
                              "أمباز الفول السوداني (كسب)",
                              "مركزات خيول ومجترات"],
                    "ماعز": ["ذرة صفراء", "شعير مطحون",
                             "نخالة قمح (ردة)", "كسب فول صويا 44%",
                             "أمباز الفول السوداني (كسب)",
                             "مركزات خيول ومجترات"],
                    "خيول": ["شعير مطحون", "ذرة صفراء",
                             "نخالة قمح (ردة)", "كسب فول صويا 44%",
                             "مولاس قصب السكر",
                             "مركزات خيول ومجترات"],
                    "إبل": ["شعير مطحون", "ذرة صفراء",
                            "نخالة قمح (ردة)", "كسب فول صويا 44%",
                            "البرسيم الجاف (الدريس)",
                            "مركزات خيول ومجترات"],
                    "دواجن لاحم": ["ذرة صفراء", "كسب فول صويا 44%",
                                    "كسب جلوتين الذرة 60%",
                                    "نخالة قمح (ردة)",
                                    "مركزات دواجن وسمان",
                                    "بريمكس تسمين دواجن (Premix)"],
                    "دواجن بياض": ["ذرة صفراء", "كسب فول صويا 44%",
                                    "كسب جلوتين الذرة 60%",
                                    "نخالة قمح (ردة)",
                                    "مركزات دواجن وسمان",
                                    "بريمكس بياض وبشاير"],
                    "سمان": ["ذرة صفراء", "كسب فول صويا 44%",
                             "مركزات دواجن وسمان",
                             "بريمكس تسمين دواجن (Premix)"],
                    "أسماك": ["ذرة صفراء", "كسب فول صويا 44%",
                              "مسحوق أسماك (Fishmeal 60%)",
                              "كسب جلوتين الذرة 60%",
                              "مركزات دواجن وسمان"]}
                for ing in dmap.get(animal, []):
                    st.session_state[f"main_chk_{ing}"] = True
                st.rerun()
        with ac2:
            if st.button("❌ مسح الكل", key="main_clr",
                          use_container_width=True):
                for cat in BIG_FEEDS_LIBRARY.values():
                    for ing in cat:
                        st.session_state[f"main_chk_{ing}"] = False
                st.rerun()

        selected, prices = [], {}
        live_prices = MarketPriceEngine.get_adjusted_market_data(
            country, "المركز", city)
        for cat_name, items in BIG_FEEDS_LIBRARY.items():
            with st.expander(f"📁 {cat_name}", expanded=False):
                cols = st.columns(3)
                for idx, ing in enumerate(items.keys()):
                    with cols[idx % 3]:
                        if st.checkbox(ing, key=f"main_chk_{ing}"):
                            selected.append(ing)
                            prices[ing] = live_prices.get(ing, 350.0)

    if len(selected) < 3:
        st.warning("⚠️ اختر 3 مواد على الأقل من الأعلى")
    else:
        st.success(f"✅ {len(selected)} مادة مختارة")

        if st.button("🚀 تشغيل محرك التكوين", type="primary",
                      use_container_width=True, key="main_run"):
            use_cp = "CP" in basis
            with st.spinner("🔄 جاري الحساب..."):
                result = formulate_feed(animal, stage, selected,
                                         prices=prices,
                                         use_cp_basis=use_cp)

            if not result["success"]:
                st.error(result["message"])
            else:
                st.success(result["message"])

                # KPIs
                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("💰 $/طن",
                            f"{result['cost_per_ton']:.2f}")
                k2.metric("📊 DP", f"{result['totals']['DP']:.2f}%",
                            f"{result['totals']['DP']-result['totals']['target_DP']:+.2f}")
                k3.metric("⚡ SE", f"{result['totals']['SE']:.2f}",
                            f"{result['totals']['SE']-result['totals']['target_SE']:+.2f}")
                k4.metric("🧬 CP", f"{result['totals']['CP']:.2f}%")
                k5.metric("📦 مكونات", len(result["formula"]))

                # جدول الخلطة
                st.markdown("#### 📋 الخلطة النهائية")
                rows = [["المادة", "النسبة %", "كجم/طن", "الحالة"]]
                for ing, pct in result["formula"].items():
                    s = ("🔒 إلزامي"
                         if ing in result["fixed_ingredients"]
                         else "🟢 أساسي" if pct >= 20
                         else "🟡 مهم" if pct >= 5
                         else "⚪ مكمل")
                    rows.append([ing, f"{pct:.2f}%",
                                  f"{pct*10:.1f}", s])
                show_arabic_table(rows, "#2e7d32",
                                    ["40%", "18%", "18%", "24%"])

                # التحذيرات
                if result["warnings"]:
                    for w in result["warnings"]:
                        st.markdown(
                            f'<div class="warning-card">{w}</div>',
                            unsafe_allow_html=True)

                # الرسوم البيانية
                cc1, cc2 = st.columns(2)
                with cc1:
                    fig = go.Figure(data=[go.Pie(
                        labels=list(result["formula"].keys()),
                        values=list(result["formula"].values()),
                        hole=0.4,
                        marker=dict(colors=px.colors.sequential.Greens))])
                    fig.update_layout(
                        title="توزيع المكونات",
                        font=dict(family="Cairo, Tajawal, sans-serif"),
                        height=400)
                    st.plotly_chart(fig, use_container_width=True)
                with cc2:
                    keys = ["Ca", "P", "Na", "K", "Mg", "NDF", "ADF", "CF"]
                    mf_std = result.get("mf_standard", {})
                    if mf_std:
                        fig = go.Figure()
                        fig.add_trace(go.Scatterpolar(
                            r=[result["minerals"].get(k, 0) /
                               max(mf_std.get(k, 1), 0.01) * 100
                               for k in keys],
                            theta=keys, fill='toself',
                            name='المحسوب', line_color='#2e7d32'))
                        fig.add_trace(go.Scatterpolar(
                            r=[100]*len(keys), theta=keys,
                            fill='toself', name='القياسي',
                            line_color='#1565C0', opacity=0.4))
                        fig.update_layout(
                            title="رادار المعادن",
                            font=dict(family="Cairo, Tajawal, sans-serif"),
                            height=400)
                        st.plotly_chart(fig, use_container_width=True)

                # تحليل الأملاح والألياف
                st.markdown("---")
                st.markdown("## 🧂🌾 تحليل الأملاح والألياف")
                render_mineral_fiber_analysis(
                    result["formula"], animal, stage, requester)

                # التصدير
                st.markdown("---")
                st.markdown("### 📥 التصدير والحفظ")
                ex1, ex2, ex3 = st.columns(3)

                with ex1:
                    try:
                        xlsx_bytes = ExcelExporter.export_full(result)
                        st.download_button(
                            "📊 تحميل Excel",
                            xlsx_bytes,
                            file_name=f"Tawor_{animal}_"
                                       f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-"
                                  "officedocument.spreadsheetml.sheet",
                            use_container_width=True)
                    except Exception as e:
                        st.warning(f"⚠️ Excel: {e}")

                with ex2:
                    try:
                        mf_r = calculate_minerals_fibers(result["formula"])
                        mf_ev = (evaluate_against_standard(
                            mf_r["values"], result["mf_standard"])
                            if result["mf_standard"] else {})
                        pdf_data = pdf_generator\
                            .generate_comprehensive_report(
                                result["formula"],
                                result["totals"]["DP"],
                                f"{animal} - {stage}",
                                result["cost_per_ton"], city,
                                result["cost_per_ton"] *
                                    EXCHANGE_RATES.get(country,
                                        {"rate": 1.0})["rate"],
                                EXCHANGE_RATES.get(country,
                                    {"sym": "USD"})["sym"],
                                result["totals"]["SE"],
                                get_current_user_name(),
                                requester_name=requester,
                                standard=std_preview,
                                mineral_data=mf_r["values"],
                                mf_standard=result["mf_standard"],
                                mf_evaluation=mf_ev,
                                ratios=mf_r["ratios"])
                        st.download_button(
                            "📄 تحميل PDF", pdf_data,
                            file_name=f"Tawor_{animal}_"
                                       f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                            mime="application/pdf",
                            use_container_width=True)
                    except Exception as e:
                        st.warning(f"⚠️ PDF: {e}")

                with ex3:
                    with st.popover("💾 حفظ في المكتبة",
                                     use_container_width=True):
                        fname = st.text_input(
                            "اسم الخلطة:",
                            value=f"{animal}-{stage}-"
                                   f"{datetime.now().strftime('%Y%m%d')}",
                            key="main_save_name")
                        breed = st.text_input("السلالة:", key="main_breed")
                        if st.button("💾 حفظ نهائي",
                                      key="main_do_save",
                                      type="primary"):
                            try:
                                fid = FormulaLibrary.save_formula(
                                    result, fname, breed, requester)
                                if fid:
                                    st.success(f"✅ تم الحفظ ({fid[:8]})")
                                else:
                                    st.error("❌ فشل الحفظ")
                            except Exception as e:
                                st.error(f"❌ {e}")


# ═══════════════════════════════════════════════════════════
# 🚀 1: الوحدة المتقدمة
# ═══════════════════════════════════════════════════════════
with tabs[1]:
    st.markdown('<div class="section-title">🚀 وحدة علوم التكوين المتقدمة</div>',
                 unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        adv_a = st.selectbox("🐾 الفصيل:",
            list(STANDARD_VALUES.keys()), key="adv_a")
    with c2:
        adv_s = st.selectbox("📋 المرحلة:",
            list(STANDARD_VALUES.get(adv_a, {}).keys()),
            key=f"adv_s_{adv_a}")
    with c3:
        adv_b = st.radio("البروتين:", ["DP", "CP"],
                          horizontal=True, key="adv_b")

    std_prev2 = STANDARD_VALUES.get(adv_a, {}).get(adv_s, {})
    if std_prev2:
        m1, m2, m3 = st.columns(3)
        m1.metric("🎯 DP", f"{std_prev2.get('DP', 0):.2f}%")
        m2.metric("⚡ SE", f"{std_prev2.get('SE', 0):.2f}")
        m3.metric("📊 CP", f"{std_prev2.get('CP', 0):.2f}%")

    with st.expander("🌾 اختر المواد المتاحة", expanded=False):
        adv_ing, adv_prices = [], {}
        for cat_name, items in BIG_FEEDS_LIBRARY.items():
            with st.expander(f"📁 {cat_name}"):
                cols = st.columns(3)
                for idx, ing in enumerate(items.keys()):
                    with cols[idx % 3]:
                        if st.checkbox(ing, key=f"adv_chk_{ing}"):
                            adv_ing.append(ing)
                            adv_prices[ing] = MarketPriceEngine\
                                .get_adjusted_market_data(
                                    "السودان", "المركز",
                                    "الخرطوم").get(ing, 350.0)

    if len(adv_ing) >= 3:
        st.success(f"✅ {len(adv_ing)} مادة مختارة")

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            run_basic = st.button("🚀 تكوين", use_container_width=True,
                                    type="primary", key="adv_run")
        with b2:
            run_sens = st.button("📊 حساسية", use_container_width=True,
                                   key="adv_sens")
        with b3:
            run_mc = st.button("🎲 مونت كارلو",
                                 use_container_width=True, key="adv_mc")
        with b4:
            run_pareto = st.button("📈 باريتو",
                                     use_container_width=True,
                                     key="adv_par")

        use_cp2 = "CP" in adv_b

        # التكوين الأساسي
        if run_basic:
            with st.spinner("🔄 الحساب..."):
                adv_result = formulate_feed(
                    adv_a, adv_s, adv_ing,
                    prices=adv_prices, use_cp_basis=use_cp2)
            st.session_state["afs_last_result"] = adv_result
            if not adv_result["success"]:
                st.error(adv_result["message"])
            else:
                st.success(adv_result["message"])

                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("💰 $/طن",
                            f"{adv_result['cost_per_ton']:.2f}")
                k2.metric("📊 DP",
                            f"{adv_result['totals']['DP']:.2f}%")
                k3.metric("⚡ SE",
                            f"{adv_result['totals']['SE']:.2f}")
                k4.metric("🧬 CP",
                            f"{adv_result['totals']['CP']:.2f}%")
                k5.metric("📦 مكونات",
                            len(adv_result["formula"]))

                rows = [["المادة", "النسبة %", "كجم/طن", "الحالة"]]
                for ing, pct in adv_result["formula"].items():
                    s = ("🔒 إلزامي"
                         if ing in adv_result["fixed_ingredients"]
                         else "🟢 أساسي" if pct >= 20
                         else "🟡 مهم" if pct >= 5
                         else "⚪ مكمل")
                    rows.append([ing, f"{pct:.2f}%",
                                  f"{pct*10:.1f}", s])
                show_arabic_table(rows, "#2e7d32",
                                    ["40%", "18%", "18%", "24%"])

                st.markdown("#### 🧂🌾 تحليل الأملاح والألياف")
                render_mineral_fiber_analysis(
                    adv_result["formula"], adv_a, adv_s)

                # تحميل Excel
                try:
                    xlsx_bytes = ExcelExporter.export_full(
                        adv_result,
                        sensitivity=st.session_state.get("afs_sens_data"),
                        monte_carlo=st.session_state.get("afs_mc_data"),
                        pareto=st.session_state.get("afs_pareto_data"))
                    st.download_button(
                        "📊 تحميل Excel كامل", xlsx_bytes,
                        file_name=f"AFS_{adv_a}_"
                                   f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-"
                              "officedocument.spreadsheetml.sheet",
                        use_container_width=True)
                except Exception as e:
                    st.warning(f"⚠️ Excel: {e}")

        # تحليل الحساسية
        if run_sens:
            with st.spinner("📊 تحليل الحساسية..."):
                sens = sensitivity_analysis(adv_a, adv_s, adv_ing,
                                             prices=adv_prices, steps=5)
                st.session_state["afs_sens_data"] = sens
            if sens and sens["dp"]:
                df = pd.DataFrame(sens)
                fig = px.scatter_3d(
                    df, x="dp", y="se", z="cost",
                    color="cost", color_continuous_scale="RdYlGn_r",
                    title="سطح الحساسية: DP × SE × التكلفة")
                fig.update_layout(
                    font=dict(family="Cairo, Tajawal, sans-serif"),
                    height=600)
                st.plotly_chart(fig, use_container_width=True)

        # مونت كارلو
        if run_mc:
            with st.spinner("🎲 2000 محاكاة..."):
                mc = monte_carlo_cost(adv_a, adv_s, adv_ing,
                                       prices=adv_prices, n_sim=2000)
                st.session_state["afs_mc_data"] = mc
            if mc:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🎯 متوسط", f"${mc['mean']:.2f}")
                c2.metric("📉 P5", f"${mc['p5']:.2f}")
                c3.metric("📊 P50", f"${mc['p50']:.2f}")
                c4.metric("📈 P95", f"${mc['p95']:.2f}")
                fig = go.Figure()
                fig.add_trace(go.Histogram(
                    x=mc["samples"], nbinsx=60,
                    marker_color='#2e7d32'))
                fig.add_vline(x=mc["base_cost"], line_dash="dash",
                                line_color="red")
                fig.update_layout(
                    title="توزيع التكلفة — مونت كارلو",
                    xaxis_title="$/طن", yaxis_title="التكرار",
                    font=dict(family="Cairo, Tajawal, sans-serif"),
                    height=450)
                st.plotly_chart(fig, use_container_width=True)

        # باريتو
        if run_pareto:
            with st.spinner("📈 رسم حد باريتو..."):
                pf = pareto_frontier(adv_a, adv_s, adv_ing,
                                       prices=adv_prices)
                st.session_state["afs_pareto_data"] = pf
            if pf:
                df = pd.DataFrame(pf)
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=df["dp"], y=df["cost"],
                    mode='lines+markers',
                    line=dict(color='#2e7d32', width=3),
                    marker=dict(size=10)))
                fig.update_layout(
                    title="حد باريتو: DP × التكلفة",
                    xaxis_title="DP %", yaxis_title="$/طن",
                    font=dict(family="Cairo, Tajawal, sans-serif"),
                    height=450)
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ اختر 3 مواد على الأقل")


# ═══════════════════════════════════════════════════════════
# 📚 2: مكتبة الخلطات
# ═══════════════════════════════════════════════════════════
with tabs[2]:
    st.markdown('<div class="section-title">📚 مكتبة الخلطات المحفوظة</div>',
                 unsafe_allow_html=True)

    if st.button("🔄 تحديث", key="lib_refresh"):
        st.rerun()

    formulas = FormulaLibrary.list_formulas(limit=200)
    if not formulas:
        st.info("📭 لا توجد خلطات محفوظة. اذهب للقطاع الحيواني "
                 "واحفظ خلطة.")
    else:
        st.success(f"📦 {len(formulas)} خلطة محفوظة")

        search = st.text_input("🔍 بحث بالاسم:", key="lib_search")
        filtered = formulas
        if search:
            filtered = [f for f in filtered
                        if search.lower() in f['formula_name'].lower()]

        for f in filtered[:30]:
            with st.expander(
                f"🧬 {f['formula_name']} — "
                f"${f['cost_per_ton']:.2f}/طن | "
                f"{f['created_date'][:16]}"):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("🐾 الفصيل", f['animal_type'])
                c2.metric("📋 المرحلة", f['stage'])
                c3.metric("💰 $/طن", f"{f['cost_per_ton']:.2f}")
                c4.metric("👤 المنشئ", f['created_by'][:20])

                loaded = FormulaLibrary.load_formula(f['formula_id'])
                if loaded and loaded.get('payload'):
                    payload = loaded['payload']
                    formula_dict = payload.get('formula', {})
                    if formula_dict:
                        rows = [["المادة", "النسبة %", "كجم/طن"]]
                        for ing, pct in formula_dict.items():
                            rows.append([ing, f"{pct:.2f}%",
                                          f"{pct*10:.1f}"])
                        show_arabic_table(rows, "#2e7d32",
                                            ["50%", "25%", "25%"])

                ac1, ac2 = st.columns(2)
                with ac1:
                    if st.button("📥 تحميل Excel",
                                  key=f"lib_xls_{f['formula_id']}"):
                        try:
                            loaded2 = FormulaLibrary\
                                .load_formula(f['formula_id'])
                            payload = loaded2.get('payload', {})
                            mini_result = {
                                'animal_type': f['animal_type'],
                                'stage': f['stage'],
                                'formula': payload.get('formula', {}),
                                'totals': payload.get('totals', {}),
                                'minerals': payload.get('minerals', {}),
                                'ratios': payload.get('ratios', {}),
                                'mineral_eval':
                                    payload.get('mineral_eval', {}),
                                'mf_standard':
                                    payload.get('mf_standard', {}),
                                'warnings':
                                    payload.get('warnings', []),
                                'smart_recommendations':
                                    payload.get('smart_recommendations',
                                                 []),
                                'fixed_ingredients':
                                    payload.get('fixed_ingredients', {}),
                                'cost_per_ton': f['cost_per_ton'],
                                'cost_per_kg': f['cost_per_ton'] / 1000,
                            }
                            xb = ExcelExporter.export_full(mini_result)
                            st.download_button(
                                "⬇️ اضغط للتحميل", xb,
                                file_name=f"{f['formula_name']}.xlsx",
                                mime="application/vnd.openxmlformats-"
                                      "officedocument.spreadsheetml.sheet",
                                key=f"dl_{f['formula_id']}")
                        except Exception as e:
                            st.error(f"❌ {e}")
                with ac2:
                    if st.button("🗑️ حذف",
                                  key=f"lib_del_{f['formula_id']}"):
                        FormulaLibrary.delete_formula(f['formula_id'])
                        st.success("🗑️ تم الحذف")
                        st.rerun()


# ═══════════════════════════════════════════════════════════
# 🧪 3: المختبر الذكي
# ═══════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown('<div class="section-title">🧪 المختبر الذكي</div>',
                 unsafe_allow_html=True)

    if st.session_state.get("lab_sample"):
        s = st.session_state["lab_sample"]
        st.success(f"📥 عينة من {s['animal']} - {s['breed']}")
        if st.button("🗑️ مسح"):
            st.session_state["lab_sample"] = None
            st.rerun()

    st.info("💡 لتحليل صورة شهادة مخبرية، استخدم تبويب 'المختبر المتقدم' "
             "أو أدخل القيم يدوياً هنا.")

    c1, c2 = st.columns(2)
    with c1:
        animal_lab = st.selectbox("الفصيل:",
            list(STANDARD_VALUES.keys()), key="lab_animal")
        st.text_input("اسم العينة:", key="lab_sample_name")
        st.number_input("CP:", value=0.0, step=0.1, key="lab_cp")
        st.number_input("DC:", value=0.0, step=0.01, key="lab_dc")
        st.number_input("SE:", value=0.0, step=0.1, key="lab_se")
    with c2:
        st.number_input("NDF:", value=0.0, step=0.1, key="lab_ndf")
        st.number_input("ADF:", value=0.0, step=0.1, key="lab_adf")
        st.number_input("Ca:", value=0.0, step=0.01, key="lab_ca")
        st.number_input("P:", value=0.0, step=0.01, key="lab_p")

    st.text_area("ملاحظات:", key="lab_notes")


# ═══════════════════════════════════════════════════════════
# 🔬 4: المختبر المتقدم
# ═══════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown('<div class="section-title">🔬 المختبر المتقدم</div>',
                 unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        lab_an = st.selectbox("الفصيل:",
            list(STANDARD_VALUES.keys()), key="labv_animal")
    with c2:
        lab_st = st.selectbox("المرحلة:",
            list(STANDARD_VALUES.get(lab_an, {}).keys()),
            key=f"labv_stage_{lab_an}")

    std_lab = STANDARD_VALUES.get(lab_an, {}).get(lab_st, {})
    mf_std_lab = MINERAL_FIBER_STANDARDS.get(lab_an, {}).get(lab_st, {})

    inputs = {}
    cols = st.columns(3)
    for idx, ing in enumerate(FLAT_FEED_DB.keys()):
        with cols[idx % 3]:
            inputs[ing] = st.number_input(f"{ing} (كجم)",
                min_value=0.0, value=0.0, step=5.0,
                key=f"labv_{ing}")

    if st.button("🧪 تشغيل التحليل", type="primary",
                  use_container_width=True, key="labv_run"):
        total = sum(inputs.values())
        if total <= 0:
            st.warning("⚠️ أدخل أوزاناً.")
        else:
            cp_t = dp_t = se_t = 0.0
            comps = []
            pcts = {}
            for ing, w in inputs.items():
                if w > 0:
                    pct = w / total * 100
                    pcts[ing] = pct
                    fd = FLAT_FEED_DB.get(ing, {})
                    cp = fd.get("CP", 0.0)
                    dc = fd.get("DC", 0.0)
                    se = fd.get("SE", 0.0)
                    cp_t += pct / 100 * cp
                    dp_t += pct / 100 * (cp * dc)
                    se_t += pct / 100 * se
                    comps.append([ing, f"{w:.1f}", f"{pct:.2f}"])

            st.success("🔬 تم التحليل!")
            t1, t2, t3 = st.tabs(["📋 المكونات", "🧬 بروتين",
                                    "🧂 أملاح وألياف"])
            with t1:
                show_arabic_table(
                    [["المادة", "الوزن", "النسبة %"]] + comps,
                    "#1565C0", ["50%", "25%", "25%"])
            with t2:
                rows = [["العنصر", "القيمة"]]
                rows.append(["CP", f"{cp_t:.2f}%"])
                rows.append(["DP", f"{dp_t:.2f}%"])
                rows.append(["SE", f"{se_t:.2f}"])
                show_arabic_table(rows, "#2e7d32", ["60%", "40%"])
            with t3:
                render_mineral_fiber_analysis(pcts, lab_an, lab_st)


# ═══════════════════════════════════════════════════════════
# 🐔 5: إدارة المزارع
# ═══════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown('<div class="section-title">🐔 إدارة المزارع</div>',
                 unsafe_allow_html=True)

    with st.expander("➕ إضافة دورة جديدة"):
        c1, c2 = st.columns(2)
        with c1:
            fn = st.text_input("اسم الدورة:", key="farm_name")
            ib = st.number_input("عدد الكتاكيت:", 1, 100000, 1000, 100,
                                   key="farm_birds")
        with c2:
            br = st.selectbox("السلالة:",
                ["Ross 308", "Cobb 500", "محلية"], key="farm_breed")
            sd = st.date_input("تاريخ البدء", datetime.now(),
                                key="farm_start")
        if st.button("💾 إنشاء", key="farm_create"):
            if fn:
                cid = secrets.token_hex(8)
                st.session_state["broiler_farms"][cid] = {
                    "farm_name": fn, "initial_birds": ib,
                    "breed": br, "start_date": sd.isoformat(),
                    "age_days": 0, "current_weight": 0.045,
                    "total_feed": 0, "dead_count": 0}
                st.success(f"✅ {fn}")
                st.rerun()

    if st.session_state["broiler_farms"]:
        for cid, farm in st.session_state["broiler_farms"].items():
            with st.expander(
                f"🏠 {farm['farm_name']} - {farm['breed']}"):
                c1, c2, c3 = st.columns(3)
                c1.metric("العدد", farm['initial_birds'])
                c1.metric("العمر", farm['age_days'])
                c2.metric("الوزن", f"{farm['current_weight']:.3f}")
                c2.metric("العلف", f"{farm['total_feed']:.1f}")
                mort = ((farm['dead_count'] /
                         farm['initial_birds']) * 100
                        if farm['initial_birds'] > 0 else 0)
                c3.metric("النفوق %", f"{mort:.1f}")
                c3.metric("النافق", farm['dead_count'])

                u1, u2 = st.columns(2)
                with u1:
                    nw = st.number_input("الوزن:", min_value=0.01,
                        value=float(farm['current_weight']),
                        step=0.01, key=f"w_{cid}")
                    nf = st.number_input("العلف:", min_value=0.0,
                        value=float(farm['total_feed']),
                        step=1.0, key=f"f_{cid}")
                with u2:
                    nd = st.number_input("النافق:", 0, value=0,
                                          step=1, key=f"d_{cid}")
                    na = st.number_input("العمر:", 0,
                        value=int(farm['age_days']),
                        step=1, key=f"a_{cid}")
                if st.button("📊 تحديث", key=f"up_{cid}"):
                    farm['current_weight'] = nw
                    farm['total_feed'] = nf
                    farm['dead_count'] += nd
                    farm['age_days'] = na
                    st.success("✅ تم التحديث")
                    st.rerun()
    else:
        st.info("📭 لا توجد دورات مزارع بعد")


# ═══════════════════════════════════════════════════════════
# 🍼 6: بدائل الحليب
# ═══════════════════════════════════════════════════════════
with tabs[6]:
    st.markdown('<div class="section-title">🍼 بدائل الحليب</div>',
                 unsafe_allow_html=True)

    at = st.selectbox("نوع الحيوان:",
        ["عجل بقري", "حملان أغنام", "جديان ماعز",
         "مهرات خيول", "أطفال إبل"], key="milk_animal")
    age = st.slider("العمر (يوم):", 1, 120, 30, key="milk_age")

    needs = {"عجل بقري": {"protein": 22, "fat": 18, "volume": 8},
             "حملان أغنام": {"protein": 24, "fat": 20, "volume": 4},
             "جديان ماعز": {"protein": 23, "fat": 19, "volume": 3},
             "مهرات خيول": {"protein": 20, "fat": 15, "volume": 5},
             "أطفال إبل": {"protein": 21, "fat": 17, "volume": 6}}
    af = 1.2 if age < 14 else 1.0 if age < 30 else 0.85 if age < 60 else 0.70
    tp = needs[at]["protein"] * af
    tf = needs[at]["fat"] * af
    dv = needs[at]["volume"] * af

    st.info(f"📊 احتياج: بروتين {tp:.1f}% | دهون {tf:.1f}% | "
             f"حجم {dv:.1f} لتر/يوم")


# ═══════════════════════════════════════════════════════════
# 💊 7: منبه الجرعات
# ═══════════════════════════════════════════════════════════
with tabs[7]:
    st.markdown('<div class="section-title">💊 منبه الجرعات</div>',
                 unsafe_allow_html=True)

    with st.expander("➕ إضافة تذكير"):
        c1, c2, c3 = st.columns(3)
        with c1:
            at2 = st.selectbox("الحيوان:",
                ["أبقار", "أغنام", "ماعز", "خيول", "إبل",
                 "دواجن", "أسماك"], key="dose_animal")
            dt = st.selectbox("النوع:",
                ["لقاح", "فيتامين", "دواء", "مضاد طفيليات"],
                key="dose_type")
            dn = st.text_input("الاسم:", key="dose_name")
        with c2:
            da = st.number_input("الجرعة:", 0.0, value=1.0,
                                   step=0.1, key="dose_amount")
            du = st.selectbox("الوحدة:",
                ["مل", "جم", "مجم", "قطرة"], key="dose_unit")
            ar_ = st.selectbox("الطريقة:",
                ["عضل", "تحت الجلد", "فموي", "مياه الشرب"],
                key="dose_route")
        with c3:
            fd = st.number_input("كل (أيام):", 1, value=7,
                                   key="dose_freq")
            sd = st.date_input("البدء", datetime.now(),
                                key="dose_start")
            notes = st.text_area("ملاحظات:", key="dose_notes")
        if st.button("💾 حفظ التذكير", key="dose_save"):
            if dn:
                st.session_state["dose_reminders"].append({
                    'id': secrets.token_hex(8),
                    'animal': at2, 'type': dt, 'name': dn,
                    'amount': da, 'unit': du, 'route': ar_,
                    'freq': fd, 'start': sd.isoformat(),
                    'next': (sd + timedelta(days=fd)).isoformat(),
                    'notes': notes})
                st.success("✅")
                st.rerun()

    if st.session_state["dose_reminders"]:
        rows = [["الاسم", "الحيوان", "الجرعة",
                 "التكرار", "القادم"]]
        for r in st.session_state["dose_reminders"]:
            rows.append([r['name'], r['animal'],
                          f"{r['amount']} {r['unit']}",
                          f"كل {r['freq']} يوم", r['next'][:10]])
        show_arabic_table(rows, "#c62828")
    else:
        st.info("📭 لا توجد تذكيرات")


# ═══════════════════════════════════════════════════════════
# 📊 8: بورصة الأسعار
# ═══════════════════════════════════════════════════════════
with tabs[8]:
    st.markdown('<div class="section-title">📊 بورصة الأسعار</div>',
                 unsafe_allow_html=True)

    if get_current_user_role() in ["owner", "specialist"]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("🐄 المواشي")
            for name in list(st.session_state[
                    "global_livestock_prices"].keys()):
                p = st.session_state["global_livestock_prices"][name]
                np_ = st.number_input(name, value=float(p), step=5.0,
                                        key=f"pl_{name}")
                st.session_state["global_livestock_prices"][name] = np_
        with c2:
            st.subheader("🥩 المنتجات")
            for name in list(st.session_state[
                    "global_products_prices"].keys()):
                p = st.session_state["global_products_prices"][name]
                np_ = st.number_input(name, value=float(p), step=0.5,
                                        key=f"pp_{name}")
                st.session_state["global_products_prices"][name] = np_
    else:
        rows = [["المنتج", "السعر ($)"]]
        for n, p in st.session_state[
                "global_livestock_prices"].items():
            rows.append([n, f"{p:.2f}"])
        show_arabic_table(rows, "#2e7d32", ["60%", "40%"])
        rows = [["المنتج", "السعر ($)"]]
        for n, p in st.session_state[
                "global_products_prices"].items():
            rows.append([n, f"{p:.2f}"])
        show_arabic_table(rows, "#1565C0", ["60%", "40%"])


# ═══════════════════════════════════════════════════════════
# 🏭 9: المستودعات
# ═══════════════════════════════════════════════════════════
with tabs[9]:
    st.markdown('<div class="section-title">🏭 المستودعات</div>',
                 unsafe_allow_html=True)

    rows = [["المادة", "الكمية (طن)", "الحد الأدنى", "الحالة"]]
    for item, data in st.session_state["inventory"].items():
        qty = data["quantity"] if isinstance(data, dict) else data
        thr = (data.get("min_threshold", 5.0)
               if isinstance(data, dict) else 5.0)
        st_ = ("🔴 نفذ" if qty <= 0
               else "🟡 منخفض" if qty < thr else "🟢 آمن")
        rows.append([item, f"{qty:.1f}", f"{thr:.1f}", st_])
    show_arabic_table(rows, "#2e7d32",
                       ["40%", "20%", "20%", "20%"])


# ═══════════════════════════════════════════════════════════
# 📈 10: الإنتاج اليومي
# ═══════════════════════════════════════════════════════════
with tabs[10]:
    st.markdown('<div class="section-title">📈 الإنتاج اليومي</div>',
                 unsafe_allow_html=True)

    with st.form("daily_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            dfarm = st.text_input("المزرعة:", key="daily_farm")
            ddate = st.date_input("التاريخ", datetime.now(),
                                    key="daily_date")
        with c2:
            dmilk = st.number_input("حليب (لتر):", 0.0,
                                      key="daily_milk")
            deggs = st.number_input("بيض (عدد):", 0,
                                      key="daily_eggs")
        with c3:
            dwg = st.number_input("زيادة الوزن (كجم):", 0.0,
                                    key="daily_wg")
            dmo = st.number_input("النافق:", 0, key="daily_mo")
        if st.form_submit_button("💾 حفظ"):
            st.session_state["daily_production_log"].append({
                "farm": dfarm, "date": ddate.isoformat(),
                "milk": dmilk, "eggs": deggs,
                "weight_gain": dwg, "mortality": dmo})
            st.success("✅ تم الحفظ")

    if st.session_state["daily_production_log"]:
        rows = [["المزرعة", "التاريخ", "حليب",
                 "بيض", "وزن", "نافق"]]
        for r in st.session_state["daily_production_log"]:
            rows.append([r['farm'], r['date'][:10],
                          r['milk'], r['eggs'],
                          r['weight_gain'], r['mortality']])
        show_arabic_table(rows, "#2e7d32")


# ═══════════════════════════════════════════════════════════
# 🔔 11: التنبيهات
# ═══════════════════════════════════════════════════════════
with tabs[11]:
    st.markdown("### 🔔 التنبيهات")
    warns = InventoryManager.check_stock_levels()
    if warns:
        rows = [["المادة", "الحالة"]]
        for item, info in warns.items():
            rows.append([item, info['status']])
        show_arabic_table(rows, "#c62828", ["60%", "40%"])
    else:
        st.success("✅ لا توجد تنبيهات")


# ═══════════════════════════════════════════════════════════
# 📈 12: التحليلات
# ═══════════════════════════════════════════════════════════
with tabs[12]:
    st.markdown('<div class="section-title">📈 التحليلات</div>',
                 unsafe_allow_html=True)

    st.subheader("🔮 تنبؤات الأسعار")
    p = PricePredictor()
    for ing in ["ذرة صفراء", "كسب فول صويا 44%",
                "نخالة قمح (ردة)"]:
        pred = p.predict_price(ing, 7)
        if pred.get('prediction'):
            ic = ("📈" if pred.get('trend') == 'up'
                  else "📉" if pred.get('trend') == 'down'
                  else "➡️")
            cp = pred.get('current_price') or 0
            st.metric(f"{ic} {ing}",
                       f"${pred['prediction']:.2f}",
                       delta=f"{pred['prediction'] - cp:.2f}")

    st.subheader("📊 الرسوم البيانية")
    dates = pd.date_range(start='2024-01-01', periods=12, freq='ME')
    df = pd.DataFrame({
        'التاريخ': dates,
        'الذرة': [220, 225, 230, 228, 235, 240,
                   238, 242, 245, 248, 250, 252],
        'الصويا': [440, 445, 442, 448, 450, 455,
                    452, 458, 460, 462, 465, 468]})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['التاريخ'], y=df['الذرة'],
        mode='lines+markers', name='الذرة',
        line=dict(color='#2e7d32', width=2)))
    fig.add_trace(go.Scatter(x=df['التاريخ'], y=df['الصويا'],
        mode='lines+markers', name='الصويا',
        line=dict(color='#1565C0', width=2)))
    fig.update_layout(
        title='اتجاه أسعار المواد الخام',
        xaxis_title='التاريخ', yaxis_title='السعر ($/طن)',
        font=dict(family="Cairo, Tajawal, sans-serif"),
        height=450)
    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════
# 💬 13: التعليقات
# ═══════════════════════════════════════════════════════════
with tabs[13]:
    st.markdown('<div class="section-title">💬 التعليقات</div>',
                 unsafe_allow_html=True)

    st.text_area("التعليقات الحالية:",
                  value=st.session_state["shared_comments"],
                  height=200, disabled=True)
    nc = st.text_area("تعليق جديد:", key="new_comment")
    if st.button("➕ نشر"):
        if nc:
            role = ("المالك"
                    if st.session_state["user_role"] == "owner"
                    else "مختص")
            st.session_state["shared_comments"] += \
                f"\n• [{role} " \
                f"{datetime.now().strftime('%Y-%m-%d %H:%M')}]: {nc}"
            st.rerun()


# ═══════════════════════════════════════════════════════════
# 📚 14: المراجع
# ═══════════════════════════════════════════════════════════
with tabs[14]:
    st.markdown('<div class="section-title">📚 المراجع العلمية</div>',
                 unsafe_allow_html=True)

    refs = {
        "📚 تغذية الحيوان": [
            ("McDonald, P., et al. (2011)",
             "Animal Nutrition", "Pearson"),
            ("NRC (2001)",
             "Nutrient Requirements of Dairy Cattle",
             "National Academies Press")],
        "🪨 المعادن": [
            ("Underwood & Suttle (1999)",
             "The Mineral Nutrition of Livestock", "CABI")],
        "🐔 تغذية الدواجن": [
            ("Leeson & Summers (2009)",
             "Commercial Poultry Nutrition",
             "Nottingham University Press")],
        "🌾 الألياف": [
            ("Mertens, D.R. (1997)",
             "Fiber Requirements of Dairy Cows",
             "Journal of Dairy Science")]}
    for cat, items in refs.items():
        with st.expander(cat):
            for authors, title, pub in items:
                st.markdown(f"""
                <div style='background:#f8f9fa; padding:12px;
                            border-radius:8px; margin-bottom:8px;
                            border-right:4px solid #2e7d32;
                            direction:rtl; text-align:right;'>
                    <b>{title}</b><br>
                    👤 {authors}<br>
                    📚 {pub}
                </div>
                """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 🌐 15: واجهة API
# ═══════════════════════════════════════════════════════════
with tabs[15]:
    st.markdown('<div class="section-title">🌐 واجهة REST API</div>',
                 unsafe_allow_html=True)

    st.markdown("""
    ### 🚀 تشغيل خدمة API

    ```bash
    uvicorn tawor_api:app --host 0.0.0.0 --port 8502
    ```

    👉 Swagger UI: [`http://localhost:8502/docs`](http://localhost:8502/docs)
    """)

    endpoints = [
        ["GET", "/health", "فحص الحالة"],
        ["POST", "/auth/register", "تسجيل مستخدم"],
        ["POST", "/auth/login", "تسجيل دخول (JWT)"],
        ["POST", "/formulate", "تكوين خلطة"],
        ["POST", "/formulas/save", "حفظ خلطة"],
        ["GET", "/formulas", "قائمة الخلطات"],
    ]
    show_arabic_table([["الطريقة", "المسار", "الوصف"]] + endpoints,
                       "#1565C0", ["15%", "40%", "45%"])


# ═══════════════════════════════════════════════════════════
# 📧 16: إرسال الكود (owner only)
# ═══════════════════════════════════════════════════════════
if get_current_user_role() == "owner":
    with tabs[16]:
        st.markdown('<div class="section-title">📧 إرسال السورس كود</div>',
                     unsafe_allow_html=True)
        em = st.text_input("البريد:", value=OWNER_EMAIL, key="send_email")
        if st.button("📤 إرسال", key="do_send_email"):
            if em and '@' in em:
                with st.spinner("جاري الإرسال..."):
                    ok, msg = send_code_to_email(em)
                    st.success(msg) if ok else st.error(msg)


# ═══════════════════════════════════════════════════════════
# 📊 17: لوحة الإدارة (owner only)
# ═══════════════════════════════════════════════════════════
if get_current_user_role() == "owner":
    with tabs[17]:
        render_admin_dashboard()


# =====================================================================
# التذييل
# =====================================================================
st.markdown("""
<div style='text-align:center; padding:20px; margin-top:30px;
            border-top:2px solid #e0e0e0; color:#888;'>
🌾 <b>تاور نولجي Tawornology v19.6</b><br>
© 2026 | الاختصاصي م. عبد القادر إسماعيل تاور<br>
🕊️ إهداء إلى روح والدي <b>إسماعيل تاور</b> وأختي <b>ابتسام</b>
</div>
""", unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════
# نهاية الكود v19.6
# ═══════════════════════════════════════════════════════════════════════
