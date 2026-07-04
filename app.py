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
        summaries = monitor.single_run()
        if hasattr(monitor.notifier, "print_once_summary"):
            monitor.notifier.print_once_summary(summaries)
        return

    monitor.run()


if __name__ == "__main__":
    main()
