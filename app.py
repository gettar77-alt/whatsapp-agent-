import json
import os
from datetime import datetime
from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import config
import database
import whatsapp
from claude_client import get_reply

app = Flask(__name__)
app.secret_key = config.ADMIN_PASSWORD + "_secret"

# إنشاء قاعدة البيانات عند تحميل التطبيق (يعمل مع gunicorn وأيضاً التشغيل اليدوي)
database.init_db()

HANDOFF_KEYWORDS = ["أوصل لك أحد", "من الفريق", "يتواصل معك"]
MEDIA_REPLY = "ما أقدر أشوف الصور أو الملفات، بس قدر أساعدك بالكلام. وش تحتاج"


def _load_apartments():
    with open(config.APARTMENTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_apartments(data):
    with open(config.APARTMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _log_handoff(phone: str, message: str):
    os.makedirs(config.LOG_DIR, exist_ok=True)
    with open(config.HANDOFF_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {phone}: {message}\n")


# =============================
#  الموقع التسويقي
# =============================

@app.route("/")
def website():
    return render_template("website.html")


@app.route("/demo")
def demo():
    return render_template("demo.html")


# =============================
#  API الشات التجريبي
# =============================

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    user_text = (data.get("message") or "").strip()
    session_id = (data.get("session") or "demo-web-user").strip()

    if not user_text:
        return jsonify({"reply": ""}), 400

    database.save_message(session_id, "user", user_text)
    history = database.get_history(session_id, config.HISTORY_LIMIT)

    try:
        reply = get_reply(history)
    except Exception:
        reply = "عذراً، حدث خطأ مؤقت. حاول مرة ثانية."

    database.save_message(session_id, "assistant", reply)
    return jsonify({"reply": reply, "length": len(reply)})


@app.route("/reset", methods=["POST"])
def reset():
    data = request.get_json(force=True)
    session_id = (data.get("session") or "demo-web-user").strip()
    database.clear_history(session_id)
    return jsonify({"ok": True})


# =============================
#  WhatsApp Cloud API Webhook
# =============================

@app.route("/webhook", methods=["GET"])
def webhook_verify():
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN:
        return challenge, 200
    return "Forbidden", 403


@app.route("/webhook", methods=["POST"])
def webhook_receive():
    data   = request.get_json(force=True, silent=True) or {}
    result = whatsapp.extract_message(data)

    if not result:
        return "", 200

    phone, user_text, msg_type = result

    # تجاهل المعارف الشخصيين
    if whatsapp.is_blacklisted(phone):
        return "", 200

    # رسائل الوسائط (صور/فيديو/صوت)
    if msg_type == "media":
        whatsapp.send_message(phone, MEDIA_REPLY)
        return "", 200

    database.save_message(phone, "user", user_text)
    history = database.get_history(phone, config.HISTORY_LIMIT)

    try:
        reply = get_reply(history)
    except Exception:
        reply = "عذراً، في مشكلة مؤقتة. حاول بعد شوي."

    database.save_message(phone, "assistant", reply)

    # تسجيل وإشعار التحويل البشري
    if any(kw in reply for kw in HANDOFF_KEYWORDS):
        _log_handoff(phone, user_text)
        whatsapp.notify_owner(phone, user_text)

    whatsapp.send_message(phone, reply)
    return "", 200


# =============================
#  لوحة الإدارة
# =============================

@app.route("/admin", methods=["GET", "POST"])
def admin():
    error = None
    if request.method == "POST" and "password" in request.form:
        if request.form["password"] == config.ADMIN_PASSWORD:
            session["admin"] = True
        else:
            error = "كلمة السر غلط"
    if not session.get("admin"):
        return render_template("admin_login.html", error=error)
    data = _load_apartments()
    return render_template("admin.html", units=data["الوحدات"])


@app.route("/admin/conversations")
def admin_conversations():
    if not session.get("admin"):
        return redirect(url_for("admin"))
    convs = database.get_all_conversations()
    return render_template("admin_conversations.html", conversations=convs)


@app.route("/admin/update-prices", methods=["POST"])
def admin_update_prices():
    if not session.get("admin"):
        return redirect(url_for("admin"))
    unit_idx     = int(request.form["unit"])
    weekday      = request.form.get("weekday", "").strip()
    weekend      = request.form.get("weekend", "").strip()
    deposit      = request.form.get("deposit", "").strip()
    data = _load_apartments()
    unit = data["الوحدات"][unit_idx]
    if weekday.isdigit():
        unit["السعر_أيام_الأسبوع"]    = int(weekday)
        unit["السعر_يبدأ_من_بالريال"] = int(weekday)
    if weekend.isdigit():
        unit["السعر_الويكند"] = int(weekend)
    if deposit.isdigit():
        unit["مبلغ_التأمين_بالريال"] = int(deposit)
    _save_apartments(data)
    return redirect(url_for("admin"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin"))


@app.route("/admin/add", methods=["POST"])
def admin_add():
    if not session.get("admin"):
        return redirect(url_for("admin"))
    unit_idx  = int(request.form["unit"])
    date_from = request.form["date_from"]
    date_to   = request.form["date_to"]
    if date_from and date_to and date_from <= date_to:
        data = _load_apartments()
        data["الوحدات"][unit_idx]["الفترات_المقفلة"].append(
            {"من": date_from, "إلى": date_to}
        )
        _save_apartments(data)
    return redirect(url_for("admin"))


@app.route("/admin/delete", methods=["POST"])
def admin_delete():
    if not session.get("admin"):
        return redirect(url_for("admin"))
    unit_idx   = int(request.form["unit"])
    period_idx = int(request.form["period"])
    data = _load_apartments()
    periods = data["الوحدات"][unit_idx]["الفترات_المقفلة"]
    if 0 <= period_idx < len(periods):
        periods.pop(period_idx)
    _save_apartments(data)
    return redirect(url_for("admin"))


if __name__ == "__main__":
    database.init_db()
    print("الخادم:   http://127.0.0.1:5000")
    print("الإدارة: http://127.0.0.1:5000/admin")
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, debug=debug_mode)
