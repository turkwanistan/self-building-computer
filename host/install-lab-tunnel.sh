#!/usr/bin/env bash
set -euo pipefail

TUNNEL_ID=${1:-}
PROFILE_NAME=optiplex-lab
PROFILE_DIR=/home/mcp/.config/tunnel-client
PROFILE_FILE=$PROFILE_DIR/$PROFILE_NAME.yaml
ENV_FILE=/etc/mcp-agent/tunnel.env
SERVICE_FILE=/etc/systemd/system/mcp-lab-tunnel.service
LAB_IP=${LAB_IP:-192.168.127.10}
LAB_MCP_URL=${LAB_MCP_URL:-http://$LAB_IP:8890/mcp}
HEALTH_ADDR=${HEALTH_ADDR:-127.0.0.1:8794}

fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "run with sudo"
[[ "$TUNNEL_ID" == tunnel_* ]] || fail "usage: sudo ./host/install-lab-tunnel.sh tunnel_<new-id>"
getent passwd mcp >/dev/null || fail "mcp user missing"
[ -r "$ENV_FILE" ] || fail "missing protected runtime environment: $ENV_FILE"
systemctl is-active --quiet mcp-agent.service || fail "production mcp-agent.service is not active"
systemctl is-active --quiet mcp-tunnel.service || fail "production mcp-tunnel.service is not active"
timeout 3 bash -c "</dev/tcp/$LAB_IP/8890" 2>/dev/null || fail "lab MCP is not reachable at $LAB_IP:8890"

install -d -m 0700 -o mcp -g mcp "$PROFILE_DIR"
[ ! -e "$PROFILE_FILE" ] || fail "$PROFILE_FILE already exists; inspect it rather than overwriting"

sudo -u mcp -H tunnel-client init \
  --profile "$PROFILE_NAME" \
  --profile-dir "$PROFILE_DIR" \
  --tunnel-id "$TUNNEL_ID" \
  --mcp-server-url "$LAB_MCP_URL" \
  --health-listen-addr "$HEALTH_ADDR" \
  --control-plane-api-key-ref env:CONTROL_PLANE_API_KEY
chmod 0600 "$PROFILE_FILE"
chown mcp:mcp "$PROFILE_FILE"

# Validate the generated profile and live control-plane/MCP connectivity without printing secrets.
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
tunnel-client doctor --profile-file "$PROFILE_FILE" --explain

cat > "$SERVICE_FILE" <<'UNIT'
[Unit]
Description=Secure MCP tunnel client for isolated mcp-lab
After=network-online.target libvirtd.service
Wants=network-online.target
ConditionPathExists=/etc/mcp-agent/tunnel.env
ConditionPathExists=/home/mcp/.config/tunnel-client/optiplex-lab.yaml

[Service]
Type=simple
User=mcp
Group=mcp
ExecStart=tunnel-client run --profile optiplex-lab --profile-dir /home/mcp/.config/tunnel-client
EnvironmentFile=/etc/mcp-agent/tunnel.env
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
InaccessiblePaths=/home/wan /root
PrivateTmp=true
ReadOnlyPaths=/home/mcp/.config/tunnel-client

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now mcp-lab-tunnel.service

for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 "http://127.0.0.1:8794/readyz" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

systemctl is-active --quiet mcp-lab-tunnel.service || {
  systemctl --no-pager --full status mcp-lab-tunnel.service || true
  journalctl -u mcp-lab-tunnel.service -n 50 --no-pager || true
  fail "mcp-lab-tunnel.service failed"
}
curl -fsS --max-time 5 "http://127.0.0.1:8794/healthz" >/dev/null || fail "lab tunnel health endpoint failed"
curl -fsS --max-time 5 "http://127.0.0.1:8794/readyz" >/dev/null || fail "lab tunnel readiness endpoint failed"
systemctl is-active --quiet mcp-tunnel.service || fail "existing production tunnel stopped unexpectedly"

echo "Optiplex_Lab tunnel service is active and ready."
echo "Profile: $PROFILE_FILE"
echo "MCP target: $LAB_MCP_URL"
echo "Health: http://127.0.0.1:8794/healthz"
echo "Production mcp-tunnel.service remains active."
