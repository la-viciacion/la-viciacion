import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..clients.hetzner import HetznerError
from ..clients.prometheus import PrometheusError
from ..config import Config
from ..crud import costs as costs_crud
from ..utils import costs, server_status

config = Config()

router = APIRouter(
    prefix="/server",
    tags=["Server"],
    dependencies=[Depends(auth.get_current_active_user)],
)


@router.get("/costs")
def get_costs(year: int = Query(..., ge=2000, le=2100, description="The year whose months are wanted"), db: Session = Depends(get_db)):
    """The twelve months of a year of costs (see `utils/costs.months`), for the history of the server page. Derived from the
    recorded rates when asked; only the years that have costs, up to the running one."""
    items = costs_crud.all_items(db)
    if year not in costs.years(items, datetime.datetime.now()):
        raise HTTPException(status_code=404, detail="Ese año no tiene gastos registrados")
    return {"year": year, "months": costs.months(items, year, datetime.datetime.now())}


@router.get("/status")
def get_status(
    window: str = Query("24h", alias="range", pattern="^(1h|24h|7d|30d)$", description="How far back the charts go"),
    refresh: bool = False,
    db: Session = Depends(get_db),
):
    """How the server is doing (CPU, memory, network, disk, traffic and the cost of the month, the year and the whole life,
    derived from the recorded rates), for every player. It asks Hetzner (a blocking call: a plain def, so it runs in a worker
    thread) and keeps the answer a minute; `refresh` asks again."""
    token = config.HETZNER_API_TOKEN
    if not token:
        return {"configured": False}
    try:
        data = server_status.status(
            token, config.HETZNER_SERVER_ID, window, refresh=refresh, prometheus_url=config.PROMETHEUS_URL
        )
    except (HetznerError, PrometheusError) as e:
        raise HTTPException(status_code=502, detail=str(e).replace(token, "***"))
    shown = {key: value for key, value in data.items() if key != "overage"}
    return {"configured": True, **shown, "cost": costs.summary(costs_crud.all_items(db), datetime.datetime.now(), data["overage"])}
