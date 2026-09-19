# ============================================================================
# 🐳 Dockerfile — Tawornology v19.5 (Streamlit + API)
# ============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# ─── تبعيات النظام ───
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl git \
    libglib2.0-0 libsm6 libxext6 libxrender1 \
    libpq-dev libgl1 \
    fonts-dejavu fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# ─── مجلد العمل ───
WORKDIR /app

# ─── متطلبات Python ───
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─── نسخ الكود ───
COPY . .

# ─── الخط العربي للـ PDF ───
RUN curl -fsSL -o /app/Amiri-Regular.ttf \
    https://raw.githubusercontent.com/aliftype/amiri/master/fonts/Amiri-Regular.ttf \
    || echo "⚠️ فشل تحميل الخط"

# ─── المجلدات الدائمة ───
RUN mkdir -p /app/tawor_user_data /app/logs

# ─── المنافذ: 8501 Streamlit + 8502 API ───
EXPOSE 8501 8502

# ─── سكربت التشغيل ───
COPY docker-start.sh /app/docker-start.sh
RUN chmod +x /app/docker-start.sh

CMD ["/app/docker-start.sh"]
