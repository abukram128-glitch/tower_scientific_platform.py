# ============================================================================
# 📲 tawor_webhook.py — إشعارات WhatsApp (Twilio + Meta Cloud API)
# ============================================================================
import os
import json
import urllib.parse
import urllib.request
import base64
from typing import Tuple, Optional


class WhatsAppNotifier:
    """
    دعم مزوّدَي واتساب:
      1) Twilio WhatsApp  → TWILIO_ACCOUNT_SID / AUTH_TOKEN / FROM
      2) Meta Cloud API   → META_PHONE_ID / META_ACCESS_TOKEN
    """

    def __init__(self):
        # Twilio
        self.twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.twilio_from = os.getenv("TWILIO_WHATSAPP_FROM",
                                      "whatsapp:+14155238886")
        # Meta
        self.meta_phone_id = os.getenv("META_PHONE_ID")
        self.meta_token = os.getenv("META_ACCESS_TOKEN")

        self.provider = None
        if self.twilio_sid and self.twilio_token:
            self.provider = "twilio"
        elif self.meta_phone_id and self.meta_token:
            self.provider = "meta"

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    # ────────────────────────────────────────────────
    # Twilio
    # ────────────────────────────────────────────────
    def _send_twilio(self, to: str, body: str,
                      media_url: Optional[str] = None) -> Tuple[bool, str]:
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"
        url = (f"https://api.twilio.com/2010-04-01/Accounts/"
               f"{self.twilio_sid}/Messages.json")
        data = {"From": self.twilio_from, "To": to, "Body": body}
        if media_url:
            data["MediaUrl"] = media_url
        encoded = urllib.parse.urlencode(data).encode()
        auth = base64.b64encode(
            f"{self.twilio_sid}:{self.twilio_token}".encode()).decode()
        req = urllib.request.Request(url, data=encoded, method="POST")
        req.add_header("Authorization", f"Basic {auth}")
        req.add_header("Content-Type",
                        "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201):
                    return True, "✅ أُرسلت عبر Twilio"
                return False, f"❌ {resp.status}"
        except Exception as e:
            return False, f"❌ {e}"

    # ────────────────────────────────────────────────
    # Meta Cloud API
    # ────────────────────────────────────────────────
    def _send_meta(self, to: str, body: str) -> Tuple[bool, str]:
        if to.startswith("whatsapp:"):
            to = to.replace("whatsapp:", "")
        to = to.replace("+", "").replace(" ", "")
        url = (f"https://graph.facebook.com/v18.0/"
               f"{self.meta_phone_id}/messages")
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body, "preview_url": False},
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {self.meta_token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201):
                    return True, "✅ أُرسلت عبر Meta"
                return False, f"❌ {resp.status}"
        except Exception as e:
            return False, f"❌ {e}"

    # ────────────────────────────────────────────────
    # الواجهة العامة
    # ────────────────────────────────────────────────
    def send_text(self, to: str, body: str) -> Tuple[bool, str]:
        if not self.enabled:
            return False, "⚠️ لم يتم تهيئة مزوّد واتساب"
        if self.provider == "twilio":
            return self._send_twilio(to, body)
        return self._send_meta(to, body)

    def send_formula(self, to: str, result: dict,
                      requester: str = "") -> Tuple[bool, str]:
        formula_lines = "\n".join(
            f"• {k}: {v:.2f}%" for k, v in
            result.get("formula", {}).items())
        msg = (
            f"🌾 *تاور نولجي — خلطة علفية*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🐾 {result.get('animal_type','')} — "
            f"{result.get('stage','')}\n"
            f"👤 {requester or 'غير محدد'}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 ${result.get('cost_per_ton',0):.2f}/طن\n"
            f"📊 DP: {result.get('totals',{}).get('DP',0):.2f}% | "
            f"SE: {result.get('totals',{}).get('SE',0):.2f}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"*المكونات:*\n{formula_lines}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🌐 الاختصاصي م. عبد القادر إسماعيل تاور"
        )
        return self.send_text(to, msg)


# ─── اختبار سريع ───
if __name__ == "__main__":
    n = WhatsAppNotifier()
    print(f"Provider: {n.provider or 'غير مُهيّأ'}")
    if n.enabled:
        ok, msg = n.send_text(os.getenv("TEST_PHONE", "+249123533489"),
                                "🧪 اختبار تاور نولجي")
        print(msg)
