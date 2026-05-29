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