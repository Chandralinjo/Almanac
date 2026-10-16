"""Build-time entry point. Never run against a user's phone database."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_staples import build


def create_food_database():
    catalog = build()
    print(f"Created bundled foods.db with {len(catalog['foods'])} sourced USDA staples")


if __name__ == '__main__':
    create_food_database()
