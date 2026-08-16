"""Telegram bot — stat postlarının yaradılması və təsdiq axını.

Əmrlər:
  /yeni [mövzu]  - yeni stat postu yarat (mövzu yazılmasa, AI özü seçir)
  /gundelik      - günün post paketini indi hazırla (2 münasibət + 2 enerji + 1 rus)
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

# Tək-tək post yaratmaq üçün mövzu seçimləri
TOPIC_CHOICES = {
    "reln": "Qadın və kişi münasibətləri",
    "family": "Ailədə bərəkət və harmoniya",
    "energy": "Çakralar, aura və enerji",
}

# Gündəlik paketin mövzu planı (2 + 2, sonda 1 rusca versiya).
# Enerji postlarından (3-cü/4-cü) biri hər gün konkret bir çakraya həsr olunur.
DAILY_TOPICS = [
    "Qadın və kişi münasibətləri, ailədə bərəkət və harmoniya",
    "Qadın və kişi münasibətləri, ailədə bərəkət və harmoniya",
    "Çakralar, aura və enerji",
    "Çakralar, aura və enerji",
]

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
    """Mövzu seçimi düymələri. lang: 'az' -> newaz, 'ru' -> newru."""
    prefix = f"new{lang}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💑 Qadın-kişi münasibətləri",
                              callback_data=f"{prefix}:reln")],
        [InlineKeyboardButton("🏠 Ailədə bərəkət",
                              callback_data=f"{prefix}:family")],
        [InlineKeyboardButton("🌀 Çakra, aura, enerji",
                              callback_data=f"{prefix}:energy")],
        [InlineKeyboardButton("🎲 AI özü seçsin",
                              callback_data=f"{prefix}:auto")],
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
    return _save_post(content, template="az")


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
    """Günün paketi: 2 münasibət + 2 enerji statı (AZ) + 1 rusca versiya.

    Enerji postlarından biri (gah 3-cü, gah 4-cü) hər gün 7 çakradan
    növbətisinə həsr olunur — statında "çakra" sözü mütləq keçir.
    """
    total = len(DAILY_TOPICS) + 1
    await bot.send_message(
        chat_id, f"🌅 Günün {total} postu hazırlanır, bir neçə dəqiqə çəkə bilər...")

    ideas: list[str] = []
    quotes: list[str] = []
    done = 0

    chakra_idx = int(db.get_state("chakra_idx", "0"))
    chakra_pos = 2 + chakra_idx % 2  # təbii görünsün deyə gah 3-cü, gah 4-cü

    for i, topic in enumerate(DAILY_TOPICS):
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
            post_id = await asyncio.to_thread(_save_post, content, "az")
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
        "/yeni [mövzu] — yeni stat postu yarat (AZ)\n"
        "/rusca [mövzu] — rus dilində stat postu yarat 🇷🇺\n"
        "/gundelik — günün paketini indi hazırla (4 AZ + 1 RU)\n"
        "/siyahi — son postlara bax\n\n"
        f"Hər gün saat {config.DAILY_POST_TIME}-da avtomatik günün paketini "
        "hazırlayacağam."
    )


async def _generate_and_send(bot: Bot, chat_id: int, note_msg,
                             topic: str | None, lang: str):
    """Verilən dildə/mövzuda post yaradıb göndərir; note_msg silinir."""
    try:
        if lang == "ru":
            content = await asyncio.to_thread(
                brain.generate_russian_post, topic)
        else:
            content = await asyncio.to_thread(brain.generate_post, topic)
        post_id = await asyncio.to_thread(_save_post, content, lang)
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
        topic = " ".join(context.args)
        msg = await update.message.reply_text("🧠 Stat hazırlanır, bir az gözlə...")
        await _generate_and_send(
            context.bot, update.effective_chat.id, msg, topic, "az")
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

    action, payload = query.data.split(":")

    # Mövzu seçimi düymələri (/yeni və /rusca menyusu)
    if action in ("newaz", "newru"):
        lang = "ru" if action == "newru" else "az"
        topic = TOPIC_CHOICES.get(payload)  # "auto" üçün None qalır
        flag = "🇷🇺 " if lang == "ru" else ""
        note = await query.message.edit_text(
            f"🧠 {flag}Stat hazırlanır, bir az gözlə...")
        await _generate_and_send(
            context.bot, query.message.chat_id, note, topic, lang)
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
        BotCommand("yeni", "Yeni AZ stat postu (mövzu seçimi ilə)"),
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
