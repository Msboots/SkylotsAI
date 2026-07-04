import requests
from bs4 import BeautifulSoup

URL = "https://skylots.org/search.php?search=&desc_check=0&catid=0&seller_id=0&buy_now=0&ex=0&end_ex=0&price_from=&price_to=&items_from=&items_to=&city=&orderby=5"

headers = {
    "User-Agent": "Mozilla/5.0"
}

html = requests.get(URL, headers=headers).text

soup = BeautifulSoup(html, "lxml")

lots = soup.select(".search_lot")

print(f"Найдено {len(lots)} лотов\n")

for lot in lots[:10]:

    title = lot.select_one(".search_lot_title")
    price = lot.select_one(".search_lot_price")
    seller = lot.select_one(".search_lot_seller_rating a:last-child")
    end = lot.select_one(".search_lot_timetoend")
    link = lot.select_one("a.search_lot_link")

    print("=" * 50)

    print("Название :", title.get_text(strip=True) if title else "-")
    print("Цена     :", price.get_text(" ", strip=True) if price else "-")
    print("До конца :", end.get_text(" ", strip=True) if end else "-")
    print("Продавец :", seller.get_text(strip=True) if seller else "-")

    if link:
        print("Ссылка   : https://skylots.org" + link["href"])
