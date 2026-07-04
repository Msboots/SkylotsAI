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
        summary = monitor.single_run()
        print(
            "Summary: "
            f"total={summary.total_lots}, "
            f"new={summary.new_lots}, "
            f"existing={summary.existing_lots}"
        )
        return

    monitor.run()


if __name__ == "__main__":
    main()
