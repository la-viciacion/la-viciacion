from ..clients.open_ai import OpenAIClient
from . import ai_prompts as prompts
from ..utils.logger import LogManager

logger = LogManager().get_logger()
oai_client = OpenAIClient()

def response_message(msg):
    completion = oai_client.chat_completion(
        user_prompt=msg, system_prompt=prompts.DEFAULT_SYSTEM_PROMPT
    )
    if completion is not None:
        logger.info(completion.choices[0].message.content)
        response = completion.choices[0].message.content
    return response