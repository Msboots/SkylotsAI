"""Тесты парсинга HTML и обработки сетевых ошибок."""

from pathlib import Path
import unittest
from unittest.mock import Mock

import requests

from skylots_ai.parser import Parser


FIXTURE_PATH = Path(__file__).parent / "tests" / "fixtures" / "lots.html"


class ParserTests(unittest.TestCase):

    def setUp(self) -> None:
        self.parser = Parser.__new__(Parser)
        self.parser.session = Mock()
        self.parser.logger = Mock()
        self.parser._html = ""

    def test_parse_lot_fixture(self) -> None:
        lots = self.parser.parse(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual(len(lots), 2)
        self.assertEqual(lots[0].id, "12345")
        self.assertEqual(lots[0].title, "Коллекционная модель")
        self.assertEqual(lots[0].price, 1234)
        self.assertEqual(lots[0].seller, "trusted_seller")
        self.assertEqual(lots[0].rating, 42.0)
        self.assertEqual(lots[0].city, "Киев")
        self.assertEqual(lots[0].remaining_time_text, "1 ч 5 мин")
        self.assertEqual(lots[0].bids_count, 3)
        self.assertEqual(lots[0].url, "https://skylots.org/12345")

    def test_invalid_lot_without_id_is_skipped(self) -> None:
        lots = self.parser.parse(FIXTURE_PATH.read_text(encoding="utf-8"))

        self.assertEqual([lot.id for lot in lots], ["12345", "67890"])

    def test_fetch_returns_empty_string_on_network_error(self) -> None:
        self.parser.session.get.side_effect = requests.ConnectionError(
            "offline",
        )

        result = self.parser.fetch("https://skylots.org/search.php")

        self.assertEqual(result, "")
        self.assertEqual(self.parser._html, "")
        self.parser.logger.error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
