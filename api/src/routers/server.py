import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import auth
from ..auth import get_db
from ..clients.ai_error import AIError
from ..clients.hetzner import HetznerError
from ..clients.prometheus import PrometheusError
from ..config import Config
from ..crud import costs as costs_crud
from ..utils import ai_spend, ai_usage, costs, server_status, settings
from ..utils.logger import LogManager

config = Config()
logger = LogManager().get_logger()

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


@router.get("/ai-costs")
def get_ai_costs(db: Session = Depends(get_db)):
    """What the AI has cost the group, in dollars (never converted to euros: the rate changes every day), for the server page:
    this month, this year and month by month, and the same for each provider (`providers`). OpenAI's part is what it billed when
    `OPENAI_ADMIN_KEY` is set and answers (a blocking call: a plain def, so it runs in a worker thread); Google has no spend API, so
    what the other providers' keys spent is always the app's estimate. Each provider says how it is known (`source`: `billed` or
    `estimated`) and so does the whole (`billed` when OpenAI's bill is all there is, `mixed` when an estimate is added to it,
    `estimated` when all of it is). Only totals, never who spent them."""
    today = datetime.date.today()
    key = settings.get("ai.openai_admin_key")
    figures = {provider: (months, "estimated") for provider, months in ai_spend.group_months_by_provider(db).items()}
    if key:
        try:
            figures["openai"] = (ai_usage.summary(key)["months"], "billed")
        except AIError as e:
            logger.warning(f"The server page could not ask OpenAI for the spend, it uses the estimate: {e}")
    providers = []
    for provider, (months, source) in sorted(figures.items()):
        rolled = ai_usage.rollup(months, today)
        if rolled["total"]:
            providers.append({"provider": provider, "source": source, **{k: rolled[k] for k in ("month", "year", "total")}})
    everything = ai_usage.rollup(ai_usage.add_months(*(months for months, _ in figures.values())), today)
    sources = {p["source"] for p in providers}
    source = "billed" if sources == {"billed"} else "mixed" if sources == {"billed", "estimated"} else "estimated"
    return {**everything, "source": source, "providers": providers}


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
