#!/bin/sh
# Checks the API after a deploy and reports the result to Telegram (the bot and chat meant for CI, not the app's bot).
set -u

target=$DEPLOY_TARGET
if [ "$target" = prod ]; then base=${DEPLOY_URL_PROD:-}; else base=${DEPLOY_URL_DEV:-}; fi

# The deploy job leaves its result even when it fails; a missing file (cancelled, timed out) counts as a failure.
result=failure
tag=
if [ -f deploy-result.env ]; then
  result=$(sed -n 's/^RESULT=//p' deploy-result.env)
  tag=$(sed -n 's/^TAG=//p' deploy-result.env)
fi
if [ "$target" = prod ]; then version=${tag:-$DEPLOY_VERSION}; else version="main@$(printf '%s' "$CI_COMMIT_SHA" | cut -c1-7)"; fi
url="${base%/}/api/v1/keepalive"

# The API restarts at the end of the deploy (and applies migrations first), so give it a minute.
api=-
if [ "$result" = success ]; then
  api=down
  for _ in $(seq 1 12); do
    if curl -fsS --max-time 10 "$url" | grep -q alive; then api=up; break; fi
    sleep 5
  done
fi

if [ "$result" != success ]; then
  ok=false; text="❌ Despliegue en $target fallido ($result)"
elif [ "$api" != up ]; then
  ok=false; text="⚠️ Desplegado en $target, pero la API no responde"
else
  ok=true; text="✅ Desplegado en $target, la API responde"
fi
text="$text
Versión: $version
Lanzado por: $GITLAB_USER_LOGIN
$CI_PIPELINE_URL"

curl -fsS --max-time 20 -o /dev/null \
  "https://api.telegram.org/bot${NOTIFY_TELEGRAM_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=$NOTIFY_TELEGRAM_CHAT_ID" \
  --data-urlencode "text=$text" \
  --data-urlencode "disable_web_page_preview=true"

# The deploy job is already red when it failed; this makes an unanswered API red too.
[ "$ok" = true ]
