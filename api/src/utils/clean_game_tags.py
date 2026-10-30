"""Passes the tags the games already have through the filter that new ones go through (utils/game_tags.py).

    python -m src.utils.clean_game_tags            # only says what it would remove
    python -m src.utils.clean_game_tags --apply    # removes it

It never adds or reorders anything: a game's tags become the ones of its list that the filter keeps. Running it again
changes nothing, and a tag removed by mistake comes back with the next RAWG sync that overwrites (or by hand)."""
import argparse
from collections import Counter

from ..database import models
from ..database.database import SessionLocal
from . import game_tags


def split(tags: str | None) -> list[str]:
    return [tag.strip() for tag in (tags or "").split(",") if tag.strip()]


def plan(rows) -> tuple[dict[str, str], Counter, Counter]:
    """From (game id, tags) rows: the new tags of each game that changes, how many games lose each tag, and how many
    have each tag now (pure)."""
    changes: dict[str, str] = {}
    removed: Counter = Counter()
    before: Counter = Counter()
    for game_id, tags in rows:
        old = split(tags)
        new = game_tags.clean(old)
        before.update(set(old))
        if new != ",".join(old):
            changes[game_id] = new
            kept = {tag.casefold() for tag in split(new)}
            removed.update({tag for tag in old if tag.casefold() not in kept})
    return changes, removed, before


def report(changes: dict[str, str], removed: Counter, before: Counter) -> str:
    lines = [f"{len(changes)} games change; {len(removed)} of {len(before)} tags would disappear.", ""]
    lines += [f"{count:5d}  {tag}" for tag, count in sorted(removed.items(), key=lambda item: (-item[1], item[0].casefold()))]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the change (without it, only report)")
    args = parser.parse_args()
    with SessionLocal() as db:
        rows = [(game_id, tags) for game_id, tags in db.query(models.Game.id, models.Game.tags).filter(models.Game.tags.isnot(None), models.Game.tags != "")]
        changes, removed, before = plan(rows)
        print(report(changes, removed, before))
        if not args.apply:
            print("\nNothing written (use --apply).")
            return
        for game_id, tags in changes.items():
            db.query(models.Game).filter(models.Game.id == game_id).update({"tags": tags}, synchronize_session=False)
        db.commit()
        print(f"\nWritten: {len(changes)} games.")


if __name__ == "__main__":
    main()
