import datetime
import json
from datetime import timezone

import requests

from ..config import Config
from . import my_utils as utils
from .logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()
time_format = "%Y-%m-%dT%H:%M:%SZ"
current_season = datetime.datetime.now().year


class ClockifyApi:
    def __init__(self) -> None:
        self.RESPONSE_OK = 0
        self.ERROR_TIMER_ACTIVE = 1
        self.GENERIC_ERROR = 2
        self.USER_NOT_EXISTS = 3
        self.API_USER_NOT_ADDED = 4
        self.GET = "GET"
        self.POST = "POST"
        self.PATCH = "PATCH"

    def send_clockify_request(self, method, endpoint, data, api_key):
        if api_key is None and api_key != config.CLOCKIFY_ADMIN_API_KEY:
            return self.API_USER_NOT_ADDED
        else:
            url = "{0}{1}".format(config.CLOCKIFY_BASEURL, endpoint)
            headers = {"X-API-KEY": api_key}
            payload = data
            try:
                if payload is not None:
                    request = requests.request(
                        method, url, headers=headers, json=payload
                    )
                else:
                    request = requests.request(method, url, headers=headers)
            except Exception as e:
                logger.error("Error on send request on clockify")
                exit(e)

            if not request.ok:
                logger.error(
                    "Error({}): {}".format(request.status_code, request.content)
                )
            return request

    def add_project(self, project_name):
        method = self.POST
        data = {"name": project_name}
        endpoint = "/workspaces/{}/projects".format(config.CLOCKIFY_WORKSPACE)
        response = self.send_clockify_request(
            method, endpoint, data, config.CLOCKIFY_ADMIN_API_KEY
        )
        return response.json()

    def get_project_by_id(self, project_id) -> json:
        method = self.GET
        endpoint = "/workspaces/{}/projects/{}".format(
            config.CLOCKIFY_WORKSPACE, project_id
        )
        response = self.send_clockify_request(
            method, endpoint, None, config.CLOCKIFY_ADMIN_API_KEY
        )
        return response.json()

    def get_project_by_name(self, project_name, strict=False) -> json:
        method = self.GET
        if strict:
            endpoint = "/workspaces/{}/projects?name={}&strict-name-search=true".format(
                config.CLOCKIFY_WORKSPACE, project_name
            )
        else:
            endpoint = "/workspaces/{}/projects?name={}".format(
                config.CLOCKIFY_WORKSPACE, project_name
            )
        response = self.send_clockify_request(
            method, endpoint, None, config.CLOCKIFY_ADMIN_API_KEY
        )
        return response.json()

    def update_project_name(self, project_id, project_name):
        # /workspaces/{workspaceId}/projects/{projectId}
        logger.info("Updating clockify name project")
        data = {"name": project_name}
        response = self.send_clockify_request(
            "PUT",
            "/workspaces/" + config.CLOCKIFY_WORKSPACE + "/projects/" + project_id,
            data,
            config.CLOCKIFY_ADMIN_API_KEY,
        )
        return response.json()

    def send_clockify_timer_request(self, action, user_id, game_name, api_key):
        method = None
        data = None
        now = datetime.datetime.now(timezone.utc).strftime(time_format)
        user = ""  # TODO: migrate to DB. config.CLOCKIFY_USERS.get(user_id)
        if api_key is None:
            return self.API_USER_NOT_ADDED
        else:
            if user is not None:
                endpoint = "/workspaces/{}/user/{}/time-entries".format(
                    config.CLOCKIFY_WORKSPACE, user
                )
                if action == "start":
                    project_id = self.get_project_id_by_strict_name(game_name, api_key)
                    method = self.POST
                    data = {
                        "start": now,
                        "description": "new time register for " + game_name,
                        "billable": "false",
                        "projectId": project_id,
                    }
                elif action == "stop":
                    method = self.PATCH
                    data = {
                        "end": now,
                    }
            else:
                return self.USER_NOT_EXISTS
            response = self.send_clockify_request(method, endpoint, data, api_key)
            # TODO add more handles (if needed)
            if response.status_code == 404 and action == "stop":
                return self.ERROR_TIMER_ACTIVE
            elif response.status_code == 200 or response.status_code == 201:
                return self.RESPONSE_OK
            else:
                return self.GENERIC_ERROR

    def get_time_entries(self, clockify_user_id, start_date=None):
        # logger.debug("Getting time entries...")
        if clockify_user_id is None or not utils.check_hex(clockify_user_id):
            return []
        # start must be in format yyyy-MM-ddThh:mm:ssZ
        try:
            if start_date is None:
                date = datetime.datetime.now()
                date = date.replace(hour=0, minute=0, second=0)
                start = date - datetime.timedelta(days=config.SYNC_DAYS)
                start = start.strftime(time_format)
            else:
                date = datetime.datetime.strptime(start_date, "%Y-%m-%d")
                start = date - datetime.timedelta()
                start = start.strftime(time_format)
            page = 0
            entries = []
            has_entries = True

            while has_entries:
                page += 1
                endpoint = "/workspaces/{}/user/{}/time-entries?page-size=500&page={}&start={}".format(
                    config.CLOCKIFY_WORKSPACE, clockify_user_id, page, start
                )
                response = self.send_clockify_request(
                    self.GET, endpoint, None, config.CLOCKIFY_ADMIN_API_KEY
                )
                if len(response.json()) > 0 and response.status_code == 200:
                    for entry in response.json():
                        entries.append(entry)
                else:
                    has_entries = False

            def get_date(elem):
                return datetime.datetime.fromisoformat(elem["timeInterval"]["start"])

            ordered_entries = sorted(entries, key=get_date)

            # Filter entries by season. Only get the current season
            if start_date is None:
                filtered_entries = [
                    entry for entry in ordered_entries 
                    if get_date(entry).year == current_season
                ]

                return filtered_entries
            return ordered_entries
        except Exception as e:
            logger.error("Error getting time entries: " + str(e))
            raise e

    def update_time_entry(self):
        # /workspaces/{workspaceId}/time-entries/{id}
        return

    def create_empty_time_entry(
        self, db, user_api_key, project_id, platform, completed=False
    ):
        # /workspaces/{workspaceId}/time-entries
        try:
            if user_api_key is not None:
                start_date = datetime.datetime.now(timezone.utc).strftime(time_format)
                end_date = datetime.datetime.now(timezone.utc).strftime(time_format)
                tags = []
                tags.append(platform)
                data = {
                    # "description": "string",
                    "end": end_date,
                    "projectId": project_id,
                    "start": start_date,
                    "tagIds": tags,
                }
                if completed:
                    logger.info("Add completed tag to time entry.")
                    tags.append(utils.get_completed_tag(db)[0])
                    data["description"] = "BipBup. ¡Juego completado!"
                response = self.send_clockify_request(
                    "POST",
                    "/workspaces/" + config.CLOCKIFY_WORKSPACE + "/time-entries",
                    data,
                    user_api_key,
                )
                return response.json()
            else:
                logger.warning("Invalid Clockify API Key")
        except Exception as e:
            logger.warning("Error creating empty entry: " + str(e))

    def get_tags(self):
        response = self.send_clockify_request(
            "GET",
            "/workspaces/" + config.CLOCKIFY_WORKSPACE + "/tags",
            None,
            config.CLOCKIFY_ADMIN_API_KEY,
        )
        return response.json()

    def get_user_by_email(self, email):
        method = self.GET
        endpoint = "/workspaces/{}/users".format(config.CLOCKIFY_WORKSPACE)
        response = self.send_clockify_request(
            method, endpoint, None, config.CLOCKIFY_ADMIN_API_KEY
        )
        for user in response.json():
            if user["email"] == email:
                return user
