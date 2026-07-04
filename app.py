"""
Skylots AI Assistant — точка входа.
"""

import argparse

from skylots_ai.monitor import Monitor, ProfileScanSummary


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
        print_summary(summaries)
        return

    monitor.run()


def print_summary(summaries: list[ProfileScanSummary]) -> None:
    for index, summary in enumerate(summaries):
        print(f"Profile: {summary.profile_name}")
        print(f"Fetched: {summary.fetched}")
        print(f"New: {summary.new_lots}")
        print(f"Existing: {summary.existing_lots}")

        if index != len(summaries) - 1:
            print("--------------------------------")


if __name__ == "__main__":
    main()
