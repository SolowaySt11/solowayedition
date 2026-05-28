from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup

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
            photo TEXT,
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
    if "italy" in u or "spain" in u or "france" in u:
        return "Европа"
    return "Другая страна"

def try_get_photo(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            meta = soup.find("meta", property="og:image")
            if meta and meta.get("content"):
                return meta["content"]
    except:
        pass
    return None

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
    c.execute("SELECT id, url, title, price, photo FROM properties WHERE folder = ? ORDER BY id", (folder,))
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

    prop_id, url, title, price, photo = rows[index]
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
            InlineKeyboardButton("🖼 Фото", callback_data=f"photo_{prop_id}")
        ],
        [InlineKeyboardButton("🗑 Переместить", callback_data=f"move_{prop_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if photo and photo.startswith("http"):
        try:
            r = requests.get(photo, timeout=10)
            await update.callback_query.edit_message_media(
                media=InputMediaPhoto(media=r.content, caption=caption, parse_mode="Markdown"),
                reply_markup=reply_markup
            )
        except:
            await update.callback_query.edit_message_text(caption, parse_mode="Markdown", reply_markup=reply_markup)
    else:
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

# --- Добавление ---
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
    photo = try_get_photo(url)

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO properties (url, title, photo, folder, date_added)
            VALUES (?, ?, ?, ?, ?)
        """, (url, "Без названия", photo, folder, datetime.now().isoformat()))
        conn.commit()
        prop_id = c.lastrowid
    except sqlite3.IntegrityError:
        await update.message.reply_text("⚠️ Объект уже есть.")
        return
    finally:
        conn.close()

    context.user_data["awaiting_price"] = prop_id
    await update.message.reply_text(f"✅ Добавлено (ID {prop_id})\n💰 Теперь отправь цену:")

async def save_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_price" not in context.user_data:
        return
    prop_id = context.user_data.pop("awaiting_price")
    price = update.message.text.strip()

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET price = ? WHERE id = ?", (price, prop_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Цена сохранена!")

    keyboard = [
        [InlineKeyboardButton("🇳🇿 Новая Зеландия", callback_data="folder_Новая Зеландия")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="folder_США")],
        [InlineKeyboardButton("🇪🇺 Европа", callback_data="folder_Европа")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👇 Выбери папку:", reply_markup=reply_markup)

# --- Ручное добавление фото ---
async def ask_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prop_id = int(query.data.split("_")[1])
    context.user_data["photo_id"] = prop_id
    await query.edit_message_text("🖼 Отправь ссылку на фото (прямую ссылку, например: https://...jpg):")

async def save_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "photo_id" not in context.user_data:
        return
    prop_id = context.user_data.pop("photo_id")
    photo_url = update.message.text.strip()

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("UPDATE properties SET photo = ? WHERE id = ?", (photo_url, prop_id))
    conn.commit()
    conn.close()

    await update.message.reply_text("✅ Фото сохранено!")

    keyboard = [
        [InlineKeyboardButton("🇳🇿 Новая Зеландия", callback_data="folder_Новая Зеландия")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="folder_США")],
        [InlineKeyboardButton("🇪🇺 Европа", callback_data="folder_Европа")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("👇 Выбери папку, чтобы увидеть объект с фото:", reply_markup=reply_markup)

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
        prop_id = int(data.split("_")[1])
        context.user_data["awaiting_price"] = prop_id
        await query.edit_message_text("💰 Введи новую цену:")
    elif data.startswith("photo_"):
        await ask_photo(update, context)
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_photo))
    print("James Edition бот (галерея + ручное фото) запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()