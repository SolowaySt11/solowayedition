from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime
import re

TOKEN = "8874435972:AAENcmVfdVyVaV2Ck4bezo9n82hH2ykJp5E"

# --- База данных ---
def init_db():
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            title TEXT,
            price TEXT,
            folder TEXT,
            date_added TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Определение папки по URL ---
def get_folder_from_url(url):
    u = url.lower()
    if "new-zealand" in u:
        return "Новая Зеландия"
    if "usa" in u:
        return "США"
    if "italy" in u or "spain" in u or "france" in u:
        return "Европа"
    return "Другая страна"

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

# --- Показать объекты в папке + кнопка "Добавить" ---
async def show_folder(update: Update, context: ContextTypes.DEFAULT_TYPE, folder, page=0):
    limit = 5
    offset = page * limit
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("SELECT id, title, price FROM properties WHERE folder = ? ORDER BY id LIMIT ? OFFSET ?", (folder, limit, offset))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM properties WHERE folder = ?", (folder,))
    total = c.fetchone()[0]
    conn.close()

    msg = f"📂 *{folder}* (стр. {page+1})\n\n" if rows else f"📂 *{folder}*\n\n"
    for row in rows:
        msg += f"*ID {row[0]}* — {row[1]}\n"
        if row[2]:
            msg += f"💰 Цена: {row[2]}\n"
        msg += "\n"

    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("◀️ Назад", callback_data=f"page_{folder}_{page-1}"))
    if (page+1)*limit < total:
        keyboard.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f"page_{folder}_{page+1}"))
    keyboard.append([InlineKeyboardButton("➕ Добавить объект", callback_data=f"add_{folder}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(msg, parse_mode="Markdown", reply_markup=reply_markup)

# --- Начало добавления (просим ссылку) ---
async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    folder = query.data.split("_")[1]
    context.user_data["add_folder"] = folder
    await query.edit_message_text("🔗 Отправь ссылку на объект James Edition:")

# --- Получение ссылки и сохранение ---
async def receive_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "add_folder" not in context.user_data:
        return
    url = update.message.text.strip()
    folder = context.user_data.pop("add_folder")
    property_id = None

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO properties (url, title, folder, date_added)
            VALUES (?, ?, ?, ?)
        """, (url, "Без названия", folder, datetime.now().isoformat()))
        conn.commit()
        property_id = c.lastrowid
    except sqlite3.IntegrityError:
        await update.message.reply_text("⚠️ Этот объект уже есть.")
        return
    finally:
        conn.close()

    keyboard = [[InlineKeyboardButton("✏️ Указать цену", callback_data=f"price_{property_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"✅ Добавлено в папку «{folder}» (ID {property_id})\n\nТеперь можешь добавить цену:",
        reply_markup=reply_markup
    )

# --- Запрос цены ---
async def ask_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    property_id = int(query.data.split("_")[1])
    context.user_data["edit_price_id"] = property_id
    await query.edit_message_text("💰 Введи цену (например: 1 500 000 USD):")

# --- Сохранение цены ---
async def save_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "edit_price_id" not in context.user_data:
        return
    property_id = context.user_data.pop("edit_price_id")
    price = update.message.text.strip()

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET price = ? WHERE id = ?", (price, property_id))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ Цена для ID {property_id} сохранена.")

# --- Запрос перемещения ---
async def ask_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    property_id = int(query.data.split("_")[1])
    context.user_data["move_id"] = property_id
    keyboard = [
        [InlineKeyboardButton("🇳🇿 Новая Зеландия", callback_data="move_to_Новая Зеландия")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="move_to_США")],
        [InlineKeyboardButton("🇪🇺 Европа", callback_data="move_to_Европа")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🗂 Выбери новую папку:", reply_markup=reply_markup)

# --- Перемещение ---
async def move_to(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if "move_id" not in context.user_data:
        return
    property_id = context.user_data.pop("move_id")
    new_folder = query.data.split("_")[2]
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET folder = ? WHERE id = ?", (new_folder, property_id))
    conn.commit()
    conn.close()
    await query.edit_message_text(f"✅ Объект ID {property_id} перемещён в папку «{new_folder}».")

# --- Главный callback ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("folder_"):
        folder = data[7:]
        await show_folder(update, context, folder, 0)
    elif data.startswith("page_"):
        parts = data.split("_")
        folder = parts[1]
        page = int(parts[2])
        await show_folder(update, context, folder, page)
    elif data.startswith("add_"):
        await start_add(update, context)
    elif data.startswith("price_"):
        await ask_price(update, context)
    elif data.startswith("move_"):
        await ask_move(update, context)
    elif data.startswith("move_to_"):
        await move_to(update, context)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_url))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_price))
    print("James Edition бот (полностью кнопочный) запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()