from openai import OpenAI

from ..utils.config import Config
from ..utils import ai_prompts as prompts
from ..utils.logger import LogManager

log_manager = LogManager()
logger = log_manager.get_logger()

config = Config()


class OpenAIClient:
    _instance = None  # Variable to store the instance

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OpenAIClient, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "client"):  # Check if the client is already initialized
            try:
                if config.OPENAI_API_KEY:
                    # logger.debug("Creating OpenAI client...")
                    try:
                        self.client = OpenAI(api_key=config.OPENAI_API_KEY)
                    except Exception as e:
                        logger.error(e)
                else:
                    logger.info("OpenAI not configured")
            except Exception as e:
                logger.error(e)

    def chat_completion(
        self,
        user_prompt: str,
        system_prompt: str,
        model: str = "gpt-4o-mini",
        temperature: float = 1,
        max_tokens: int = None,
        response_format: object = None,
    ):
        """
        Function to complete a chat based on the provided model and messages.

        Parameters:
            prompt (str): The prompt to use for the chat completion.
            model (str): The model to use for chat completion.
            temperature (float): Controls randomness in the chat generation.
            max_tokens (int): Maximum number of tokens to generate.
            response_format (object): Format of the response. Eg: { "type": "json_object" } (see OpenAI docs).

        Returns:
            completion: The completed chat based on the input messages and model.
        """
        if not hasattr(self, "client"):
            logger.info("OpenAI client not initialized")
            return None
        user_message = [{"role": "user", "content": user_prompt}]
        system_message = {
            "role": "system",
            "content": system_prompt,
        }
        messages = [system_message] + user_message
        completion = self.client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            messages=messages,
        )
        return completion
