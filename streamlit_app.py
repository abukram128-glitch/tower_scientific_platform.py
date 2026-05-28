import base64
import io
import os
import smtplib
import urllib.parse
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# محاولة استيراد المكتبات مع معالجة الأخطاء
ARABIC_SUPPORT = False
REPORTLAB_SUPPORT = False

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SUPPORT = True
except ImportError:
    pass

try:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas
    REPORTLAB_SUPPORT = True
except ImportError:
    pass

import numpy as np
import pandas as pd
import streamlit as st
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
# دوال معالجة العربية
# ==========================================

def fix_arabic_text(text):
    if not ARABIC_SUPPORT:
        return str(text)
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except:
        return str(text)

# ==========================================
# دوال توليد التقرير (بدون PDF إذا لزم الأمر)
# ==========================================

def generate_html_report(formula, target_protein, breed, cost, city, local_cost, local_sym, computed_se, mode_label):
    """توليد تقرير HTML بديل عن PDF"""
    html_content = f"""
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>تقرير منصة تاور العلمية</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .header {{ background-color: #2e7d32; color: white; padding: 20px; text-align: center; }}
            .content {{ padding: 20px; }}
            .formula-item {{ border-right: 3px solid #2e7d32; padding: 8px; margin: 5px 0; }}
            .footer {{ margin-top: 30px; font-size: 12px; text-align: center; color: gray; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>🌾 منصة تاور العلمية للانتاج الحيواني وتركيب الاعلاف</h2>
            <h3>الاختصاصي م. عبد القادر إسماعيل تاور</h3>
        </div>
        <div class="content">
            <p><strong>الموقع:</strong> {city}</p>
            <p><strong>الفصيل:</strong> {breed}</p>
            <p><strong>نظام الحساب:</strong> {mode_label}</p>
            <p><strong>البروتين المستهدف:</strong> {target_protein}%</p>
            <p><strong>معادل النشاء:</strong> {computed_se:.2f} وحدة</p>
            <p><strong>تكلفة الطن:</strong> ${cost:.2f} ({local_cost:,.2f} {local_sym})</p>
            
            <h3>المقادير الدقيقة:</h3>
    """
    for name, pct in formula.items():
        html_content += f'<div class="formula-item">▪️ {name}: {pct:.2f}% ({pct*10:.1f} كجم/طن)</div>'
    
    html_content += f"""
            <p><strong>تاريخ التقرير:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        <div class="footer">
            تم التوليد بواسطة منصة تاور العلمية © 2026
        </div>
    </body>
    </html>
    """
    return html_content

# ==========================================
# إدارة قاعدة البيانات
# ==========================================

@st.cache_resource
def init_database():
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
    
    cursor.execute("SELECT COUNT(*) FROM Ingredients")
    if cursor.fetchone()[0] == 0:
        seed_database(conn)
    
    conn.close()
    return True

def seed_database(conn):
    cursor = conn.cursor()
    
    library = {
        "🌾 الحبوب ومصادر الطاقة": {
            "ذرة صفراء": {"CP": 8.5, "lys": 0.24, "met": 0.17, "DC": 0.85, "SE": 80.0, "price": 230.0},
            "ذرة بيضاء": {"CP": 8.8, "lys": 0.23, "met": 0.16, "DC": 0.83, "SE": 78.0, "price": 225.0},
            "شعير مطحون": {"CP": 11.5, "lys": 0.36, "met": 0.19, "DC": 0.80, "SE": 71.0, "price": 210.0},
            "سورجم (فتريتة)": {"CP": 10.0, "lys": 0.22, "met": 0.15, "DC": 0.78, "SE": 70.0, "price": 195.0},
            "قمح": {"CP": 12.0, "lys": 0.32, "met": 0.21, "DC": 0.85, "SE": 75.0, "price": 240.0},
        },
        "🌱 الأكساب ومصادر البروتين": {
            "كسب فول صويا 44%": {"CP": 44.0, "lys": 2.70, "met": 0.62, "DC": 0.90, "SE": 74.0, "price": 440.0},
            "كسب فول صويا 48%": {"CP": 48.0, "lys": 2.90, "met": 0.67, "DC": 0.91, "SE": 76.0, "price": 480.0},
            "كسب عباد الشمس": {"CP": 36.0, "lys": 1.20, "met": 0.75, "DC": 0.76, "SE": 42.0, "price": 310.0},
            "أمباز الفول السوداني": {"CP": 46.0, "lys": 1.60, "met": 0.52, "DC": 0.88, "SE": 73.0, "price": 460.0},
            "كسب بذور القطن": {"CP": 41.0, "lys": 1.75, "met": 0.64, "DC": 0.78, "SE": 55.0, "price": 290.0},
        },
        "🧬 بروتين حيواني": {
            "مسحوق أسماك 60%": {"CP": 60.0, "lys": 4.50, "met": 1.65, "DC": 0.85, "SE": 65.0, "price": 850.0},
        },
        "🪨 أملاح ومعادن": {
            "ملح الطعام": {"CP": 0.0, "lys": 0.0, "met": 0.0, "DC": 0.0, "SE": 0.0, "price": 30.0},
            "الحجر الجيري": {"CP": 0.0, "lys": 0.0, "met": 0.0, "DC": 0.0, "SE": 0.0, "price": 40.0},
            "فوسفات ثنائي الكالسيوم": {"CP": 0.0, "lys": 0.0, "met": 0.0, "DC": 0.0, "SE": 0.0, "price": 280.0},
        },
        "🔬 إضافات": {
            "بريمكس دواجن": {"CP": 0.0, "lys": 0.0, "met": 0.0, "DC": 0.0, "SE": 0.0, "price": 230.0},
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
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        st.error("⚠️ يرجى إعداد الأسرار في Streamlit Cloud")
        return False
    
    try:
        msg = MIMEMultipart()
        msg["From"] = SENDER_EMAIL
        msg["To"] = receiver_email
        msg["Subject"] = "🌾 كود منصة تاور العلمية"
        
        body = f"""السلام عليكم،

هذا هو كود منصة تاور العلمية للانتاج الحيواني وتركيب الاعلاف.

تاريخ الإرسال: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

تم إنشاء هذا التقرير بواسطة المنصة.

تحياتي،
الاختصاصي م. عبد القادر إسماعيل تاور"""
        
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        st.error(f"فشل الإرسال: {str(e)}")
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
    
    # تحذيرات حول المكتبات المفقودة
    if not ARABIC_SUPPORT:
        st.info("ℹ️ النصوص العربية تعرض بشكل مبسط (مكتبة إضافية للتنسيق غير متوفرة)")
    
    if not REPORTLAB_SUPPORT:
        st.info("ℹ️ تقارير PDF غير متوفرة، سيتم استخدام تقارير HTML بديلة")
    
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
        st.markdown("""
        <div style="text-align: center; padding: 50px;">
            <h1 style="color: #2e7d32;">🔒 منصة تاور العلمية</h1>
            <h3 style="color: #555;">للانتاج الحيواني وتركيب الاعلاف</h3>
            <p style="color: #888;">الاختصاصي م. عبد القادر إسماعيل تاور</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.container():
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                input_code = st.text_input("كود الدخول:", type="password", placeholder="أدخل الكود هنا")
                if st.button("تسجيل الدخول", type="primary", use_container_width=True):
                    if input_code in CODES_DB:
                        st.session_state["approved"] = True
                        st.session_state["user_role"] = CODES_DB[input_code]
                        st.rerun()
                    else:
                        st.error("❌ الكود غير صحيح")
        st.stop()
    
    # الشريط الجانبي
    role_name = {
        "owner": "المالك (صلاحية كاملة) 👑",
        "specialist": "المختص / الطبيب البيطري 👨‍🔬",
        "breeder": "المربي 🌾"
    }[st.session_state["user_role"]]
    
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/000000/chicken--v1.png", width=80)
        st.success(f"مرحباً {role_name}")
        st.markdown("---")
        
        if st.button("🚪 تسجيل الخروج", use_container_width=True):
            st.session_state["approved"] = False
            st.rerun()
        
        st.markdown("---")
        st.caption(f"© 2026 منصة تاور العلمية")
        st.caption("الاختصاصي م. عبد القادر إسماعيل تاور")
    
    # تحميل البيانات
    feeds_library = load_feeds_from_db()
    
    # العنوان الرئيسي
    st.title("🌾 منصة تاور العلمية للانتاج الحيواني وتركيب الاعلاف")
    st.markdown("---")
    
    # تبويبات
    tab1, tab2, tab3, tab4 = st.tabs(["🔬 تركيب الأعلاف", "📊 إدارة المخزون", "📈 التقارير", "📖 المساعدة"])
    
    with tab1:
        st.subheader("🎯 نظام تركيب الأعلاف الذكي (أقل تكلفة)")
        
        col1, col2 = st.columns(2)
        with col1:
            country = st.selectbox("🇸🇦 الدولة:", ["السودان", "مصر", "ليبيا", "السعودية", "الإمارات", "قطر", "الكويت", "عمان", "البحرين", "اليمن", "فلسطين", "الأردن", "العراق", "لبنان", "سوريا", "تونس", "الجزائر", "المغرب", "موريتانيا", "جيبوتي", "الصومال", "جزر القمر"])
        with col2:
            city = st.text_input("📍 المدينة:", "الخرطوم", placeholder="مثال: الخرطوم، طرابلس، الرياض")
        
        st.markdown("#### 📦 اختر مكونات العلف:")
        
        selected_ingredients = []
        prices = {}
        
        for cat_name, items in feeds_library.items():
            with st.expander(f"📁 {cat_name}", expanded="الحبوب" in cat_name or "بروتين" in cat_name):
                cols = st.columns(3)
                for idx, (name, data) in enumerate(items.items()):
                    with cols[idx % 3]:
                        default_selected = name in ["ذرة صفراء", "كسب فول صويا 44%", "ملح الطعام", "الحجر الجيري"]
                        if st.checkbox(name, value=default_selected, key=f"sel_{name}"):
                            selected_ingredients.append(name)
                            prices[name] = st.number_input(
                                f"💰 سعر {name} ($/طن)",
                                value=float(data["price"]),
                                key=f"price_{name}",
                                step=5.0
                            )
        
        col1, col2 = st.columns(2)
        with col1:
            target_protein = st.slider("🎯 نسبة البروتين المستهدفة (%)", 5.0, 40.0, 16.0, 0.5)
        with col2:
            use_digestible = st.toggle("🧬 استخدام البروتين المهضوم (DP)", value=True, help="البروتين المهضوم يعطي دقة أكبر في التغذية")
        
        if st.button("🚀 تشغيل محرك الاستمثال الخطي", type="primary", use_container_width=True):
            if len(selected_ingredients) < 2:
                st.warning("⚠️ يرجى اختيار مكونين على الأقل (مثلاً: ذرة + كسب صويا)")
            else:
                with st.spinner("🧮 جاري حساب التركيبة المثلى..."):
                    try:
                        # مصفوفة التكلفة
                        c = [prices[ing] for ing in selected_ingredients]
                        
                        # قيد المجموع الكلي = 100%
                        A_eq = [[1.0] * len(selected_ingredients)]
                        b_eq = [100.0]
                        
                        # قيد البروتين
                        protein_row = []
                        for ing in selected_ingredients:
                            found = False
                            for cat in feeds_library.values():
                                if ing in cat:
                                    cp = cat[ing]["CP"]
                                    dc = cat[ing]["DC"] if use_digestible else 1.0
                                    protein_row.append(cp * dc)
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
                            st.balloons()
                            st.success("✅ تم حساب التركيبة المثلى بنجاح!")
                            
                            col_r1, col_r2 = st.columns(2)
                            
                            with col_r1:
                                st.markdown("### 📝 المقادير لكل طن:")
                                formula = {}
                                for ing, pct in zip(selected_ingredients, result.x):
                                    if pct > 0.01:
                                        formula[ing] = pct
                                        st.markdown(f"""
                                        <div style="background-color: #f0f8f0; padding: 8px 15px; margin: 5px 0; border-radius: 8px; border-right: 4px solid #2e7d32;">
                                            <b>{ing}</b>: {pct:.1f}% → <b>{pct*10:.1f} كجم</b> لكل طن
                                        </div>
                                        """, unsafe_allow_html=True)
                                
                                st.session_state["last_formula"] = formula
                            
                            with col_r2:
                                st.markdown("### 💰 التكلفة والجودة:")
                                st.metric("💰 تكلفة الطن الواحد", f"${result.fun:.2f}")
                                st.metric("🧬 البروتين المحقق", f"{target_protein:.1f}%")
                                
                                # حساب معادل النشاء التقريبي
                                se_total = 0
                                for ing, pct in zip(selected_ingredients, result.x):
                                    if pct > 0.01:
                                        for cat in feeds_library.values():
                                            if ing in cat:
                                                se_total += (pct / 100) * cat[ing]["SE"]
                                                break
                                st.metric("🌽 معادل النشاء (SE)", f"{se_total:.1f} وحدة")
                            
                            # حفظ النتائج للتقارير
                            st.session_state["last_cost"] = result.fun
                            st.session_state["last_protein"] = target_protein
                            st.session_state["last_se"] = se_total
                            st.session_state["last_city"] = city
                            
                        else:
                            st.error("❌ لم يتم إيجاد حل مناسب")
                            st.markdown("""
                            ### 💡 اقتراحات لحل المشكلة:
                            1. **أضف المزيد من المكونات** - خاصة مصادر البروتين (كسب صويا، أمباز فول)
                            2. **خفف نسبة البروتين** - جرب خفضها بمقدار 1-2%
                            3. **تأكد من الأسعار** - الأسعار المنخفضة جداً قد تسبب مشاكل
                            4. **أضف مكونات جديدة** - مثل كسب عباد الشمس أو كسب بذور القطن
                            """)
                    except Exception as e:
                        st.error(f"حدث خطأ تقني: {str(e)}")
    
    with tab2:
        st.subheader("📊 إدارة المخزون والمستودعات")
        
        if "inventory" not in st.session_state:
            st.session_state["inventory"] = {}
            for cat in feeds_library.values():
                for name in cat:
                    st.session_state["inventory"][name] = 10.0
        
        # خصم تلقائي
        if "last_formula" in st.session_state and st.session_state["last_formula"]:
            with st.expander("🔄 خصم مكونات آخر خلطة من المخزون", expanded=True):
                tons = st.number_input("الكمية المنتجة (بالطن):", min_value=0.1, value=1.0, step=0.5)
                if st.button("تأكيد الخصم", type="primary"):
                    for name, pct in st.session_state["last_formula"].items():
                        if name in st.session_state["inventory"]:
                            consumed = (pct / 100) * tons
                            st.session_state["inventory"][name] = max(0, st.session_state["inventory"][name] - consumed)
                    st.success(f"✅ تم خصم {tons} طن من المخزون")
                    st.rerun()
        
        st.markdown("---")
        st.markdown("### 📦 أرصدة المخزون الحالية:")
        
        # عرض المخزون بشكل منظم
        cols = st.columns(3)
        idx = 0
        for name, qty in sorted(st.session_state["inventory"].items())[:30]:
            with cols[idx % 3]:
                if qty < 2:
                    status = "🔴 حرج"
                    color = "#ffebee"
                elif qty < 10:
                    status = "🟡 منخفض"
                    color = "#fff3e0"
                else:
                    status = "🟢 جيد"
                    color = "#e8f5e9"
                
                if st.session_state["user_role"] == "owner":
                    new_qty = st.number_input(
                        f"{name}",
                        value=float(qty),
                        key=f"inv_{name}",
                        step=1.0,
                        label_visibility="collapsed"
                    )
                    st.session_state["inventory"][name] = new_qty
                    st.caption(f"الحالة: {status}")
                else:
                    st.markdown(f"""
                    <div style="background-color: {color}; padding: 8px 12px; margin: 4px 0; border-radius: 8px;">
                        <b>{name}</b><br>
                        <span style="font-size: 18px; font-weight: bold;">{qty:.1f} طن</span><br>
                        <span style="font-size: 12px;">{status}</span>
                    </div>
                    """, unsafe_allow_html=True)
            idx += 1
    
    with tab3:
        st.subheader("📈 التقارير والتحليلات")
        
        if "last_formula" in st.session_state and st.session_state["last_formula"]:
            st.markdown("### آخر خلطة تم تركيبها:")
            
            mode_label = "بروتين مهضوم (DP)" if use_digestible else "بروتين خام"
            
            # عرض التقرير
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""
                **📍 الموقع:** {st.session_state.get('last_city', 'غير محدد')}
                
                **🧬 البروتين المستهدف:** {st.session_state.get('last_protein', 0):.1f}%
                
                **🌽 معادل النشاء:** {st.session_state.get('last_se', 0):.1f} وحدة
                
                **💰 تكلفة الطن:** ${st.session_state.get('last_cost', 0):.2f}
                
                **📋 نظام الحساب:** {mode_label}
                """)
            
            # تصدير التقرير
            st.markdown("---")
            st.markdown("### 📎 تصدير التقرير")
            
            # تقرير HTML
            html_report = generate_html_report(
                st.session_state["last_formula"],
                st.session_state.get('last_protein', 0),
                "سلالة عامة",
                st.session_state.get('last_cost', 0),
                st.session_state.get('last_city', 'غير محدد'),
                st.session_state.get('last_cost', 0) * 600,
                "SDG",
                st.session_state.get('last_se', 0),
                mode_label
            )
            
            st.download_button(
                label="📄 تحميل التقرير (HTML)",
                data=html_report,
                file_name=f"tower_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
                mime="text/html",
                use_container_width=True
            )
            
            # مشاركة عبر واتساب
            share_msg = f"🌾 منصة تاور العلمية\nالخلطة العلفية بتكلفة ${st.session_state.get('last_cost', 0):.2f}/طن\nالبروتين: {st.session_state.get('last_protein', 0)}%"
            share_url = f"https://wa.me/?text={urllib.parse.quote(share_msg)}"
            st.link_button("📱 مشاركة النتيجة عبر واتساب", share_url, use_container_width=True)
            
        else:
            st.info("ℹ️ قم بتركيب علفة أولاً في تبويب 'تركيب الأعلاف' لتظهر التقارير هنا")
    
    with tab4:
        st.subheader("📖 دليل المستخدم")
        
        st.markdown("""
        ## 🌾 منصة تاور العلمية للانتاج الحيواني وتركيب الاعلاف
        
        ### 👨‍🔬 المشرف العام
        **الاختصاصي م. عبد القادر إسماعيل تاور**
        
        ---
        
        ### 🔑 أكواد الدخول والصلاحيات
        
        | الكود | الصلاحية | الميزات |
        |-------|----------|---------|
        | `202687` | مالك المنصة | صلاحية كاملة - تعديل الأسعار والمخزون |
        | `2020` | مختص / طبيب بيطري | صلاحية متقدمة - تركيب ومشاهدة |
        | `2026` | مربي | صلاحية أساسية - تركيب فقط |
        
        ---
        
        ### 🎯 كيفية استخدام المنصة
        
        #### الخطوة 1: اختيار الموقع
        - اختر الدولة والمدينة لتحديد أسعار السوق
        - الأسعار يتم تحديثها حسب المنطقة
        
        #### الخطوة 2: اختيار المكونات
        - اختر المواد العلفية المتوفرة لديك
        - يفضل اختيار 4-6 مكونات للحصول على أفضل نتيجة
        - المكونات الأساسية الموصى بها:
          - مصدر طاقة: ذرة، شعير، سورجم
          - مصدر بروتين: كسب صويا، أمباز فول، كسب عباد شمس
        
        #### الخطوة 3: تحديد المواصفات
        - حدد نسبة البروتين المستهدفة
        - اختر استخدام البروتين المهضوم (DP) للدقة العالية
        
        #### الخطوة 4: تشغيل المحرك
        - اضغط على زر "تشغيل محرك الاستمثال الخطي"
        - سيتم حساب التركيبة الأقل تكلفة التي تحقق المواصفات
        
        ---
        
        ### 💡 نصائح مهمة
        
        1. **كلما زاد عدد المكونات**، كانت النتيجة أفضل وتكلفة أقل
        2. **تأكد من صحة الأسعار** المدخلة للحصول على تكلفة حقيقية
        3. **استخدم البروتين المهضوم (DP)** للحصول على دقة علمية أعلى
        4. **يمكنك تعديل المخزون** في تبويب "إدارة المخزون"
        
        ---
        
        ### 📞 للاستفسارات والدعم الفني
        """)
        
        if WHATSAPP_NUMBER and WHATSAPP_NUMBER != "" and WHATSAPP_NUMBER != "+249123533489":
            st.link_button("📱 تواصل عبر واتساب", f"https://wa.me/{WHATSAPP_NUMBER}", use_container_width=True)
        else:
            st.info("📱 سيتم إضافة رقم واتساب للتواصل قريباً")
        
        if GOOGLE_FORM_URL and GOOGLE_FORM_URL != "https://forms.gle/example":
            st.link_button("📝 تقديم استشارة أو اقتراح", GOOGLE_FORM_URL, use_container_width=True)
        
        st.markdown("---")
        st.caption("© 2026 منصة تاور العلمية للانتاج الحيواني وتركيب الاعلاف")
        st.caption("جميع الحقوق محفوظة - الاختصاصي م. عبد القادر إسماعيل تاور")
    
    # إرسال الكود للمالك
    if st.session_state["user_role"] == "owner" and SENDER_EMAIL:
        st.divider()
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("📧 إرسال نسخة الكود إلى البريد الإلكتروني", use_container_width=True):
                with st.spinner("جاري إرسال الكود..."):
                    if send_code_to_mail(OWNER_EMAIL):
                        st.success(f"✅ تم إرسال الكود بنجاح إلى {OWNER_EMAIL}")
                    else:
                        st.error("❌ فشل الإرسال - تأكد من إعدادات البريد في Secrets")

if __name__ == "__main__":
    main()
