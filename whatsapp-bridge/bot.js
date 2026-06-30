// ============================================================
//  جسر مها — ربط كجهاز مرتبط بواتساب (Linked Device)
// ------------------------------------------------------------
//  القاعدة الأساسية:
//   - الرقم غير المحفوظ كجهة اتصال (عميل جديد)  → مها ترد
//   - الرقم المحفوظ بالاسم (معارف صاحب الرقم)    → تتجاهل تماماً
//  يحتفظ بنفس الرقم والحساب والمحادثات — صفر حذف، صفر فقدان بيانات.
//  يعيد استخدام "عقل مها" (Claude + الشخصية + قاعدة البيانات) عبر /chat.
// ============================================================

const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const axios = require("axios");
const fs = require("fs");
const path = require("path");

// ------- تحميل متغيرات البيئة من ملف .env (نفس ملف العقل) -------
// الجسر ما يعتمد على systemd عشان يقرأ .env — يقرأه بنفسه لضمان توفر
// المتغيرات المهمة مثل OWNER_PHONE و WHATSAPP_VERIFY_TOKEN حتى لو ما مُرّرت للخدمة.
(function loadEnv() {
  try {
    const envPath = process.env.ENV_FILE || path.join(__dirname, "..", ".env");
    if (!fs.existsSync(envPath)) return;
    for (const line of fs.readFileSync(envPath, "utf8").split(/\r?\n/)) {
      const s = line.trim();
      if (!s || s.startsWith("#")) continue;
      const eq = s.indexOf("=");
      if (eq === -1) continue;
      const key = s.slice(0, eq).trim();
      let val = s.slice(eq + 1).trim();
      if (
        (val.startsWith('"') && val.endsWith('"')) ||
        (val.startsWith("'") && val.endsWith("'"))
      ) {
        val = val.slice(1, -1);
      }
      // لا نطغى على متغير موجود مسبقاً (systemd له الأولوية)
      if (key && !(key in process.env)) process.env[key] = val;
    }
    console.log("تم تحميل إعدادات .env في الجسر");
  } catch (e) {
    console.error("تعذّر قراءة .env في الجسر:", e.message);
  }
})();

// عقل مها (خادم فلاسك المحلي) — يرجّع الرد بالنجدي
const BRAIN_URL = process.env.BRAIN_URL || "http://127.0.0.1:5000/chat";
// مكان حفظ جلسة الربط (تبقى بعد إعادة التشغيل بدون إعادة مسح QR)
const SESSION_PATH =
  process.env.SESSION_PATH || "/opt/maha/whatsapp-bridge/.wwebjs_auth";
// مجلد صور الشقق (كل شقة في مجلد فرعي باسمها)
const MEDIA_DIR = process.env.MEDIA_DIR || "/opt/maha/media";
// رقم المالك لتنبيهه عند طلب التحويل — يُقرأ من .env، ولا يُرسل لأي عميل أبداً
const OWNER_PHONE = process.env.OWNER_PHONE || "";
// متابعة العميل اللي سكت — رابط العقل + توكن داخلي + كل كم نتحقق
const FOLLOWUP_URL =
  process.env.FOLLOWUP_URL || "http://127.0.0.1:5000/followups";
const INTERNAL_TOKEN = process.env.WHATSAPP_VERIFY_TOKEN || "";
const FOLLOWUP_EVERY_MS = 15 * 60 * 1000; // كل ربع ساعة

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
client.on("ready", () => {
  console.log("مها متصلة وجاهزة — ترد على الأرقام غير المحفوظة فقط");
  // نبدأ دورة متابعة العملاء اللي سكتوا
  setInterval(runFollowups, FOLLOWUP_EVERY_MS);
});
client.on("disconnected", (r) => console.log("انقطع الاتصال:", r));

// ------- متابعة العميل اللي سكت -------
async function runFollowups() {
  try {
    const res = await axios.get(FOLLOWUP_URL, {
      params: { token: INTERNAL_TOKEN },
      timeout: 30000,
    });
    const items = (res.data && res.data.items) || [];
    for (const it of items) {
      const jid = String(it.phone).replace(/\D/g, "") + "@c.us";
      await client.sendMessage(jid, it.message);
      console.log(`[متابعة] أُرسلت متابعة إلى ${it.phone}`);
      await humanDelay(1500, 4000);
    }
  } catch (e) {
    console.error("خطأ في المتابعة:", e.message);
  }
}

function humanDelay(minMs, maxMs) {
  return new Promise((res) => setTimeout(res, minMs + Math.random() * (maxMs - minMs)));
}

// انتظار مدة محسوبة مسبقاً
function sleep(ms) {
  return new Promise((res) => setTimeout(res, ms));
}

// رقم عشوائي ضمن مدى (تشويش بشري — لا نكرر نفس الرقم)
function rand(min, max) {
  return min + Math.random() * (max - min);
}

// الساعة الحالية بتوقيت الرياض (UTC+3)
function ksaHour() {
  return (new Date().getUTCHours() + 3) % 24;
}

// معامل البطء حسب وقت اليوم: نهاراً حاضرة وسريعة، بالليل المتأخر أبطأ
function nightFactor() {
  const h = ksaHour();
  if (h >= 1 && h < 7) return 2.2; // الليل المتأخر — أبطأ بوضوح (إحساس النوم)
  if (h < 1) return 1.6; // بعد منتصف الليل
  if (h >= 23) return 1.5; // قبيل منتصف الليل
  return 1.0; // نهاراً
}

// وقت الرياض بصيغة مقروءة (يُستخدم في تنبيه المالك)
function ksaTimeString() {
  const now = new Date(Date.now() + 3 * 3600 * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return (
    `${now.getUTCFullYear()}-${p(now.getUTCMonth() + 1)}-${p(now.getUTCDate())} ` +
    `${p(now.getUTCHours())}:${p(now.getUTCMinutes())}`
  );
}

// إرسال صور شقة معيّنة (كل الصور داخل /opt/maha/media/<key>/)
async function sendPhotos(chatId, key, phone) {
  try {
    const dir = path.join(MEDIA_DIR, key);
    if (!fs.existsSync(dir)) {
      console.log(`[صور] المجلد غير موجود: ${dir}`);
      return;
    }
    const files = fs
      .readdirSync(dir)
      .filter((f) => /\.(jpe?g|png|webp)$/i.test(f))
      .sort();
    // ترسل كل الصور دفعة وحدة ورا بعض بدون تأخير بينها (تبان كمجموعة)
    for (const f of files) {
      const media = MessageMedia.fromFilePath(path.join(dir, f));
      await client.sendMessage(chatId, media);
    }
    console.log(`[صور] أُرسلت ${files.length} صورة (${key}) إلى ${phone}`);
  } catch (e) {
    console.error("خطأ في إرسال الصور:", e.message);
  }
}

// تحويل رقم سعودي لأي صيغة إلى معرّف واتساب صحيح (966XXXXXXXXX@c.us)
// يتقبّل: 05XXXXXXXX أو 5XXXXXXXX أو 9665XXXXXXXX أو 009665XXXXXXXX
function toJid(num) {
  let d = String(num || "").replace(/\D/g, "");
  if (d.startsWith("00")) d = d.slice(2); // 00966... -> 966...
  if (d.length === 10 && d.startsWith("05")) d = "966" + d.slice(1); // 05XXXXXXXX
  else if (d.length === 9 && d.startsWith("5")) d = "966" + d; // 5XXXXXXXX
  return d + "@c.us";
}

// تنبيه المالك لما عميل يطلب التحويل (يُرسل لرقم المالك فقط)
// summary = ملخص مختصر لطلب العميل تكتبه مها (اختياري)
async function alertOwner(customerPhone, summary) {
  if (!OWNER_PHONE) {
    console.error("[تحويل] OWNER_PHONE غير مضبوط — ما أقدر أنبّه المالك");
    return;
  }
  try {
    const jid = toJid(OWNER_PHONE);
    // ما نخمّن الرقم — لو ما توفّر نكتب "غير متوفر"
    const numLine = customerPhone ? `+${customerPhone}` : "غير متوفر";
    let body =
      `تنبيه من مها: عميل يبي يتواصل معك\n` +
      `رقم العميل: ${numLine}\n` +
      `الوقت: ${ksaTimeString()} (توقيت الرياض)`;
    if (summary) body += `\nالتفاصيل: ${summary}`;
    await client.sendMessage(jid, body);
    console.log(`[تحويل] نُبّه المالك بخصوص ${numLine}`);
  } catch (e) {
    console.error("خطأ في تنبيه المالك:", e.message);
  }
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
    const phone = msg.from.replace("@c.us", "");
    const contact = await msg.getContact();
    if (contact.isMyContact) {
      console.log(`[تجاهل] رقم محفوظ: ${phone}`);
      return;
    }
    console.log(`[وارد] رقم غير محفوظ: ${phone}`);

    // رقم العميل الحقيقي (للتنبيه): نأخذه من جهة الاتصال لأنه أدق من معرّف
    // المحادثة، ولا نخمّنه أبداً — لو ما عرفناه نتركه فاضي.
    let customerNumber = "";
    if (contact && contact.number) {
      customerNumber = String(contact.number).replace(/\D/g, "");
    } else if (
      contact &&
      contact.id &&
      contact.id.user &&
      /^\d{7,15}$/.test(contact.id.user)
    ) {
      customerNumber = contact.id.user;
    } else if (msg.from.endsWith("@c.us")) {
      customerNumber = phone.replace(/\D/g, "");
    }

    const text = (msg.body || "").trim();
    if (!text) return;

    const chat = await msg.getChat();
    const nf = nightFactor(); // معامل البطء حسب وقت اليوم

    // 4) تأخير قراءة بشري (وأحياناً تكون مشغولة) ثم تعلّمها مقروءة
    let readMs = rand(2000, 8000) * nf;
    if (Math.random() < 0.1) readMs += rand(15000, 40000); // ~10%: كانت مشغولة
    readMs = Math.min(readMs, 45000); // سقف أمان
    await sleep(readMs);
    try {
      await chat.sendSeen();
    } catch (e) {}

    // 5) تأخير تفكير قصير قبل ما تبدأ ترد (استيعاب + صياغة)
    await humanDelay(2000 * nf, 7000 * nf);

    // 6) اسأل عقل مها عن الرد
    const res = await axios.post(
      BRAIN_URL,
      { message: text, session: phone },
      { timeout: 60000 }
    );
    let reply = res.data && res.data.reply ? res.data.reply : "";
    if (!reply) return;

    // 6) استخراج العلامات: التحويل للمالك [[handoff]] وصور الشقق [[photos:KEY]]
    let handoff = false;
    let handoffSummary = "";
    const hMark = reply.match(/\[\[handoff(?::([^\]]*))?\]\]/);
    if (hMark) {
      handoff = true;
      handoffSummary = (hMark[1] || "").trim();
      reply = reply.replace(hMark[0], "").trim();
    }
    let photoKey = null;
    const mark = reply.match(/\[\[photos:([^\]]+)\]\]/);
    if (mark) {
      photoKey = mark[1].trim();
      reply = reply.replace(mark[0], "").trim();
    }

    // 8) أرسل النص رسائل متتابعة بإيقاع بشري (فاصل + يكتب الآن + مدة كتابة)
    if (reply) {
      // نقسّم الرد عند السطور الفارغة — كل مقطع رسالة مستقلة
      let chunks = reply
        .split(/\n{2,}/)
        .map((s) => s.trim())
        .filter(Boolean);
      // امنع إرسال نفس الرسالة مرتين في نفس الرد (نشيل المكرر ونبقي أول ظهور)
      chunks = chunks.filter((c, idx) => chunks.indexOf(c) === idx);
      for (let i = 0; i < chunks.length; i++) {
        const chunk = chunks[i];
        // فاصل بين الرسالة والثانية (ما نرسلهم في نفس اللحظة أبداً)
        if (i > 0) await humanDelay(900 * nf, 2500 * nf);
        try {
          await chat.sendStateTyping();
        } catch (e) {}
        // مدة الكتابة ≈ عدد الحروف ÷ (4–7 حرف/ثانية) + تشويش، بسقف 12 ثانية
        const typeMs = Math.min(
          (chunk.length / rand(4, 7)) * 1000 + rand(300, 1200),
          12000
        );
        await sleep(typeMs);
        await client.sendMessage(msg.from, chunk);
      }
      console.log(`[رد] أُرسل إلى ${phone} (${chunks.length} رسالة)`);
    }

    // 9) أرسل الصور إن طلبها العميل
    if (photoKey) {
      await sendPhotos(msg.from, photoKey, phone);
    }

    // 10) نبّه المالك إن وافق العميل على التحويل (بالرقم الحقيقي للعميل)
    if (handoff) {
      await alertOwner(customerNumber, handoffSummary);
    }
  } catch (e) {
    console.error("خطأ في معالجة رسالة:", e.message);
  }
});

client.initialize();
