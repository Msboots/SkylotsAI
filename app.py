"""
Skylots AI Assistant — точка входа.
"""

import argparse

from skylots_ai.monitor import Monitor


def main() -> None:
    parser = argparse.ArgumentParser(description="Skylots AI Assistant")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run monitor once and exit",
    )
    args = parser.parse_args()

    monitor = Monitor()

    if args.once:
        monitor.single_run()
        return

    monitor.run()


if __name__ == "__main__":
    main()
