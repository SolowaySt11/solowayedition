def fetch_property_data(url):
    print(f"🔍 Запрос к {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.jamesedition.com/",
            "Connection": "keep-alive"
        }
        response = requests.get(url, headers=headers, timeout=30)
        print(f"📡 Статус ответа: {response.status_code}")

        # Отладочный вывод HTML в логи
        print("--- НАЧАЛО HTML СТРАНИЦЫ (первые 2000 символов) ---")
        print(response.text[:2000])
        print("--- КОНЕЦ HTML СТРАНИЦЫ ---")

        soup = BeautifulSoup(response.text, 'html.parser')

        # Название
        title = soup.find("meta", property="og:title")
        title = title["content"].strip() if title else "Без названия"
        print(f"📌 Название: {title}")

        # Цена (HKD)
        price_hkd = None
        meta_price = soup.find("meta", property="og:price:amount")
        if meta_price and meta_price.get("content"):
            price_hkd = float(meta_price["content"])
            print(f"💰 Цена из og:price:amount: {price_hkd}")

        if not price_hkd:
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if data.get("@type") == "Product" and data.get("offers"):
                        price_hkd = float(data["offers"]["price"])
                        print(f"💰 Цена из JSON-LD: {price_hkd}")
                        break
                except:
                    pass

        if not price_hkd:
            price_span = soup.find("span", class_="price")
            if price_span:
                match = re.search(r"[\d,]+\.?\d*", price_span.text)
                if match:
                    price_hkd = float(match.group().replace(",", ""))
                    print(f"💰 Цена из span.price: {price_hkd}")

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

        # Фото
        photo_url = ""
        meta_img = soup.find("meta", property="og:image")
        if meta_img and meta_img.get("content"):
            photo_url = meta_img["content"]
            print(f"🖼️ Фото найдено: {photo_url[:50]}...")

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
        print(f"❌ Ошибка парсинга {url}: {e}")
        return None