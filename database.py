"""
database.py
-----------
كل ما يخص حفظ واسترجاع المحادثات من قاعدة بيانات SQLite.

SQLite قاعدة بيانات مدمجة في بايثون: عبارة عن ملف واحد (conversations.db)
لا تحتاج خادماً منفصلاً. نحفظ فيها كل رسالة مع رقم جوال العميل ووقتها،
ثم نسترجع آخر عدد من الرسائل لنرسلها لـ Claude ليفهم سياق المحادثة.
"""

import sqlite3
from datetime import datetime, timedelta
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
        # جدول تتبّع رسائل المتابعة (عشان ما نكرر المتابعة لنفس العميل)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS followups (phone TEXT PRIMARY KEY, for_msg TEXT)"
        )
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


def get_last_activity(phone: str):
    """آخر وقت رسالة لعميل معيّن (قبل حفظ الرسالة الحالية)، أو None لو جديد."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT created_at FROM messages WHERE phone = ? ORDER BY id DESC LIMIT 1",
            (phone,),
        ).fetchone()
    return row[0] if row else None


def get_silent_customers(min_hours: float, max_hours: float) -> list:
    """
    عملاء آخر رسالة لهم من مها (assistant) وسكتوا فترة ضمن النطاق المحدد،
    وما أُرسلت لهم رسالة متابعة بعد آخر رسالة منهم. تُرجع قائمة أرقام جوال.
    """
    now = datetime.now()
    lo = (now - timedelta(hours=max_hours)).isoformat(timespec="seconds")
    hi = (now - timedelta(hours=min_hours)).isoformat(timespec="seconds")
    result = []
    with closing(_connect()) as conn:
        phones = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT phone FROM messages "
                "WHERE phone NOT LIKE 'demo-%' AND phone NOT LIKE 'test%'"
            ).fetchall()
        ]
        for phone in phones:
            last = conn.execute(
                "SELECT role, created_at FROM messages WHERE phone = ? "
                "ORDER BY id DESC LIMIT 1",
                (phone,),
            ).fetchone()
            if not last:
                continue
            role, last_at = last
            if role != "assistant":
                continue                      # آخر رسالة لازم تكون من مها (العميل سكت)
            if not (lo <= last_at <= hi):
                continue                      # خارج نطاق الصمت
            last_user = conn.execute(
                "SELECT created_at FROM messages WHERE phone = ? AND role = 'user' "
                "ORDER BY id DESC LIMIT 1",
                (phone,),
            ).fetchone()
            last_user_at = last_user[0] if last_user else ""
            fr = conn.execute(
                "SELECT for_msg FROM followups WHERE phone = ?", (phone,)
            ).fetchone()
            if fr and fr[0] >= last_user_at:
                continue                      # سبق وأرسلنا متابعة بعد آخر رسالة منه
            result.append(phone)
    return result


def mark_followup(phone: str):
    """تسجيل إن العميل أُرسلت له متابعة الآن (يمنع التكرار)."""
    stamp = datetime.now().isoformat(timespec="seconds")
    with closing(_connect()) as conn:
        conn.execute(
            "INSERT INTO followups (phone, for_msg) VALUES (?, ?) "
            "ON CONFLICT(phone) DO UPDATE SET for_msg = excluded.for_msg",
            (phone, stamp),
        )
        conn.commit()


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
