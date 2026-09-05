"""Telegram bot — stat postlarının yaradılması və təsdiq axını.

Əmrlər:
  /yeni [mövzu]  - yeni stat postu yarat (mövzu və şablon seçimi ilə)
  /rusca [mövzu] - rusca stat postu (həmişə template2)
  /gundelik      - günün post paketini indi hazırla (2 ümumi + 2 enerji + 1 rus)

Şablonlar: gündəlik paketdə AZ statları gün-gün növbələşir — bir gün hamısı
template3, sonra 4, 5, 6, yenidən 3 (soruşulmur). Hər
TEMPLATE1_EVERY_N_DAYS-cı gün bütün paket template1-də olur.
/yeni ilə tək post yaradanda şablon soruşulur. Rusca statlar həmişə template2-dədir.
  /siyahi        - son postlar və statusları
  /yardim        - əmrlərin siyahısı

Hər gün DAILY_POST_TIME vaxtında bot avtomatik günün paketini hazırlayıb
təsdiq üçün göndərir.
"""
import asyncio
import datetime
import logging
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import (
    Bot,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from . import brain, config, db, imager

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    "pending": "⏳ Gözləyir",
    "approved": "✅ Təsdiqlənib",
    "rejected": "❌ Rədd edilib",
    "published": "📤 Paylaşılıb",
}

# Model keçidi barədə sonuncu bildirilən model (təkrar spam olmasın deyə)
_notified_model: str | None = None

# Şablonlar (template_config.json açarları)
TPL_AZ1, TPL_AZ3, TPL_AZ4, TPL_AZ5, TPL_AZ6, TPL_RU = (
    "az", "az3", "az4", "az5", "az6", "ru")
# AZ statları növbə ilə 3 → 4 → 5 → 6 → 3 ...
AZ_TEMPLATE_ROTATION = [TPL_AZ3, TPL_AZ4, TPL_AZ5, TPL_AZ6]
# Sayğaclar: az_tpl_idx — /yeni tək postlar (post-post), az_daily_tpl_idx — gündəlik (gün-gün)
TEMPLATE1_EVERY_N_DAYS = 10                 # hər 10-cu gün bütün paket template1
TEMPLATE_LABELS = {
    TPL_AZ3: "3️⃣ Template 3",
    TPL_AZ4: "4️⃣ Template 4",
    TPL_AZ5: "5️⃣ Template 5",
    TPL_AZ6: "6️⃣ Template 6",
    TPL_AZ1: "1️⃣ Template 1",
}


def _next_az_template() -> str:
    """Tək AZ postu üçün növbəti şablon (3→4→5→6, sayğac bazada saxlanılır)."""
    return _rotate(AZ_TEMPLATE_ROTATION, "az_tpl_idx", 1)[0]


def _next_daily_template() -> str:
    """Günün paketi üçün şablon: gün-gün 3 → 4 → 5 → 6 → 3 ..."""
    return _rotate(AZ_TEMPLATE_ROTATION, "az_daily_tpl_idx", 1)[0]


# Tək-tək post yaratmaq üçün mövzu seçimləri (/yeni və /rusca menyusu).
# (açar, düymə yazısı, AI-yə göndərilən tam mövzu) — brand_profile-dakı 16 sütun.
TOPIC_MENU = [
    ("reln",     "💑 Qadın-kişi münasibətləri",
     "Qadın və kişi münasibətləri, ailə harmoniyası, ailədə bərəkət"),
    ("energy",   "🌀 Çakra, aura, enerji",
     "Çakralar, aura və enerji"),
    ("peace",    "🕊 Daxili rahatlıq",
     "Daxili rahatlıq və mənəvi inkişaf"),
    ("psych",    "🧠 Psixologiya və hisslər",
     "İnsan psixologiyası və hisslər"),
    ("relation", "🤝 Münasibətlər",
     "Münasibətlər"),
    ("subcon",   "🌊 Şüuraltı",
     "Şüuraltı"),
    ("tantra",   "🧘 Tantra yoqa",
     "Tantra yoqa"),
    ("breath",   "🌬 Nəfəs texnikaları",
     "Nəfəs texnikaları"),
    ("intuit",   "👁 İntuisiya, bəsirət",
     "İntuisiya, altıncı hiss və bəsirət"),
    ("selfsug",  "🗣 Özünütəlqin",
     "Özünütəlqin"),
    ("grat",     "🙏 Şükür, yüksək vibrasiya",
     "Şükür və yüksək vibrasiya"),
    ("awaken",   "✨ Ruhani oyanış",
     "Ruhani oyanış və aydınlanma"),
    ("abund",    "🌾 Bolluq və bərəkət",
     "Bolluq və bərəkət enerjisi"),
    ("love",     "❤️ Sevgi enerjisi",
     "Sevgi enerjisi"),
    ("release",  "🍂 Keçmişi buraxmaq",
     "Keçmişi buraxmaq və enerjini yeniləmək"),
    ("nature",   "🌿 Təbiətlə balans",
     "Təbiətlə enerji balansı"),
]
TOPIC_CHOICES = {key: topic for key, _label, topic in TOPIC_MENU}

# Gündəlik paket: 2 ümumi + 2 enerji statı (sonda 1 rusca versiya).
# Ümumi 2 stat: GENERAL_TOPIC_ROTATION-dan NÖVBƏ ilə (16-cı mövzudan 1-ciyə doğru,
# hər gün növbəti 2 mövzu; siyahı bitəndə əvvəldən başlayır). Bir gündə 2 ümumi
# stat heç vaxt eyni mövzuda olmur.
# Enerji 2 stat: biri hər gün 7 çakradan növbətisinə həsr olunur (CHAKRAS),
# digəri ENERGY_TOPIC_ROTATION-dakı 3 mövzunu növbə ilə gəzir.
# Növbə sayğacları bazadakı state-də saxlanılır: general_idx, energy_idx, chakra_idx.
GENERAL_TOPIC_ROTATION = [
    "Təbiətlə enerji balansı",                                     # 16
    "Keçmişi buraxmaq və enerjini yeniləmək",                      # 15
    "Sevgi enerjisi",                                              # 14
    "Bolluq və bərəkət enerjisi",                                  # 13
    "Ruhani oyanış və aydınlanma",                                 # 12
    "Nəfəs texnikaları",                                           # 8
    "Tantra yoqa",                                                 # 7
    "Şüuraltı",                                                    # 6
    "Münasibətlər",                                                # 5
    "İnsan psixologiyası və hisslər",                              # 4
    "Daxili rahatlıq və mənəvi inkişaf",                           # 3
    "Qadın və kişi münasibətləri, ailə harmoniyası, ailədə bərəkət",  # 1
]
# "Çakralar, aura və enerji" burada YOXDUR — çakra mövzusunu ayrıca çakra postu örtür.
ENERGY_TOPIC_ROTATION = [
    "İntuisiya, altıncı hiss və bəsirət",
    "Özünütəlqin",
    "Şükür və yüksək vibrasiya",
]
GENERAL_PER_DAY = 2
ENERGY_PER_DAY = 2
DAILY_POST_COUNT = GENERAL_PER_DAY + ENERGY_PER_DAY


def _rotate(pool: list[str], state_key: str, count: int) -> list[str]:
    """pool-dan növbəti `count` mövzunu qaytarır və sayğacı irəli çəkir."""
    idx = int(db.get_state(state_key, "0")) % len(pool)
    picked = [pool[(idx + k) % len(pool)] for k in range(count)]
    db.set_state(state_key, str((idx + count) % len(pool)))
    return picked


def _pick_daily_topics() -> list[str]:
    """Günün 4 mövzusu: 2 ümumi (növbə ilə) + 2 enerji.

    Enerji mövzularından biri növbəti çakra postu üçün yer tutur (mətn
    _send_daily_batch-də CHAKRAS-dan gəlir), digəri 4 enerji mövzusundan
    növbətisidir (3 mövzu). Çakra postunun yeri hər gün 3-cü/4-cü olaraq dəyişir.
    """
    general = _rotate(GENERAL_TOPIC_ROTATION, "general_idx", GENERAL_PER_DAY)
    energy = _rotate(ENERGY_TOPIC_ROTATION, "energy_idx", 1)
    chakra_idx = int(db.get_state("chakra_idx", "0"))
    chakra_slot = ["<çakra>"]
    if chakra_idx % 2 == 0:
        return general + chakra_slot + energy   # çakra 3-cü
    return general + energy + chakra_slot       # çakra 4-cü


# 7 çakra — gün-gün növbə ilə fırlanır (növbə bazadakı state-də saxlanılır)
CHAKRAS = [
    ("Kök çakra (Muladhara)",
     "onurğanın dibində; təhlükəsizlik, torpağa bağlılıq, sabitlik, yaşam gücü"),
    ("Sakral çakra (Svadhistana)",
     "göbəkdən bir az aşağıda; həzz, yaradıcılıq, duyğuların sərbəst axını"),
    ("Günəş kəbəsi çakrası (Manipura)",
     "qarın nahiyəsində; iradə, özünəinam, daxili güc və qərarlılıq"),
    ("Ürək çakrası (Anahata)",
     "sinənin ortasında; sevgi, mərhəmət, bağışlama, qəbul etmə"),
    ("Boğaz çakrası (Vişuddha)",
     "boğazda; özünüifadə, həqiqəti demək, daxili səsə sədaqət"),
    ("Üçüncü göz çakrası (Acna)",
     "qaşların arasında; intuisiya, aydın görmə, daxili müdriklik"),
    ("Tac çakrası (Sahasrara)",
     "başın təpəsində; kainatla bağlılıq, mənəvi oyanış, bütövlük"),
]


def _is_admin(update: Update) -> bool:
    return update.effective_user is not None and \
        update.effective_user.id in config.TELEGRAM_ADMIN_IDS


def _topic_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Mövzu seçimi düymələri (16 mövzu, 2 sütun). lang: 'az' -> newaz, 'ru' -> newru."""
    prefix = f"new{lang}"
    buttons = [InlineKeyboardButton(label, callback_data=f"{prefix}:{key}")
               for key, label, _topic in TOPIC_MENU]
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton("🎲 AI özü seçsin",
                                      callback_data=f"{prefix}:auto")])
    return InlineKeyboardMarkup(rows)


def _template_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Şablon seçimi düymələri (/yeni menyusu). prefix: 'tplaz:<topic_key>'."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔁 Növbə ilə (3→4→5→6)",
                              callback_data=f"{prefix}:auto")],
        [InlineKeyboardButton(TEMPLATE_LABELS[TPL_AZ3],
                              callback_data=f"{prefix}:{TPL_AZ3}"),
         InlineKeyboardButton(TEMPLATE_LABELS[TPL_AZ4],
                              callback_data=f"{prefix}:{TPL_AZ4}")],
        [InlineKeyboardButton(TEMPLATE_LABELS[TPL_AZ5],
                              callback_data=f"{prefix}:{TPL_AZ5}"),
         InlineKeyboardButton(TEMPLATE_LABELS[TPL_AZ6],
                              callback_data=f"{prefix}:{TPL_AZ6}")],
        [InlineKeyboardButton(TEMPLATE_LABELS[TPL_AZ1],
                              callback_data=f"{prefix}:{TPL_AZ1}")],
    ])


def _keyboard(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Təsdiq", callback_data=f"approve:{post_id}"),
            InlineKeyboardButton("🔄 Yenidən", callback_data=f"regen:{post_id}"),
            InlineKeyboardButton("🗑 Sil", callback_data=f"delete:{post_id}"),
        ],
        [
            InlineKeyboardButton("➕ Əlavə yarat", callback_data=f"extra:{post_id}"),
        ],
    ])


def _save_post(content: brain.PostContent, template: str) -> int:
    """Postu şəkilə çevirib bazaya yazır (bloklayıcı)."""
    image_path = imager.render_post_image(content.quote, template=template)
    return db.add_post(
        idea=content.idea,
        caption=content.caption,
        hashtags="",
        image_headline=content.quote,
        image_subtext=template,
        image_path=image_path,
    )


def _create_post(topic: str | None = None,
                 avoid_ideas: list[str] | None = None) -> int:
    content = brain.generate_post(topic, avoid_ideas)
    return _save_post(content, template=_next_az_template())


async def _notify_model_switch(bot: Bot, chat_id: int):
    """AI modeli ehtiyat modelə keçibsə, bir dəfə məlumat verir."""
    global _notified_model
    if config.AI_PROVIDER != "gemini":
        return
    used = brain.last_used_model
    primary = config.GEMINI_MODELS[0] if config.GEMINI_MODELS else None
    if used and primary and used != primary:
        if used != _notified_model:
            _notified_model = used
            await bot.send_message(
                chat_id,
                f"ℹ️ {primary} modelinin gündəlik limiti dolub — "
                f"postlar indi {used} ilə hazırlanır.")
    else:
        _notified_model = None  # əsas model yenidən işləyir


def _model_info_line() -> str | None:
    """Şəklin altına yazılacaq qısa texniki məlumat: model + limit vəziyyəti."""
    model = brain.last_used_model
    if not model:
        return None
    used = db.usage_today(model)
    limit = brain.get_limit(model)
    if limit:
        return f"🧠 {model} · bu gün: {used}/{limit} · qalan: {max(limit - used, 0)}"
    return f"🧠 {model} · bu gün: {used} sorğu"


async def _send_post(bot: Bot, chat_id: int, post_id: int, prefix: str = ""):
    post = db.get_post(post_id)
    with open(post["image_path"], "rb") as photo:
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=_model_info_line(),
            reply_markup=_keyboard(post_id),
        )


async def _send_daily_batch(bot: Bot, chat_id: int):
    """Günün paketi: 2 ümumi + 2 enerji statı (AZ) + 1 rusca versiya.

    Ümumi statlar GENERAL_TOPIC_ROTATION-dan, enerji statı ENERGY_TOPIC_ROTATION-dan
    növbə ilə seçilir (bax _pick_daily_topics). Enerji postlarından biri
    (gah 3-cü, gah 4-cü) hər gün 7 çakradan növbətisinə həsr olunur —
    statında "çakra" sözü mütləq keçir.

    Şablon soruşulmur: günün bütün AZ statları eyni şablondadır, gün-gün
    3 → 4 → 5 → 6 → 3 növbəsi ilə. Hər TEMPLATE1_EVERY_N_DAYS-cı gün bütün
    paket template1-də olur. Rusca stat həmişə template2-dədir.
    """
    total = DAILY_POST_COUNT + 1
    daily_topics = _pick_daily_topics()

    daily_no = int(db.get_state("daily_no", "0")) + 1
    db.set_state("daily_no", str(daily_no))
    # Hər 10-cu gün bütün paket template1-də; digər günlər 3→4→5→6 növbəsi
    if daily_no % TEMPLATE1_EVERY_N_DAYS == 0:
        day_template = TPL_AZ1
        tpl_note = f"şablon: {TEMPLATE_LABELS[TPL_AZ1]} (10 günlük növbə)"
    else:
        day_template = _next_daily_template()
        tpl_note = f"şablon: {TEMPLATE_LABELS[day_template]}"
    await bot.send_message(
        chat_id, f"🌅 Günün {total} postu hazırlanır, bir neçə dəqiqə çəkə bilər...\n"
                 f"🖼 {tpl_note}")

    ideas: list[str] = []
    quotes: list[str] = []
    done = 0

    chakra_idx = int(db.get_state("chakra_idx", "0"))
    chakra_pos = GENERAL_PER_DAY + chakra_idx % 2  # gah 3-cü, gah 4-cü

    for i, topic in enumerate(daily_topics):
        try:
            if i == chakra_pos:
                name, hint = CHAKRAS[chakra_idx % len(CHAKRAS)]
                content = await asyncio.to_thread(
                    brain.generate_chakra_post, name, hint,
                    ideas if ideas else None)
                db.set_state("chakra_idx", str(chakra_idx + 1))
            else:
                content = await asyncio.to_thread(
                    brain.generate_post, topic, ideas if ideas else None)
            post_id = await asyncio.to_thread(_save_post, content, day_template)
            ideas.append(content.idea)
            quotes.append(content.quote)
            await _send_post(bot, chat_id, post_id, prefix=f"[{i + 1}/{total}] ")
            await _notify_model_switch(bot, chat_id)
            done += 1
        except Exception:
            logger.exception("Gündəlik post %s yaradıla bilmədi", i + 1)

    if quotes:
        try:
            ru_content = await asyncio.to_thread(brain.make_russian_version, quotes)
            ru_id = await asyncio.to_thread(_save_post, ru_content, "ru")
            await _send_post(bot, chat_id, ru_id, prefix=f"[{total}/{total}] 🇷🇺 ")
            await _notify_model_switch(bot, chat_id)
            done += 1
        except Exception:
            logger.exception("Rusca post yaradıla bilmədi")

    await bot.send_message(
        chat_id, f"✨ Hazırdır! {done}/{total} post təsdiqini gözləyir.")


async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    # Gündəlik paket birinci (əsas) adminə göndərilir
    await _send_daily_batch(context.bot, config.TELEGRAM_ADMIN_IDS[0])


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        await update.message.reply_text("Bu bot şəxsi istifadə üçündür.")
        return
    await update.message.reply_text(
        "Salam! Mən sənin SMM köməkçinəm. 🤖\n\n"
        "/yeni [mövzu] — yeni stat postu yarat (AZ, şablon seçimi ilə)\n"
        "/rusca [mövzu] — rus dilində stat postu yarat 🇷🇺\n"
        "/gundelik — günün paketini indi hazırla (4 AZ + 1 RU, şablon gün-gün 3→4→5→6)\n"
        "/siyahi — son postlara bax\n\n"
        f"Hər gün saat {config.DAILY_POST_TIME}-da avtomatik günün paketini "
        "hazırlayacağam."
    )


async def _generate_and_send(bot: Bot, chat_id: int, note_msg,
                             topic: str | None, lang: str,
                             template: str | None = None):
    """Verilən dildə/mövzuda post yaradıb göndərir; note_msg silinir.

    template: AZ üçün şablon açarı; None olsa növbə ilə (3→4→5→6).
    Rusca post həmişə template2 ("ru") ilə yaradılır.
    """
    try:
        if lang == "ru":
            content = await asyncio.to_thread(
                brain.generate_russian_post, topic)
            tpl = TPL_RU
        else:
            content = await asyncio.to_thread(brain.generate_post, topic)
            tpl = template or _next_az_template()
        post_id = await asyncio.to_thread(_save_post, content, tpl)
    except Exception:
        logger.exception("Post yaradıla bilmədi (%s)", lang)
        await note_msg.edit_text("⚠️ Xəta baş verdi. Bir az sonra yenidən cəhd et.")
        return
    await note_msg.delete()
    await _send_post(bot, chat_id, post_id)
    await _notify_model_switch(bot, chat_id)


async def cmd_rusca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    if context.args:
        topic = " ".join(context.args)
        msg = await update.message.reply_text(
            "🧠🇷🇺 Rusca stat hazırlanır, bir az gözlə...")
        await _generate_and_send(
            context.bot, update.effective_chat.id, msg, topic, "ru")
        return
    await update.message.reply_text(
        "🇷🇺 Rusca post üçün mövzunu seç:", reply_markup=_topic_keyboard("ru"))


async def cmd_yeni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    if context.args:
        # Sərbəst yazılmış mövzu callback-ə sığmaya bilər — user_data-da saxlanılır
        context.user_data["custom_topic"] = " ".join(context.args)
        await update.message.reply_text(
            f"🖼 «{context.user_data['custom_topic']}» üçün şablonu seç:",
            reply_markup=_template_keyboard("tplaz:custom"))
        return
    await update.message.reply_text(
        "📝 Yeni post üçün mövzunu seç:", reply_markup=_topic_keyboard("az"))


async def cmd_gundelik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    await _send_daily_batch(context.bot, update.effective_chat.id)


async def cmd_siyahi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return
    posts = db.list_posts(limit=10)
    if not posts:
        await update.message.reply_text("Hələ heç bir post yoxdur. /yeni yaz!")
        return
    lines = [
        f"#{p['id']} {STATUS_LABELS.get(p['status'], p['status'])} — {p['idea'][:60]}"
        for p in posts
    ]
    await update.message.reply_text("\n".join(lines))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(update):
        return

    action, payload = query.data.split(":", 1)

    # /yeni menyusu, 1-ci addım: mövzu seçildi → şablon soruşulur
    if action == "newaz":
        label = next((lbl for key, lbl, _t in TOPIC_MENU if key == payload),
                     "🎲 AI özü seçsin")
        await query.message.edit_text(
            f"🖼 {label}\nŞablonu seç:",
            reply_markup=_template_keyboard(f"tplaz:{payload}"))
        return

    # /yeni menyusu, 2-ci addım: şablon seçildi → post hazırlanır
    if action == "tplaz":
        topic_key, tpl = payload.split(":")
        if topic_key == "custom":
            topic = context.user_data.get("custom_topic")
        else:
            topic = TOPIC_CHOICES.get(topic_key)  # "auto" üçün None qalır
        template = None if tpl == "auto" else tpl
        note = await query.message.edit_text("🧠 Stat hazırlanır, bir az gözlə...")
        await _generate_and_send(
            context.bot, query.message.chat_id, note, topic, "az", template)
        return

    # /rusca menyusu: mövzu seçildi → template2 ilə post hazırlanır
    if action == "newru":
        topic = TOPIC_CHOICES.get(payload)  # "auto" üçün None qalır
        note = await query.message.edit_text(
            "🧠 🇷🇺 Stat hazırlanır, bir az gözlə...")
        await _generate_and_send(
            context.bot, query.message.chat_id, note, topic, "ru")
        return

    post_id = int(payload)

    if action == "approve":
        db.set_status(post_id, "approved")
        await query.edit_message_caption(caption="✅ Təsdiqləndi")
    elif action in ("delete", "reject"):
        old = db.delete_post(post_id)
        if old and old.get("image_path"):
            try:
                Path(old["image_path"]).unlink(missing_ok=True)
            except OSError:
                logger.warning("Şəkil silinə bilmədi: %s", old["image_path"])
        await query.message.delete()
    elif action == "extra":
        # Mövcud post toxunulmaz qalır, eyni mövzuda əlavə yeni stat yaranır
        old = db.get_post(post_id)
        note = await query.message.reply_text(
            f"➕ Post #{post_id} mövzusunda əlavə stat hazırlanır...")
        try:
            content = await asyncio.to_thread(
                brain.generate_post, old["idea"], [old["image_headline"]])
            template = old["image_subtext"] or "az"
            if template == "ru":
                content = await asyncio.to_thread(
                    brain.make_russian_version, [content.quote])
            new_id = await asyncio.to_thread(_save_post, content, template)
        except Exception:
            logger.exception("Əlavə post yaradıla bilmədi")
            await note.edit_text("⚠️ Xəta baş verdi, yenidən cəhd et.")
            return
        await note.delete()
        await _send_post(context.bot, query.message.chat_id, new_id, prefix="➕ ")
        await _notify_model_switch(context.bot, query.message.chat_id)
    elif action == "regen":
        db.set_status(post_id, "rejected")
        old = db.get_post(post_id)
        await query.edit_message_caption(
            caption=f"🔄 Post #{post_id} yenidən hazırlanır...")
        try:
            # Eyni mövzuda, amma köhnə statdan fərqli yeni stat
            content = await asyncio.to_thread(
                brain.generate_post, old["idea"], [old["image_headline"]])
            template = old["image_subtext"] or "az"
            if template == "ru":
                content = await asyncio.to_thread(
                    brain.make_russian_version, [content.quote])
            new_id = await asyncio.to_thread(_save_post, content, template)
        except Exception:
            logger.exception("Post yenidən yaradıla bilmədi")
            await query.message.reply_text("⚠️ Xəta baş verdi, yenidən cəhd et.")
            return
        await _send_post(context.bot, query.message.chat_id, new_id, prefix="🔄 ")
        await _notify_model_switch(context.bot, query.message.chat_id)


async def _post_init(app: Application):
    """Telegram-dakı əmr menyusunu yeniləyir."""
    await app.bot.set_my_commands([
        BotCommand("yeni", "Yeni AZ stat postu (mövzu + şablon seçimi)"),
        BotCommand("rusca", "Rusca stat postu (mövzu seçimi ilə) 🇷🇺"),
        BotCommand("gundelik", "Günün paketi: 4 AZ + 1 RU"),
        BotCommand("siyahi", "Son postlar və statusları"),
    ])


def build_app() -> Application:
    # Şəkillər ~1 MB-dır. Standart limitlər (write 5 san, media 20 san)
    # yavaş şəbəkədə çatmır və "TimedOut" xətası verir — genişləndirilib.
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .media_write_timeout(180)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("yeni", cmd_yeni))
    app.add_handler(CommandHandler("rusca", cmd_rusca))
    app.add_handler(CommandHandler("gundelik", cmd_gundelik))
    app.add_handler(CommandHandler("siyahi", cmd_siyahi))
    app.add_handler(CallbackQueryHandler(on_button))

    hour, minute = (int(x) for x in config.DAILY_POST_TIME.split(":"))
    app.job_queue.run_daily(
        daily_job,
        time=datetime.time(hour, minute, tzinfo=ZoneInfo(config.TIMEZONE)),
        name="daily_posts",
    )
    return app
