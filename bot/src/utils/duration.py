def format_duration(seconds) -> str:
    """3725 -> '01h02m'. Units are spelled out so nobody reads it as minutes and seconds."""
    if seconds is None:
        return "00h00m"
    seconds = int(seconds)
    return f"{seconds // 3600:02d}h{seconds % 3600 // 60:02d}m"
