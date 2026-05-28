import base64
import io
import os
import smtplib
import urllib.parse
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# محاولة استيراد مكتبات العربية مع معالجة الأخطاء
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SUPPORT = True
except ImportError:
    ARABIC_SUPPORT = False
    # دوال بديلة إذا فشل التثبيت
    def get_display(x): return str(x)
    arabic_reshaper = None

import numpy as np
import pandas as pd
import streamlit as st
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from scipy.optimize import linprog

# ==========================================
# قراءة الأسرار من Streamlit Secrets
# ==========================================

SMTP_SERVER = st.secrets.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(st.secrets.get("SMTP_PORT", "587"))
SENDER_EMAIL = st.secrets.get("SENDER_EMAIL", "")
SENDER_PASSWORD = st.secrets.get("SENDER_PASSWORD", "")
OWNER_EMAIL = st.secrets.get("OWNER_EMAIL", "")
WHATSAPP_NUMBER = st.secrets.get("WHATSAPP_NUMBER", "")
GOOGLE_FORM_URL = st.secrets.get("GOOGLE_FORM_URL", "https://forms.gle/example")
DB_NAME = st.secrets.get("DB_NAME", "tower_scientific.db")

# الأكواد المعتمدة لنظام الصلاحيات
CODES_DB = {
    "202687": "owner",
    "2020": "specialist", 
    "2026": "breeder",
}

# ==========================================
# دوال معالجة العربية (آمنة)
# ==========================================

def fix_arabic_text(text):
    """معالجة النصوص العربية - تعمل حتى بدون المكتبات"""
    if not ARABIC_SUPPORT or arabic_reshaper is None:
        return str(text)
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

# ==========================================
# إدارة قاعدة البيانات
# ==========================================

@st.cache_resource
def init_database():
    """تهيئة قاعدة البيانات"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Ingredients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        category TEXT NOT NULL,
        price_per_ton REAL NOT NULL,
        max_limit REAL DEFAULT 100.0,
        min_limit REAL DEFAULT 0.0
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS Nutrient_Matrix (
        ingredient_id INTEGER,
        crude_protein REAL DEFAULT 0.0,
        lysine REAL DEFAULT 0.0,
        methionine REAL DEFAULT 0.0,
        digestibility_coeff REAL DEFAULT 1.0,
        starch_equivalent REAL DEFAULT 0.0,
        FOREIGN KEY (ingredient_id) REFERENCES Ingredients(id) ON DELETE CASCADE
    )
    ''')
    
    conn.commit()
    
    # فحص إذا كانت قاعدة البيانات فارغة
    cursor.execute("SELECT COUNT(*) FROM Ingredients")
    if cursor.fetchone()[0] == 0:
        seed_database(conn)
    
    conn.close()
    return True

def seed_database(conn):
    """ضخ البيانات الأولية"""
    cursor = conn.cursor()
    
    library = {
        "🌾 الحبوب ومصادر الطاقة": {
            "ذرة صفراء": {"CP": 8.5, "lys": 0.24, "met": 0.17, "DC": 0.85, "SE": 80.0, "price": 230.0},
            "ذرة بيضاء": {"CP": 8.8, "lys": 0.23, "met": 0.16, "DC": 0.83, "SE": 78.0, "price": 225.0},
            "شعير مطحون": {"CP": 11.5, "lys": 0.36, "met": 0.19, "DC": 0.80, "SE": 71.0, "price": 210.0},
            "سورجم (فتريتة)": {"CP": 10.0, "lys": 0.22, "met": 0.15, "DC": 0.78, "SE": 70.0, "price": 195.0},
        },
        "🌱 الأكساب ومصادر البروتين": {
            "كسب فول صويا 44%": {"CP": 44.0, "lys": 2.70, "met": 0.62, "DC": 0.90, "SE": 74.0, "price": 440.0},
            "كسب فول صويا 48%": {"CP": 48.0, "lys": 2.90, "met": 0.67, "DC": 0.91, "SE": 76.0, "price": 480.0},
            "كسب عباد الشمس 36%": {"CP": 36.0, "lys": 1.20, "met": 0.75, "DC": 0.76, "SE": 42.0, "price": 310.0},
            "أمباز الفول السوداني (كسب)": {"CP": 46.0, "lys": 1.60, "met": 0.52, "DC": 0.88, "SE": 73.0, "price": 460.0},
        },
        "🧬 مصادر البروتين الحيواني": {
            "مسحوق أسماك (Fishmeal 60%)": {"CP": 60.0, "lys": 4.50, "met": 1.65, "DC": 0.85, "SE": 65.0, "price": 850.0},
        },
        "🪨 الأملاح والمعادن": {
            "ملح الطعام": {"CP": 0.0, "lys": 0.0, "met": 0.0, "DC": 0.0, "SE": 0.0, "price": 30.0},
            "الحجر الجيري": {"CP": 0.0, "lys": 0.0, "met": 0.0, "DC": 0.0, "SE": 0.0, "price": 40.0},
            "فوسفات ثنائي الكالسيوم (DCP)": {"CP": 0.0, "lys": 0.0, "met": 0.0, "DC": 0.0, "SE": 0.0, "price": 280.0},
        },
        "🔬 الإنزيمات والإضافات": {
            "بريمكس تسمين دواجن": {"CP": 0.0, "lys": 0.0, "met": 0.0, "DC": 0.0, "SE": 0.0, "price": 230.0},
        }
    }
    
    for cat, items in library.items():
        for name, nut in items.items():
            cursor.execute("""
                INSERT OR IGNORE INTO Ingredients (name, category, price_per_ton, max_limit, min_limit)
                VALUES (?, ?, ?, 100.0, 0.0)
            """, (name, cat, nut["price"]))
            
            cursor.execute("SELECT id FROM Ingredients WHERE name=?", (name,))
            result = cursor.fetchone()
            if result:
                ing_id = result[0]
                cursor.execute("""
                    INSERT OR REPLACE INTO Nutrient_Matrix VALUES (?, ?, ?, ?, ?, ?)
                """, (ing_id, nut["CP"], nut["lys"], nut["met"], nut["DC"], nut["SE"]))
    
    conn.commit()

@st.cache_data(ttl=3600)
def load_feeds_from_db():
    """تحميل الأعلاف من قاعدة البيانات"""
    conn = sqlite3.connect(DB_NAME)
    query = """
    SELECT i.name, i.category, i.price_per_ton, i.max_limit, i.min_limit,
           n.crude_protein, n.lysine, n.methionine, n.digestibility_coeff, n.starch_equivalent
    FROM Ingredients i JOIN Nutrient_Matrix n ON i.id = n.ingredient_id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    structured_library = {}
    for cat in df['category'].unique():
        structured_library[cat] = {}
        sub_df = df[df['category'] == cat]
        for _, row in sub_df.iterrows():
            structured_library[cat][row['name']] = {
                "CP": row['crude_protein'], 
                "lys": row['lysine'], 
                "met": row['methionine'],
                "DC": row['digestibility_coeff'], 
                "SE": row['starch_equivalent'], 
                "price": row['price_per_ton'], 
                "max": row['max_limit'], 
                "min": row['min_limit']
            }
    return structured_library

def send_code_to_mail(receiver_email):
    """إرسال الكود عبر البريد"""
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        st.error("⚠️ يرجى إعداد الأسرار في Streamlit Cloud")
        return False
    
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = receiver_email
        msg["Subject"] = "🌾 كود منصة تاور العلمية"
        
        body = "السلام عليكم، هذا هو كود المنصة."
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"فشل الإرسال: {e}")
        return False

# ==========================================
# واجهة Streamlit الرئيسية
# ==========================================

def main():
    st.set_page_config(
        page_title="منصة تاور العلمية",
        page_icon="🌾",
        layout="wide",
    )
    
    # تحذير إذا كانت مكتبات العربية غير مثبتة
    if not ARABIC_SUPPORT:
        st.warning("⚠️ ملاحظة: بعض مكتبات عرض اللغة العربية غير مثبتة. النصوص ستعرض بشكل مبسط ولكن جميع الوظائف تعمل بشكل طبيعي.")
    
    # تهيئة قاعدة البيانات
    try:
        init_database()
    except Exception as e:
        st.error(f"خطأ في قاعدة البيانات: {e}")
        st.stop()
    
    # بوابة الدخول
    if "approved" not in st.session_state:
        st.session_state["approved"] = False
        st.session_state["user_role"] = None
    
    if not st.session_state["approved"]:
        st.markdown("<h2 style='text-align:center;'>🔒 منصة تاور العلمية</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;'>الاختصاصي م. عبد القادر إسماعيل تاور</p>", unsafe_allow_html=True)
        
        input_code = st.text_input("كود الدخول:", type="password")
        
        if st.button("تسجيل الدخول", type="primary"):
            if input_code in CODES_DB:
                st.session_state["approved"] = True
                st.session_state["user_role"] = CODES_DB[input_code]
                st.rerun()
            else:
                st.error("❌ كود غير صحيح")
        st.stop()
    
    # الترحيب
    role_name = {
        "owner": "المالك 👑",
        "specialist": "المختص 👨‍🔬",
        "breeder": "المربي 🌾"
    }[st.session_state["user_role"]]
    
    st.sidebar.success(f"مرحباً {role_name}")
    if st.sidebar.button("تسجيل الخروج"):
        st.session_state["approved"] = False
        st.rerun()
    
    # تحميل البيانات
    feeds_library = load_feeds_from_db()
    
    # العنوان الرئيسي
    st.title("🌾 منصة تاور العلمية للانتاج الحيواني وتركيب الاعلاف")
    st.caption("الاختصاصي م. عبد القادر إسماعيل تاور")
    
    # تبويبات
    tab1, tab2, tab3 = st.tabs(["🔬 تركيب الأعلاف", "📊 إدارة المخزون", "📖 المساعدة"])
    
    with tab1:
        st.subheader("🎯 نظام تركيب الأعلاف الذكي")
        
        col1, col2 = st.columns(2)
        with col1:
            country = st.selectbox("الدولة:", ["السودان", "مصر", "ليبيا", "السعودية", "الإمارات", "أخرى"])
        with col2:
            city = st.text_input("المدينة:", "الخرطوم")
        
        st.markdown("#### 📦 اختر مكونات العلف:")
        
        selected_ingredients = []
        prices = {}
        
        for cat_name, items in feeds_library.items():
            with st.expander(cat_name):
                cols = st.columns(3)
                for idx, (name, data) in enumerate(items.items()):
                    with cols[idx % 3]:
                        if st.checkbox(name, key=f"sel_{name}"):
                            selected_ingredients.append(name)
                            prices[name] = st.number_input(
                                f"سعر {name} ($/طن)",
                                value=float(data["price"]),
                                key=f"price_{name}"
                            )
        
        target_protein = st.slider("🎯 نسبة البروتين المستهدفة (%)", 5.0, 40.0, 16.0)
        
        if st.button("🚀 تشغيل المحرك", type="primary"):
            if len(selected_ingredients) < 2:
                st.warning("⚠️ يرجى اختيار مكونين على الأقل")
            else:
                with st.spinner("جاري حساب التركيبة المثلى..."):
                    try:
                        # مصفوفة التكلفة
                        c = [prices[ing] for ing in selected_ingredients]
                        
                        # قيود المساواة (المجموع 100%)
                        A_eq = [[1.0] * len(selected_ingredients)]
                        b_eq = [100.0]
                        
                        # قيد البروتين
                        protein_row = []
                        for ing in selected_ingredients:
                            found = False
                            for cat in feeds_library.values():
                                if ing in cat:
                                    protein_row.append(cat[ing]["CP"])
                                    found = True
                                    break
                            if not found:
                                protein_row.append(0.0)
                        
                        A_eq.append(protein_row)
                        b_eq.append(target_protein)
                        
                        # حدود المكونات
                        bounds = []
                        for ing in selected_ingredients:
                            found = False
                            for cat in feeds_library.values():
                                if ing in cat:
                                    bounds.append((cat[ing]["min"], cat[ing]["max"]))
                                    found = True
                                    break
                            if not found:
                                bounds.append((0.0, 100.0))
                        
                        result = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")
                        
                        if result.success:
                            st.success("✅ تم حساب التركيبة المثلى!")
                            
                            col_r1, col_r2 = st.columns(2)
                            with col_r1:
                                st.markdown("**📝 المقادير لكل طن:**")
                                for ing, pct in zip(selected_ingredients, result.x):
                                    if pct > 0.01:
                                        st.markdown(f"- {ing}: **{pct:.1f}%** ({pct*10:.1f} كجم)")
                            
                            with col_r2:
                                st.metric("💰 تكلفة الطن", f"${result.fun:.2f}")
                                st.metric("🧬 البروتين المحقق", f"{target_protein:.1f}%")
                            
                            # تخزين النتيجة للاستخدام في التبويبات الأخرى
                            st.session_state["last_formula"] = {ing: pct for ing, pct in zip(selected_ingredients, result.x) if pct > 0.01}
                            st.session_state["last_cost"] = result.fun
                        else:
                            st.error("❌ لم يتم إيجاد حل مناسب. حاول:")
                            st.markdown("""
                            - إضافة مكونات أكثر (خاصة مصادر البروتين)
                            - خفض نسبة البروتين المستهدفة قليلاً
                            - التأكد من صحة الأسعار المدخلة
                            """)
                    except Exception as e:
                        st.error(f"حدث خطأ أثناء الحساب: {str(e)}")
    
    with tab2:
        st.subheader("📊 إدارة المخزون")
        
        if "inventory" not in st.session_state:
            st.session_state["inventory"] = {}
            for cat in feeds_library.values():
                for name in cat:
                    st.session_state["inventory"][name] = 10.0
        
        # إضافة خصم تلقائي من آخر خلطة
        if "last_formula" in st.session_state and st.button("🔄 خصم مكونات آخر خلطة من المخزون"):
            tons = st.number_input("الكمية المنتجة (طن):", min_value=0.1, value=1.0, step=0.5)
            if st.button("تأكيد الخصم"):
                for name, pct in st.session_state["last_formula"].items():
                    if name in st.session_state["inventory"]:
                        consumed = (pct / 100) * tons
                        st.session_state["inventory"][name] -= consumed
                st.success(f"✅ تم خصم مكونات {tons} طن من المخزون")
                st.rerun()
        
        st.markdown("---")
        
        # عرض المخزون
        for name, qty in list(st.session_state["inventory"].items())[:20]:
            col1, col2 = st.columns([3, 1])
            with col1:
                status = "🔴" if qty < 5 else "🟢" if qty > 20 else "🟡"
                st.write(f"{status} **{name}**")
            with col2:
                if st.session_state["user_role"] == "owner":
                    st.session_state["inventory"][name] = st.number_input(
                        "طن", value=float(qty), key=f"inv_{name}", label_visibility="collapsed"
                    )
                else:
                    st.write(f"{qty:.1f} طن")
    
    with tab3:
        st.subheader("📖 دليل المستخدم")
        st.markdown("""
        ## 📚 منصة تاور العلمية للانتاج الحيواني وتركيب الاعلاف
        
        **المشرف العام:** الاختصاصي م. عبد القادر إسماعيل تاور
        
        ### 🔑 أكواد الدخول:
        | الكود | الصلاحية |
        |-------|----------|
        | `202687` | مالك المنصة (صلاحية كاملة) |
        | `2020` | مختص / طبيب بيطري |
        | `2026` | مربي (صلاحية محدودة) |
        
        ### 🎯 كيفية الاستخدام:
        1. اختر الدولة والمدينة لتحديد أسعار السوق
        2. اختر المكونات العلفية المتوفرة لديك
        3. حدد نسبة البروتين المستهدفة
        4. اضغط "تشغيل المحرك" للحصول على التركيبة المثلى
        
        ### 💡 نصائح مهمة:
        - كلما زاد عدد المكونات المختارة، كانت النتيجة أفضل
        - يفضل إضافة مصادر بروتين مثل (كسب فول الصويا، أمباز الفول)
        - يمكن تعديل الأسعار يدوياً حسب السوق المحلي
        
        ### 📞 للاستفسارات:
        """)
        
        if WHATSAPP_NUMBER and WHATSAPP_NUMBER != "":
            st.link_button("📱 تواصل عبر واتساب", f"https://wa.me/{WHATSAPP_NUMBER}")
        
        if GOOGLE_FORM_URL and GOOGLE_FORM_URL != "https://forms.gle/example":
            st.link_button("📝 تقديم اقتراح أو استشارة", GOOGLE_FORM_URL)
    
    # إرسال الكود للمالك
    if st.session_state["user_role"] == "owner" and SENDER_EMAIL:
        st.divider()
        col1, col2 = st.columns([3, 1])
        with col2:
            if st.button("📧 إرسال نسخة الكود إلى البريد", type="secondary"):
                with st.spinner("جاري الإرسال..."):
                    if send_code_to_mail(OWNER_EMAIL):
                        st.success("✅ تم إرسال الكود بنجاح إلى بريدك")
                    else:
                        st.error("❌ فشل الإرسال، تأكد من إعدادات البريد")

if __name__ == "__main__":
    main()
