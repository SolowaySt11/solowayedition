from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
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

# --- Вспомогательные функции ---
def get_exchange_rate():
    """Курс HKD к RUB через ExchangeRate-API"""
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/HKD", timeout=10)
        data = r.json()
        return data['rates']['RUB']
    except:
        return 12.0  # fallback курс, если API недоступен

import json
import re

def fetch_property_data(url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.jamesedition.com/"
        }
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. Название — берём из <title> или og:title
        title = soup.find("meta", property="og:title")
        title = title["content"].strip() if title else None
        if not title:
            title_tag = soup.find("title")
            title = title_tag.text.strip() if title_tag else "Без названия"

        # 2. Цена — сначала из JSON-LD, потом из og:price:amount
        price_hkd = None
        # JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if data.get("@type") == "Product" and data.get("offers"):
                    price_hkd = float(data["offers"]["price"])
                    break
            except:
                pass
        if not price_hkd:
            meta_price = soup.find("meta", property="og:price:amount")
            if meta_price and meta_price.get("content"):
                price_hkd = float(meta_price["content"])
        if not price_hkd:
            price_text = soup.find("div", class_="price")
            if price_text:
                match = re.search(r"[\d,]+\.?\d*", price_text.text)
                if match:
                    price_hkd = float(match.group().replace(",", ""))

        # 3. Конвертация в рубли
        rate = get_exchange_rate()
        price_rub = round(price_hkd * rate, 2) if price_hkd else None

        # 4. Город и страна — из URL (надёжнее)
        country_match = re.search(r"/real_estate/[^/]+-([a-z-]+(?:-usa)?)/", url)
        country = country_match.group(1).replace("-", " ").title() if country_match else "Неизвестно"
        # Убираем лишнее "New Zealand" -> "New Zealand"
        if "new zealand" in country.lower():
            country = "New Zealand"
        if "usa" in country.lower():
            country = "USA"

        city_match = re.search(r"/real_estate/([^/]+)-[a-z-]+(?:-usa)?/", url)
        city = city_match.group(1).replace("-", " ").title() if city_match else "Неизвестно"

        # 5. Площадь — ищем по ключевым словам в тексте
        land_area = ""
        house_area = ""
        for elem in soup.find_all(["div", "span", "li"]):
            text = elem.get_text(strip=True)
            if "acre" in text.lower() and "land" in text.lower():
                land_area = text
            if "sqft" in text.lower() and ("living" in text.lower() or "floor" in text.lower() or "home" in text.lower()):
                house_area = text

        # 6. Агентство
        agency = ""
        agent_elem = soup.find("div", class_="agent-name")
        if agent_elem:
            agency = agent_elem.text.strip()
        if not agency:
            agent_elem = soup.find("a", class_="agent")
            if agent_elem:
                agency = agent_elem.text.strip()

        # 7. Фото
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

# --- Обработчики команд ---
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление объекта по ссылке (/add url)"""
    if not context.args:
        await update.message.reply_text("❌ Используй: /add https://www.jamesedition.com/...")
        return
    url = context.args[0]
    await update.message.reply_text("🔄 Получаю данные с James Edition...")
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

    # Формируем ответ
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

    # Отправляем фото, если есть
    if data['photo_url']:
        try:
            photo_response = requests.get(data['photo_url'], timeout=10)
            await update.message.reply_photo(photo=photo_response.content)
        except:
            pass

async def list_properties(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список объектов в папке (/list Новая Зеландия)"""
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
    """Переместить объект в папку (/move id Новая Зеландия)"""
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏡 *James Edition Трекер*\n\n"
        "Команды:\n"
        "/add <url> — добавить объект\n"
        "/list <папка> — показать объекты в папке (Новая Зеландия, Европа, США)\n"
        "/move <id> <папка> — переместить объект в папку\n"
        "/start — это сообщение",
        parse_mode="Markdown"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_properties))
    app.add_handler(CommandHandler("move", move))
    print("James Edition бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()