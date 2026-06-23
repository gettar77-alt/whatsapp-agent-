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

from datetime import datetime, timedelta, timezone

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


def _build_system_prompt() -> str:
    """قراءة شخصية الايجنت وبيانات الشقق ودمجهما في نص تعليمات واحد."""
    with open(config.SYSTEM_PROMPT_FILE, encoding="utf-8") as f:
        persona = f.read().strip()

    with open(config.APARTMENTS_FILE, encoding="utf-8") as f:
        apartments_data = f.read().strip()

    # نلصق تاريخ اليوم + بيانات الشقق أسفل شخصية الايجنت ليعتمد عليها في إجاباته
    return (
        persona
        + "\n\n"
        + _today_line()
        + "\n\n"
        + "===== بيانات الشقق والأسعار (اعتمد عليها فقط في إجاباتك) =====\n"
        + apartments_data
    )


def get_reply(history: list) -> str:
    """
    إرسال تاريخ المحادثة إلى Claude والحصول على نص الرد.
    history: قائمة رسائل بصيغة [{"role": "user"/"assistant", "content": "..."}]
    تُعيد: نص رد الايجنت.
    """
    system_prompt = _build_system_prompt()

    response = _client.messages.create(
        model=config.CLAUDE_MODEL,            # اسم الموديل من الإعدادات (claude-haiku-4-5)
        max_tokens=config.CLAUDE_MAX_TOKENS,  # أقصى طول للرد
        temperature=config.CLAUDE_TEMPERATURE,  # 0.6 = ردود طبيعية متزنة
        system=system_prompt,                 # شخصية الايجنت + بيانات الشقق
        messages=history,                     # تاريخ المحادثة كاملاً
    )

    # رد النموذج يأتي كقائمة "مقاطع"؛ نجمع النصية منها في نص واحد
    text_parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_parts).strip()
