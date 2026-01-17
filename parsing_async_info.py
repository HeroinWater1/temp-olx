import asyncio
import aiohttp
import aiofiles
import csv
import io
import os
from bs4 import BeautifulSoup

class OlxScraper:
    
    CSV_FILE = "data.csv"
    HISTORY_FILE = "history_ids.txt" # Файл, где храним список скачанных ID
    
    def __init__(self):
        self.processed_ids = set()

    # 1. Загрузка истории (чтобы не скачивать повторно при перезапуске)
    def load_history(self):
        if os.path.exists(self.HISTORY_FILE):
            with open(self.HISTORY_FILE, "r", encoding="utf-8") as f:
                self.processed_ids = {line.strip() for line in f if line.strip()}
            print(f"Loaded {len(self.processed_ids)} IDs from history.")
        else:
            print("History file not found. Starting fresh.")

    # 2. Создание CSV с заголовками (если файла нет)
    async def init_csv_file(self):
        if not os.path.exists(self.CSV_FILE):
            async with aiofiles.open(self.CSV_FILE, mode='w', encoding='utf-8-sig', newline='') as f:
                # Добавил столбец ID в начало, это полезно для сверки
                header = "ID;Title;Price;Date;Owner;Description;Link\n"
                await f.write(header)

    async def getRequest(self, session, url, semaphore):
        async with semaphore:
            try:
                async with session.get(url, timeout=15) as response:
                    if response.status == 200:
                        return await response.text()
                    return None
            except Exception as e:
                print(f"Error connection {url}: {e}")
                return None

    async def process_link(self, session, link, index, semaphore, file_lock):
        full_url = "https://olx.kz" + link.strip()
        
        html = await self.getRequest(session, full_url, semaphore)
        
        if not html:
            return

        soup = BeautifulSoup(html, 'lxml')

        def get_text_safe(css_class):
            try:
                text = soup.find(class_=css_class).get_text(strip=True)
                # Ваши замены + защита CSV
                return text.replace(";", ",").replace("\n", " ").replace("\r", "").replace("ID:", "").strip()
            except AttributeError:
                return "NO DATA"

        # --- ЭТАП 1: Проверка ID (самое важное) ---
        # Класс ID на OLX обычно "css-ooacec" или "css-12hdxwj" (проверьте актуальность)
        ad_id = get_text_safe("css-ooacec") 

        # Если не смогли найти ID, но страница загрузилась, лучше сохранить как есть,
        # либо пропустить. Тут логика: если есть ID и он в базе -> пропускаем.
        if ad_id != "NO DATA" and ad_id in self.processed_ids:
            print(f"Skipping: {index} | ID {ad_id} already exists.")
            return

        # --- ЭТАП 2: Сбор данных (если ID новый) ---
        title = get_text_safe("css-1au435n")
        description = get_text_safe("css-19duwlz")
        owner = get_text_safe("css-14tb3q5")
        date = get_text_safe("css-7b83xv") # Ваше поле даты
        price = get_text_safe("css-yauxmy")

        # Формируем строку CSV в памяти
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        # Записываем ID первым, потом всё остальное
        writer.writerow([ad_id, title, price, date, owner, description, full_url])
        csv_line = output.getvalue()
        output.close()

        # --- ЭТАП 3: Запись на диск ---
        async with file_lock:
            # 1. Пишем данные
            async with aiofiles.open(self.CSV_FILE, "a", encoding='utf-8-sig') as f_csv:
                await f_csv.write(csv_line)
            
            # 2. Если ID валидный, добавляем его в историю
            if ad_id != "NO DATA":
                async with aiofiles.open(self.HISTORY_FILE, "a", encoding='utf-8') as f_hist:
                    await f_hist.write(ad_id + "\n")
                self.processed_ids.add(ad_id)
        
        print(f"SAVED: {index} | ID: {ad_id} | Price: {price}")

    async def getInfoPageAsync(self, filename, headers, startwith):
        self.load_history()     # Загружаем ID
        await self.init_csv_file() # Проверяем CSV
        
        print("Starting scraping...")

        with open(filename, 'r') as file:
            all_links = file.readlines()

        semaphore = asyncio.Semaphore(15) 
        file_lock = asyncio.Lock()

        async with aiohttp.ClientSession(headers=headers) as session:
            tasks = []
            for index, link in enumerate(all_links, start=1):
                if index <= startwith:
                    continue
                
                task = asyncio.create_task(
                    self.process_link(session, link, index, semaphore, file_lock)
                )
                tasks.append(task)

            await asyncio.gather(*tasks)

if __name__ == "__main__":
    scraper = OlxScraper()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    # Ваш файл со ссылками
    asyncio.run(scraper.getInfoPageAsync("_links.txt", headers, startwith=0))