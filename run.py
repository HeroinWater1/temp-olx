import asyncio
import os
import random
import logging
import datetime
import aiofiles
import re
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from typing import List, Set, Optional
from bs4 import BeautifulSoup

# curl_cffi для имитации реального браузера
from curl_cffi.requests import AsyncSession, RequestsError

# ==========================================
# ⚙️ КОНФИГУРАЦИЯ
# ==========================================
class Config:
    TG_TOKEN = "8329418917:AAFFp0sKg_lm3rWnPxCkTYQ-luPFf2gjhoY"
    TG_CHAT_ID = "7413543865"

    # --- Настройки ---
    CHECK_INTERVAL = 120       
    REQUEST_TIMEOUT = 30
    CONCURRENT_REQUESTS = 5
    
    # Retry настройки
    MAX_RETRIES = 3 
    BACKOFF_FACTOR = 2 

    # --- Файлы ---
    CSV_FILE = "data.csv"
    HISTORY_FILE = "history_ids.txt"
    LOG_FILE = "bot_log.txt"

    # --- Ротация браузеров ---
    BROWSER_IMPERSONATIONS = [
        "chrome110", "chrome119", "chrome120", 
        "edge101", "safari15_5"
    ]

    URL_TARGETS = [
        'https://www.olx.kz/alm/q-asus-rog/?search%5Border%5D=created_at%3Adesc',
        'https://www.olx.kz/alm/q-lenovo-legion/?search%5Border%5D=created_at%3Adesc'
    ]

    KEYWORDS = [
        "rtx", "4070", "4080", "5070", "5080", "4060", 
        "ti", "super", "legion", "rog", "strix", 
        "oled", "i7", "i9", "ryzen 7", "ryzen 9"
    ]

# ==========================================
# 📝 МОДЕЛИ
# ==========================================
@dataclass
class ProductItem:
    id: str
    title: str
    price: str
    date: str
    owner: str
    description: str
    link: str

    def to_csv_line(self) -> str:
        clean_desc = self.description.replace(";", ",").replace("\n", " ")
        return f"{self.id};{self.title};{self.price};{self.date};{self.owner};{clean_desc};{self.link}\n"

# ==========================================
# 🪵 ЛОГИРОВАНИЕ
# ==========================================
def setup_logger():
    logger = logging.getLogger("OLX_Bot")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []

    file_fmt = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s', 
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_fmt = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s', 
        datefmt='%H:%M:%S'
    )

    fh = RotatingFileHandler(Config.LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(file_fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(console_fmt)
    logger.addHandler(ch)

    return logger

logger = setup_logger()

# ==========================================
# 💾 ИСТОРИЯ
# ==========================================
class HistoryManager:
    def __init__(self):
        self.processed_ids: Set[str] = set()
        self._lock = asyncio.Lock()

    def load(self):
        if os.path.exists(Config.HISTORY_FILE):
            try:
                with open(Config.HISTORY_FILE, "r", encoding="utf-8") as f:
                    # Читаем только непустые строки
                    self.processed_ids = {line.strip() for line in f if line.strip()}
                logger.info(f"📚 History loaded: {len(self.processed_ids)} IDs.")
            except Exception as e:
                logger.error(f"Failed to load history: {e}")

    def exists(self, ad_id: str) -> bool:
        return ad_id in self.processed_ids

    async def add(self, ad_id: str):
        if ad_id not in self.processed_ids:
            self.processed_ids.add(ad_id)
            try:
                async with self._lock:
                    async with aiofiles.open(Config.HISTORY_FILE, "a", encoding='utf-8') as f:
                        await f.write(ad_id + "\n")
            except Exception as e:
                logger.error(f"Failed to write history to disk: {e}")

history_manager = HistoryManager()

# ==========================================
# 🌐 СЕТЕВОЙ СЛОЙ
# ==========================================
class NetworkClient:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_with_retry(self, url: str) -> Optional[str]:
        delay = 2.0
        for attempt in range(1, Config.MAX_RETRIES + 1):
            try:
                await asyncio.sleep(random.uniform(1.0, 3.0))
                response = await self.session.get(url, timeout=Config.REQUEST_TIMEOUT)

                if response.status_code == 200:
                    return response.text
                elif response.status_code == 403:
                    logger.warning(f"⛔ 403 Forbidden. Attempt {attempt}")
                    await asyncio.sleep(delay * 5)
                elif response.status_code in [404, 410]:
                    return None
                else:
                    logger.warning(f"⚠️ Status {response.status_code}. Attempt {attempt}")

            except Exception as e:
                logger.warning(f"💥 Network Error ({e}). Attempt {attempt}")
            
            if attempt < Config.MAX_RETRIES:
                await asyncio.sleep(delay)
                delay *= Config.BACKOFF_FACTOR
        
        return None

# ==========================================
# 🔍 СБОРЩИК
# ==========================================
class LinkCollector:
    def __init__(self, client: NetworkClient):
        self.client = client

    async def collect_new_links(self) -> List[str]:
        all_links = []
        logger.info("🔍 Scanning for new links...")

        for url in Config.URL_TARGETS:
            html = await self.client.get_with_retry(url)
            if not html: continue

            try:
                soup = BeautifulSoup(html, 'lxml')
                found = []
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if ("/d/obyavlenie/" in href or "/obyavlenie/" in href) and \
                       "promoted" not in href and "search" not in href:
                        if href.startswith("/"): href = "https://olx.kz" + href
                        found.append(href)
                
                all_links.extend(list(set(found)))
            except Exception as e:
                logger.error(f"Parsing error in collector: {e}")

        unique = list(set(all_links))
        logger.info(f"📦 Unique links found: {len(unique)}")
        return unique

# ==========================================
# 🛠️ ОБРАБОТЧИК (ОБНОВЛЕННАЯ ЛОГИКА ID)
# ==========================================
class ProductProcessor:
    def __init__(self, client: NetworkClient):
        self.client = client
        self.file_lock = asyncio.Lock()

    async def _send_telegram(self, item: ProductItem):
        api_url = f"https://api.telegram.org/bot{Config.TG_TOKEN}/sendMessage"
        msg = (
            f"🔥 <b>Новое объявление!</b>\n\n"
            f"💻 {item.title}\n💰 {item.price}\n📅 {item.date}\n\n"
            f"🔗 <a href='{item.link}'>Открыть</a>"
        )
        payload = {"chat_id": Config.TG_CHAT_ID, "text": msg, "parse_mode": "HTML"}
        try:
            await self.client.session.post(api_url, json=payload, timeout=10)
        except Exception as e:
            logger.error(f"Telegram fail: {e}")

    @staticmethod
    def _extract_id_from_url(url: str) -> str:
        """
        Извлекает ID СТРОГО из ссылки.
        Формат: ...-ID8H3j.html или ...-ID12345.html
        """
        try:
            # Ищем "-ID" и берем всё до точки или конца
            match = re.search(r'-ID([a-zA-Z0-9]+)(\.html|$)', url)
            if match:
                return match.group(1)
        except Exception:
            pass
        return "UNKNOWN"

    @staticmethod
    def _clean(soup, css):
        el = soup.find(class_=css)
        return el.get_text(strip=True).replace("ID:", "").strip() if el else None

    async def process_link(self, url: str, sem):
        # 1. СТРОГАЯ ПРОВЕРКА ПО URL ID
        # Мы даже не пытаемся качать страницу, если ID уже известен
        url_id = self._extract_id_from_url(url)
        
        if url_id == "UNKNOWN":
            logger.debug(f"⚠️ Could not extract ID from URL: {url}")
            return # Пропускаем "битые" ссылки без ID
            
        if history_manager.exists(url_id):
            # Товар уже был, выходим МОМЕНТАЛЬНО
            return

        async with sem:
            # 2. Только теперь качаем страницу (экономия времени)
            html = await self.client.get_with_retry(url)
            if not html: return

            try:
                soup = BeautifulSoup(html, 'lxml')

                title = self._clean(soup, "css-1au435n")
                price = self._clean(soup, "css-yauxmy")
                
                # Если страница загрузилась, но данных нет - возможно OLX поменял верстку
                if not title:
                    logger.debug(f"Title not found for {url_id}. Check selectors.")
                    title = "NO TITLE"
                if not price:
                    price = "NO PRICE"

                item = ProductItem(
                    id=url_id, # Используем ТОЛЬКО ID из URL
                    title=title,
                    price=price,
                    date=self._clean(soup, "css-7b83xv") or "",
                    owner=self._clean(soup, "css-14tb3q5") or "",
                    description=self._clean(soup, "css-19duwlz") or "",
                    link=url
                )

                # 3. Сохранение
                async with self.file_lock:
                    async with aiofiles.open(Config.CSV_FILE, "a", encoding='utf-8-sig') as f:
                        await f.write(item.to_csv_line())

                # Добавляем в историю
                await history_manager.add(url_id)

                logger.info(f"✅ NEW ITEM [{url_id}]: {item.title[:30]} | {item.price}")

                # 4. Проверка на ключевые слова
                full_text = (item.title + " " + item.description).lower()
                if any(k.lower() in full_text for k in Config.KEYWORDS):
                    logger.info("🚀 MATCH! Sending TG.")
                    await self._send_telegram(item)

            except Exception as e:
                logger.error(f"Processing error {url}: {e}", exc_info=True)

    async def run_batch(self, links):
        if not links: return
        sem = asyncio.Semaphore(Config.CONCURRENT_REQUESTS)
        await asyncio.gather(*[self.process_link(url, sem) for url in links])

# ==========================================
# 🚀 MAIN
# ==========================================
async def main():
    logger.info("🤖 FAST URL-ID MONITOR STARTED")
    
    if not os.path.exists(Config.CSV_FILE):
        async with aiofiles.open(Config.CSV_FILE, 'w', encoding='utf-8-sig') as f:
            await f.write("ID;Title;Price;Date;Owner;Description;Link\n")

    history_manager.load()
    
    while True:
        cycle_start = datetime.datetime.now()
        current_impersonation = random.choice(Config.BROWSER_IMPERSONATIONS)
        
        try:
            async with AsyncSession(impersonate=current_impersonation) as session:
                client = NetworkClient(session)
                collector = LinkCollector(client)
                processor = ProductProcessor(client)

                links = await collector.collect_new_links()
                if links:
                    await processor.run_batch(links)
                else:
                    logger.warning("⚠️ No links found.")

        except Exception as e:
            logger.critical(f"🔥 CRASH: {e}", exc_info=True)
            await asyncio.sleep(60)

        duration = (datetime.datetime.now() - cycle_start).total_seconds()
        sleep_time = max(10, Config.CHECK_INTERVAL - duration)
        
        logger.info(f"💤 Waiting {sleep_time:.1f}s...")
        await asyncio.sleep(sleep_time)

if __name__ == '__main__':
    try:
        if os.name == 'nt':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user.")
