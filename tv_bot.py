import json
import logging
import os
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, ConversationHandler

BOT_TOKEN = os.environ.get("BOT_TOKEN")
YOUR_CHAT_ID = int(os.environ.get("YOUR_CHAT_ID"))
ARCHIVE_CHANNEL = "@zzalalkfnfjejdnfjkfie"

EPISODES_FILE = Path(__file__).parent / "episodes.json"
HISTORY_FILE = Path(__file__).parent / "watch_history.json"
PAGE_SIZE = 10

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

WAITING_SERIES, WAITING_NAME, WAITING_VIDEO = range(3)

def load_episodes():
    if not EPISODES_FILE.exists():
        return {}
    with open(EPISODES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_episodes(data):
    with open(EPISODES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def record_watch(series, ep_name, file_id):
    history = load_history()
    history[series] = {"episode": ep_name, "file_id": file_id, "watched_at": datetime.now().strftime("%d/%m/%Y %H:%M")}
    save_history(history)

def get_last_watched(series):
    return load_history().get(series)

def get_next_episode(series, current_name):
    episodes = load_episodes().get(series, {}).get("episodes", [])
    for i, ep in enumerate(episodes):
        if ep["name"] == current_name and i + 1 < len(episodes):
            return episodes[i + 1]
    return None

def is_authorized(update):
    return update.effective_user.id == YOUR_CHAT_ID

def series_keyboard():
    data = load_episodes()
    history = load_history()
    if not data:
        return InlineKeyboardMarkup([])
    buttons = []
    for series in sorted(data.keys()):
        label = f"🔖 {series}" if series in history else series
        buttons.append([InlineKeyboardButton(label, callback_data=f"series|{series}|0")])
    return InlineKeyboardMarkup(buttons)

def episodes_keyboard(series, page):
    data = load_episodes()
    episodes = data.get(series, {}).get("episodes", [])
    last = get_last_watched(series)
    last_name = last["episode"] if last else None
    total_pages = max(1, (len(episodes) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    chunk = episodes[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    buttons = []
    if last_name:
        buttons.append([InlineKeyboardButton(f"▶️ Riprendi: {last_name}", callback_data=f"play|{series}|{last_name}")])
    for ep in chunk:
        label = f"✅ {ep['name']}" if ep["name"] == last_name else ep["name"]
        buttons.append([InlineKeyboardButton(label, callback_data=f"play|{series}|{ep['name']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prec", callback_data=f"series|{series}|{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Succ ▶️", callback_data=f"series|{series}|{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🏠 Home", callback_data="home")])
    text = f"📺 *{series}*"
    if total_pages > 1:
        text += f" — Pagina {page+1}/{total_pages}"
    text += "\nScegli un episodio:"
    if last_name:
        text += "\n✅ = ultimo visto"
    return text, InlineKeyboardMarkup(buttons)

async def cmd_start(update, context):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Non autorizzato.")
        return
    data = load_episodes()
    if not data:
        await update.message.reply_text("📭 Nessuna serie ancora.\n\nAggiungi il primo episodio con:\n`/nuovoep`", parse_mode="Markdown")
        return
    await update.message.reply_text("📺 *Scegli una serie:*\n🔖 = segnaposto salvato", reply_markup=series_keyboard(), parse_mode="Markdown")

async def cmd_cronologia(update, context):
    if not is_authorized(update):
        return
    history = load_history()
    if not history:
        await update.message.reply_text("📭 Nessun episodio visto ancora.")
        return
    lines = ["📋 *Ultimi episodi visti:*\n"]
    for series, data in sorted(history.items()):
        lines.append(f"🎬 *{series}*\n   └ {data['episode']}\n   └ 🕐 {data['watched_at']}\n")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_whoami(update, context):
    user = update.effective_user
    await update.message.reply_text(f"👤 Nome: {user.full_name}\n🆔 Chat ID: `{user.id}`", parse_mode="Markdown")

async def cmd_help(update, context):
    if not is_authorized(update):
        return
    await update.message.reply_text(
        "🤖 *Comandi disponibili:*\n\n"
        "/start — Menu principale\n"
        "/nuovoep — Aggiungi un episodio inviando il video\n"
        "/cronologia — Ultimi episodi visti\n"
        "/whoami — Il tuo Chat ID\n"
        "/help — Questo messaggio",
        parse_mode="Markdown"
    )

async def cmd_nuovoep(update, context):
    if not is_authorized(update):
        return
    await update.message.reply_text("🎬 *Nuovo episodio*\n\nCome si chiama la serie?\n\nEs: `One Piece`\n\nScrivi /annulla per uscire.", parse_mode="Markdown")
    return WAITING_SERIES

async def receive_series(update, context):
    if not is_authorized(update):
        return ConversationHandler.END
    context.user_data["series"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Serie: *{context.user_data['series']}*\n\nCome si chiama l'episodio?\n\nEs: `OP01 - Il re dei pirati`", parse_mode="Markdown")
    return WAITING_NAME

async def receive_name(update, context):
    if not is_authorized(update):
        return ConversationHandler.END
    context.user_data["ep_name"] = update.message.text.strip()
    await update.message.reply_text(f"✅ Episodio: *{context.user_data['ep_name']}*\n\nOra inviami il file video 🎥", parse_mode="Markdown")
    return WAITING_VIDEO

async def receive_video(update, context):
    if not is_authorized(update):
        return ConversationHandler.END
    if update.message.video:
        file_id = update.message.video.file_id
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Inviami un file video o documento.")
        return WAITING_VIDEO
    series = context.user_data["series"]
    ep_name = context.user_data["ep_name"]
    await update.message.reply_text("⏳ Salvo il video nel canale archivio...")
    try:
        sent = await context.bot.send_document(
            chat_id=ARCHIVE_CHANNEL,
            document=file_id,
            caption=f"🎬 {series} — {ep_name}"
        )
        archive_file_id = sent.document.file_id
    except Exception as e:
        await update.message.reply_text(f"❌ Errore nel salvare sul canale: {e}\n\nAssicurati che il bot sia admin del canale.")
        return ConversationHandler.END
    data = load_episodes()
    if series not in data:
        data[series] = {"episodes": []}
    existing = [ep["name"] for ep in data[series]["episodes"]]
    if ep_name in existing:
        await update.message.reply_text(f"⚠️ *{ep_name}* è già presente.", parse_mode="Markdown")
        return ConversationHandler.END
    data[series]["episodes"].append({"name": ep_name, "file_id": archive_file_id})
    save_episodes(data)
    total = len(data[series]["episodes"])
    await update.message.reply_text(f"✅ Salvato!\n\n🎬 *{series}*\n📺 {ep_name}\n📊 Totale episodi: {total}", parse_mode="Markdown")
    return ConversationHandler.END

async def cmd_annulla(update, context):
    await update.message.reply_text("❌ Operazione annullata.")
    return ConversationHandler.END

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    if not is_authorized(update):
        await query.edit_message_text("⛔ Non autorizzato.")
        return
    data = query.data
    if data == "home":
        await query.edit_message_text("📺 *Scegli una serie:*\n🔖 = segnaposto salvato", reply_markup=series_keyboard(), parse_mode="Markdown")
        return
    if data.startswith("series|"):
        _, series, page_str = data.split("|", 2)
        text, keyboard = episodes_keyboard(series, int(page_str))
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
        return
    if data.startswith("play|"):
        _, series, ep_name = data.split("|", 2)
        episodes_data = load_episodes()
        episodes = episodes_data.get(series, {}).get("episodes", [])
        ep = next((e for e in episodes if e["name"] == ep_name), None)
        if not ep:
            await query.edit_message_text("❌ Episodio non trovato.")
            return
        await query.edit_message_text(f"⏳ Carico *{ep_name}*...", parse_mode="Markdown")
        try:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=ep["file_id"],
                caption=f"🎬 *{series}*\n📺 {ep_name}",
                parse_mode="Markdown"
            )
        except Exception as e:
            await context.bot.send_message(chat_id=query.message.chat_id, text=f"❌ Errore: {e}")
            return
        record_watch(series, ep_name, ep["file_id"])
        next_ep = get_next_episode(series, ep_name)
        keyboard_rows = []
        if next_ep:
            keyboard_rows.append([InlineKeyboardButton(f"▶️ Prossimo: {next_ep['name']}", callback_data=f"play|{series}|{next_ep['name']}")])
        keyboard_rows.append([InlineKeyboardButton("🏠 Home", callback_data="home")])
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="✅ Buona visione! 🍿",
            reply_markup=InlineKeyboardMarkup(keyboard_rows)
        )

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("nuovoep", cmd_nuovoep)],
        states={
            WAITING_SERIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_series)],
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
            WAITING_VIDEO: [MessageHandler(filters.VIDEO | filters.Document.ALL, receive_video)],
        },
        fallbacks=[CommandHandler("annulla", cmd_annulla)],
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("cronologia", cmd_cronologia))
    app.add_handler(CommandHandler("whoami", cmd_whoami))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 Bot avviato!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
