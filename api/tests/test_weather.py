import datetime
import unittest
from unittest import mock

import requests

from src.database import models
from src.utils import places, weather
from tests.sqlite_db import make_session

DAY = datetime.date(2027, 5, 4)
MADRID = (40.4165, -3.70256)


def payload(day, codes):
    return {
        "hourly": {
            "time": [f"{day.isoformat()}T{hour:02d}:00" for hour in range(24)],
            "weather_code": codes,
        }
    }


def answer(body, ok=True, status=200):
    response = mock.Mock(ok=ok, status_code=status)
    response.json.return_value = body
    return response


class PureTests(unittest.TestCase):
    def test_the_answer_of_open_meteo_becomes_the_codes_of_each_hour_of_each_day(self):
        body = {"hourly": {"time": ["2027-05-04T00:00", "2027-05-04T23:00", "2027-05-05T01:00"], "weather_code": [3, None, 95]}}
        days = weather.parse(body)
        self.assertEqual(days[DAY][0], 3)
        self.assertIsNone(days[DAY][23])
        self.assertEqual(days[DAY + datetime.timedelta(days=1)][1], 95)
        self.assertEqual(weather.parse({}), {})

    def test_the_place_is_rounded_to_a_kilometre(self):
        self.assertEqual(weather.place_key(40.41651, -3.70256), "40.42,-3.70")

    def test_the_weather_is_the_one_of_the_hour_a_timer_started_in(self):
        codes = {DAY: [0] * 24}
        codes[DAY][21] = 95
        self.assertTrue(weather.at(codes, datetime.datetime(2027, 5, 4, 21, 59), weather.THUNDERSTORM))
        self.assertFalse(weather.at(codes, datetime.datetime(2027, 5, 4, 22, 0), weather.THUNDERSTORM))
        self.assertFalse(weather.at({}, datetime.datetime(2027, 5, 4, 21, 10), weather.THUNDERSTORM))  # a day it knows nothing about
        self.assertEqual({95, 96, 99}, weather.THUNDERSTORM)
        self.assertEqual({45, 48}, weather.FOG)

    def test_old_days_go_to_the_archive_and_recent_ones_to_the_forecast_in_requests_of_bounded_length(self):
        today = datetime.date(2027, 9, 1)
        old = [datetime.date(2027, 1, 1) + datetime.timedelta(days=n) for n in range(0, 70)]
        recent = [today - datetime.timedelta(days=2), today - datetime.timedelta(days=1)]
        chunks = weather.chunks(old + recent, today)
        self.assertEqual(chunks[0][0], weather.ARCHIVE_URL)
        self.assertEqual(sum(1 for url, _, _ in chunks if url == weather.ARCHIVE_URL), 2)  # 70 days: two requests
        self.assertEqual(chunks[-1], (weather.FORECAST_URL, recent[0], recent[1]))
        self.assertTrue(all((last - first).days < weather.CHUNK_DAYS for _, first, last in chunks))
        self.assertEqual(weather.chunks([], today), [])


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.db = make_session()
        weather._down_until = 0.0
        self.addCleanup(setattr, weather, "_down_until", 0.0)
        self.today = datetime.date(2027, 6, 1)

    def get(self, days, response):
        with mock.patch.object(weather.requests, "get", return_value=response) as get:
            return weather.codes_for_days(self.db, *MADRID, days, today=self.today), get

    def test_a_day_that_is_over_is_asked_for_once_and_kept(self):
        codes = [0] * 24
        codes[9] = 95
        found, get = self.get([DAY], answer(payload(DAY, codes)))
        self.assertEqual(found[DAY][9], 95)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"]["hourly"], "weather_code")
        self.assertEqual(self.db.query(models.WeatherDay).one().place, "40.42,-3.70")
        again, get = self.get([DAY], answer({}, ok=False, status=500))  # it does not even ask
        self.assertEqual(again[DAY][9], 95)
        get.assert_not_called()

    def test_today_and_a_day_with_missing_hours_are_never_kept(self):
        incomplete = [0] * 23 + [None]
        self.get([DAY], answer(payload(DAY, incomplete)))
        self.get([self.today], answer(payload(self.today, [0] * 24)))
        self.assertEqual(self.db.query(models.WeatherDay).count(), 0)

    def test_a_failure_is_unavailable_and_is_not_retried_at_once(self):
        with mock.patch.object(weather.requests, "get", side_effect=requests.ConnectionError("down")) as get:
            with self.assertRaises(weather.WeatherUnavailable):
                weather.codes_for_days(self.db, *MADRID, [DAY], today=self.today)
            with self.assertRaises(weather.WeatherUnavailable):
                weather.codes_for_days(self.db, *MADRID, [DAY], today=self.today)
        self.assertEqual(get.call_count, 1)

    def test_an_error_status_is_unavailable(self):
        with mock.patch.object(weather.requests, "get", return_value=answer({}, ok=False, status=429)):
            with self.assertRaises(weather.WeatherUnavailable):
                weather.codes_for_days(self.db, *MADRID, [DAY], today=self.today)


class PlacesTests(unittest.TestCase):
    def test_the_label_does_not_repeat_the_name(self):
        self.assertEqual(places.label({"name": "Madrid", "admin1": "Comunidad de Madrid", "country": "España"}), "Madrid, Comunidad de Madrid, España")
        self.assertEqual(places.label({"name": "Madrid", "admin1": "Madrid", "country": "España"}), "Madrid, España")

    def test_the_answers_without_coordinates_are_left_out(self):
        body = {"results": [
            {"name": "Madrid", "admin1": "Comunidad de Madrid", "country": "España", "latitude": 40.41650001, "longitude": -3.70256},
            {"name": "Nowhere"},
        ]}
        self.assertEqual(places.parse(body), [{"name": "Madrid, Comunidad de Madrid, España", "latitude": 40.4165, "longitude": -3.70256}])
        self.assertEqual(places.parse({}), [])

    def test_a_short_query_asks_nothing(self):
        with mock.patch.object(places.requests, "get") as get:
            self.assertEqual(places.search(" a "), [])
        get.assert_not_called()

    def test_search_asks_in_spanish_and_reports_a_failure(self):
        with mock.patch.object(places.requests, "get", return_value=answer({"results": []})) as get:
            self.assertEqual(places.search("Madrid"), [])
        self.assertEqual(get.call_args.kwargs["params"]["language"], "es")
        with mock.patch.object(places.requests, "get", side_effect=requests.Timeout("slow")):
            with self.assertRaises(places.PlacesUnavailable):
                places.search("Madrid")
