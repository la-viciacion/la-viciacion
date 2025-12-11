# La Viciación

## Basic config

### Environment

Copy `.env.template` to `.env` and fill with your values

### Webhooks

Copy `api/app/routers/webhooks_template.py` to `api/app/routers/webhooks_template.py`. This file allows to create your own 'public' webhooks if you need. So, you can create an endpoint like `/tBn7NyNHAsP9WjP3sJUXglxaTATJxrfs3J2DauBV5fthwuGKq3le`, and call directly from another service without authentication like the `bot` routes (to execute other processes).

### OpenAI integration

If you want to use OpenAI integration (adding your API key to .env file), you need to copy `api/app/utils/ai_prompts_template.py` to `api/app/utils/ai_prompts.py`. Then, you could adjust the prompts for the predefined notifications.
