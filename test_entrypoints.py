"""Тесты совместимых точек входа."""

import unittest

import app
import main
import watcher


class EntrypointTests(unittest.TestCase):

    def test_legacy_entrypoints_delegate_to_app(self) -> None:
        self.assertIs(main.main, app.main)
        self.assertIs(watcher.main, app.main)


if __name__ == "__main__":
    unittest.main()
