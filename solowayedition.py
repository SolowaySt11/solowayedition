from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
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
            price_hkd REAL,
            price_rub REAL,
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

def get_exchange_rate():
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/HKD", timeout=10)
        data = r.json()
        return data['rates']['RUB']
    except:
        return 12.0

def fetch_property_data(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')

        # Название
        title = soup.find("meta", property="og:title")
        title = title["content"].strip() if title else "Без названия"

        # Цена (HKD)
        price_hkd = None
        meta_price = soup.find("meta", property="og:price:amount")
        if meta_price and meta_price.get("content"):
            price_hkd = float(meta_price["content"])
        if not price_hkd:
            price_span = soup.find("span", class_="price")
            if price_span:
                match = re.search(r"[\d,]+\.?\d*", price_span.text)
                if match:
                    price_hkd = float(match.group().replace(",", ""))

        rate = get_exchange_rate()
        price_rub = round(price_hkd * rate, 2) if price_hkd else None

        # Город и страна из URL
        country_match = re.search(r"/real_estate/[^/]+-([a-z-]+(?:-usa)?)/", url)
        country = country_match.group(1).replace("-", " ").title() if country_match else "Неизвестно"
        if "new zealand" in country.lower():
            country = "New Zealand"
        if "usa" in country.lower():
            country = "USA"

        city_match = re.search(r"/real_estate/([^/]+)-[a-z-]+(?:-usa)?/", url)
        city = city_match.group(1).replace("-", " ").title() if city_match else "Неизвестно"

        # Площадь
        land_area = ""
        house_area = ""
        area_text = soup.find("div", string=re.compile(r"Lot|Land|Acres", re.I))
        if area_text:
            land_area = area_text.find_parent().text.strip()
        area_text = soup.find("div", string=re.compile(r"Living|Floor|Home", re.I))
        if area_text:
            house_area = area_text.find_parent().text.strip()

        # Агентство
        agency = ""
        agent_elem = soup.find("div", class_="agent-name")
        if agent_elem:
            agency = agent_elem.text.strip()

        # Фото (одно)
        photo_url = ""
        meta_img = soup.find("meta", property="og:image")
        if meta_img and meta_img.get("content"):
            photo_url = meta_img["content"]

        return {
            "title": title,
            "price_hkd": price_hkd,
            "price_rub": price_rub,
            "city": city,
            "country": country,
            "land_area": land_area,
            "house_area": house_area,
            "agency": agency,
            "photo_url": photo_url,
            "url": url
        }
    except Exception as e:
        print(f"Ошибка парсинга {url}: {e}")
        return None

# --- Состояние диалога ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("➕ Добавить объект", callback_data="add_object")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🏡 *James Edition Трекер*\n\n"
        "Нажми кнопку и отправь ссылку на недвижимость с James Edition.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "add_object":
        await query.edit_message_text("📎 Отправь ссылку на объект James Edition:")
        context.user_data["awaiting_url"] = True

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_url"):
        return
    url = update.message.text.strip()
    if not url.startswith("https://www.jamesedition.com/"):
        await update.message.reply_text("❌ Это не похоже на ссылку James Edition. Попробуй ещё раз.")
        return
    context.user_data["awaiting_url"] = False
    await update.message.reply_text("🔄 Получаю данные...")
    data = fetch_property_data(url)
    if not data:
        await update.message.reply_text("❌ Не удалось получить данные по ссылке.")
        return

    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO properties (url, title, price_hkd, price_rub, city, country, land_area, house_area, agency, photo_url, folder, date_added)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (url, data['title'], data['price_hkd'], data['price_rub'], data['city'], data['country'],
              data['land_area'], data['house_area'], data['agency'], data['photo_url'], "Новая Зеландия", datetime.now().isoformat()))
        conn.commit()
        property_id = c.lastrowid
    except sqlite3.IntegrityError:
        await update.message.reply_text("⚠️ Этот объект уже есть в базе.")
        return
    finally:
        conn.close()

    # Текст
    msg = f"✅ *Добавлено! ID: {property_id}*\n\n"
    msg += f"🏠 *{data['title']}*\n"
    msg += f"💰 Цена: {data['price_hkd']:,.0f} HKD ≈ {data['price_rub']:,.0f} RUB\n" if data['price_hkd'] else "💰 Цена не указана\n"
    msg += f"📍 *{data['city']}, {data['country']}*\n"
    if data['land_area']:
        msg += f"🌿 Участок: {data['land_area']}\n"
    if data['house_area']:
        msg += f"🏡 Дом: {data['house_area']}\n"
    if data['agency']:
        msg += f"🏢 Агентство: {data['agency']}\n"
    msg += f"\n📎 *Ссылка:* {url}"
    await update.message.reply_text(msg, parse_mode="Markdown")

    # Фото
    if data['photo_url']:
        try:
            photo_response = requests.get(data['photo_url'], timeout=10)
            await update.message.reply_photo(photo=photo_response.content)
        except:
            pass

# --- Остальные команды (список, перемещение) ---
async def list_properties(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Укажи папку: /list Новая Зеландия")
        return
    folder = " ".join(context.args)
    conn = sqlite3.connect("edition.db")
    c = conn.cursor()
    c.execute("SELECT id, title, price_hkd, price_rub, city, country, url FROM properties WHERE folder = ? ORDER BY id", (folder,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        await update.message.reply_text(f"📭 В папке «{folder}» пока нет объектов.")
        return
    msg = f"📂 *Папка: {folder}*\n\n"
    for row in rows:
        msg += f"*ID {row[0]}* — {row[1]}\n"
        msg += f"💰 {row[2]:,.0f} HKD ≈ {row[3]:,.0f} RUB\n" if row[2] else "💰 Цена не указана\n"
        msg += f"📍 {row[4]}, {row[5]}\n🔗 [Ссылка]({row[6]})\n\n"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await update.message.reply_text("❌ Используй: /move <id> <Новая Зеландия | Европа | США>")
        return
    try:
        property_id = int(context.args[0])
        folder = " ".join(context.args[1:])
        if folder not in ["Новая Зеландия", "Европа", "США"]:
            await update.message.reply_text("❌ Папка должна быть: Новая Зеландия, Европа или США")
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
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    app.add_handler(CommandHandler("list", list_properties))
    app.add_handler(CommandHandler("move", move))
    print("James Edition бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()