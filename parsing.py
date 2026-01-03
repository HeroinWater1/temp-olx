from bs4 import BeautifulSoup
import requests as req
from time import sleep
from random import randint
import sqlite3
class Main:
    def __init__(self, url: str, headers: dict, save=True, pages=25):
        # if save:
        #     self.__getHttpPages(pages,url,headers)
        # self.__getPageSoup("pages_olx", pages)
        self.__getInfoPage('links.txt', headers)
    def __getPretty(self, url: str, headers: dict, page: int):
        session = req.Session()
        src = session.get(url.replace('PAGE', str(page)), headers=headers).text
        soup = BeautifulSoup(src, 'lxml')
        return soup.prettify()
    def __getHttpPages(self, page_number: int, url: str, headers: dict):
        for page in range(1, 26):
            with open(f'pages_olx/page_{page}.html', 'w', encoding='utf-8') as file:
                file.write(self.__getPretty(url=url, headers=headers, page=page)) 
                sleep(randint(2, 5))
                print(f'This is page number: {page}')
    def __getInfoPage(self, filename, headers):
        with open(filename, 'r') as file:
            for index, link in enumerate(file.readlines(), start=1):
                link = "https://olx.kz" + link.rstrip()
                sleep(randint(5, 10))
                soup = BeautifulSoup(req.get(link).text, 'lxml')
                try:
                    title = soup.find(class_="css-1au435n").text
                except:
                    print("Cannot find title")
                    title = "NO DATA"
                try:
                    description = soup.find(class_='css-19duwlz').text

                except:
                    print("Cannot find description")
                    description = "NO DATA"
                try:
                    owner = soup.find(class_="css-14tb3q5").text
                except:
                    print("Cannot find owner name")
                    owner = "NO DATA"
                try:
                    location = soup.find(class_="css-3cz5o2").text
                except:
                    print("Cannot find location")
                    location = "NO DATA"
                try:
                    price = soup.find(class_="css-yauxmy")
                except:
                    print("Cannot find price")
                    price = "NO DATA"
                with open("data.txt", "a") as file:
                    file.write(f"\nTitle = {title}\nDescription = {description}\nOwner = {owner}\nLocation = {location}\nLink={link}\nPrice={price}\n##################################################################################################")
                    print(f"Counting: {index}")

    def __getPageSoup(self, pages_folder: str, pages: int):
        with open("links.txt", mode='a', encoding='utf-8') as links:
            for page in range(1, pages+1):
                with open(f"{pages_folder}/page_{page}.html", encoding='utf-8') as file:
                    soup = BeautifulSoup(file, 'lxml')
                    listCard = soup.select(".css-u2ayx9 a")
                    # print(listCard)
                    for card in listCard:
                        link = card.get('href')
                        # print(link)
                        links.write(link + "\n")    
        
def main():
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    url = 'https://www.olx.kz/alm/q-%D0%B8%D0%B3%D1%80%D0%BE%D0%B2%D0%BE%D0%B9-%D0%BD%D0%BE%D1%83%D1%82%D0%B1%D1%83%D0%BA/?page=PAGE'
    main = Main(url, headers=headers, save=False)
    
if __name__ == '__main__':
    main()
