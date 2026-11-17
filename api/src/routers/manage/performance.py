"""How the API itself is doing (admin panel): requests, response time, errors and the slowest routes, from the figures the
API exposes to Prometheus (utils/metrics.py)."""
from fastapi import HTTPException, Query

from ...clients.prometheus import PrometheusError
from ...config import Config
from ...utils import performance
from .common import router

config = Config()


@router.get("/performance")
def get_performance(
    window: str = Query("24h", alias="range", pattern="^(1h|24h|7d|30d)$", description="How far back the charts go"),
    refresh: bool = False,
):
    """Plain `def`: it asks Prometheus (a blocking call), so it runs in a worker thread. It needs the monitoring profile
    (PROMETHEUS_URL); without it there is nothing to ask and the panel says so."""
    if not config.PROMETHEUS_URL:
        return {"configured": False}
    try:
        return {"configured": True, **performance.overview(config.PROMETHEUS_URL, window, refresh=refresh)}
    except PrometheusError as e:
        raise HTTPException(status_code=502, detail=str(e))
