FROM python:3.14-slim-trixie

WORKDIR /app

# The season changes and the sessions are dated at local midnight, and the weather and sky achievements read
# the same hours. Only a default: the TZ of the .env, when there is one, wins (see docs/configuration.md).
ENV TZ=Europe/Madrid

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

# The release tag, passed by release.yml; a build from a checkout reports `dev`.
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

CMD ["./entrypoint.sh"]
