import logging
import os
import re

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
from sheets_db import SheetsDB

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

db = SheetsDB()

# ── стани ────────────────────────────────────────────────────────────────────
OWN_PLATE, OWN_CONFIRM, OWN_MANAGE = range(3)
REP_PLATE, REP_REASON, REP_PHOTO   = range(10, 13)

REASONS = [
    "🚗 Заблокував виїзд з гаража",
    "🛑 Загородив проїзд",
    "🚶 Припаркував на тротуарі",
    "🔄 Заблокував інше авто",
    "✏️ Інше (написати вручну)",
]


def norm(plate: str) -> str:
    return re.sub(r"\s+", "", plate.upper())

def valid(plate: str) -> bool:
    return bool(re.match(r"^[A-ZА-ЯІЇЄa-zа-яіїє0-9]{4,10}$", plate))


# ── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚗 Я власник — зареєструвати авто", callback_data="owner")],
        [InlineKeyboardButton("🔔 Повідомити про авто що заважає", callback_data="report")],
    ])
    await update.message.reply_text(
        "👋 *Система сповіщення про авто*\n\nОберіть дію:",
        parse_mode="Markdown",
        reply_markup=kb,
    )


# ════════════════════════════════════════════════════════════════════════════
# ВЛАСНИК
# ════════════════════════════════════════════════════════════════════════════

async def owner_entry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _owner_menu(update, context)

async def owner_entry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.delete()
    return await _owner_menu(update, context)

async def _owner_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cars = db.get_cars_by_user(user.id)
    if cars:
        text = "👤 *Мій гараж*\n\n" + "\n".join(f"🚗 {p}" for p in cars) + "\n\nЩо зробити?"
        kb = [["➕ Додати авто", "🗑 Видалити авто"], ["📋 Мої авто", "🏠 Меню"]]
        await _send(update, text, ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return OWN_MANAGE
    else:
        await _send(update, "🚗 *Реєстрація авто*\n\nВведи номерний знак:\nПриклад: `АЕ1234АЕ`")
        return OWN_PLATE

async def own_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"own_plate: отримано '{update.message.text}'")
    plate = norm(update.message.text)

    if not valid(plate):
        await update.message.reply_text("❌ Невірний формат. Приклад: `АЕ1234АЕ`", parse_mode="Markdown")
        return OWN_PLATE

    existing = db.find_owner(plate)
    if existing:
        if existing["user_id"] == str(update.effective_user.id):
            await update.message.reply_text(f"⚠️ *{plate}* вже зареєстровано на тебе.", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"❌ *{plate}* вже зайнятий.", parse_mode="Markdown")
        return OWN_PLATE

    context.user_data["plate"] = plate
    u = update.effective_user
    tag = f"@{u.username}" if u.username else u.full_name
    kb = [["✅ Підтвердити", "❌ Скасувати"]]
    await update.message.reply_text(
        f"Підтвердь:\n\n🚗 *{plate}*\n👤 {tag}",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )
    return OWN_CONFIRM

async def own_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "✅ Підтвердити":
        u = update.effective_user
        plate = context.user_data["plate"]
        ok = db.register_car(plate, str(u.id), u.username or "", u.full_name)
        if ok:
            await update.message.reply_text(
                f"✅ *{plate}* зареєстровано!\n\nКоли хтось повідомить про твоє авто — прийде сповіщення 📱",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove(),
            )
        else:
            await update.message.reply_text("❌ Помилка збереження. Спробуй /owner")
    else:
        await update.message.reply_text("Скасовано.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def own_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🏠 Меню":
        await update.message.reply_text("Головне меню:", reply_markup=ReplyKeyboardRemove())
        await cmd_start(update, context)
        return ConversationHandler.END

    if text == "📋 Мої авто":
        cars = db.get_cars_by_user(user.id)
        await update.message.reply_text("🚗 " + "\n🚗 ".join(cars) if cars else "Немає авто.")
        return OWN_MANAGE

    if text == "➕ Додати авто":
        await update.message.reply_text("Введи номер:", reply_markup=ReplyKeyboardRemove())
        return OWN_PLATE

    if text == "🗑 Видалити авто":
        cars = db.get_cars_by_user(user.id)
        if not cars:
            await update.message.reply_text("Немає авто.")
            return OWN_MANAGE
        kb = [[p] for p in cars] + [["❌ Скасувати"]]
        await update.message.reply_text("Який номер видалити?",
            reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        context.user_data["deleting"] = True
        return OWN_MANAGE

    if context.user_data.get("deleting"):
        if text == "❌ Скасувати":
            context.user_data.pop("deleting", None)
            return await _owner_menu(update, context)
        plate = norm(text)
        if db.remove_car(plate, str(user.id)):
            await update.message.reply_text(f"✅ *{plate}* видалено.", parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Не знайдено.")
        context.user_data.pop("deleting", None)
        return await _owner_menu(update, context)

    return OWN_MANAGE


# ════════════════════════════════════════════════════════════════════════════
# РЕПОРТ
# ════════════════════════════════════════════════════════════════════════════

async def report_entry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔔 *Повідомити про авто*\n\nВведи номерний знак:\nПриклад: `АЕ1234АЕ`",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return REP_PLATE

async def report_entry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.delete()
    await q.message.reply_text(
        "🔔 *Повідомити про авто*\n\nВведи номерний знак:\nПриклад: `АЕ1234АЕ`",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return REP_PLATE

async def rep_plate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    plate = norm(update.message.text)
    owner = db.find_owner(plate)
    if not owner:
        await update.message.reply_text(
            f"❌ *{plate}* не знайдено в базі.\n\nВласник не зареєстрований. Перевір номер.",
            parse_mode="Markdown",
        )
        return REP_PLATE

    context.user_data["rep_plate"] = plate
    context.user_data["rep_owner"] = owner
    kb = [[r] for r in REASONS]
    await update.message.reply_text(
        f"✅ Знайдено *{plate}*\n\nЩо сталося?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )
    return REP_REASON

async def rep_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "✏️ Інше (написати вручну)":
        context.user_data["custom"] = True
        await update.message.reply_text("Опиши проблему:", reply_markup=ReplyKeyboardRemove())
        return REP_REASON

    if context.user_data.get("custom"):
        context.user_data["rep_reason"] = text
        context.user_data.pop("custom", None)
    else:
        context.user_data["rep_reason"] = re.sub(r"^.\s*", "", text).strip()

    kb = [["⏭ Пропустити фото"]]
    await update.message.reply_text(
        f"Причина: *{context.user_data['rep_reason']}*\n\n📷 Надішли фото або пропусти:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True),
    )
    return REP_PHOTO

async def rep_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_id = None
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    elif update.message.text != "⏭ Пропустити фото":
        await update.message.reply_text("Надішли фото або натисни «Пропустити фото».")
        return REP_PHOTO

    plate  = context.user_data["rep_plate"]
    owner  = context.user_data["rep_owner"]
    reason = context.user_data.get("rep_reason", "Не вказано")
    reporter = update.effective_user
    tag = f"@{reporter.username}" if reporter.username else reporter.full_name

    msg = (
        f"🚨 *УВАГА! Проблема з твоїм авто!*\n\n"
        f"🚗 Номер: *{plate}*\n"
        f"⚠️ Проблема: {reason}\n\n"
        f"📍 Повідомив: {tag}\n\n"
        "Будь ласка, відреагуй якнайшвидше! 🙏"
    )

    try:
        if photo_id:
            await context.bot.send_photo(chat_id=int(owner["user_id"]),
                                         photo=photo_id, caption=msg, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=int(owner["user_id"]),
                                           text=msg, parse_mode="Markdown")

        await update.message.reply_text(
            f"✅ *Сповіщення надіслано!*\n\nВласник *{plate}* отримав повідомлення. Дякуємо! 🙌",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        db.log_incident(plate, reason, str(reporter.id), tag, bool(photo_id))

    except Exception as e:
        logger.error(f"send_notification: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Не вдалося надіслати. Власник ще не запускав бот — порадь йому написати /start.",
            reply_markup=ReplyKeyboardRemove(),
        )

    return ConversationHandler.END


# ── cancel / helper ───────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Скасовано. /start — головне меню.",
                                    reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def _send(update: Update, text: str, markup=None):
    kwargs = dict(text=text, parse_mode="Markdown",
                  reply_markup=markup or ReplyKeyboardRemove())
    if update.message:
        await update.message.reply_text(**kwargs)
    elif update.callback_query:
        await update.callback_query.message.reply_text(**kwargs)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN не задано!")

    app = Application.builder().token(token).build()

    owner_conv = ConversationHandler(
        entry_points=[
            CommandHandler("owner", owner_entry_cmd),
            CallbackQueryHandler(owner_entry_cb, pattern="^owner$"),
        ],
        states={
            OWN_PLATE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, own_plate)],
            OWN_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, own_confirm)],
            OWN_MANAGE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, own_manage)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    report_conv = ConversationHandler(
        entry_points=[
            CommandHandler("report", report_entry_cmd),
            CallbackQueryHandler(report_entry_cb, pattern="^report$"),
        ],
        states={
            REP_PLATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, rep_plate)],
            REP_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, rep_reason)],
            REP_PHOTO:  [
                MessageHandler(filters.PHOTO, rep_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rep_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(owner_conv)
    app.add_handler(report_conv)

    logger.info("Бот запущено ✅")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
