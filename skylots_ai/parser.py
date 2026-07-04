"""
Парсинг лотов с skylots.org.
"""

import logging
import re
from urllib.parse import urljoin

import browser_cookie3
import requests
from bs4 import BeautifulSoup, Tag

from skylots_ai.config import Config
from skylots_ai.logger import LOG_NAME, setup
from skylots_ai.models import Lot

BASE_URL = "https://skylots.org"


class Parser:

    def __init__(
        self,
        config: Config | None = None,
        session: requests.Session | None = None,
    ):
        self.config = config or Config()
        self.session = session or self._create_session()
        self.logger = self._get_logger()
        self._html: str = ""

    def fetch(self) -> str:
        url = self._build_search_url()

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            self._html = response.text
            return self._html
        except requests.RequestException as exc:
            self.logger.error("Network error while fetching lots: %s", exc)
            self._html = ""
            return ""

    def parse(self, html: str | None = None) -> list[Lot]:
        source = html if html is not None else self._html

        if not source:
            source = self.fetch()

        if not source:
            return []

        soup = BeautifulSoup(source, "lxml")
        lots: list[Lot] = []

        for element in soup.select(".search_lot"):
            lot = self._parse_element(element)
            if lot is not None:
                lots.append(lot)

        return lots

    @staticmethod
    def parse_price(text: str) -> int:
        match = re.search(r"[\d\s.,]+", text)
        if not match:
            return 0

        normalized = match.group().replace(" ", "").replace(",", ".")

        try:
            return int(float(normalized))
        except ValueError:
            return 0

    @staticmethod
    def parse_rating(text: str) -> float | None:
        match = re.search(r"\((\d+)\)", text)
        if not match:
            return None

        return float(match.group(1))

    @staticmethod
    def parse_city(text: str) -> str | None:
        city = text.strip()
        return city or None

    def _build_search_url(self) -> str:
        max_price = self.config.max_price
        return (
            f"{BASE_URL}/search.php?"
            f"search=&desc_check=0&catid=0&seller_id=0&buy_now=0&ex=0&end_ex=0"
            f"&price_from=&price_to={max_price}"
            f"&items_from=&items_to=&city=&orderby=5"
        )

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            }
        )
        self._load_cookies(session)
        return session

    def _load_cookies(self, session: requests.Session) -> None:
        try:
            cookies = browser_cookie3.chrome(domain_name="skylots.org")
            session.cookies.update(cookies)
        except Exception as exc:
            self.logger.warning("Failed to load browser cookies: %s", exc)

    def _get_logger(self) -> logging.Logger:
        logger = logging.getLogger(LOG_NAME)
        if not logger.handlers:
            setup()
        return logging.getLogger(LOG_NAME)

    def _parse_element(self, element: Tag) -> Lot | None:
        link = element.select_one("a.search_lot_link")
        if link is None:
            return None

        href = link.get("href", "")
        lot_id = self._extract_lot_id(href)
        if not lot_id:
            return None

        title_el = element.select_one(".search_lot_title")
        title = title_el.get_text(strip=True) if title_el else ""

        price_el = element.select_one(".search_lot_price")
        price_text = price_el.get_text(" ", strip=True) if price_el else ""
        price = self.parse_price(price_text)

        seller_el = element.select_one(".search_lot_seller_rating")
        seller_text = seller_el.get_text(" ", strip=True) if seller_el else ""
        seller = self._extract_seller(seller_el)
        rating = self.parse_rating(seller_text)

        place_el = element.select_one(".search_lot_place")
        place_text = place_el.get_text(strip=True) if place_el else ""
        city = self.parse_city(place_text)

        end_el = element.select_one(".search_lot_timetoend")
        end_time = end_el.get_text(" ", strip=True) if end_el else None

        return Lot(
            id=lot_id,
            title=title,
            seller=seller,
            price=price,
            url=urljoin(BASE_URL, href),
            city=city,
            rating=rating,
            end_time=end_time,
        )

    @staticmethod
    def _extract_lot_id(href: str) -> str:
        match = re.match(r"/(\d+)", href)
        return match.group(1) if match else ""

    @staticmethod
    def _extract_seller(element: Tag | None) -> str:
        if element is None:
            return ""

        link = element.select_one("a[href]:not([onclick])")
        return link.get_text(strip=True) if link else ""
