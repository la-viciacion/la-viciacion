"""How the server the app runs on is doing, for the panel everybody can open: its state, CPU, memory, network and disk
over a window, the traffic of the month and an estimate of what the month, the year and the whole life of the server cost.

Whatever the machine can say about itself comes from the Prometheus of the monitoring profile of docker-compose.yml when
PROMETHEUS_URL is set (CPU, disk I/O, memory, disk space, load, uptime); Hetzner gives what only it knows (the state and
type of the server, the network as the hypervisor sees it, the month's traffic, the prices). Without Prometheus, Hetzner
also gives the CPU and the disk I/O.

Nothing is stored (rule 2): it is asked to Hetzner (clients/hetzner.py) and Prometheus and kept in memory for a minute,
so a panel that opens again and again asks once. The cost is an estimate, not the invoice (Hetzner has no billing API): the server by the
hour up to its monthly price, its backups (a fifth of the server) and the traffic beyond what the plan includes. Volumes,
snapshots and extra IPs are not counted. The year and the total add the months before this one the same way, with the
price the server has today."""
import datetime

from ..clients import hetzner, prometheus
from ..clients.prometheus import PrometheusError
from .ttl_cache import TtlCache

CACHE_SECONDS = 60
BACKUPS_SHARE = 0.2
BYTES_PER_TB = 1e12
# window -> (how far back in seconds, seconds between two points); few enough points for a phone's chart
WINDOWS = {"1h": (3600, 30), "24h": (86400, 300), "7d": (7 * 86400, 1800), "30d": (30 * 86400, 7200)}
SERIES = {
    "cpu": "cpu",
    "net_in": "network.0.bandwidth.in",
    "net_out": "network.0.bandwidth.out",
    "disk_read": "disk.0.bandwidth.read",
    "disk_write": "disk.0.bandwidth.write",
}

# What node-exporter reports about the machine (the monitoring profile of docker-compose.yml); `/` is the host's root, not a container's
ROOT = '{mountpoint="/",fstype!~"tmpfs|overlay|squashfs|ramfs"}'
REAL_DISKS = '{device!~"loop.*|ram.*|dm-.*|sr.*"}'
NOW_QUERIES = {
    "memory_total": "node_memory_MemTotal_bytes",
    "memory_available": "node_memory_MemAvailable_bytes",
    "disk_total": f"max(node_filesystem_size_bytes{ROOT})",
    "disk_available": f"max(node_filesystem_avail_bytes{ROOT})",
    "load1": "node_load1",
    "load5": "node_load5",
    "load15": "node_load15",
    "cores": 'count(node_cpu_seconds_total{mode="idle"})',
    "uptime": "time() - node_boot_time_seconds",
}
MIN_RATE_SECONDS = 60  # a rate needs at least two scrapes (every 30 s) inside its window
# Over each chart, replacing what Hetzner would say about the same thing
REPLACED_METRICS = ("cpu", "disk_read", "disk_write")


def series_queries(step: int) -> dict[str, str]:
    """The expressions drawn over time. A rate is taken over as long as a point of the chart lasts, so a peak between two
    points of a 30-day chart is part of one of them instead of falling in the gap."""
    window = f"{max(step, MIN_RATE_SECONDS)}s"
    return {
        "memory": "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
        "disk": f"100 * (1 - max(node_filesystem_avail_bytes{ROOT}) / max(node_filesystem_size_bytes{ROOT}))",
        "cpu": f'100 * (1 - avg(rate(node_cpu_seconds_total{{mode="idle"}}[{window}])))',
        "disk_read": f"sum(rate(node_disk_read_bytes_total{REAL_DISKS}[{window}]))",
        "disk_write": f"sum(rate(node_disk_written_bytes_total{REAL_DISKS}[{window}]))",
    }


_cache = TtlCache(CACHE_SECONDS)


def points(time_series: dict, name: str) -> list[list[float]]:
    """`[[unix seconds, value], ...]` of one series; Hetzner sends the values as text and leaves holes as null."""
    found = []
    for stamp, value in (time_series.get(name) or {}).get("values") or []:
        if value is not None:
            found.append([int(stamp), round(float(value), 3)])
    return found


def shape_metrics(time_series: dict) -> dict:
    return {key: points(time_series, name) for key, name in SERIES.items()}


def _location(server: dict) -> dict:
    """Where the server lives: `location` on the server, or inside `datacenter` in the answers of the older API."""
    return server.get("location") or server["datacenter"]["location"]


def _price(server: dict) -> dict:
    """The prices of the server's type in the location it lives in."""
    location = _location(server)["name"]
    prices = server["server_type"]["prices"]
    return next((p for p in prices if p["location"] == location), prices[0])


def _next_month(day: datetime.datetime) -> datetime.datetime:
    return (day + datetime.timedelta(days=32)).replace(day=1)


def estimate_cost(server: dict, now: datetime.datetime) -> dict:
    """What the running month, the running year and the whole life of the server have cost so far, and what the month
    and the year will have cost by their end (VAT included, euros). Pure. Past months use the server's current price and
    backups, and no traffic beyond the plan (Hetzner only reports the traffic of the running month), so everything but
    the running month is an approximation."""
    price = _price(server)
    hourly, monthly = float(price["price_hourly"]["gross"]), float(price["price_monthly"]["gross"])
    created = datetime.datetime.fromisoformat(server["created"]).astimezone(datetime.timezone.utc)
    backups = BACKUPS_SHARE if server.get("backup_window") else 0
    over = max((server.get("outgoing_traffic") or 0) - (server.get("included_traffic") or 0), 0)
    traffic = over / BYTES_PER_TB * float(price["price_per_tb_traffic"]["gross"])

    def server_cost(start: datetime.datetime, end: datetime.datetime) -> float:
        """The server between two instants, hour by hour up to the monthly price."""
        return min(max((end - max(start, created)).total_seconds(), 0) / 3600 * hourly, monthly)

    def total(cost: float) -> float:
        return cost * (1 + backups) + traffic

    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    so_far = server_cost(month_start, now)
    projected = min(so_far + max((_next_month(month_start) - now).total_seconds(), 0) / 3600 * hourly, monthly)

    before_this_year = before_this_month = 0.0  # the months already closed, without traffic
    start = created.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while start < month_start:
        amount = server_cost(start, _next_month(start)) * (1 + backups)
        before_this_month += amount
        if start.year == now.year:
            before_this_year += amount
        start = _next_month(start)

    # the months of this year still to come, at the monthly price (a whole month always reaches it), without traffic
    ahead = (12 - now.month) * monthly * (1 + backups)

    return {
        "currency": "EUR",
        "month": {"so_far": round(total(so_far), 2), "projected": round(total(projected), 2)},
        "year": {"so_far": round(before_this_year + total(so_far), 2), "projected": round(before_this_year + total(projected) + ahead, 2)},
        "total": {"so_far": round(before_this_month + total(so_far), 2), "since": created.date().isoformat()},
    }


def shape_host(now: dict, charts: dict) -> dict:
    """The panel's figures of the machine from the instant values and the series of SERIES_QUERIES. Pure. A value
    Prometheus has no data for is None, and the part that needs it is left out."""
    def used(total, available):
        return None if total is None or available is None else {"used": total - available, "total": total}

    memory = used(now["memory_total"], now["memory_available"])
    disk = used(now["disk_total"], now["disk_available"])
    return {
        "memory": memory and {**memory, "series": charts["memory"]},
        "disk": disk and {**disk, "series": charts["disk"]},
        "load": None if now["load1"] is None else [now["load1"], now["load5"], now["load15"]],
        "cores": None if now["cores"] is None else int(now["cores"]),
        "uptime": None if now["uptime"] is None else int(now["uptime"]),
    }


def fetch_host(url: str, start: datetime.datetime, end: datetime.datetime, step: int) -> tuple[dict, dict]:
    """Asks Prometheus for the machine's figures: (the host section, the series that replace Hetzner's CPU and disk I/O).
    Raises PrometheusError if it does not answer or knows nothing yet."""
    now = {key: prometheus.instant(url, expression) for key, expression in NOW_QUERIES.items()}
    if now["memory_total"] is None:
        raise PrometheusError("Prometheus todavía no tiene datos de la máquina: ¿está arrancado node-exporter?")
    charts = {key: prometheus.series(url, expression, start, end, step) for key, expression in series_queries(step).items()}
    return shape_host(now, charts), {key: charts[key] for key in REPLACED_METRICS}


def describe(server: dict) -> dict:
    kind, place = server["server_type"], _location(server)
    return {
        "name": server["name"],
        "status": server["status"],  # running, off, starting, migrating...
        "created": server["created"],
        "type": kind["name"],
        "cores": kind["cores"],
        "memory_gb": kind["memory"],
        "disk_gb": kind["disk"],
        "location": f"{place['city']}, {place['country']}",
        "traffic": {
            "in": server.get("ingoing_traffic") or 0,
            "out": server.get("outgoing_traffic") or 0,
            "included": server.get("included_traffic") or 0,
        },
    }


def _fetch(token: str, server_id: str, window: str, now: datetime.datetime, prometheus_url: str) -> dict:
    server = hetzner.server(token, server_id)
    seconds, step = WINDOWS[window]
    start = now - datetime.timedelta(seconds=seconds)
    # Not set up: Hetzner gives everything it can. Set up and failing is an error of the whole panel, not a quiet gap in it
    host, replaced = fetch_host(prometheus_url, start, now, step) if prometheus_url else (None, {})
    series = hetzner.metrics(token, server["id"], start, now, step, hetzner.NETWORK_ONLY if prometheus_url else hetzner.METRIC_TYPES)
    return {
        "window": window,
        "step": step,
        "fetched_at": now.isoformat(),
        "server": describe(server),
        "metrics": {**shape_metrics(series), **replaced},
        "host": host,
        "cost": estimate_cost(server, now),
    }


def status(token: str, server_id: str, window: str, refresh: bool = False, prometheus_url: str = "") -> dict:
    """The state, the metrics of `window`, the machine's figures from Prometheus (when `prometheus_url` is set) and the
    cost estimate, from memory while fresh. Blocks on the network: call it
    from a worker thread. Raises HetznerError if Hetzner refuses or does not answer. The caller must drop `cost` for
    whoever may not see it, and must not change what it gets."""
    if refresh:
        _cache.clear()
    return _cache.get(window, lambda: _fetch(token, server_id, window, datetime.datetime.now(datetime.timezone.utc), prometheus_url))


def clear() -> None:
    _cache.clear()
