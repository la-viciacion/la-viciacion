from enum import Enum

from ..database import schemas
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()


class CustomExceptions:
    class SignUp(Enum):
        USER_ALREADY_EXISTS = {
            "message": "Username is already registered",
            "code": "SIGNUP_01",
        }
        EMAIL_ALREADY_EXISTS = {
            "message": "Email is already registered",
            "code": "SIGNUP_02",
        }
        PASSWORD_REQUIREMENTS = {
            "message": "Password not match with requirements",
            "code": "SIGNUP_03",
        }
        INVALID_INVITATION_KEY = {
            "message": "Invalid or missing invitation key",
            "code": "SIGNUP_04",
        }
        EMAIL_VALIDATION = {
            "message": "The email has not a valid email format",
            "code": "SIGNUP_05",
        }

    class User(Enum):
        USER_NOT_EXISTS = {"message": "User not exists", "code": "USER_01"}

    def __init__(self, reason) -> None:
        logger.info(reason)
        self.message = reason.value["message"]
        self.code = reason.value["code"]

    def to_json(self):
        return {"message": self.message, "code": self.code}
