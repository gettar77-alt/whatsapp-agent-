"""
test_chat.py
------------
أداة اختبار محلية لمحادثة الايجنت من سطر الأوامر مباشرة (بدون واتساب).

تتيح لك تجربة شخصية الايجنت وردوده بسرعة، وتعديل system_prompt.txt
أو apartments.json ورؤية الأثر فوراً قبل الربط الفعلي بالواتساب.

طريقة التشغيل (من داخل مجلد المشروع):
    python test_chat.py

أوامر خاصة أثناء المحادثة:
    خروج   → إنهاء المحادثة
    جديد   → مسح المحادثة الحالية والبدء من الصفر
"""

import config
import database
from claude_client import get_reply

# رقم وهمي خاص بالاختبار (يميّز محادثة الاختبار عن محادثات العملاء الحقيقيين)
TEST_PHONE = "test-cli-user"


def main():
    # تجهيز قاعدة البيانات (تُنشأ تلقائياً أول مرة)
    database.init_db()

    print("=" * 55)
    print("  محادثة تجريبية مع الايجنت")
    print("  اكتب 'خروج' للإنهاء، أو 'جديد' لمسح المحادثة")
    print("=" * 55)
    print()

    while True:
        try:
            user_text = input("أنت: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nانتهت المحادثة.")
            break

        if not user_text:
            continue

        if user_text in ("خروج", "exit", "quit"):
            print("انتهت المحادثة.")
            break

        if user_text in ("جديد", "مسح", "reset"):
            database.clear_history(TEST_PHONE)
            print("\n[تم مسح المحادثة. ابدأ من جديد]\n")
            continue

        # 1) حفظ رسالة العميل
        database.save_message(TEST_PHONE, "user", user_text)

        # 2) استرجاع تاريخ المحادثة (آخر HISTORY_LIMIT رسالة)
        history = database.get_history(TEST_PHONE, config.HISTORY_LIMIT)

        # 3) سؤال Claude — مع معالجة أي خطأ في الاتصال حتى لا تتعطل الأداة
        try:
            reply = get_reply(history)
        except Exception as error:
            print(f"\n[حدث خطأ أثناء الاتصال بـ Claude]: {error}\n")
            continue

        # 4) حفظ رد الايجنت ثم عرضه
        database.save_message(TEST_PHONE, "assistant", reply)
        print(f"\nالايجنت: {reply}\n")


if __name__ == "__main__":
    main()
