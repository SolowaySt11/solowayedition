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

# --- Главное меню ---
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
        keyboard = [[InlineKeyboardButton("➕ Добавить объект", callback_data=f"add_{folder}")]]
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
            InlineKeyboardButton("◀️ Назад", callback_data=f"card_{folder}_prev"),
            InlineKeyboardButton("Вперёд ▶️", callback_data=f"card_{folder}_next")
        ],
        [
            InlineKeyboardButton("➕ Добавить", callback_data=f"add_{folder}"),
            InlineKeyboardButton("✏️ Цена", callback_data=f"price_{prop_id}"),
            InlineKeyboardButton("✏️ Название", callback_data=f"title_{prop_id}")
        ]
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

# --- Добавление (простое, без запутанных состояний) ---
async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    folder = query.data.split("_")[1]
    context.user_data["add_folder"] = folder
    await query.edit_message_text("🔗 Отправь ссылку на объект James Edition:")

async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "add_folder" not in context.user_data:
        return
    url = update.message.text.strip()
    folder = context.user_data.pop("add_folder")

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO properties (url, title, folder, date_added)
        VALUES (?, ?, ?, ?)
    """, (url, "Без названия", folder, datetime.now().isoformat()))
    conn.commit()
    prop_id = c.lastrowid
    conn.close()

    context.user_data["new_property_id"] = prop_id
    await update.message.reply_text(f"✅ Добавлено (ID {prop_id})\n📝 Отправь название объекта:")

async def save_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "new_property_id" not in context.user_data:
        return
    prop_id = context.user_data.pop("new_property_id")
    title = update.message.text.strip()

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET title = ? WHERE id = ?", (title, prop_id))
    conn.commit()
    conn.close()

    context.user_data["price_property_id"] = prop_id
    await update.message.reply_text(f"✅ Название сохранено!\n💰 Теперь отправь цену (например: 1 500 000 USD):")

async def save_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "price_property_id" not in context.user_data:
        return
    prop_id = context.user_data.pop("price_property_id")
    price = update.message.text.strip()

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET price = ? WHERE id = ?", (price, prop_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Объект полностью добавлен!")

    # Показать главное меню
    keyboard = [
        [InlineKeyboardButton("🇳🇿 Новая Зеландия", callback_data="folder_Новая Зеландия")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="folder_США")],
        [InlineKeyboardButton("🇪🇺 Европа", callback_data="folder_Европа")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👇 Выбери папку, чтобы увидеть добавленный объект:", reply_markup=reply_markup)

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

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_title))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_price))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_title))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_price))
    print("James Edition бот (простой) запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()