def format_duration(seconds) -> str:
    """3725 -> '01h02m'. Units are spelled out so nobody reads it as minutes and seconds."""
    if seconds is None:
        return "00h00m"
    seconds = int(seconds)
    return f"{seconds // 3600:02d}h{seconds % 3600 // 60:02d}m"


def format_players(names: list[str], shown: int = 3) -> str:
    """['Ana', 'Bob', 'Cris', 'Dan', 'Eva'] -> 'Ana, Bob, Cris y 2 más' (at most three names)."""
    if len(names) <= shown:
        return f"{', '.join(names[:-1])} y {names[-1]}" if len(names) > 1 else "".join(names)
    return f"{', '.join(names[:shown])} y {len(names) - shown} más"
