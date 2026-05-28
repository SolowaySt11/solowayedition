from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime
import re
import os

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
            city TEXT,
            country TEXT,
            land_area TEXT,
            house_area TEXT,
            agency TEXT,
            photo_url TEXT,
            folder TEXT,
            date_added TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- Определение страны по URL (без парсинга страницы) ---
def get_folder_from_url(url):
    u = url.lower()
    if "new-zealand" in u:
        return "Новая Зеландия"
    if "/usa/" in u or "united-states" in u:
        return "США"
    if "/italy/" in u:
        return "Италия"
    if "/spain/" in u:
        return "Испания"
    if "/france/" in u:
        return "Франция"
    return "Другая страна"

# --- Попытка достать главное фото (og:image) без полноценного парсинга ---
def try_get_photo(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9"
        }
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            meta = soup.find("meta", property="og:image")
            if meta and meta.get("content"):
                return meta["content"]
    except:
        pass
    return None

# --- Добавление объекта (только ссылка, без цены) ---
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Используй: /add https://www.jamesedition.com/...")
        return
    url = context.args[0]
    folder = get_folder_from_url(url)

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
        await update.message.reply_text("⚠️ Этот объект уже есть в базе.")
        return
    finally:
        conn.close()

    # Пробуем получить фото
    photo_url = try_get_photo(url)
    if photo_url:
        try:
            photo_response = requests.get(photo_url, timeout=10)
            await update.message.reply_photo(photo=photo_response.content, caption=f"✅ Добавлено в папку «{folder}» (ID {property_id})")
        except:
            await update.message.reply_text(f"✅ Добавлено в папку «{folder}» (ID {property_id})\n(фото не загрузилось)")
    else:
        await update.message.reply_text(f"✅ Добавлено в папку «{folder}» (ID {property_id})")

    await update.message.reply_text("✏️ Теперь можешь добавить цену, фото, описание командой /edit <id>")

# --- Ручное редактирование ---
async def edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Используй: /edit <id> цена|фото|название <значение>")
        return
    property_id = int(context.args[0])
    field = context.args[1].lower()
    value = " ".join(context.args[2:]) if len(context.args) > 2 else ""

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    if field == "цена":
        c.execute("UPDATE properties SET price = ? WHERE id = ?", (value, property_id))
    elif field == "фото":
        c.execute("UPDATE properties SET photo_url = ? WHERE id = ?", (value, property_id))
    elif field == "название":
        c.execute("UPDATE properties SET title = ? WHERE id = ?", (value, property_id))
    else:
        await update.message.reply_text("❌ Можно редактировать: цена, фото, название")
        conn.close()
        return
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ Поле «{field}» для ID {property_id} обновлено.")

# --- Пагинация и список по папке ---
async def list_folder(update: Update, context: ContextTypes.DEFAULT_TYPE, folder, page=0):
    limit = 10
    offset = page * limit
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("SELECT id, title, price FROM properties WHERE folder = ? ORDER BY id LIMIT ? OFFSET ?", (folder, limit, offset))
    rows = c.fetchall()
    c.execute("SELECT COUNT(*) FROM properties WHERE folder = ?", (folder,))
    total = c.fetchone()[0]
    conn.close()

    if not rows:
        await update.message.reply_text(f"📭 В папке «{folder}» пока нет объектов.")
        return

    msg = f"📂 *Папка: {folder}* (страница {page+1})\n\n"
    for row in rows:
        msg += f"*ID {row[0]}* — {row[1]}\n"
        if row[2]:
            msg += f"💰 Цена: {row[2]}\n"
        else:
            msg += "💰 Цена не указана\n"
        msg += "\n"

    keyboard = []
    if page > 0:
        keyboard.append(InlineKeyboardButton("◀️ Назад", callback_data=f"{folder}_page_{page-1}"))
    if (page+1)*limit < total:
        keyboard.append(InlineKeyboardButton("Вперёд ▶️", callback_data=f"{folder}_page_{page+1}"))
    if keyboard:
        reply_markup = InlineKeyboardMarkup([keyboard])
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("Новая Зеландия_page_"):
        page = int(data.split("_")[-1])
        await list_folder(update, context, "Новая Зеландия", page)
    elif data.startswith("США_page_"):
        page = int(data.split("_")[-1])
        await list_folder(update, context, "США", page)
    elif data.startswith("Европа_page_"):
        page = int(data.split("_")[-1])
        await list_folder(update, context, "Европа", page)
    else:
        await start(update, context)

# --- Главное меню с кнопками папок ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇳🇿 Новая Зеландия", callback_data="Новая Зеландия_page_0")],
        [InlineKeyboardButton("🇺🇸 США", callback_data="США_page_0")],
        [InlineKeyboardButton("🇪🇺 Европа", callback_data="Европа_page_0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🏡 *James Edition Трекер*\n\n"
        "Команды:\n"
        "/add <url> — добавить объект (папка определится автоматически)\n"
        "/edit <id> цена|фото|название <значение> — редактировать\n"
        "/move <id> <папка> — переместить в другую папку\n"
        "/list <папка> — показать объекты в папке\n\n"
        "👇 *Выбери папку:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Используй: /move <id> <Новая Зеландия | США | Европа>")
        return
    try:
        property_id = int(context.args[0])
        folder = " ".join(context.args[1:])
        if folder not in ["Новая Зеландия", "США", "Европа"]:
            await update.message.reply_text("❌ Папка должна быть: Новая Зеландия, США или Европа")
            return
        conn = sqlite3.connect("edition.db")
        c = conn.cursor()
        c.execute("UPDATE properties SET folder = ? WHERE id = ?", (folder, property_id))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Объект ID {property_id} перемещён в папку «{folder}».")
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("edit", edit))
    app.add_handler(CommandHandler("move", move))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("James Edition бот (финальная стабильная версия) запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()