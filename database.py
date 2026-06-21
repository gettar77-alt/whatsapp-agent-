"""
database.py
-----------
كل ما يخص حفظ واسترجاع المحادثات من قاعدة بيانات SQLite.

SQLite قاعدة بيانات مدمجة في بايثون: عبارة عن ملف واحد (conversations.db)
لا تحتاج خادماً منفصلاً. نحفظ فيها كل رسالة مع رقم جوال العميل ووقتها،
ثم نسترجع آخر عدد من الرسائل لنرسلها لـ Claude ليفهم سياق المحادثة.
"""

import sqlite3
from datetime import datetime
from contextlib import closing

import config


def _connect():
    """فتح اتصال بقاعدة البيانات (ملف conversations.db)."""
    return sqlite3.connect(config.DATABASE_FILE)


def init_db():
    """
    إنشاء قاعدة البيانات وجدول الرسائل إذا لم يكونا موجودين.
    آمن تماماً: لو الجدول موجود مسبقاً لا يحدث شيء.
    نستدعي هذه الدالة مرة واحدة عند بدء التشغيل.
    """
    with closing(_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                phone      TEXT NOT NULL,   -- رقم جوال العميل (يميّز كل محادثة)
                role       TEXT NOT NULL,   -- 'user' للوارد، 'assistant' للصادر
                content    TEXT NOT NULL,   -- نص الرسالة
                created_at TEXT NOT NULL    -- وقت الرسالة
            )
            """
        )
        # فهرس على رقم الجوال لتسريع استرجاع محادثة عميل معيّن
        conn.execute("CREATE INDEX IF NOT EXISTS idx_phone ON messages(phone)")
        conn.commit()


def save_message(phone: str, role: str, content: str):
    """
    حفظ رسالة واحدة في قاعدة البيانات.
    phone   : رقم جوال العميل.
    role    : 'user' (رسالة من العميل) أو 'assistant' (رد البوت).
    content : نص الرسالة.
    """
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO messages (phone, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (phone, role, content, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()


def get_history(phone: str, limit: int):
    """
    استرجاع آخر (limit) رسالة لعميل معيّن، مرتبة من الأقدم إلى الأحدث،
    بالشكل الذي يفهمه Claude: قائمة من {"role": ..., "content": ...}.
    """
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages "
            "WHERE phone = ? ORDER BY id DESC LIMIT ?",
            (phone, limit),
        ).fetchall()

    # جلبناها من الأحدث للأقدم (DESC) لأخذ آخر عدد، نعكسها لتعود بالترتيب الزمني
    rows.reverse()
    return [{"role": role, "content": content} for role, content in rows]


def clear_history(phone: str):
    """حذف كامل محادثة عميل معيّن."""
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM messages WHERE phone = ?", (phone,))
        conn.commit()


def get_all_conversations() -> list:
    """جلب كل المحادثات مجمّعة حسب رقم العميل لصفحة الإدارة."""
    with closing(_connect()) as conn:
        phones = conn.execute(
            "SELECT DISTINCT phone, MAX(created_at) as last_msg "
            "FROM messages WHERE phone NOT LIKE 'demo-%' AND phone != 'test-cli-user' "
            "GROUP BY phone ORDER BY last_msg DESC"
        ).fetchall()

        result = []
        for phone, last_msg in phones:
            msgs = conn.execute(
                "SELECT role, content, created_at FROM messages "
                "WHERE phone = ? ORDER BY id DESC LIMIT 20",
                (phone,)
            ).fetchall()
            msgs.reverse()
            result.append({
                "phone": phone,
                "last_msg": last_msg,
                "messages": [{"role": r, "content": c, "time": t} for r, c, t in msgs]
            })
    return result
