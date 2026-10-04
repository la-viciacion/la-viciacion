FROM python:3.14-slim-trixie

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

# The release tag, passed by release.yml; a build from a checkout reports `dev`.
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

CMD ["./entrypoint.sh"]
