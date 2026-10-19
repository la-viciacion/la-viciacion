"""Takes the screenshots of the documentation from the demo stack (docs-demo/demo.py up + seed).

    python docs-demo/screenshots.py            # every shot
    python docs-demo/screenshots.py home game  # only these

Needs Playwright and Pillow (pip install playwright pillow); it drives the Edge or Chrome that is installed,
nothing is downloaded. The pictures go to docs/assets/screens/ as WebP.
"""
import datetime
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo  # noqa: E402
from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

FRONT = "http://localhost:3100"
OUT = demo.ROOT / "docs" / "assets" / "screens"
DESKTOP = {"width": 1280, "height": 800}
PHONE = {"width": 390, "height": 844}


def lookups(token):
    games = {g["name"]: g["id"] for g in demo.call("GET", "/games/", token=token)}
    players = {p["username"]: p["id"] for p in demo.call("GET", "/users/", token=token)}
    return games, players


def best_month(token, username):
    """The finished month of the running season in which the player played most: the recap that looks best."""
    today = datetime.date.today()
    months = [f"{today.year}-{m:02d}" for m in range(1, today.month)]
    return max(months, key=lambda m: demo.call("GET", f"/statistics/recap/{m}?username={username}", token=token)["player"]["seconds"])


def click(selector, wait=900):
    def do(page):
        page.click(selector)
        page.wait_for_timeout(wait)
    return do


def several(*steps):
    def do(page):
        for step in steps:
            step(page)
    return do


def search(text):
    def do(page):
        page.locator("#gamePickerSearch").press_sequentially(text, delay=60)
        page.wait_for_timeout(1200)
    return do


def pick_first(page):
    page.locator(".modal-result-row").first.click()
    page.wait_for_timeout(1000)


def story_slide(n):
    """Moves a story forward n slides (tapping its right side)."""
    def do(page):
        for _ in range(n):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
        page.wait_for_timeout(700)
    return do


# name, user ("" = signed out), route, viewport, options. `full` takes the whole page; `do` runs on the page first.
def shots(g, p, month):
    D, P = DESKTOP, PHONE
    admin = lambda tab: ("dani", f"#/admin/{tab}" if tab else "#/admin", D, {})  # noqa: E731
    return [
        ("login", "", "#/", D, {}),
        ("home", "bea", "#/", D, {}),
        ("home-phone", "bea", "#/", P, {}),
        ("home-history", "bea", "#/", D, {"do": click(".history-row"), "full": False}),
        ("menu", "bea", "#/", D, {"do": click("#menuBtn")}),
        ("menu-phone", "bea", "#/", P, {"do": click("#menuBtn")}),
        ("playing", "bea", "#/", D, {"do": click(".playing-chip")}),
        ("picker", "bea", "#/", D, {"do": several(click("#chooseGameBtn"), search("hol"))}),
        ("picker-platform", "bea", "#/", D, {"do": several(click("#chooseGameBtn"), search("hades ii"), pick_first)}),
        ("manual", "bea", "#/", D, {"do": several(click("#manualSessionBtn"), search("celeste"), pick_first)}),
        ("complete", "bea", "#/", D, {"do": click(".btn-complete:not(.done)")}),
        ("activity", "bea", "#/activity", D, {}),
        ("games", "bea", "#/games", D, {}),
        ("game", "bea", f"#/game/{g['Hades II']}", D, {}),
        ("calendar", "bea", "#/calendar", D, {}),
        ("achievements", "bea", "#/achievements", D, {}),
        ("players", "bea", "#/players", D, {}),
        ("player", "bea", f"#/player/{p['cai']}", D, {}),
        ("profile", "bea", "#/profile/resumen", D, {}),
        ("profile-games", "bea", "#/profile/juegos", D, {}),
        ("profile-settings", "bea", "#/profile/ajustes", D, {}),
        ("wishlist", "bea", "#/wishlist", D, {}),
        ("recommendations", "bea", "#/recommendations", D, {}),
        ("challenges", "bea", "#/challenges", D, {}),
        ("recap", "bea", f"#/recap/{month}", D, {}),
        ("recap-group", "bea", f"#/recap/{month}", D, {"do": click("text=El grupo")}),
        ("story-1", "bea", f"#/story/{month}", P, {}),
        ("story-3", "bea", f"#/story/{month}", P, {"do": story_slide(2)}),
        ("story-5", "bea", f"#/story/{month}", P, {"do": story_slide(4)}),
        ("admin-home", *admin("")),
        ("admin-games", *admin("games")),
        ("admin-platforms", *admin("platforms")),
        ("admin-achievements", *admin("achievements")),
        ("admin-users", *admin("users")),
        ("admin-timers", *admin("timers")),
        ("admin-challenges", *admin("challenges")),
        ("admin-sends", *admin("sends")),
        ("admin-channels", *admin("channels")),
        ("admin-ai", *admin("ai")),
        ("admin-recap", *admin("recap")),
        ("admin-announce", *admin("announce")),
        ("admin-mail", *admin("mail")),
        ("admin-backup", *admin("backup")),
        ("admin-audit", *admin("audit")),
    ]


def save(png, name):
    OUT.mkdir(parents=True, exist_ok=True)
    Image.open(io.BytesIO(png)).convert("RGB").save(OUT / f"{name}.webp", "WEBP", quality=86, method=6)


def main(wanted):
    env = demo.read_env()
    admin = demo.login("admin", env["GOD_ADMIN_PASS"])
    g, p = lookups(admin)
    tokens = {u: demo.login(u, env["DEMO_PLAYER_PASS"]) for u in ("bea", "dani")}
    month = best_month(tokens["bea"], "bea")
    all_shots = shots(g, p, month)
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel="msedge")
        except Exception:
            browser = pw.chromium.launch(channel="chrome")
        for name, user, route, viewport, opts in all_shots:
            if wanted and name not in wanted:
                continue
            phone = viewport is PHONE
            ctx = browser.new_context(viewport=viewport, device_scale_factor=2 if phone else 1, is_mobile=phone,
                                      has_touch=phone, locale="es-ES", timezone_id="Europe/Madrid", color_scheme="dark")
            if user:
                ctx.add_init_script(f"localStorage.setItem('lv_token', {tokens[user]!r})")
            page = ctx.new_page()
            page.goto(f"{FRONT}/{route}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1200)
            try:  # the offer to turn on push notifications that every new browser gets
                page.get_by_role("button", name="Ahora no").first.click(timeout=800)
                page.wait_for_timeout(300)
            except Exception:
                pass
            if "do" in opts:
                opts["do"](page)
            save(page.screenshot(full_page=opts.get("full", False)), name)
            print("shot", name)
            ctx.close()
        if not wanted or "home-timer" in wanted:
            running = demo.call("POST", "/timers/start", {"user_id": p["bea"], "game_id": g["Hades II"], "platform": "pc"}, token=tokens["bea"])
            try:
                ctx = browser.new_context(viewport=DESKTOP, locale="es-ES", timezone_id="Europe/Madrid", color_scheme="dark")
                ctx.add_init_script(f"localStorage.setItem('lv_token', {tokens['bea']!r})")
                page = ctx.new_page()
                page.goto(f"{FRONT}/#/")
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(2500)
                try:
                    page.get_by_role("button", name="Ahora no").first.click(timeout=800)
                    page.wait_for_timeout(300)
                except Exception:
                    pass
                save(page.screenshot(), "home-timer")
                print("shot home-timer")
                ctx.close()
            finally:
                demo.call("DELETE", f"/timers/cancel/{running['id']}?user_id={p['bea']}", token=tokens["bea"])
        browser.close()


if __name__ == "__main__":
    main(set(sys.argv[1:]))
