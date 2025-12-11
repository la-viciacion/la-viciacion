import datetime
import json
import logging
import os
import random
import re
import sys

import requests
import telegram
import utils.messages as msgs
from telegram import Bot, Update
from telegram.ext import ContextTypes, ConversationHandler
from utils.clockify_api import ClockifyApi
from utils.config import Config
from typing import Tuple, Dict, Any
from utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()
clockify = ClockifyApi()


class MyUtils:
    """_summary_"""

    def __init__(self, silent=None):
        self.bot = Bot(config.TELEGRAM_TOKEN)
        self.silent = silent
        # Conversation routes
        (
            self.ACTIVATE_ACCOUNT,
            self.MAIN_MENU,
            self.MY_ROUTES,
            self.RANKING_ROUTES,
            self.INFO_GAME,
            self.SEND_MESSAGE,
            self.EXCEL_STUFF,
            self.EXCEL_TIME_SELECT_GAME,
            self.EXCEL_ADD_TIME,
            self.EXCEL_CONFIRM_TIME,
            self.EXCEL_COMPLETE_GAME,
            self.EXCEL_CONFIRM_COMPLETED,
            self.EXCEL_ADD_GAME,
            self.EXCEL_ADD_GAME_PLATFORM,
            self.EXCEL_ADD_GAME_CONFIRMATION,
            self.EXCEL_RATE_GAME,
            self.EXCEL_RATE_GAME_RATING,
            self.EXCEL_CONFIRM_RATE,
            self.EXCEL_START_TIMER,
            self.EXCEL_START_TIMER_COMPLETED,
            self.EXCEL_STOP_TIMER,
        ) = range(21)

    def make_request(self, method, url, json=None):
        headers = {"x-api-key": config.API_KEY}
        response = requests.request(method, url=url, headers=headers, json=json)
        return response

    def make_clockify_request(self, method, url, json=None):
        headers = {"X-API-KEY": config.CLOCKIFY_ADMIN_API_KEY}
        response = requests.request(method, url=url, headers=headers, json=json)
        return response

    async def send_message(self, msg):
        async with self.bot:
            await self.bot.send_message(
                chat_id=config.TELEGRAM_GROUP_ID,
                text=msg,
                parse_mode=telegram.constants.ParseMode.MARKDOWN,
            )

    async def send_admin_message(self, msg):
        async with self.bot:
            await self.bot.send_message(
                chat_id=config.TELEGRAM_ADMIN_CHAT_ID,
                text=msg,
                parse_mode=telegram.constants.ParseMode.MARKDOWN,
            )

    async def send_photo(self, msg, picture_url):
        async with self.bot:
            await self.bot.send_photo(
                chat_id=config.TELEGRAM_GROUP_ID,
                caption=msg,
                photo=picture_url,
                parse_mode=telegram.constants.ParseMode.MARKDOWN,
            )

    def check_valid_chat(self, update: Update) -> Tuple[bool, Dict[str, Any]]:
        try:
            username = update.message.from_user.username
            user_id = update.message.from_user.id
            chat_id = update.message.chat_id
            if chat_id < 0:
                if chat_id != int(config.TELEGRAM_GROUP_ID):
                    return False, {}
            url = config.API_URL + "/users/" + username
            logger.info(url)
            response = self.make_request("GET", url)
            if response.status_code == 200:
                user = {"username": username, "telegram_id": user_id}
                url = config.API_URL + "/users"
                response = self.make_request("PATCH", url, json=user)
                logger.info(response.json())
                return True, response.json()
            else:
                logger.info("STATUS CODE: " + str(response.status_code))
                logger.info(
                    "Error on request to check valid chat: " + str(response.status_code)
                )
                logger.info(response.json())
                logger.info("Response above.")
                return False, {"error": "not_found"}
        except Exception as e:
            logger.info("Error checking valid chat: " + str(e))
            if "Max retries exceeded" in str(e):
                return False, {"error": "api"}
            else:
                return False, {"error": "unknown"}

    async def reply_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, msg
    ) -> None:
        await update.message.reply_text(
            msg,
            disable_notification=True,
            disable_web_page_preview=None,
            parse_mode=telegram.constants.ParseMode.MARKDOWN,
        )
        return ConversationHandler.END

    async def response_conversation(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, msg
    ):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            msg, parse_mode=telegram.constants.ParseMode.MARKDOWN
        )
        return ConversationHandler.END

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        name = update.message.from_user.first_name
        msg = msgs.start(name)
        await self.reply_message(update, context, msg)

    async def info_dev(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat_id = update.message.chat_id
        await self.reply_message(update, context, chat_id)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        msg = msgs.command_list
        await self.reply_message(update, context, msg)

    def convert_time_to_hours(self, seconds):
        if seconds is None:
            return "0h0m"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining_seconds = seconds % 60
        return f"{hours}h{minutes}m{remaining_seconds}s"

    def convert_hours_minutes_to_seconds(self, time) -> int:
        if time is None:
            return 0
        return time * 3600

    def format_text_for_md2(self, text):
        text = (
            text.replace(".", "\.")
            .replace("!", "\!")
            .replace("-", "\-")
            .replace("+", "\+")
            .replace("=", "\=")
            .replace("(", "\(")
            .replace(")", "\)")
            .replace("[", "\[")
            .replace("]", "\]")
        )
        return text

    def platform(self, platform: str):
        if "switch" in platform:
            platform = platform.replace("switch", "Switch")
        if "nintendo" in platform:
            platform = platform.replace("nintendo", "Nintendo")
        if "steam" in platform:
            platform = platform.replace("steam", "Steam")
        if "playstation" in platform:
            platform = platform.replace("playstation", "playStation")
        if "Playstation" in platform:
            platform = platform.replace("Playstation", "playStation")
        if "xbox" in platform.lower():
            platform = platform.replace("xbox", "Xbox")
        if "pc" in platform.lower():
            platform = platform.replace("pc", "PC")
        if "Pc" in platform.lower():
            platform = platform.replace("Pc", "PC")
        return platform

    def load_json_response(self, response):
        return json.loads(json.dumps(response))