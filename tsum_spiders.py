import scrapy
from scrapy.http import Request
from scrapy.utils.response import open_in_browser
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

class TsumSpider(scrapy.Spider):
    name = 'tsum'
    allowed_domains = ['tsum.ru']
    start_urls = ['https://www.tsum.ru/catalog/sumki-18438/']
    
    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'DOWNLOAD_DELAY': 3,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'RETRY_TIMES': 3,
        'COOKIES_ENABLED': True,
        'ROBOTSTXT_OBEY': False,
    }
    
    def start_requests(self):
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
            'Referer': 'https://www.tsum.ru/'
        }
        for url in self.start_urls:
            yield Request(url, headers=headers, callback=self.parse_catalog)
    
    def parse_catalog(self, response):
        # Проверяем статус ответа
        if response.status != 200:
            self.logger.error(f"Ошибка доступа: {response.status}")
            return
        current_page = response.meta.get('page', 1)
        self.logger.info(f"Обрабатываю страницу #{current_page}")
        # Ищем контейнер каталога
        catalog_div = response.css('div[data-meta-name="catalog"]')
        
        if not catalog_div:
            self.logger.error('div с data-meta-name="catalog" не найден')
            return
        
        # Извлекаем ссылки на товары
        product_links = catalog_div.css('a.InternalProductCard__container___C_ZUB[data-meta-name="product"]::attr(href)').getall()
        
        if not product_links:
            self.logger.warning('Не найдено ссылок на товары')
            return
            
        self.logger.info(f"Найдено {len(product_links)} товаров")
        
        # Обрабатываем каждую ссылку на товар
        for link in product_links:
            absolute_url = urljoin(response.url, link)
            yield Request(
                absolute_url, 
                callback=self.parse_product,
                headers={'Referer': response.url}
            )
            
        next_page = current_page + 1
        next_page_url = f"https://www.tsum.ru/catalog/sumki-18438/?page={next_page}"
        #self.logger.info(f"{next_page_url}, {response.url}")
        
        # Проверяем есть ли еще товары (эмпирическая проверка)
        if len(product_links) >= 60 and next_page <= 59:  # Если на странице много товаров, вероятно есть следующая
            yield Request(
                next_page_url,
                callback=self.parse_catalog,
                headers={'Referer': response.url},
                meta={'page': next_page}
            )
        else:
            self.logger.info(f"Достигнут конец каталога на странице {current_page}")

    
    
    def parse_product(self, response):
        if response.status != 200:
            self.logger.error(f"Ошибка доступа к товару: {response.status}")
            return
            
        item = {}
        
        # # Парсим название товара
        # product_name = response.css('h1.description__productName___HvN8s::text').get()
        # if product_name:
        #     item['name'] = product_name.strip()
        soup = BeautifulSoup(response.text, 'html.parser')
        product_name = soup.find('h1', class_='description__productName___HvN8s')

        if product_name:
            # Извлечение текста из тега
            name_text = product_name.get_text()
            item['name'] = name_text
           
        price_div = soup.find('span', attrs={'data-test-id': 'productPrice'})

        # Способ 2: CSS-селектор (более современный подход)
        #price_div = soup.select_one('div[data-test-id="productPrice"]')

        # Проверка и извлечение текста
        price = 0
        if price_div:
            price = str(price_div.get_text(strip=True))  # "1 599 ₽"
            price = price.replace('₽', '')
            price = price.replace('\xa0', '')
            print(int(price))

        # Парсим характеристики
        sections = soup.find_all('section', class_='SegmentsView__section___jGPx8')
        texts = []
        
        for section in sections:
            list_items = section.find_all('li')
        
            texts = texts + [li.get_text() for li in list_items]
            
        # Парсим параметры
        characteristics = {}
        characteristics['price'] = price

        for item_text in texts:
            if ':' not in item_text:
                continue
                
            key, value = map(str.strip, item_text.split(':', 1))
            
            if key == 'Состав':
                value = value.replace(';', '')
            if key == 'Параметры изделия':
                parsed = self.parse_parameters(value)
                characteristics.update(parsed)
            else:
                characteristics[key] = value
                
            #characteristics[key] = value
        
        item['characteristics'] = characteristics
        
        yield item
    
    def parse_parameters(self, value):
        result = {}
        
        size_pattern = r'([А-Яа-я]+)[ :]+(\d+)\s*см'
        sizes = re.findall(size_pattern, value)
        
        kit_match = re.search(r'входит:\s*([^\.]+)', value, re.IGNORECASE)
        
        for name, val in sizes:
            clean_name = name.strip().capitalize()
            result[clean_name] = int(val)
        
        if kit_match:
            result['Комплект'] = kit_match.group(1).strip(' ,')
        
        if 'Ремешка' in result:
            result['Длина ремешка'] = result.pop('Ремешка')
            
        return result