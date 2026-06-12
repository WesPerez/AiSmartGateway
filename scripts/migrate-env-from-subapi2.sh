#!/bin/sh
set -eu

source_env="${1:-../Sub2API/.env}"
target_env="${2:-.env}"

get_env() {
  key="$1"
  awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }' "$source_env"
}

random_token() {
  openssl rand -base64 72 | tr -dc 'A-Za-z0-9' | head -c 48
}

test -f "$source_env" || {
  echo "Missing source env: $source_env" >&2
  exit 1
}

cat > "$target_env" <<EOF
DOMAIN=$(get_env API_DOMAIN)
TZ=Asia/Shanghai
ACME_EMAIL=$(get_env ACME_EMAIL)

MASTER_API_KEY=$(random_token)
ADMIN_TOKEN=$(random_token)

PROBE_INTERVAL_SECONDS=60
PROBE_TIMEOUT_SECONDS=12
REQUEST_TIMEOUT_SECONDS=120
MAX_RETRIES_PER_REQUEST=8
MIN_HEALTHY_PROVIDERS=1
ENABLE_RESPONSES_PROBE=true
PROBE_ON_STARTUP=true

UPSTREAM_X666_KEY=$(get_env X666_API_KEY)
UPSTREAM_ANYROUTER_KEY=$(get_env ANYROUTER_API_KEY)
UPSTREAM_EQING_KEY=$(get_env SUB2API_API_KEY)
UPSTREAM_MUYUAN_KEY=$(get_env MUYUAN_API_KEY)
UPSTREAM_SHAREDCHAT_KEY=$(get_env SHAREDCHAT_API_KEY)
UPSTREAM_VOLCES_KEY=$(get_env VOLCES_API_KEY)
EOF

chmod 600 "$target_env"
echo "Wrote $target_env"
