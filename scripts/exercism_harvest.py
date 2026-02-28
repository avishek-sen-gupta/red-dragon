"""Fetch canonical-data.json files from Exercism's problem-specifications repo.

Usage:
    poetry run python scripts/exercism_harvest.py leap collatz-conjecture difference-of-squares

Downloads each exercise's canonical-data.json from GitHub and writes it
to tests/unit/exercism/exercises/<exercise>/canonical_data.json.
"""

import json
import logging
import sys
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/"
    "exercism/problem-specifications/main/exercises"
)

EXERCISES_DIR = (
    Path(__file__).parent.parent / "tests" / "unit" / "exercism" / "exercises"
)


def _exercise_dir_name(exercise_slug: str) -> str:
    """Convert an exercise slug (e.g. 'collatz-conjecture') to dir name."""
    return exercise_slug.replace("-", "_")


def fetch_canonical_data(exercise_slug: str) -> dict:
    """Download canonical-data.json for *exercise_slug* from GitHub."""
    url = f"{GITHUB_RAW_BASE}/{exercise_slug}/canonical-data.json"
    logger.info("Fetching %s", url)
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def save_canonical_data(exercise_slug: str, data: dict) -> Path:
    """Write canonical data to the exercises directory."""
    dir_name = _exercise_dir_name(exercise_slug)
    out_dir = EXERCISES_DIR / dir_name
    out_dir.mkdir(parents=True, exist_ok=True)
    solutions_dir = out_dir / "solutions"
    solutions_dir.mkdir(exist_ok=True)

    out_path = out_dir / "canonical_data.json"
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    logger.info("Wrote %s", out_path)
    return out_path


def main(exercises: list[str]) -> None:
    """Fetch and save canonical data for each exercise."""
    for slug in exercises:
        logger.info("Processing exercise: %s", slug)
        data = fetch_canonical_data(slug)
        save_canonical_data(slug, data)
    logger.info("Done — fetched %d exercise(s)", len(exercises))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <exercise-slug> [<exercise-slug> ...]")
        sys.exit(1)
    main(sys.argv[1:])
