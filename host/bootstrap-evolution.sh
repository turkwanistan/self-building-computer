#!/usr/bin/env bash
set -euo pipefail

REPO=/home/mcp/projects/projects/self-building-computer
CTL_SRC="$REPO/host/evolutionctl.py"
VERIFY_SRC="$REPO/host/verify-evolution-mcp.py"

fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "run with sudo"
[ -f "$CTL_SRC" ] || fail "missing $CTL_SRC"
[ -f "$VERIFY_SRC" ] || fail "missing $VERIFY_SRC"
[ -f "$REPO/candidate/release.json" ] || fail "missing no-op candidate manifest"
[ -x /home/mcp/agent/.venv/bin/python ] || fail "generation-0 runtime venv not found"

for cmd in python3 systemctl runuser install; do
  command -v "$cmd" >/dev/null || fail "missing command: $cmd"
done

if ! command -v socat >/dev/null || ! python3 -m venv --help >/dev/null 2>&1; then
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y socat python3-venv
fi

install -d -m 0755 /opt/mcp /opt/mcp/releases /opt/mcp/guardrails /opt/mcp/guardrails/releases
install -d -m 0750 /var/lib/mcp-evolution
install -d -m 0755 /etc/mcp-evolution /etc/mcp-evolution/slots /usr/local/libexec

if [ ! -x /opt/mcp/runtime-venv/bin/python ]; then
  python3 -m venv /opt/mcp/runtime-venv
fi
/opt/mcp/runtime-venv/bin/pip install --disable-pip-version-check -q 'mcp[cli]>=1.3.0,<2' 'pytest>=7,<9'

install -m 0755 "$CTL_SRC" /usr/local/sbin/mcp-evolution
install -m 0755 "$VERIFY_SRC" /usr/local/libexec/mcp-evolution-verify-mcp

MCP_UID=$(id -u mcp)

cat > /etc/systemd/system/mcp-evolution-guardrail.service <<EOF
[Unit]
Description=Protected generation-0 MCP guardrail backend
After=network-online.target docker.service mcp-playwright.service
Wants=network-online.target

[Service]
Type=simple
User=mcp
Group=mcp
WorkingDirectory=/home/mcp/agent
ExecStart=/usr/local/sbin/mcp-evolution run-guardrail
Environment=DOCKER_HOST=unix:///run/user/${MCP_UID}/docker.sock
EnvironmentFile=-/etc/mcp-agent/agent.env
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
InaccessiblePaths=/home/wan /root
PrivateTmp=true
ReadWritePaths=/home/mcp/projects /home/mcp/agent /home/mcp/cache/pip/wheels /home/mcp/cache/npm

[Install]
WantedBy=multi-user.target
EOF

for SLOT in blue green; do
cat > "/etc/systemd/system/mcp-evolution-${SLOT}.service" <<EOF
[Unit]
Description=Evolvable MCP ${SLOT} slot
After=network-online.target mcp-evolution-guardrail.service
Wants=network-online.target
Requires=mcp-evolution-guardrail.service
ConditionPathExists=/etc/mcp-evolution/slots/${SLOT}.env

[Service]
Type=simple
User=mcp
Group=mcp
ExecStart=/usr/local/sbin/mcp-evolution run-slot ${SLOT}
Restart=always
RestartSec=2
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
ProtectClock=true
ProtectHostname=true
ProtectProc=invisible
ProcSubset=pid
CapabilityBoundingSet=
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_INET AF_INET6
IPAddressDeny=any
IPAddressAllow=localhost
InaccessiblePaths=/etc/mcp-agent /var/lib/mcp-evolution /run /var/run
ReadOnlyPaths=/opt/mcp /etc/mcp-evolution

[Install]
WantedBy=multi-user.target
EOF
done

cat > /etc/systemd/system/mcp-evolution-frontdoor.service <<'EOF'
[Unit]
Description=Root-controlled fixed MCP front door on 127.0.0.1:8790
After=network-online.target mcp-evolution-guardrail.service
Wants=network-online.target
Requires=mcp-evolution-guardrail.service
ConditionPathExists=/etc/mcp-evolution/frontdoor.env

[Service]
Type=simple
User=nobody
Group=nogroup
ExecStart=/usr/local/sbin/mcp-evolution run-frontdoor
Restart=always
RestartSec=1
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
CapabilityBoundingSet=
RestrictSUIDSGID=true
RestrictAddressFamilies=AF_INET AF_INET6
IPAddressDeny=any
IPAddressAllow=localhost
InaccessiblePaths=/home /root /etc/mcp-agent /var/lib/mcp-evolution /run /var/run
ReadOnlyPaths=/etc/mcp-evolution

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# Bootstrap first establishes an equivalent blue stable release behind a separate
# protected guardrail backend, then atomically cuts the fixed 8790 route over.
/usr/local/sbin/mcp-evolution bootstrap

# Immediately stage the equivalent green candidate for the no-op lifecycle drill.
/usr/local/sbin/mcp-evolution stage

echo
echo "Evolution bootstrap and no-op candidate staging complete."
echo "Inspect with: sudo mcp-evolution status"
echo "Then activate the READY_TO_ACTIVATE release printed above."
