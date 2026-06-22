// ============================================================
//  جسر مها — ربط كجهاز مرتبط بواتساب (Linked Device)
// ------------------------------------------------------------
//  القاعدة الأساسية:
//   - الرقم غير المحفوظ كجهة اتصال (عميل جديد)  → مها ترد
//   - الرقم المحفوظ بالاسم (معارف صاحب الرقم)    → تتجاهل تماماً
//  يحتفظ بنفس الرقم والحساب والمحادثات — صفر حذف، صفر فقدان بيانات.
//  يعيد استخدام "عقل مها" (Claude + الشخصية + قاعدة البيانات) عبر /chat.
// ============================================================

const { Client, LocalAuth } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const axios = require("axios");

// عقل مها (خادم فلاسك المحلي) — يرجّع الرد بالنجدي
const BRAIN_URL = process.env.BRAIN_URL || "http://127.0.0.1:5000/chat";
// مكان حفظ جلسة الربط (تبقى بعد إعادة التشغيل بدون إعادة مسح QR)
const SESSION_PATH =
  process.env.SESSION_PATH || "/opt/maha/whatsapp-bridge/.wwebjs_auth";

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_PATH }),
  puppeteer: {
    headless: true,
    // نستخدم جوجل كروم الكامل (أكثر استقراراً على السيرفر من النسخة المدمجة)
    executablePath:
      process.env.PUPPETEER_EXECUTABLE_PATH || "/usr/bin/google-chrome-stable",
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
    ],
  },
});

// ------- أحداث الاتصال -------
client.on("qr", (qr) => {
  console.log("\n=============== امسح هذا الكود ===============");
  console.log(
    "من جوال صاحب الرقم: واتساب بزنس ← الإعدادات ← الأجهزة المرتبطة ← ربط جهاز\n"
  );
  qrcode.generate(qr, { small: true });
});

client.on("authenticated", () => console.log("تم التوثيق"));
client.on("ready", () =>
  console.log("مها متصلة وجاهزة — ترد على الأرقام غير المحفوظة فقط")
);
client.on("disconnected", (r) => console.log("انقطع الاتصال:", r));

function humanDelay(minMs, maxMs) {
  return new Promise((res) => setTimeout(res, minMs + Math.random() * (maxMs - minMs)));
}

// ------- معالجة الرسائل الواردة -------
client.on("message", async (msg) => {
  try {
    // 1) تجاهل المجموعات والحالات ورسائلي أنا
    if (msg.from.endsWith("@g.us")) return; // مجموعة
    if (msg.from === "status@broadcast") return; // حالة
    if (msg.fromMe) return;

    // 2) نص فقط (الوسائط نتجاهلها حالياً)
    if (msg.type !== "chat") return;

    // 3) القاعدة الذهبية: لو الرقم محفوظ كجهة اتصال → تجاهل تماماً
    const contact = await msg.getContact();
    if (contact.isMyContact) return;

    const phone = msg.from.replace("@c.us", "");
    const text = (msg.body || "").trim();
    if (!text) return;

    // 4) تأخير بشري قبل الرد (تقرأ الرسالة)
    await humanDelay(2000, 6000);

    // 5) اسأل عقل مها عن الرد
    const res = await axios.post(
      BRAIN_URL,
      { message: text, session: phone },
      { timeout: 60000 }
    );
    const reply = res.data && res.data.reply ? res.data.reply : "";
    if (!reply) return;

    // 6) مؤشر "يكتب..." + تأخير يتناسب مع طول الرد
    const chat = await msg.getChat();
    await chat.sendStateTyping();
    await humanDelay(1500, Math.min(1500 + reply.length * 60, 9000));

    await client.sendMessage(msg.from, reply);
  } catch (e) {
    console.error("خطأ في معالجة رسالة:", e.message);
  }
});

client.initialize();
