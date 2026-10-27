"""What players paid for their games and what that comes to per hour. Only the price is stored (`users_game_prices`, one per
player, game and platform); the cost per hour, the personal summary and the group's mean are derived when asked.

Privacy: a player's prices are theirs to read (and an administrator's, like the rest of their data). The group only gets a
**mean cost per hour of a game**, and only when at least MIN_CONTRIBUTORS players contribute to it, so that no one's price
can be worked out from it (the hours of each player in a game are public, so a cost per hour of one player would give their
price away): it is never given per player."""
import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import models

MIN_CONTRIBUTORS = 3  # players needed for the group's cost per hour of a game to be shown
MIN_SECONDS = 1800  # a game played less than this has no cost per hour (the figure would mean nothing)
MAX_CENTS = 1_000_000  # 10,000 euros: more is a typing mistake


class PriceError(ValueError):
    """The price or the game it is for is not valid (the message is shown to the player)."""


def per_hour(cents: int, seconds: int) -> int | None:
    """Euro cents per hour, rounded, or None when too little was played to say (pure)."""
    return round(cents * 3600 / seconds) if seconds >= MIN_SECONDS else None


def cents_of(amount) -> int:
    """A price in euros (a number, or text with a comma) as cents; PriceError when it is not a price (pure)."""
    try:
        cents = round(float(str(amount).replace(",", ".")) * 100)
    except (ValueError, TypeError):
        raise PriceError("El precio no es un número")
    if not 0 <= cents <= MAX_CENTS:
        raise PriceError(f"El precio debe estar entre 0 y {MAX_CENTS // 100} euros")
    return cents


def prices_of(db: Session, user_id: int) -> dict[tuple[str, str], int]:
    """{(game id, platform id): cents} of a player."""
    return {
        (game_id, platform): cents
        for game_id, platform, cents in db.query(models.UserGamePrice.game_id, models.UserGamePrice.platform, models.UserGamePrice.amount_cents)
        .filter(models.UserGamePrice.user_id == user_id)
    }


def set_price(db: Session, user_id: int, game_id: str, platform: str, amount) -> int | None:
    """Note what the player paid for a game on a platform (`amount` in euros), or take the price off (`amount` None).
    The game has to be in their library on that platform (any season). Returns the cents, or None when removed."""
    has = db.query(models.UserGame.id).filter_by(user_id=user_id, game_id=game_id, platform=platform).first()
    if has is None:
        raise PriceError("No tienes este juego en esa plataforma")
    row = db.query(models.UserGamePrice).filter_by(user_id=user_id, game_id=game_id, platform=platform).first()
    if amount is None or amount == "":
        if row is not None:
            db.delete(row)
            db.commit()
        return None
    cents = cents_of(amount)
    if row is None:
        db.add(models.UserGamePrice(user_id=user_id, game_id=game_id, platform=platform, amount_cents=cents))
    else:
        row.amount_cents = cents
        row.updated_at = datetime.datetime.now()
    db.commit()
    return cents


def _seconds(db: Session, user_ids=None, game_ids=None) -> dict[tuple[int, str], int]:
    """{(user, game): seconds played} from the finished sessions."""
    query = db.query(models.GameTimer.user_id, models.GameTimer.game_id, func.sum(models.GameTimer.duration_seconds)).filter(
        models.GameTimer.is_active == False  # noqa: E712
    )
    if user_ids is not None:
        query = query.filter(models.GameTimer.user_id.in_(list(user_ids)))
    if game_ids is not None:
        query = query.filter(models.GameTimer.game_id.in_(list(game_ids)))
    return {(user_id, game_id): int(total or 0) for user_id, game_id, total in query.group_by(models.GameTimer.user_id, models.GameTimer.game_id)}  # SUM() is a Decimal in MariaDB


# ── the group's cost per hour (pure, from the facts) ────────────


def group_rows(prices: dict[tuple[int, str], int], seconds: dict[tuple[int, str], int]) -> list[dict]:
    """The mean cost per hour of each game that enough players contribute to (pure). `prices` is {(user, game): cents in
    total for that player and game}, `seconds` {(user, game): seconds}. A player contributes when they have a price for the
    game and played it at least MIN_SECONDS; the mean is the sum of their prices over the sum of their hours, so a player
    with many hours weighs more. Games with fewer than MIN_CONTRIBUTORS contributors are left out, and the answer has no
    player in it. Cheapest per hour first."""
    per_game: dict[str, list[tuple[int, int]]] = {}
    for (user_id, game_id), cents in prices.items():
        played = seconds.get((user_id, game_id), 0)
        if played >= MIN_SECONDS:
            per_game.setdefault(game_id, []).append((cents, played))
    rows = [
        {"game_id": game_id, "contributors": len(parts), "per_hour_cents": per_hour(sum(c for c, _ in parts), sum(s for _, s in parts))}
        for game_id, parts in per_game.items() if len(parts) >= MIN_CONTRIBUTORS
    ]
    return sorted(rows, key=lambda r: (r["per_hour_cents"], -r["contributors"], r["game_id"]))


def _totals_by_player_and_game(db: Session, user_ids: set[int]) -> dict[tuple[int, str], int]:
    totals: dict[tuple[int, str], int] = {}
    for user_id, game_id, cents in db.query(models.UserGamePrice.user_id, models.UserGamePrice.game_id, models.UserGamePrice.amount_cents):
        if user_id in user_ids:
            totals[(user_id, game_id)] = totals.get((user_id, game_id), 0) + cents
    return totals


def _players(db: Session) -> set[int]:
    return {user_id for (user_id,) in db.query(models.User.id).filter(models.not_god())}


def group_value(db: Session, limit: int = 10) -> dict:
    """The group's cost per hour of the games with enough contributors: the cheapest and the most expensive per hour
    (`limit` each), and how many games there are. No player, no price."""
    prices = _totals_by_player_and_game(db, _players(db))
    rows = group_rows(prices, _seconds(db, game_ids={game for _, game in prices}))
    names = {game.id: game for game in db.query(models.Game).filter(models.Game.id.in_([r["game_id"] for r in rows] or [""]))}
    shown = [{**r, "game_name": names[r["game_id"]].name, "image_url": names[r["game_id"]].image_url} for r in rows]
    return {
        "min_contributors": MIN_CONTRIBUTORS,
        "games": len(shown),
        "cheapest": shown[:limit],
        "priciest": list(reversed(shown))[:limit],
    }


def game_value(db: Session, game_id: str) -> dict | None:
    """The group's mean cost per hour of one game, or None when fewer than MIN_CONTRIBUTORS players contribute to it."""
    prices = {key: cents for key, cents in _totals_by_player_and_game(db, _players(db)).items() if key[1] == game_id}
    rows = group_rows(prices, _seconds(db, game_ids=[game_id]))
    return {"per_hour_cents": rows[0]["per_hour_cents"], "contributors": rows[0]["contributors"]} if rows else None


# ── a player's own summary ──────────────────────────────────────


def value(db: Session, user_id: int) -> dict:
    """What a player has spent on their games and what it comes to per hour: the total, the hours of the priced games, the
    mean cost per hour and, game by game, the price, the hours and the cost per hour (the cheapest per hour first, the
    games with too little time last)."""
    totals = _totals_by_player_and_game(db, {user_id})
    seconds = _seconds(db, user_ids=[user_id])
    names = {game.id: game for game in db.query(models.Game).filter(models.Game.id.in_([game for _, game in totals] or [""]))}
    games = [
        {
            "game_id": game_id, "game_name": names[game_id].name, "image_url": names[game_id].image_url, "price_cents": cents,
            "seconds": seconds.get((user_id, game_id), 0), "per_hour_cents": per_hour(cents, seconds.get((user_id, game_id), 0)),
        }
        for (_, game_id), cents in totals.items()
    ]
    games.sort(key=lambda g: (g["per_hour_cents"] is None, g["per_hour_cents"] or 0, g["game_name"].lower()))
    counted = [g for g in games if g["per_hour_cents"] is not None]
    spent = sum(g["price_cents"] for g in games)
    counted_cents, counted_seconds = sum(g["price_cents"] for g in counted), sum(g["seconds"] for g in counted)
    return {
        "spent_cents": spent,
        "priced_games": len(games),
        "counted_games": len(counted),
        "counted_seconds": counted_seconds,
        "per_hour_cents": per_hour(counted_cents, counted_seconds),
        "games": games,
    }
