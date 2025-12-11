import datetime
from datetime import timezone

import requests
from utils.config import Config

from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()


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
                logger.info("Error on send request on clockify")
                exit(e)

            if not request.ok:
                logger.debug(
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

    def get_project(self, project_id):
        # https://api.clockify.me/api/v1/workspaces/{workspaceId}/projects/{projectId}
        method = self.GET
        endpoint = "/workspaces/{}/projects/{}".format(
            config.CLOCKIFY_WORKSPACE, project_id
        )
        response = self.send_clockify_request(
            method, endpoint, None, config.CLOCKIFY_ADMIN_API_KEY
        )
        return response.json()

    def get_project_id_by_strict_name(self, game_name, api_key):
        if api_key is None:
            return self.API_USER_NOT_ADDED
        else:
            method = self.GET
            endpoint = (
                "/workspaces/{0}/projects?name={1}&strict-name-search=true".format(
                    config.CLOCKIFY_WORKSPACE, game_name
                )
            )
            data = None
            response = self.send_clockify_request(method, endpoint, data, api_key)
            if response.status_code == 200 and len(response.json()) > 0:
                return response.json()[0].get("id")
            else:
                Exception(game_name + " not exists")
                # exit()

    def get_time_entries(self, user_id, start=None):
        if user_id is None:
            return []
        page = 0
        headers = {"X-API-KEY": config.CLOCKIFY_ADMIN_API_KEY}
        entries = []
        has_entries = True
        while has_entries:
            page += 1
            if start is not None:
                endpoint = "/workspaces/{}/user/{}/time-entries?page-size=500&page={}&start={}".format(
                    config.CLOCKIFY_WORKSPACE, user_id, page, start
                )
            else:
                endpoint = (
                    "/workspaces/{}/user/{}/time-entries?page-size=500&page={}".format(
                        config.CLOCKIFY_WORKSPACE, user_id, page
                    )
                )
            response = self.send_clockify_request(
                self.GET, endpoint, None, config.CLOCKIFY_ADMIN_API_KEY
            )
            if len(response.json()) > 0:
                for entry in response.json():
                    entries.append(entry)
            else:
                has_entries = False
        return entries

    def add_time_entry(self, player, date, time):
        return
