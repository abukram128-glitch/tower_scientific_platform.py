#!/bin/bash
# ============================================================================
# 🚀 تشغيل Streamlit + FastAPI في نفس الحاوية
# ============================================================================
set -e

echo "🌾 بدء تاور نولجي v19.5..."

# ─── متغيرات افتراضية ───
export TAWOR_JWT_SECRET="${TAWOR_JWT_SECRET:-$(python -c 'import secrets; print(secrets.token_urlsafe(64))')}"
export TAWOR_DB_PATH="${TAWOR_DB_PATH:-/app/tawor_user_data/tawor_api.db}"

# ─── إنشاء مجلد السجلات ───
mkdir -p /app/logs /app/tawor_user_data

# ─── تشغيل API في الخلفية ───
echo "🌐 تشغيل API على :8502 ..."
uvicorn tawor_api:app \
    --host 0.0.0.0 --port 8502 \
    --workers 2 \
    --log-level info \
    > /app/logs/api.log 2>&1 &
API_PID=$!

# ─── الانتظار حتى يجهز API ───
sleep 4
curl -sf http://localhost:8502/health > /dev/null \
    && echo "✅ API جاهز" \
    || echo "⚠️ تحذير: API لم يستجب بعد"

# ─── تشغيل Streamlit ───
echo "🌾 تشغيل Streamlit على :8501 ..."
exec streamlit run tawornology_main.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.fileWatcherType none \
    --browser.gatherUsageStats false
