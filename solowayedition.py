from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime

TOKEN = "8874435972:AAENcmVfdVyVaV2Ck4bezo9n82hH2ykJp5E"

# --- База данных ---
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

def get_folder_from_url(url):
    u = url.lower()
    if "new-zealand" in u:
        return "Новая Зеландия"
    if "usa" in u:
        return "США"
    return "Европа"

# --- Главное меню (только кнопки) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇳🇿 Новая Зеландия", callback_data="folder_Новая Зеландия")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="folder_США")],
        [InlineKeyboardButton("🇪🇺 Европа", callback_data="folder_Европа")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🏡 *James Edition Трекер*\n\n👇 *Выбери папку:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# --- Показать карточку ---
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
            f"📂 *{folder}*\n\nПока ничего нет.",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return

    if index < 0:
        index = 0
    if index >= len(rows):
        index = len(rows) - 1

    prop_id, url, title, price = rows[index]
    context.user_data[f"card_{folder}"] = index

    caption = f"*ID {prop_id}* — {title}\n"
    if price:
        caption += f"💰 Цена: {price}\n"

    keyboard = [
        [InlineKeyboardButton("🔗 Открыть ссылку", url=url)],
        [
            InlineKeyboardButton("◀️", callback_data=f"card_{folder}_prev"),
            InlineKeyboardButton("▶️", callback_data=f"card_{folder}_next")
        ],
        [
            InlineKeyboardButton("➕ Добавить", callback_data=f"add_{folder}"),
            InlineKeyboardButton("✏️ Цена", callback_data=f"price_{prop_id}"),
            InlineKeyboardButton("✏️ Название", callback_data=f"title_{prop_id}")
        ],
        [InlineKeyboardButton("🗑 Переместить", callback_data=f"move_{prop_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(caption, parse_mode="Markdown", reply_markup=reply_markup)

# --- Навигация ---
async def card_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    parts = data.split("_")
    folder = parts[1]
    direction = parts[2]
    current = context.user_data.get(f"card_{folder}", 0)
    new_index = current + 1 if direction == "next" else current - 1
    await show_card(update, context, folder, new_index)

# --- Добавление (пошаговое, только кнопки) ---
async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    folder = query.data.split("_")[1]
    context.user_data["add_folder"] = folder
    context.user_data["add_step"] = "url"
    await query.edit_message_text("🔗 Отправь ссылку на James Edition:")

async def handle_add_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("add_step")
    if step != "url":
        return

    url = update.message.text.strip()
    folder = context.user_data["add_folder"]
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO properties (url, title, folder, date_added)
        VALUES (?, ?, ?, ?)
    """, (url, "Без названия", folder, datetime.now().isoformat()))
    conn.commit()
    prop_id = c.lastrowid
    conn.close()

    context.user_data["add_id"] = prop_id
    context.user_data["add_step"] = "title"
    await update.message.reply_text(f"✅ Добавлено (ID {prop_id})\n📝 Теперь отправь **название**:")

async def handle_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("add_step")
    if step != "title":
        return
    prop_id = context.user_data["add_id"]
    title = update.message.text.strip()

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET title = ? WHERE id = ?", (title, prop_id))
    conn.commit()
    conn.close()

    context.user_data["add_step"] = "price"
    await update.message.reply_text(f"✅ Название сохранено!\n💰 Теперь отправь **цену**:")

async def handle_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("add_step")
    if step != "price":
        return
    prop_id = context.user_data.pop("add_id")
    price = update.message.text.strip()

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET price = ? WHERE id = ?", (price, prop_id))
    conn.commit()
    conn.close()

    context.user_data.pop("add_folder", None)
    context.user_data.pop("add_step", None)

    await update.message.reply_text("✅ Объект полностью добавлен!")

    # Показать главное меню
    keyboard = [
        [InlineKeyboardButton("🇳🇿 Новая Зеландия", callback_data="folder_Новая Зеландия")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="folder_США")],
        [InlineKeyboardButton("🇪🇺 Европа", callback_data="folder_Европа")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👇 *Выбери папку, чтобы увидеть объект:*", reply_markup=reply_markup, parse_mode="Markdown")

# --- Редактирование ---
async def edit_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prop_id = int(query.data.split("_")[1])
    context.user_data["edit_title_id"] = prop_id
    await query.edit_message_text("📝 Введи новое название:")

async def save_edit_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "edit_title_id" not in context.user_data:
        return
    prop_id = context.user_data.pop("edit_title_id")
    new_title = update.message.text.strip()
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET title = ? WHERE id = ?", (new_title, prop_id))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Название изменено.")

async def edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prop_id = int(query.data.split("_")[1])
    context.user_data["edit_price_id"] = prop_id
    await query.edit_message_text("💰 Введи новую цену:")

async def save_edit_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "edit_price_id" not in context.user_data:
        return
    prop_id = context.user_data.pop("edit_price_id")
    new_price = update.message.text.strip()
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET price = ? WHERE id = ?", (new_price, prop_id))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ Цена изменена.")

# --- Перемещение ---
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

# --- Главный callback ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("folder_"):
        folder = data[7:]
        await show_card(update, context, folder, 0)
    elif data.startswith("card_"):
        await card_nav(update, context)
    elif data.startswith("add_"):
        await start_add(update, context)
    elif data.startswith("price_"):
        await edit_price(update, context)
    elif data.startswith("title_"):
        await edit_title(update, context)
    elif data.startswith("move_"):
        await ask_move(update, context)
    elif data.startswith("move_to_"):
        await move_to(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_title_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_price_input))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_title))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_price))
    print("James Edition бот (полностью кнопочный) запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()