#!/usr/bin/env bash
set -euo pipefail

PROTECTED=/home/mcp/.config/tunnel-client/optiplex.yaml
DUPLICATES=(
  /home/mcp/projects/projects/optiplex-mcp-agent/tunnel-profiles/optiplex.yaml
  /home/mcp/agent/tunnel-profiles/optiplex.yaml
)

fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "run with sudo"
[ -s "$PROTECTED" ] || fail "protected tunnel profile missing: $PROTECTED"
chown mcp:mcp "$PROTECTED"
chmod 0600 "$PROTECTED"

for path in "${DUPLICATES[@]}"; do
  [ -e "$path" ] || continue
  if ! cmp -s "$path" "$PROTECTED"; then
    fail "refusing to remove non-identical tunnel profile copy: $path"
  fi
  rm -f "$path"
  echo "removed duplicate tunnel profile: $path"
done

echo "protected tunnel profile retained at $PROTECTED"
systemctl is-active --quiet mcp-tunnel.service || fail "mcp-tunnel.service is not active"
echo "mcp-tunnel.service active"
