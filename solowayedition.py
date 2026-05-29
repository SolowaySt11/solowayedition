from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
from datetime import datetime
import os
import requests
import re
import json
from bs4 import BeautifulSoup
import html

TOKEN = "8874435972:AAENcmVfdVyVaV2Ck4bezo9n82hH2ykJp5E"

# Путь для постоянного хранения
DB_PATH = "/data/edition.db"

# Создаём папку /data если её нет
os.makedirs("/data", exist_ok=True)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            title TEXT,
            price TEXT,
            folder TEXT,
            date_added TEXT,
            details TEXT
        )
    """)
    # Добавляем колонку details если её нет (для старых баз)
    try:
        c.execute("ALTER TABLE properties ADD COLUMN details TEXT")
    except:
        pass
    conn.commit()
    conn.close()

init_db()

ALLOWED_USERS = {
    "Соловей": "2011",
}

def try_parse_james_edition(url):
    """
    Пытается достать данные из Google Cache
    Возвращает словарь с данными или None
    """
    try:
        # Попытка 1: Google Cache
        cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(cache_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()
            
            # ===== НАЗВАНИЕ =====
            title = None
            
            # Способ 1: og:title
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content'].strip()
            
            # Способ 2: Обычный title
            if not title:
                title_tag = soup.find('title')
                if title_tag:
                    title_text = title_tag.get_text()
                    title_text = re.sub(r'\s*[-|]\s*James\s*Edition.*', '', title_text, flags=re.IGNORECASE)
                    title_text = title_text.replace('Google Search', '').strip()
                    if title_text:
                        title = title_text
            
            # УБИРАЕМ ID ИЗ НАЗВАНИЯ (если остался)
            if title:
                # Убираем числа в конце (6+ цифр)
                title = re.sub(r'\s+\d{6,}\s*$', '', title)
                title = title.strip()
            
            # Способ 3: Из URL
            if not title:
                parts = url.rstrip('/').split('/')
                if len(parts) > 1:
                    raw_title = parts[-1].replace('-', ' ').title()
                    raw_title = re.sub(r'\s+\d{6,}\s*$', '', raw_title)
                    title = raw_title.strip()
                else:
                    title = url
            
            # ===== ЦЕНА =====
            price = None
            
            # Способ 0: Meta-теги цены
            og_price = soup.find('meta', property='product:price:amount')
            if og_price and og_price.get('content'):
                currency = soup.find('meta', property='product:price:currency')
                curr = currency['content'] if currency and currency.get('content') else '$'
                price = f"{curr}{og_price['content']}"
            
            # Способ 1: JSON-LD структурированные данные
            if not price:
                scripts = soup.find_all('script', type='application/ld+json')
                for script in scripts:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, dict):
                            # Ищем цену в offers
                            offers = data.get('offers', {})
                            if isinstance(offers, dict):
                                price_val = offers.get('price')
                                currency_val = offers.get('priceCurrency', 'USD')
                                if price_val:
                                    symbols = {'USD': '$', 'EUR': '€', 'GBP': '£'}
                                    curr_symbol = symbols.get(currency_val, '$')
                                    price = f"{curr_symbol}{price_val:,.0f}"
                                    break
                    except:
                        pass
            
            # Способ 2: Регулярки по тексту
            if not price:
                price_patterns = [
                    r'(?:Price|price|PRICE)\s*:?\s*([\$€£]\s*[\d,]+(?:\.\d{2})?)',
                    r'([\$€£]\s*[\d,]{1,10}(?:\.\d{2})?)',
                    r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:USD|EUR|GBP)',
                ]
                
                for pattern in price_patterns:
                    match = re.search(pattern, text[:2000])  # Ищем только в начале текста
                    if match:
                        price = match.group(1) if len(match.groups()) > 0 else match.group()
                        price = price.replace(' ', '')
                        if not price.startswith(('$', '€', '£')):
                            if '$' in text[:500]:
                                price = '$' + price
                            elif '€' in text[:500]:
                                price = '€' + price
                            elif '£' in text[:500]:
                                price = '£' + price
                        break
            
            # ===== ХАРАКТЕРИСТИКИ =====
            details = []
            
            # Площадь
            area_patterns = [
                r'(\d{2,4})\s*m²',
                r'(\d{2,4})\s*sq\.?\s*ft',
                r'(\d{2,4})\s*sqm',
            ]
            for pattern in area_patterns:
                area_match = re.search(pattern, text, re.IGNORECASE)
                if area_match:
                    details.append(f"📐 {area_match.group(1)} m²")
                    break
            
            # Спальни
            beds_match = re.search(r'(\d+)\s*(?:bedroom|beds?)', text, re.IGNORECASE)
            if beds_match:
                details.append(f"🛏 {beds_match.group(1)} спальни")
            
            # Ванные
            baths_match = re.search(r'(\d+)\s*(?:bathroom|baths?)', text, re.IGNORECASE)
            if baths_match:
                details.append(f"🚿 {baths_match.group(1)} ванные")
            
            # Локация из URL
            location_match = re.search(r'jamesedition\.com/real_?estate/([^/]+/[^/]+)/', url)
            if location_match:
                loc = location_match.group(1).replace('-', ' ').title()
                details.append(f"📍 {loc}")
            
            details_str = ' | '.join(details) if details else ''
            
            if title or price or details_str:
                return {
                    'title': title or url,
                    'price': price or '',
                    'details': details_str
                }
        
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
    
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "authenticated" not in context.user_data:
        await update.message.reply_text("🔐 Привет! Введи свой ник:")
        context.user_data["awaiting_username"] = True
        return
    
    await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    else:
        await update.callback_query.edit_message_text(
            "🏡 James Edition Трекер\n\n👇 Выбери папку:",
            reply_markup=reply_markup
        )

async def show_card(update: Update, context: ContextTypes.DEFAULT_TYPE, folder, index=0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, url, title, price, details FROM properties WHERE folder = ? ORDER BY id", (folder,))
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

    prop_id, url, title, price, details = rows[index]
    context.user_data[f"card_{folder}"] = index

    caption = f"🏠 <a href='{url}'>{title}</a>\n"
    if price:
        caption += f"💰 {price}\n"
    if details:
        caption += f"📋 {details}\n"

    keyboard = [
        [InlineKeyboardButton("🔗 Открыть ссылку", url=url)],
        [
            InlineKeyboardButton("◀️", callback_data=f"card_{folder}_prev"),
            InlineKeyboardButton(f"{index + 1}/{len(rows)}", callback_data="noop"),
            InlineKeyboardButton("▶️", callback_data=f"card_{folder}_next")
        ],
        [
            InlineKeyboardButton("➕ Добавить", callback_data=f"add_{folder}"),
            InlineKeyboardButton("📝 Изменить", callback_data=f"edit_{prop_id}")
        ],
        [InlineKeyboardButton("🗑 Переместить", callback_data=f"move_{prop_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(caption, reply_markup=reply_markup, parse_mode="HTML")

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
    await query.edit_message_text(
        "🔗 Отправь ссылку на объект James Edition\n\n"
        "🤖 Я попробую автоматически достать цену и описание!",
        parse_mode="Markdown"
    )

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Сначала проверяем аутентификацию
    if context.user_data.get("awaiting_username") or context.user_data.get("awaiting_password"):
        await handle_auth(update, context)
        return
    
    if "authenticated" not in context.user_data:
        await update.message.reply_text("🔐 Сначала авторизуйся: /start")
        return
    
    if context.user_data.get("awaiting_url1"):
        await handle_url1(update, context)
    elif context.user_data.get("awaiting_manual_title"):
        await handle_manual_title(update, context)
    elif context.user_data.get("awaiting_url2"):
        await handle_url2(update, context)
    elif context.user_data.get("awaiting_edit"):
        await handle_edit(update, context)

async def handle_auth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_username"):
        username = update.message.text.strip()
        if username in ALLOWED_USERS:
            context.user_data["temp_username"] = username
            context.user_data["awaiting_username"] = False
            context.user_data["awaiting_password"] = True
            await update.message.reply_text("🔑 Введи пароль:")
        else:
            await update.message.reply_text("❌ Неверный ник. Попробуй ещё раз:")
        return

    if context.user_data.get("awaiting_password"):
        password = update.message.text.strip()
        username = context.user_data.get("temp_username")
        if ALLOWED_USERS.get(username) == password:
            context.user_data["authenticated"] = True
            context.user_data.pop("temp_username", None)
            context.user_data.pop("awaiting_password", None)
            await update.message.reply_text("✅ Доступ разрешён!")
            await show_main_menu(update, context)
        else:
            context.user_data.pop("temp_username", None)
            context.user_data.pop("awaiting_password", None)
            context.user_data.pop("awaiting_username", None)
            await update.message.reply_text("❌ Неверный пароль. Начни заново с /start")
        return

async def handle_url1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url1 = update.message.text.strip()
    folder = context.user_data["add_folder"]
    
    # Пытаемся распарсить
    await update.message.reply_text("🔍 Пытаюсь достать данные из кэша Google...")
    parsed = try_parse_james_edition(url1)
    
    if parsed:
        # Получилось!
        title = parsed['title']
        price = parsed['price']
        details = parsed['details']
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO properties (url, title, price, folder, date_added, details) VALUES (?, ?, ?, ?, ?, ?)",
                  (url1, title, price, folder, datetime.now().isoformat(), details))
        conn.commit()
        conn.close()
        
        msg = f"✅ Автоматически найдено:\n"
        msg += f"🏠 {title}\n"
        if price:
            msg += f"💰 {price}\n"
        if details:
            msg += f"📋 {details}\n"
        msg += "\nОбъект добавлен!"
        
        await update.message.reply_text(msg)
        context.user_data["awaiting_url1"] = False
        await show_main_menu(update, context)
    else:
        # Не получилось — переходим к ручному вводу
        await update.message.reply_text(
            "⚠️ Не удалось автоматически достать данные.\n"
            "Введи **название** объекта вручную:",
            parse_mode="Markdown"
        )
        # Сохраняем URL во временные данные
        context.user_data["temp_url"] = url1
        context.user_data["awaiting_url1"] = False
        context.user_data["awaiting_manual_title"] = True

async def handle_manual_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручной ввод названия"""
    title = update.message.text.strip()
    folder = context.user_data["add_folder"]
    url = context.user_data.get("temp_url", title)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO properties (url, title, folder, date_added) VALUES (?, ?, ?, ?)",
              (url, title, folder, datetime.now().isoformat()))
    conn.commit()
    prop_id = c.lastrowid
    conn.close()
    
    context.user_data["awaiting_manual_title"] = False
    context.user_data["awaiting_url2"] = True
    context.user_data["temp_id"] = prop_id
    context.user_data.pop("temp_url", None)
    
    await update.message.reply_text("🔗 Теперь отправь **вторую ссылку** (для превью):", parse_mode="Markdown")

async def handle_url2(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url2 = update.message.text.strip()
    prop_id = context.user_data.pop("temp_id")
    context.user_data["awaiting_url2"] = False

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE properties SET price = ? WHERE id = ?", (url2, prop_id))
    conn.commit()
    conn.close()

    context.user_data.pop("add_folder", None)
    
    await update.message.reply_text("✅ Объект добавлен. Используй /start чтобы увидеть карточки.")
    await show_main_menu(update, context)

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

    conn = sqlite3.connect(DB_PATH)
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE properties SET folder = ? WHERE id = ?", (new_folder, prop_id))
    conn.commit()
    conn.close()
    await query.edit_message_text(f"✅ Объект перемещён в папку «{new_folder}».")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if "authenticated" not in context.user_data:
        await query.edit_message_text("🔐 Сначала авторизуйся: /start")
        return

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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_messages))
    
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()