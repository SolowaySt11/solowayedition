from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime

TOKEN = "8874435972:AAENcmVfdVyVaV2Ck4bezo9n82hH2ykJp5E"

def init_db():
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            title TEXT,
            price TEXT,
            folder TEXT,
            date_added TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇳🇿 Новая Зеландия", callback_data="folder_Новая Зеландия")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="folder_США")],
        [InlineKeyboardButton("🇪🇺 Европа", callback_data="folder_Европа")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            "🏡 James Edition Трекер\n\n👇 Выбери папку:",
            reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            "🏡 James Edition Трекер\n\n👇 Выбери папку:",
            reply_markup=reply_markup
        )

async def show_card(update: Update, context: ContextTypes.DEFAULT_TYPE, folder, index=0):
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("SELECT id, url, title, price FROM properties WHERE folder = ? ORDER BY id", (folder,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        keyboard = [[InlineKeyboardButton("➕ Добавить", callback_data=f"add_{folder}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            f"📂 {folder}\n\nПока ничего нет.",
            reply_markup=reply_markup
        )
        return

    if index < 0:
        index = 0
    if index >= len(rows):
        index = len(rows) - 1

    prop_id, url, title, price = rows[index]
    context.user_data[f"card_{folder}"] = index

    caption = f"🏠 {title}\n"
    if price:
        caption += f"🔗 [Превью]({price})\n"

    keyboard = [
        [InlineKeyboardButton("🔗 Открыть ссылку", url=url)],
        [
            InlineKeyboardButton("◀️", callback_data=f"card_{folder}_prev"),
            InlineKeyboardButton(f"{index + 1}/{len(rows)}", callback_data="noop"),
            InlineKeyboardButton("▶️", callback_data=f"card_{folder}_next")
        ],
        [
            InlineKeyboardButton("➕ Добавить", callback_data=f"add_{folder}"),
            InlineKeyboardButton("📝 Изменить ссылку", callback_data=f"edit_{prop_id}")
        ],
        [InlineKeyboardButton("🗑 Переместить", callback_data=f"move_{prop_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(caption, reply_markup=reply_markup, parse_mode="Markdown")

async def card_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    parts = data.split("_")
    folder = parts[1]
    direction = parts[2]
    current = context.user_data.get(f"card_{folder}", 0)
    new_index = current + 1 if direction == "next" else current - 1
    await show_card(update, context, folder, new_index)

async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    folder = query.data.split("_")[1]
    context.user_data["add_folder"] = folder
    context.user_data["awaiting_url1"] = True
    context.user_data["awaiting_url2"] = False
    context.user_data["awaiting_edit"] = False
    await query.edit_message_text("🔗 Отправь **первую ссылку** (на дом):", parse_mode="Markdown")

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, какое действие ожидается
    if context.user_data.get("awaiting_url1"):
        await handle_url1(update, context)
    elif context.user_data.get("awaiting_url2"):
        await handle_url2(update, context)
    elif context.user_data.get("awaiting_edit"):
        await handle_edit(update, context)

async def handle_url1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url1 = update.message.text.strip()
    folder = context.user_data["add_folder"]

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("INSERT INTO properties (url, title, folder, date_added) VALUES (?, ?, ?, ?)",
              (url1, url1, folder, datetime.now().isoformat()))
    conn.commit()
    prop_id = c.lastrowid
    conn.close()

    context.user_data["awaiting_url1"] = False
    context.user_data["awaiting_url2"] = True
    context.user_data["temp_id"] = prop_id
    await update.message.reply_text("🔗 Теперь отправь **вторую ссылку** (она будет показывать превью в карточке):", parse_mode="Markdown")

async def handle_url2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url2 = update.message.text.strip()
    prop_id = context.user_data.pop("temp_id")
    context.user_data["awaiting_url2"] = False

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET price = ? WHERE id = ?", (url2, prop_id))
    conn.commit()
    conn.close()

    # Очищаем все состояния ожидания
    context.user_data.pop("add_folder", None)
    
    await update.message.reply_text("✅ Объект добавлен. Используй /start чтобы увидеть карточки.")
    await start(update, context)

async def edit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prop_id = int(query.data.split("_")[1])
    context.user_data["edit_id"] = prop_id
    context.user_data["awaiting_edit"] = True
    context.user_data["awaiting_url1"] = False
    context.user_data["awaiting_url2"] = False
    await query.edit_message_text("🔗 Отправь **новую ссылку** (она заменит текущую):", parse_mode="Markdown")

async def handle_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prop_id = context.user_data.pop("edit_id")
    context.user_data["awaiting_edit"] = False
    new_link = update.message.text.strip()

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET price = ? WHERE id = ?", (new_link, prop_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Ссылка обновлена. Используй /start чтобы увидеть изменения.")

async def ask_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prop_id = int(query.data.split("_")[1])
    context.user_data["move_id"] = prop_id
    keyboard = [
        [InlineKeyboardButton("🇳🇿 Новая Зеландия", callback_data="move_to_Новая Зеландия")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="move_to_США")],
        [InlineKeyboardButton("🇪🇺 Европа", callback_data="move_to_Европа")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🗂 Выбери новую папку:", reply_markup=reply_markup)

async def move_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if "move_id" not in context.user_data:
        return
    prop_id = context.user_data.pop("move_id")
    new_folder = query.data.split("_")[2]
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET folder = ? WHERE id = ?", (new_folder, prop_id))
    conn.commit()
    conn.close()
    await query.edit_message_text(f"✅ Объект перемещён в папку «{new_folder}».")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "noop":
        return
    elif data.startswith("folder_"):
        folder = data.split("_", 1)[1]
        await show_card(update, context, folder, 0)
    elif data.startswith("card_"):
        await card_nav(update, context)
    elif data.startswith("add_"):
        await start_add(update, context)
    elif data.startswith("edit_"):
        await edit_link(update, context)
    elif data.startswith("move_"):
        await ask_move(update, context)
    elif data.startswith("move_to_"):
        await move_to(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    # Единый обработчик для всех текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()