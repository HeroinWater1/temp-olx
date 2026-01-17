from bs4 import BeautifulSoup
import requests as req
from time import sleep
from random import randint
import sqlite3
class Main:
    def __init__(self, url: str, headers: dict, pages, save=True):
        self.__getPageSoup(pages, headers=headers,url=url)
    def __getUrl(self, url: str, headers: dict, page: int):
        session = req.Session()
        src = session.get(url.replace('PAGE', str(page)), headers=headers).text
        soup = BeautifulSoup(src, 'lxml')
        return soup

    def __getPageSoup(self, pages: int, url, headers):
        with open("_links.txt", mode='w', encoding='utf-8') as links:
            for page in range(1, pages+1):
                soup = self.__getUrl(url=url, headers=headers, page=page)
                listCard = soup.select(".css-u2ayx9 a")
                for card in listCard:
                    link = card.get('href')
                    links.write(link + "\n")    
        
def main():
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    url_list = ['https://www.olx.kz/alm/q-asus-rog/?page=PAGE', 'https://www.olx.kz/alm/q-lenovo-legion/?page=PAGE']
    for index, url in enumerate(url_list):
        if index==0:
            Main(url, headers=headers, save=True, pages=9)
        else:
            Main(url, headers=headers, save=True, pages=6)
    
if __name__ == '__main__':
    main()
