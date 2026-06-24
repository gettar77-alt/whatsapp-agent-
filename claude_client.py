"""
claude_client.py
----------------
كل ما يخص التواصل مع نموذج Claude عبر مكتبة Anthropic الرسمية.

الفكرة:
  - نقرأ شخصية الايجنت (system_prompt.txt) وبيانات الشقق (apartments.json)
    ونجمعهما في "تعليمات النظام" (system prompt) التي ترشد النموذج.
  - نرسل تاريخ المحادثة كاملاً للنموذج فيرد بردّ مناسب للسياق.

ملاحظة: نقرأ الملفين عند كل رسالة، فأي تعديل تجريه على شخصية الايجنت
أو بيانات الشقق يظهر أثره فوراً دون إعادة تشغيل أو لمس الكود.
"""

import json
from datetime import date, datetime, timedelta, timezone

import anthropic

import config

# إنشاء عميل Anthropic مرة واحدة باستخدام المفتاح من الإعدادات
_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

# توقيت الرياض (UTC+3 بدون توقيت صيفي)
_KSA = timezone(timedelta(hours=3))
# الإثنين=0 ... الأحد=6 (ترتيب datetime.weekday)
_AR_WEEKDAYS = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]


def _today_line() -> str:
    """سطر يوضّح تاريخ اليوم بالميلادي واسم اليوم بتوقيت الرياض."""
    now = datetime.now(_KSA)
    return (
        "===== تاريخ اليوم (للرجوع إليه عند فهم بكرا/الخميس/نهاية الأسبوع) =====\n"
        f"اليوم {_AR_WEEKDAYS[now.weekday()]} الموافق {now.strftime('%Y-%m-%d')} ميلادي، بتوقيت الرياض."
    )


def _short_name(unit: dict) -> str:
    """اسم مختصر وثابت للشقة عشان الجدول يكون واضح وما يلتبس."""
    name = unit.get("الاسم", "")
    if "بينت" in name or "بنت هاوس" in name or "دورين" in name:
        return "البينت هاوس"
    if "اقتصادي" in name:
        return "الشقة الاقتصادية"
    if "جناح" in name:
        return "الجناح الفاخر"
    return name or "شقة"


def _availability_block(apartments: dict) -> str:
    """
    نحسب التوفر آلياً (بالكود) ونقدّمه كشبكة صريحة عشان الدقة 100%:
    لكل يوم سطر، وداخله حالة كل شقة مكتوبة صراحة (متاح/محجوز).
    النموذج ما يستنتج شي — بس يلقى سطر اليوم ويقرأ حالة الشقة المطلوبة.
    """
    today = datetime.now(_KSA).date()
    units = apartments.get("الوحدات", [])
    # لكل وحدة: اسمها المختصر + مجموعة أيامها المقفلة (للبحث السريع)
    prepared = [(_short_name(u), set(u.get("الأيام_المقفلة", []) or [])) for u in units]

    lines = [
        "===== جدول التوفر الرسمي (المصدر الوحيد للتوفر — اقرئي منه حرفياً) =====",
        f"اليوم هو: {_AR_WEEKDAYS[today.weekday()]} {today.isoformat()}",
        "كل سطر = يوم، وجنب كل شقة حالتها (متاح = فاضية تنحجز، محجوز = مأخوذة):",
        "",
    ]
    horizon = 60  # نغطي شهرين قدّام
    for i in range(horizon):
        d = today + timedelta(days=i)
        ds = d.isoformat()
        tag = ""
        if i == 0:
            tag = " (اليوم)"
        elif i == 1:
            tag = " (بكرا)"
        elif i == 2:
            tag = " (بعد بكرا)"
        statuses = [
            f"{name} = {'محجوز' if ds in locked else 'متاح'}" for name, locked in prepared
        ]
        lines.append(
            f"{_AR_WEEKDAYS[d.weekday()]} {ds}{tag}  ←  " + "  |  ".join(statuses)
        )
    return "\n".join(lines)


def _build_system_prompt() -> str:
    """قراءة شخصية الايجنت وبيانات الشقق ودمجهما في نص تعليمات واحد."""
    with open(config.SYSTEM_PROMPT_FILE, encoding="utf-8") as f:
        persona = f.read().strip()

    with open(config.APARTMENTS_FILE, encoding="utf-8") as f:
        apartments_raw = f.read().strip()

    try:
        apartments = json.loads(apartments_raw)
    except Exception:
        apartments = {}

    # نلصق تاريخ اليوم + جدول التوفر المحسوب + بيانات الشقق أسفل الشخصية
    return (
        persona
        + "\n\n"
        + _today_line()
        + "\n\n"
        + _availability_block(apartments)
        + "\n\n"
        + "===== بيانات الشقق والأسعار (اعتمد عليها فقط في إجاباتك) =====\n"
        + apartments_raw
    )


_RETURNING_NOTE = (
    "\n\n===== ملاحظة عن هذا العميل =====\n"
    "هذا العميل تكلّم معك سابقاً ورجع بعد فترة. رحّبي فيه كعميل راجع بشكل ودّي "
    "ومختصر (مثل: هلا فيك مرة ثانية / حياك الله، نوّري) بدون ما تعيدين التعريف "
    "الرسمي الكامل من جديد، وكمّلي معاه على طول."
)


def get_reply(history: list, returning: bool = False) -> str:
    """
    إرسال تاريخ المحادثة إلى Claude والحصول على نص الرد.
    history: قائمة رسائل بصيغة [{"role": "user"/"assistant", "content": "..."}]
    returning: هل هذا عميل رجع بعد فترة (يأثر على التحية).
    تُعيد: نص رد الايجنت.
    """
    system_prompt = _build_system_prompt()
    if returning:
        system_prompt += _RETURNING_NOTE

    response = _client.messages.create(
        model=config.CLAUDE_MODEL,            # اسم الموديل من الإعدادات
        max_tokens=config.CLAUDE_MAX_TOKENS,  # أقصى طول للرد
        temperature=config.CLAUDE_TEMPERATURE,  # طبيعية متزنة
        # نخزّن التعليمات الثابتة (الشخصية + بيانات الشقق) مؤقتاً لتخفيض التكلفة
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=history,                     # تاريخ المحادثة كاملاً
    )

    # رد النموذج يأتي كقائمة "مقاطع"؛ نجمع النصية منها في نص واحد
    text_parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_parts).strip()
