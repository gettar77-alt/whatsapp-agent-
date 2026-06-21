import requests
import config

GRAPH_URL = f"https://graph.facebook.com/v20.0/{config.WHATSAPP_PHONE_ID}/messages"
HEADERS = {
    "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
    "Content-Type": "application/json",
}


def send_message(to: str, text: str) -> bool:
    """إرسال رسالة نصية عبر WhatsApp Cloud API."""
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        r = requests.post(GRAPH_URL, headers=HEADERS, json=payload, timeout=15)
        return r.status_code == 200
    except Exception:
        return False


def notify_owner(phone: str, message: str):
    """إشعار المالك فوراً عند طلب تحويل بشري."""
    if not config.OWNER_PHONE:
        return
    text = f"تنبيه من مها\nعميل يطلب التحدث مع شخص\nالرقم: {phone}\nرسالته: {message}"
    send_message(config.OWNER_PHONE, text)


def extract_message(data: dict):
    """
    يستخرج (phone, text, msg_type) من webhook payload.
    msg_type: 'text' أو 'media' (صور/فيديو/صوت)
    يُعيد None إذا ما فيه رسالة.
    """
    try:
        value = data["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return None
        msg = value["messages"][0]
        phone = msg["from"]
        msg_type = msg["type"]

        if msg_type == "text":
            return phone, msg["text"]["body"], "text"

        # صور أو فيديو أو صوت — نرد برسالة موحدة
        if msg_type in ("image", "video", "audio", "document", "sticker"):
            return phone, None, "media"

        return None
    except (KeyError, IndexError):
        return None


def is_blacklisted(phone: str) -> bool:
    """يتحقق إذا الرقم في قائمة المعارف الشخصيين."""
    try:
        with open(config.BLACKLIST_FILE, encoding="utf-8") as f:
            numbers = {line.strip() for line in f if line.strip()}
        return phone in numbers
    except FileNotFoundError:
        return False
