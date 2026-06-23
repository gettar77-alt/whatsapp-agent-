import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"الإعداد '{key}' غير موجود في ملف .env — تأكد من إضافته."
        )
    return value


# ===== مفاتيح مطلوبة =====
ANTHROPIC_API_KEY   = _require("ANTHROPIC_API_KEY")
WHATSAPP_TOKEN      = _require("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID   = _require("WHATSAPP_PHONE_ID")
WHATSAPP_VERIFY_TOKEN = _require("WHATSAPP_VERIFY_TOKEN")

# ===== إعدادات اختيارية =====
ADMIN_PASSWORD      = os.getenv("ADMIN_PASSWORD", "admin1234")
OWNER_PHONE         = os.getenv("OWNER_PHONE", "")   # رقم المالك لاستقبال إشعارات التحويل
CLAUDE_MODEL        = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
HISTORY_LIMIT       = int(os.getenv("HISTORY_LIMIT", "20"))
CLAUDE_TEMPERATURE  = float(os.getenv("CLAUDE_TEMPERATURE", "0.6"))
CLAUDE_MAX_TOKENS   = int(os.getenv("CLAUDE_MAX_TOKENS", "1024"))

# اعتبار العميل "راجع" لو رجع بعد هذا العدد من الساعات من آخر نشاط
RETURNING_GAP_HOURS = float(os.getenv("RETURNING_GAP_HOURS", "3"))
# المتابعة لو سكت العميل: نطاق الصمت (بالساعات) اللي نرسل فيه رسالة تذكير
FOLLOWUP_MIN_HOURS  = float(os.getenv("FOLLOWUP_MIN_HOURS", "3"))
FOLLOWUP_MAX_HOURS  = float(os.getenv("FOLLOWUP_MAX_HOURS", "24"))

# ===== مسارات الملفات =====
BASE_DIR            = os.path.dirname(os.path.abspath(__file__))
SYSTEM_PROMPT_FILE  = os.path.join(BASE_DIR, "system_prompt.txt")
APARTMENTS_FILE     = os.path.join(BASE_DIR, "apartments.json")
DATABASE_FILE       = os.path.join(BASE_DIR, "conversations.db")
LOG_DIR             = os.path.join(BASE_DIR, "logs")
HANDOFF_LOG_FILE    = os.path.join(LOG_DIR, "handoff_log.txt")
BLACKLIST_FILE      = os.path.join(BASE_DIR, "personal_contacts.txt")
