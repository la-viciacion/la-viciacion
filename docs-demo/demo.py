"""Throwaway demo stack for the documentation screenshots.

    python docs-demo/demo.py up      # writes docs-demo/.env, makes the covers, builds and starts the stack
    python docs-demo/demo.py seed    # fills it with invented players, games and sessions through the API
    python docs-demo/demo.py down    # stops it and deletes its database

The stack (docs-demo/compose.yml) is a second, separate project: front on http://localhost:3100, API on
127.0.0.1:5100, its own database volume. Nothing here touches the real stack or real data, and the data it
creates is made up (the games are real titles with generated covers; the players do not exist). It needs
Pillow for the covers and avatars (the API's virtual environment has it). Stdlib only for the rest.
"""
import datetime
import json
import math
import random
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ENV_FILE = HERE / ".env"
API = "http://127.0.0.1:5100/api/v1"
COMPOSE = ["docker", "compose", "-p", "lavi-demo", "--env-file", str(ENV_FILE),
           "-f", str(ROOT / "docker-compose.yml"), "-f", str(HERE / "compose.yml")]
SERVICES = ["laviciacion-db", "laviciacion-api", "laviciacion-front"]

# title, developer, release date, genres, tags, hours to complete, platforms, hue of the cover
GAMES = [
    ("Hades", "Supergiant Games", "2020-09-17", "Action, Indie, RPG", "Roguelike, Singleplayer", 22, ["pc", "switch"], 12),
    ("Hades II", "Supergiant Games", "2025-09-25", "Action, Indie, RPG", "Roguelike, Singleplayer", 25, ["pc"], 285),
    ("Celeste", "Maddy Makes Games", "2018-01-25", "Platformer, Indie", "Singleplayer, Difficult", 9, ["pc", "switch"], 330),
    ("Hollow Knight", "Team Cherry", "2017-02-24", "Action, Platformer, Indie", "Metroidvania, Singleplayer", 27, ["pc", "switch"], 220),
    ("The Witcher 3: Wild Hunt", "CD Projekt Red", "2015-05-18", "RPG, Action", "Open World, Singleplayer", 51, ["pc", "ps5"], 35),
    ("Elden Ring", "FromSoftware", "2022-02-25", "RPG, Action", "Open World, Difficult", 60, ["pc", "ps5"], 45),
    ("Stardew Valley", "ConcernedApe", "2016-02-26", "Simulation, RPG, Indie", "Farming, Relaxing", 53, ["pc", "switch"], 110),
    ("Portal 2", "Valve", "2011-04-18", "Puzzle, Adventure", "Co-op, Singleplayer", 9, ["pc"], 195),
    ("It Takes Two", "Hazelight Studios", "2021-03-26", "Adventure, Platformer", "Co-op, Multiplayer", 14, ["pc", "ps5"], 25),
    ("Mario Kart 8 Deluxe", "Nintendo", "2017-04-28", "Racing", "Multiplayer, Party", 10, ["switch"], 0),
    ("The Legend of Zelda: Breath of the Wild", "Nintendo", "2017-03-03", "Adventure, Action", "Open World, Singleplayer", 53, ["switch"], 140),
    ("Resident Evil 4", "Capcom", "2023-03-24", "Action, Horror", "Horror, Survival Horror", 16, ["pc", "ps5"], 355),
    ("Alan Wake 2", "Remedy Entertainment", "2023-10-27", "Action, Adventure", "Horror, Singleplayer", 20, ["pc", "ps5"], 170),
    ("Hi-Fi Rush", "Tango Gameworks", "2023-01-25", "Action, Rhythm", "Singleplayer, Colorful", 13, ["pc"], 60),
    ("Disco Elysium", "ZA/UM", "2019-10-15", "RPG, Indie", "Story Rich, Singleplayer", 24, ["pc"], 20),
    ("Cyberpunk 2077", "CD Projekt Red", "2020-12-10", "RPG, Action", "Open World, Sci-fi", 27, ["pc", "ps5"], 55),
    ("God of War Ragnarök", "Santa Monica Studio", "2022-11-09", "Action, Adventure", "Story Rich, Singleplayer", 26, ["ps5"], 200),
    ("Baldur's Gate 3", "Larian Studios", "2023-08-03", "RPG, Strategy", "Co-op, Story Rich", 75, ["pc"], 5),
    ("Hogwarts Legacy", "Avalanche Software", "2023-02-10", "RPG, Action", "Open World, Singleplayer", 31, ["pc", "ps5"], 260),
    ("Overcooked! 2", "Team17", "2018-08-07", "Party, Simulation", "Co-op, Multiplayer", 11, ["pc", "switch"], 30),
    ("Super Mario Odyssey", "Nintendo", "2017-10-27", "Platformer, Adventure", "Singleplayer, Colorful", 13, ["switch"], 0),
    ("Silent Hill 2", "Bloober Team", "2024-10-08", "Horror, Adventure", "Horror, Survival Horror", 14, ["pc", "ps5"], 190),
    ("Balatro", "LocalThunk", "2024-02-20", "Card, Roguelike, Indie", "Roguelike, Singleplayer", 20, ["pc", "mobile"], 140),
    ("Dead Cells", "Motion Twin", "2018-08-07", "Action, Roguelike, Indie", "Roguelike, Difficult", 15, ["pc", "switch"], 340),
    ("Starfall Odyssey", "Demo Studio", "2026-11-12", "RPG, Adventure", "Singleplayer", None, ["pc"], 250),
    ("Hollow Harbor", "Demo Studio", "2026-10-30", "Horror, Adventure", "Horror, Singleplayer", None, ["pc", "ps5"], 175),
    ("Kart Rivals Turbo", "Demo Studio", "2026-12-04", "Racing, Party", "Multiplayer", None, ["switch-2"], 15),
    ("Neon Drifters", "Demo Studio", "2026-10-23", "Racing, Action", "Multiplayer", None, ["pc"], 310),
    ("Moss Kingdom", "Demo Studio", "2026-10-27", "Adventure, Platformer", "Singleplayer, Relaxing", None, ["switch"], 120),
    ("Pixel Farmers", "Demo Studio", "2026-10-06", "Simulation, Indie", "Farming, Relaxing", None, ["pc", "mobile"], 90),
    ("Lanternfall", "Demo Studio", None, "Platformer, Indie", "Singleplayer", None, ["pc"], 50),
]

# username, display name, is_admin, hue of the avatar, sessions per week, usual start hour, favourite games
PLAYERS = [
    ("bea", "Bea", False, 330, 3.2, 21, ["Hades", "Hades II", "Celeste", "Stardew Valley", "Balatro", "Hollow Knight", "It Takes Two", "Hi-Fi Rush", "Disco Elysium", "Portal 2", "Dead Cells"]),
    ("cai", "Cai", False, 200, 3.8, 22, ["Elden Ring", "Dead Cells", "Hollow Knight", "Resident Evil 4", "Silent Hill 2", "Hades II", "Hades", "Celeste", "Alan Wake 2", "Cyberpunk 2077"]),
    ("dani", "Dani", True, 150, 2.6, 20, ["Baldur's Gate 3", "The Witcher 3: Wild Hunt", "Cyberpunk 2077", "Disco Elysium", "Portal 2", "Hades", "Baldur's Gate 3", "Hogwarts Legacy", "Balatro", "Stardew Valley"]),
    ("eva", "Eva", False, 280, 2.8, 17, ["Stardew Valley", "Overcooked! 2", "Mario Kart 8 Deluxe", "Super Mario Odyssey", "It Takes Two", "Hades II", "Celeste", "Hades", "Dead Cells", "Balatro"]),
    ("fran", "Fran", False, 40, 2.2, 23, ["God of War Ragnarök", "Alan Wake 2", "Resident Evil 4", "Hogwarts Legacy", "Elden Ring", "Silent Hill 2", "Cyberpunk 2077", "The Witcher 3: Wild Hunt", "Hi-Fi Rush"]),
    ("nico", "Nico", False, 100, 1.8, 19, ["The Legend of Zelda: Breath of the Wild", "Mario Kart 8 Deluxe", "Hi-Fi Rush", "Celeste", "Overcooked! 2", "Stardew Valley", "Hades", "Super Mario Odyssey", "Portal 2"]),
]

FIRST_DAY = datetime.date(2025, 3, 3)


def run(cmd, **kw):
    print("$", " ".join(str(c) for c in cmd[:6]), "...")
    return subprocess.run(cmd, cwd=ROOT, check=True, **kw)


def write_env():
    if ENV_FILE.exists():
        return
    pw = lambda: "Dm1!" + secrets.token_hex(6)  # noqa: E731  (12-24 chars, upper, lower, digit, special)
    ENV_FILE.write_text("\n".join([
        "# Generated by docs-demo/demo.py: random values for a throwaway stack. Never commit it.",
        "TELEGRAM_TOKEN=", "TELEGRAM_GROUP_ID=", "TELEGRAM_ADMIN_CHAT_ID=",
        "MARIADB_HOST=laviciacion-db", f"MARIADB_ROOT_PASSWORD={secrets.token_hex(12)}",
        "MARIADB_DATABASE=laviciacion", "MARIADB_USER=laviciacion", f"MARIADB_PASSWORD={secrets.token_hex(12)}",
        f"GOD_ADMIN_PASS={pw()}", f"DEMO_PLAYER_PASS={pw()}", f"SECRET_KEY={secrets.token_hex(32)}",
        "ACCESS_TOKEN_EXPIRE_MINUTES=10080", 'CORS_ORIGINS=["http://localhost:3100"]',
        "RAWG_API_KEY=", "AI_PROVIDER=", "AI_API_KEY=", "AI_MODEL=", "PUBLIC_URL=",
        "SMTP_HOST=", "SMTP_PORT=587", "SMTP_SECURITY=starttls", "SMTP_EMAIL=", "SMTP_USER=", "SMTP_PASS=",
        "API_URL=http://laviciacion-api:5000/api/v1", "API_DOCS_ENABLED=false", "TZ=Europe/Madrid",
        "ENVIRONMENT=development", "SENTRY_URL_API=", "SENTRY_URL_BOT=", "API_LOG_LEVEL=INFO", "BOT_LOG_LEVEL=INFO",
        "LAVI_VERSION=demo", "",
    ]), encoding="utf-8")


def read_env():
    out = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k] = v
    return out


def slug(name):
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-").replace("--", "-")


def make_images():
    from PIL import Image, ImageDraw, ImageFont
    import colorsys

    def gradient(size, hue, sat=0.55):
        w, h = size
        img = Image.new("RGB", size)
        px = img.load()
        for y in range(h):
            for x in range(w):
                t = (x / w * 0.6 + y / h * 0.4)
                r, g, b = colorsys.hsv_to_rgb(((hue + 40 * t) % 360) / 360, sat, 0.85 - 0.45 * t)
                px[x, y] = (int(r * 255), int(g * 255), int(b * 255))
        return img

    covers = HERE / "covers"
    covers.mkdir(exist_ok=True)
    big, small = ImageFont.load_default(size=58), ImageFont.load_default(size=26)
    for title, dev, _, _, _, _, _, hue in GAMES:
        img = gradient((600, 600), hue)
        d = ImageDraw.Draw(img)
        words, lines, line = title.split(), [], ""
        for w in words:
            if d.textlength((line + " " + w).strip(), font=big) > 480 and line:
                lines.append(line)
                line = w
            else:
                line = (line + " " + w).strip()
        lines.append(line)
        y = 300 - 34 * len(lines)
        for ln in lines:
            d.text((300, y), ln, font=big, fill="white", anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))
            y += 68
        d.text((300, 540), dev, font=small, fill=(255, 255, 255), anchor="mm")
        img.save(covers / f"{slug(title)}.png")

    avatars = HERE / "avatars"
    avatars.mkdir(exist_ok=True)
    initial = ImageFont.load_default(size=120)
    for username, name, _, hue, *_ in PLAYERS:
        img = gradient((256, 256), hue, 0.6)
        d = ImageDraw.Draw(img)
        d.text((128, 128), name[0], font=initial, fill="white", anchor="mm")
        img.save(avatars / f"{username}.png")


def up():
    write_env()
    make_images()
    run(COMPOSE + ["up", "-d", "--build"] + SERVICES)
    print("waiting for the API...")
    for _ in range(120):
        try:
            urllib.request.urlopen(f"{API}/keepalive", timeout=3)
            break
        except OSError:
            time.sleep(5)
    else:
        sys.exit("the API did not come up")
    print("ready: http://localhost:3100")


def down():
    run(COMPOSE + ["down", "-v"])


# ── seeding ──────────────────────────────────────────────────────────────

def call(method, path, body=None, token=None, form=None, files=None):
    headers = {}
    data = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif files is not None:
        boundary = secrets.token_hex(8)
        name, content = files
        data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                "Content-Type: image/png\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body, default=str).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code in (502, 503, 504) and attempt < 4:
                time.sleep(2)
                continue
            raise RuntimeError(f"{method} {path} -> {e.code}: {detail}")
        except OSError:
            if attempt == 4:
                raise
            time.sleep(2)


def sql(statement):
    env = read_env()
    subprocess.run(["docker", "exec", "lavi-demo-db", "mariadb", "-uroot", f"-p{env['MARIADB_ROOT_PASSWORD']}",
                    env["MARIADB_DATABASE"], "-e", statement.replace("%%", "%")], check=True)


def login(username, password):
    return call("POST", "/token", form={"username": username, "password": password})["access_token"]


def build_sessions(rng, players, games_by_name):
    """Invented sessions. Each player works through their favourites one at a time, moving on when they have
    played about as long as the game takes (or giving up now and then) and not going back to one for months;
    evenings and weekends mostly, with quiet spells so that streaks and comebacks exist."""
    today = datetime.date.today()
    released = {g[0]: datetime.date.fromisoformat(g[2]) if g[2] else datetime.date.max for g in GAMES}
    out = []
    for username, _, _, _, per_week, hour, favourites in players:
        busy_until = datetime.datetime.min
        run_hours, last_done, current, target = {}, {}, None, 0
        day = FIRST_DAY
        while day < today:
            if current is None or run_hours.get(current, 0) >= target or rng.random() < 0.004:
                if current is not None:
                    last_done[current] = day
                options = [f for f in favourites if released[f] <= day and (day - last_done.get(f, datetime.date.min)).days > 150]
                if not options:  # every favourite is recent: go back to any of them rather than stop playing
                    options = [f for f in favourites if released[f] <= day]
                current = rng.choice(options) if options else None
                if current:
                    hours = games_by_name[current]["hours"] or 15
                    target = hours * rng.uniform(0.95, 1.25)
            weekend = day.weekday() >= 5
            chance = per_week / 7 * (1.7 if weekend else 1.0)
            if (day.toordinal() // 9 + sum(map(ord, username)) % 7) % 11 == 0:
                chance *= 0.15
            if current and rng.random() < chance:
                start_hour = hour + rng.randint(-2, 2) + (-5 if weekend else 0)
                start = datetime.datetime.combine(day, datetime.time(max(9, min(start_hour, 23)), rng.choice([0, 10, 20, 30, 45])))
                minutes = int(min(300, max(25, rng.lognormvariate(math.log(95), 0.55))))
                side = [f for f in favourites if released[f] <= day and games_by_name[f]["hours"] and games_by_name[f]["hours"] <= 15]
                game = rng.choice(side) if side and rng.random() < 0.12 else current
                platform = rng.choice(games_by_name[game]["platforms"])
                end = start + datetime.timedelta(minutes=minutes)
                if start > busy_until and end < datetime.datetime.now() - datetime.timedelta(hours=1):
                    out.append((username, game, platform, start, end))
                    busy_until = end + datetime.timedelta(minutes=5)
                    if game == current:
                        run_hours[current] = run_hours.get(current, 0) + minutes / 60
            day += datetime.timedelta(days=1)
    return out


def seed():
    env = read_env()
    admin = login("admin", env["GOD_ADMIN_PASS"])
    rng = random.Random(2026)

    print("games...")
    games_by_name = {}
    existing = {g["name"]: g for g in call("GET", "/games/", token=admin)}
    for title, dev, released, genres, tags, hours, platforms, _ in GAMES:
        g = existing.get(title) or call("POST", "/games/", {"name": title}, token=admin)
        call("PATCH", f"/manage/games/{g['id']}", {
            "dev": dev, "release_date": released, "genres": genres, "tags": tags,
            "avg_time": hours * 3600 if hours else None, "image_url": f"/demo-covers/{slug(title)}.png",
        }, token=admin)
        games_by_name[title] = {"id": g["id"], "platforms": platforms, "hours": hours}

    print("players...")
    ids, tokens = {}, {}
    known = {u["username"]: u for u in call("GET", "/manage/users?limit=200", token=admin).get("items", [])} \
        if isinstance(call("GET", "/manage/users?limit=200", token=admin), dict) else {}
    for username, name, is_admin, *_ in PLAYERS:
        user = known.get(username) or call("POST", "/manage/users", {
            "email": f"{username}@example.com", "username": username, "name": name,
            "password": env["DEMO_PLAYER_PASS"], "is_admin": is_admin,
        }, token=admin)
        ids[username] = user["id"]
        tokens[username] = login(username, env["DEMO_PLAYER_PASS"])
        png = (HERE / "avatars" / f"{username}.png").read_bytes()
        call("PATCH", f"/users/{username}/avatar", files=(f"{username}.png", png), token=tokens[username])

    print("sessions (this takes a few minutes)...")
    sessions = build_sessions(rng, PLAYERS, games_by_name)
    totals = {}

    def post(s):
        username, game, platform, start, end = s
        body = {"user_id": ids[username], "game_id": games_by_name[game]["id"], "platform": platform,
                "start_time": start.isoformat(), "end_time": end.isoformat()}
        for attempt in range(4):
            try:
                return call("POST", "/manage/timers", body, token=admin)
            except RuntimeError as e:
                # two sessions of one player creating the same library entry at once: the second asks again
                if "-> 409" not in str(e) or attempt == 3:
                    raise
                time.sleep(0.5)

    for s in sessions:
        key = (s[0], s[1], s[3].year)
        totals[key] = totals.get(key, 0) + (s[4] - s[3]).total_seconds() / 3600
    # in order per player (a player's sessions never overlap, but the server checks while writing)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i, _ in enumerate(pool.map(post, sessions)):
            if i % 100 == 0:
                print(f"  {i}/{len(sessions)}")

    print("completions and ratings...")
    last_day = {}
    for username, game, _, start, _ in sessions:
        last_day[(username, game, start.year)] = max(last_day.get((username, game, start.year), start.date()), start.date())
    for username, *_ in PLAYERS:
        entries = call("GET", f"/manage/library?user_id={ids[username]}&limit=200", token=admin)["items"]
        rated = set()
        for e in entries:
            g = next(v for k, v in games_by_name.items() if v["id"] == e["game_id"])
            name = next(k for k, v in games_by_name.items() if v["id"] == e["game_id"])
            hours = totals.get((username, name, e["season"]), 0)
            if g["hours"] and hours >= g["hours"] * 0.9:
                call("PATCH", f"/manage/library/{e['id']}", {
                    "completed": True, "completed_date": str(last_day[(username, name, e["season"])]),
                }, token=admin)
            if hours >= 3 and name not in rated and rng.random() < 0.8:
                rated.add(name)
                call("POST", "/manage/scores", {"user_id": ids[username], "game_id": g["id"], "score": rng.randint(55, 98)}, token=admin)

    print("wishlists...")
    upcoming = [name for name, game in games_by_name.items() if game["hours"] is None]
    for username, *_ in PLAYERS:
        for name in rng.sample(upcoming, k=rng.randint(1, 3)):
            call("PUT", f"/users/{username}/wishlist/{games_by_name[name]['id']}", token=tokens[username])

    print("challenges...")
    month = datetime.date.today().strftime("%Y-%m")
    for body in ({"kind": "game_of_month", "game_id": games_by_name["Hades II"]["id"], "month": month,
                  "min_hours_each": 5, "min_hours_total": 30, "announce": False},
                 {"kind": "themed", "theme": "Terror", "month": month, "mode": "play", "min_hours_each": 3, "announce": False}):
        try:
            call("POST", "/manage/challenges", body, token=admin)
        except RuntimeError as e:
            print("  skipped:", e)

    print("dates of the ratings and the audit log...")
    # a rating is dated when it was saved (now, for the seed): move each to the last time the game was played, and
    # leave the audit log with a few believable changes instead of every row the seed wrote
    sql("UPDATE game_scores gs SET updated_at = (SELECT MAX(t.end_time) FROM game_timers t "
        "WHERE t.user_id = gs.user_id AND t.game_id = gs.game_id) WHERE EXISTS (SELECT 1 FROM game_timers t "
        "WHERE t.user_id = gs.user_id AND t.game_id = gs.game_id)")
    sql("TRUNCATE TABLE audit_log")
    call("PUT", "/manage/settings", {"values": {"monthly.enabled": True}}, token=admin)
    call("PATCH", f"/manage/games/{games_by_name['Lanternfall']['id']}", {"dev": "Lantern Works"}, token=admin)
    call("PATCH", f"/manage/users/{ids['nico']}", {"name": "Nico"}, token=admin)
    call("POST", "/manage/platforms", {"name": "Meta Quest"}, token=admin)
    sql("UPDATE audit_log SET created_at = created_at - INTERVAL (5 - id %% 5) DAY - INTERVAL (id * 37 %% 600) MINUTE")

    print("two players playing right now...")
    for username, game in (("cai", "Hollow Knight"), ("eva", "Overcooked! 2")):
        g = games_by_name[game]
        call("POST", "/timers/start", {"user_id": ids[username], "game_id": g["id"], "platform": g["platforms"][0]}, token=tokens[username])
    print("done. Players: " + ", ".join(p[0] for p in PLAYERS) + " (password: DEMO_PLAYER_PASS in docs-demo/.env); admin: GOD_ADMIN_PASS")


if __name__ == "__main__":
    commands = {"up": up, "seed": seed, "down": down}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()
