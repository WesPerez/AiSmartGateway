#!/bin/sh
set -eu

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

test -f .env || fail ".env is missing"

set -a
. ./.env
set +a

: "${DOMAIN:?DOMAIN is empty}"
: "${MASTER_API_KEY:?MASTER_API_KEY is empty}"
: "${ADMIN_TOKEN:?ADMIN_TOKEN is empty}"

base="${VERIFY_BASE_URL:-https://$DOMAIN}"

echo "=============================="
echo "1. Docker containers"
echo "=============================="
docker compose ps

echo ""
echo "=============================="
echo "2. Public health"
echo "=============================="
curl -fsS "$base/health" | jq .

echo ""
echo "=============================="
echo "2b. Admin UI and overview"
echo "=============================="
curl -fsS "$base/admin/" | grep -q "AI Smart Gateway Admin"
echo "Admin UI OK: $base/admin/"
curl -fsS "$base/admin/api/overview" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | jq '{
      base_url,
      admin_url,
      api_key_present: ((.master_api_key | length) > 0),
      provider_count,
      model_count: (.models | length)
    }'

echo ""
echo "=============================="
echo "3. Available models"
echo "=============================="
curl -fsS "$base/v1/models" \
  -H "Authorization: Bearer $MASTER_API_KEY" | jq .

echo ""
echo "=============================="
echo "4. Health matrix summary"
echo "=============================="
curl -fsS "$base/admin/matrix" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | jq '{
      last_probe_at,
      providers: (.providers | length),
      chat_healthy: (.health.chat | to_entries | map(.value | to_entries[] | select(.value.healthy == true)) | length),
      responses_healthy: (.health.responses | to_entries | map(.value | to_entries[] | select(.value.healthy == true)) | length),
      chat_models: (.health.chat | to_entries | map(select(any(.value[]; .healthy == true)) | .key)),
      responses_models: (.health.responses | to_entries | map(select(any(.value[]; .healthy == true)) | .key))
    }'

echo ""
echo "=============================="
echo "4b. Provider config summary"
echo "=============================="
curl -fsS "$base/admin/api/providers" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  | jq '{
      count: (.providers | length),
      providers: [.providers[] | {
        id,
        name,
        base_url,
        api_key_set,
        api_key_preview,
        runtime
      }]
    }'

echo ""
echo "=============================="
echo "5. Real chat request"
echo "=============================="
model="$(curl -fsS "$base/v1/models" -H "Authorization: Bearer $MASTER_API_KEY" | jq -r '.data[0].id')"
echo "Testing model: $model"

if [ "$model" = "null" ] || [ -z "$model" ]; then
  fail "No available model. Check /admin/matrix."
fi

curl -fsS "$base/v1/chat/completions" \
  -H "Authorization: Bearer $MASTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$model\",
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": \"只回复 pong\"
      }
    ],
    \"max_tokens\": 20,
    \"stream\": false
  }" | jq .
