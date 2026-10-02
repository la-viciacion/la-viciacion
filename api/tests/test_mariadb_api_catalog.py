"""Games, platforms, achievement images, rankings and push subscriptions through real requests (MariaDB
required, see api_support.py). RAWG and HowLongToBeat are replaced by fakes: nothing leaves the process."""
import datetime
import io
from datetime import timedelta
from types import SimpleNamespace
from unittest import mock

from PIL import Image

from src.database import database
from src.utils import messages, my_utils, push, seasons, settings
from tests.api_support import ApiTestCase


def ago(**delta) -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0) - timedelta(**delta)


class Response:
    """What `requests.get` returns, as far as the code uses it."""

    def __init__(self, payload=None, ok=True, status=200):
        self.payload, self.ok, self.status_code, self.content = payload, ok, status, b"body"

    def json(self):
        return self.payload


class Rawg:
    """A fake RAWG: answers the search and the details/stores endpoints from a dict."""

    def __init__(self, search=None, details=None, stores=None, fail=False):
        self.search, self.details, self.stores, self.fail, self.calls = search or [], details or {}, stores or {}, fail, []

    async def __call__(self, url, params, timeout):
        self.calls.append(url)
        if self.fail:
            raise ConnectionError("RAWG is down")
        if url.endswith("/stores"):
            rawg_id = int(url.split("/")[-2])
            return Response({"results": self.stores.get(rawg_id, [])})
        if url.rstrip("/").endswith("/games"):
            return Response({"results": self.search})
        rawg_id = int(url.rstrip("/").split("/")[-1])
        return Response(self.details[rawg_id]) if rawg_id in self.details else Response(ok=False, status=404)


def hltb(*results, fail=False):
    """A fake HowLongToBeat class whose search returns `results`."""

    class Fake:
        async def async_search(self, name):
            if fail:
                raise TimeoutError("HLTB is down")
            return list(results)

    return Fake


def hltb_hit(main=12.4, dev="HLTB Studio", steam=None, similarity=0.9):
    return SimpleNamespace(similarity=similarity, gameplay_main=main, profile_dev=dev, profile_steam=steam, json_content={"x": 1})


CELESTE = {"id": 101, "name": "Celeste", "slug": "celeste", "released": "2018-01-25", "background_image": "https://img/celeste.jpg",
           "genres": [{"name": "Platformer"}, {"name": "Indie"}], "developers": [{"name": "Maddy Makes Games"}],
           "publishers": [{"name": "Publisher Co"}], "platforms": [{"platform": {"name": "PC"}}, {"platform": {"name": "Nintendo Switch"}}],
           "rating": 4.4, "metacritic": 92}


class CatalogTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.ana = self.user("ana")
        self.root = self.user("root", admin=True)

    def with_rawg(self, rawg, hltb_class=None):
        """Turns on a RAWG key and puts the fakes in place for the rest of the test."""
        for patcher in (
            mock.patch.object(type(my_utils.config), "RAWG_API_KEY", new_callable=mock.PropertyMock, return_value="test-key"),
            mock.patch.object(my_utils, "_http_get", new=rawg),
            mock.patch.object(my_utils, "HowLongToBeat", new=hltb_class or hltb()),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)


class GamesTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.game("celeste", "Celeste", genres="Platformer")
        self.game("hades", "Hades")
        self.game("hollow-knight", "Hollow Knight")

    def test_the_catalogue_needs_a_login(self):
        self.assertEqual(self.api("GET", "/games/").status_code, 401)

    def test_it_lists_the_games_with_an_optional_limit(self):
        self.assertEqual(len(self.api("GET", "/games/", as_user="ana").json()), 3)
        self.assertEqual(len(self.api("GET", "/games/", as_user="ana", params={"limit": 2}).json()), 2)

    def test_it_searches_by_part_of_the_name(self):
        found = self.api("GET", "/games/", as_user="ana", params={"name": "ll"}).json()
        self.assertEqual(sorted(g["name"] for g in found), ["Hollow Knight"])
        self.assertEqual(self.api("GET", "/games/", as_user="ana", params={"name": "zzz"}).json(), [])

    def test_it_returns_one_game_or_404(self):
        self.assertEqual(self.api("GET", "/games/celeste", as_user="ana").json()["genres"], "Platformer")
        missing = self.api("GET", "/games/nope", as_user="ana")
        self.assertEqual((missing.status_code, missing.json()["detail"]), (404, "Game not exists"))

    def test_only_an_admin_edits_a_game_and_empty_fields_keep_their_value(self):
        body = {"name": "Celeste (Deluxe)", "dev": "Matt Makes Games"}
        self.assertEqual(self.api("PUT", "/games/celeste", as_user="ana", json=body).status_code, 403)
        done = self.api("PUT", "/games/celeste", as_user="root", json=body).json()
        self.assertEqual((done["name"], done["dev"], done["genres"]), ("Celeste (Deluxe)", "Matt Makes Games", "Platformer"))
        self.assertEqual(self.api("PUT", "/games/nope", as_user="root", json=body).status_code, 404)
        self.assertEqual(self.api("PUT", "/games/celeste", as_user="root", json={"dev": "x"}).status_code, 422)  # the name is required


class SearchRawgTests(CatalogTestCase):
    def search(self, query="cel"):
        return self.api("GET", "/games/search-rawg", as_user="ana", params={"query": query})

    def test_a_query_needs_two_characters(self):
        self.assertEqual(self.search("a").status_code, 400)
        self.assertEqual(self.search("  ").status_code, 400)

    def test_without_a_key_it_finds_nothing(self):
        self.assertEqual(self.search().json(), [])

    def test_the_results_are_mapped_and_marked_when_the_game_is_already_here(self):
        other = dict(CELESTE, id=102, name="Celeste Classic", slug="celeste-classic")
        self.with_rawg(Rawg(search=[CELESTE, other]))
        self.game("celeste", "Celeste", rawg_id=101)
        first, second = self.search().json()
        self.assertEqual((first["rawg_id"], first["name"], first["released"]), (101, "Celeste", "2018-01-25"))
        self.assertEqual((first["genres"], first["platforms"]), (["Platformer", "Indie"], ["PC", "Nintendo Switch"]))
        self.assertEqual((first["exists_in_db"], first["db_game_id"]), (True, "celeste"))
        self.assertFalse(second["exists_in_db"])

    def test_a_game_is_recognised_by_name_or_slug_too(self):
        self.with_rawg(Rawg(search=[CELESTE]))
        self.game("by-name", "Celeste")
        self.assertTrue(self.search().json()[0]["exists_in_db"])

    def test_a_failing_rawg_is_an_empty_list_not_an_error(self):
        self.with_rawg(Rawg(fail=True))
        self.assertEqual(self.search().json(), [])
        self.with_rawg(Rawg())
        with mock.patch.object(my_utils, "_http_get", new=mock.AsyncMock(return_value=Response(ok=False, status=500))):
            self.assertEqual(self.search().json(), [])


class CreateGameTests(CatalogTestCase):
    def create(self, **body):
        body.setdefault("name", "Celeste")
        return self.api("POST", "/games/", as_user="ana", json=body)

    def test_a_game_is_stored_with_what_rawg_and_howlongtobeat_know(self):
        rawg = Rawg(details={101: CELESTE}, stores={101: [{"url": "https://store.steampowered.com/app/504230/Celeste/"}]})
        self.with_rawg(rawg, hltb(hltb_hit(main=12.4)))
        response = self.create(rawg_id=101)
        self.assertEqual(response.status_code, 201)
        game = response.json()
        self.assertEqual((game["name"], game["dev"], game["slug"], game["rawg_id"]), ("Celeste", "Maddy Makes Games", "celeste", 101))
        self.assertEqual((game["genres"], game["steam_id"], game["avg_time"], game["release_date"]), ("Platformer,Indie", "504230", 12, "2018-01-25"))
        self.assertEqual(len(game["id"]), 36)  # a generated uuid
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM games"), 1)

    def test_the_developer_falls_back_to_the_publisher_and_then_to_howlongtobeat(self):
        no_dev = dict(CELESTE, developers=[])
        self.with_rawg(Rawg(details={101: no_dev}), hltb(hltb_hit()))
        self.assertEqual(self.create(rawg_id=101).json()["dev"], "Publisher Co")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM games"), 1)
        nobody = dict(CELESTE, id=202, name="Other", slug="other", developers=[], publishers=[])
        self.with_rawg(Rawg(details={202: nobody}), hltb(hltb_hit(dev="HLTB Studio", steam=777)))
        other = self.create(name="Other", rawg_id=202).json()
        self.assertEqual((other["dev"], other["steam_id"]), ("HLTB Studio", "777"))

    def test_a_failing_howlongtobeat_does_not_stop_the_game_from_being_added(self):
        self.with_rawg(Rawg(details={101: CELESTE}), hltb(fail=True))
        game = self.create(rawg_id=101).json()
        self.assertEqual((game["name"], game["avg_time"]), ("Celeste", 0))

    def test_without_a_rawg_id_the_best_search_result_is_used(self):
        self.with_rawg(Rawg(search=[CELESTE], details={101: CELESTE}))
        game = self.create(name="celeste").json()
        self.assertEqual((game["name"], game["rawg_id"]), ("Celeste", 101))

    def test_when_rawg_knows_nothing_the_game_is_added_as_typed(self):
        self.with_rawg(Rawg())
        game = self.create(name="My Indie Thing").json()
        self.assertEqual((game["name"], game["dev"], game["rawg_id"], game["avg_time"]), ("My Indie Thing", "-", None, 0))

    def test_without_a_rawg_key_it_still_works(self):
        game = self.create(name="Offline Game").json()
        self.assertEqual((game["name"], game["rawg_id"]), ("Offline Game", None))

    def test_a_game_already_in_the_database_is_refused_by_rawg_id_or_by_name(self):
        self.game("celeste", "Celeste", rawg_id=101)
        self.assertEqual(self.create(name="Whatever", rawg_id=101).status_code, 400)
        duplicate = self.create(name="CELESTE")
        self.assertEqual((duplicate.status_code, duplicate.json()["detail"]), (400, "Game already in DB"))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM games"), 1)

    def test_rawg_resolving_to_a_game_already_here_returns_that_game(self):
        self.game("celeste", "Celeste")
        self.with_rawg(Rawg(search=[CELESTE], details={101: CELESTE}))
        response = self.create(name="celeste classic remaster")  # a different typed name that RAWG resolves to Celeste
        self.assertEqual(response.json()["id"], "celeste")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM games"), 1)


class PlatformsAndAchievementImagesTests(CatalogTestCase):
    def png(self):
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), (1, 2, 3)).save(buffer, "PNG")
        return buffer.getvalue()

    def key(self):
        return self.scalar("SELECT `key` FROM achievements ORDER BY id LIMIT 1")

    def put(self, data, key=None, as_user="root"):
        return self.api("PATCH", f"/utils/achievement-image/{key or self.key()}", as_user=as_user, files={"file": ("a.png", data, "image/png")})

    def test_the_platforms_need_a_login_and_come_with_names(self):
        self.assertEqual(self.api("GET", "/utils/platforms").status_code, 401)
        platforms = {p["id"]: p["name"] for p in self.api("GET", "/utils/platforms", as_user="ana").json()}
        self.assertEqual(platforms["pc"], "PC")
        self.assertIn("switch", platforms)

    def test_an_achievement_image_is_public_once_uploaded(self):
        key = self.key()
        self.assertEqual(self.api("GET", f"/utils/achievement-image/{key}").status_code, 400)  # none yet
        self.assertEqual(self.put(self.png()).status_code, 200)
        served = self.api("GET", f"/utils/achievement-image/{key}")  # no token: an <img> cannot send one
        self.assertEqual((served.status_code, served.headers["content-type"], served.content), (200, "image/png", self.png()))

    def test_an_unknown_achievement_is_a_404(self):
        self.assertEqual(self.api("GET", "/utils/achievement-image/nope").status_code, 404)
        self.assertEqual(self.put(self.png(), key="nope").status_code, 404)

    def test_only_an_admin_uploads_and_only_real_small_images(self):
        self.assertEqual(self.put(self.png(), as_user="ana").status_code, 403)
        refused = self.put(b"GIF89a not an image")
        self.assertEqual((refused.status_code, refused.json()["detail"]), (400, messages.FILE_TYPE_NOT_ALLOWED))
        big = self.put(b"\x89PNG" + b"0" * 1_100_000)
        self.assertEqual((big.status_code, big.json()["detail"]), (400, messages.FILE_TOO_BIG_ACHIEVEMENTS))


class RankingsTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.bea = self.user("bea")
        self.game("celeste", "Celeste")
        self.game("hades", "Hades")
        today = datetime.date.today()
        for days in (0, 1, 2):
            self.session(self.ana, "celeste", ago(days=days, hours=2), 60)
        self.session(self.bea, "hades", ago(hours=5), 30, "switch")
        self.library_entry(self.ana, "celeste", today, "pc", completed=1, completed_date=today)
        self.library_entry(self.bea, "hades", today, "switch")

    def rankings(self, **params):
        response = self.api("GET", "/statistics/rankings", as_user="ana", params=params)
        self.assertEqual(response.status_code, 200)
        return {block["type"]: block["data"] for block in response.json()}

    def test_every_ranking_is_returned_by_default(self):
        self.assertEqual(
            list(self.rankings()),
            ["user_hours", "user_days", "user_played_games", "user_completed_games", "achievements", "user_ratio",
             "user_current_streak", "user_best_streak", "games_most_played", "platform_played", "debt", "games_last_played"],
        )

    def test_the_players_are_ranked_by_hours_days_and_streaks(self):
        data = self.rankings()
        self.assertEqual([(r["name"], r["played_time"]) for r in data["user_hours"]][:2], [("Ana", 10800), ("Bea", 1800)])
        self.assertEqual([(r["name"], r["played_days"]) for r in data["user_days"]][:2], [("Ana", 3), ("Bea", 1)])
        self.assertEqual(data["user_current_streak"][0]["current_streak"], 3)
        self.assertEqual(data["user_best_streak"][0]["best_streak"], 3)

    def test_games_and_platforms_are_ranked_too(self):
        data = self.rankings()
        self.assertEqual([(g["game_id"], g["played_time"]) for g in data["games_most_played"]], [("celeste", 10800), ("hades", 1800)])
        self.assertEqual([g["game_id"] for g in data["games_last_played"]], ["celeste", "hades"])
        self.assertEqual({p["tag_id"]: p["count"] for p in data["platform_played"]}, {"pc": 1, "switch": 1})

    def test_completions_and_ratio(self):
        data = self.rankings()
        self.assertEqual(data["user_completed_games"][0]["completed_games"], 1)
        self.assertEqual(data["user_ratio"][0]["ratio"], 1.0)
        self.assertEqual(data["debt"], [{"message": "Debt is not implemented yet"}])

    def test_a_subset_can_be_asked_for_and_an_unknown_one_is_answered_politely(self):
        data = self.rankings(ranking="user_hours,nope")
        self.assertEqual(list(data), ["user_hours", "nope"])
        self.assertEqual(data["nope"], {"message": "More rankings are coming"})

    def test_the_emergency_account_and_the_disabled_never_appear(self):
        self.user("admin", admin=True)
        self.user("gone", active=False)
        names = {r["name"] for r in self.rankings(ranking="user_hours")["user_hours"]}
        self.assertNotIn("Admin", names)
        self.assertNotIn("Gone", names)

    def test_a_previous_season_does_not_count(self):
        self.session(self.bea, "celeste", datetime.datetime(seasons.current() - 1, 5, 1, 20, 0), 600)
        hours = {r["name"]: r["played_time"] for r in self.rankings(ranking="user_hours")["user_hours"]}
        self.assertEqual(hours["Bea"], 1800)

    def test_rankings_need_a_login(self):
        self.assertEqual(self.api("GET", "/statistics/rankings").status_code, 401)


class UserStatisticsTests(CatalogTestCase):
    def setUp(self):
        super().setUp()
        self.game("celeste", "Celeste")
        today = datetime.date.today()
        self.session(self.ana, "celeste", ago(hours=3), 60)
        self.library_entry(self.ana, "celeste", today, "pc", completed=1, completed_date=today)

    def stats(self, as_user="ana", username="ana", **params):
        return self.api("GET", f"/statistics/users/{username}", as_user=as_user, params=params)

    def test_every_kind_is_returned_by_default_with_its_length(self):
        blocks = {b["type"]: b for b in self.stats().json()}
        self.assertEqual(list(blocks), ["played_games", "completed_games", "top_games", "achievements", "streak"])
        self.assertEqual((blocks["played_games"]["len_data"], blocks["completed_games"]["len_data"]), (1, 1))
        self.assertEqual(blocks["top_games"]["data"][0]["game_id"], "celeste")
        self.assertEqual(blocks["achievements"]["data"], [])

    def test_a_subset_and_an_unknown_kind(self):
        blocks = self.stats(ranking="played_games,nonsense").json()
        self.assertEqual([b["type"] for b in blocks], ["played_games", "nonsense"])
        self.assertEqual(blocks[1]["data"], {"message": "nonsense is not a valid ranking"})

    def test_it_is_private_and_unknown_users_are_404(self):
        self.user("bea")
        self.assertEqual(self.stats(as_user="bea").status_code, 403)
        self.assertEqual(self.stats(as_user="root").status_code, 200)
        self.assertEqual(self.stats(as_user="root", username="nobody").status_code, 404)


class PushTests(CatalogTestCase):
    SUBSCRIPTION = {"endpoint": "https://push.example/send/abc", "keys": {"p256dh": "p256", "auth": "auth"}, "user_agent": "Chrome on Android"}

    def enable_push(self):
        with database.SessionLocal() as db:
            push.ensure_vapid_keys(db)
            settings.set_values(db, {"push.enabled": True})
        settings._cache.clear()

    def subscribe(self, as_user="ana", **overrides):
        return self.api("POST", "/push/subscribe", as_user=as_user, json={**self.SUBSCRIPTION, **overrides})

    def test_push_is_off_until_an_admin_turns_it_on(self):
        config = self.api("GET", "/push/config", as_user="ana").json()
        self.assertEqual(config, {"enabled": False, "public_key": None, "devices": []})
        refused = self.subscribe()
        self.assertEqual(refused.status_code, 409)

    def test_once_enabled_the_public_key_is_offered(self):
        self.enable_push()
        config = self.api("GET", "/push/config", as_user="ana").json()
        self.assertTrue(config["enabled"])
        self.assertTrue(config["public_key"])

    def test_a_device_is_registered_listed_and_refreshed_not_duplicated(self):
        self.enable_push()
        self.assertEqual(self.subscribe().status_code, 200)
        self.assertEqual(self.subscribe(user_agent="Chrome 2").status_code, 200)
        devices = self.api("GET", "/push/config", as_user="ana").json()["devices"]
        self.assertEqual(len(devices), 1)
        self.assertEqual((devices[0]["endpoint"], devices[0]["receive_group"], devices[0]["user_agent"]), (self.SUBSCRIPTION["endpoint"], True, "Chrome 2"))

    def test_a_device_that_changes_account_moves_to_it(self):
        self.enable_push()
        self.user("bea")
        self.subscribe()
        self.subscribe(as_user="bea")
        self.assertEqual(self.api("GET", "/push/config", as_user="ana").json()["devices"], [])
        self.assertEqual(len(self.api("GET", "/push/config", as_user="bea").json()["devices"]), 1)

    def test_only_the_newest_devices_are_kept(self):
        self.enable_push()
        for n in range(push.MAX_DEVICES_PER_USER + 3):
            self.subscribe(endpoint=f"https://push.example/send/{n}")
        endpoints = [d["endpoint"] for d in self.api("GET", "/push/config", as_user="ana").json()["devices"]]
        self.assertEqual(len(endpoints), push.MAX_DEVICES_PER_USER)
        self.assertNotIn("https://push.example/send/0", endpoints)
        self.assertIn(f"https://push.example/send/{push.MAX_DEVICES_PER_USER + 2}", endpoints)

    def test_the_subscription_is_validated(self):
        self.enable_push()
        self.assertEqual(self.subscribe(endpoint="http://insecure.example/x").status_code, 422)
        self.assertEqual(self.subscribe(endpoint="").status_code, 422)
        self.assertEqual(self.subscribe(keys={"p256dh": "", "auth": "a"}).status_code, 422)
        self.assertEqual(self.subscribe(endpoint="https://" + "a" * 800).status_code, 422)

    def test_a_device_is_removed_only_by_its_owner(self):
        self.enable_push()
        self.user("bea")
        self.subscribe()
        self.api("POST", "/push/unsubscribe", as_user="bea", json={"endpoint": self.SUBSCRIPTION["endpoint"]})
        self.assertEqual(len(self.api("GET", "/push/config", as_user="ana").json()["devices"]), 1)
        self.api("POST", "/push/unsubscribe", as_user="ana", json={"endpoint": self.SUBSCRIPTION["endpoint"]})
        self.assertEqual(self.api("GET", "/push/config", as_user="ana").json()["devices"], [])

    def test_a_device_can_stop_receiving_group_notices_but_only_its_owner_decides(self):
        self.enable_push()
        self.user("bea")
        self.subscribe()
        mine = {"endpoint": self.SUBSCRIPTION["endpoint"], "receive_group": False}
        self.assertEqual(self.api("PATCH", "/push/subscription", as_user="bea", json=mine).status_code, 404)
        self.assertEqual(self.api("PATCH", "/push/subscription", as_user="ana", json=mine).json(), {"receive_group": False})
        self.assertFalse(self.api("GET", "/push/config", as_user="ana").json()["devices"][0]["receive_group"])

    def test_every_push_route_needs_a_login(self):
        self.assertEqual(self.api("GET", "/push/config").status_code, 401)
        self.assertEqual(self.api("POST", "/push/subscribe", json=self.SUBSCRIPTION).status_code, 401)
