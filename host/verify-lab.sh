#!/usr/bin/env bash
set -euo pipefail
LAB_IP=${LAB_IP:-192.168.127.10}
LAB_NAME=${LAB_NAME:-mcp-lab}
LAB_HUMAN_USER=${LAB_HUMAN_USER:-wan}
SSH_KEY=/home/${LAB_HUMAN_USER}/.ssh/mcp-lab_ed25519
KNOWN=/var/lib/mcp-evolution/mcp-lab-known_hosts
ssh_lab=(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" lab@"$LAB_IP")

printf '=== DOMAIN/RECOVERY ===\n'
virsh -c qemu:///system dominfo "$LAB_NAME"
virsh -c qemu:///system snapshot-list "$LAB_NAME"
printf 'console tty: '; virsh -c qemu:///system ttyconsole "$LAB_NAME"

printf '\n=== ROOT / SERVICE / PUBLIC INTERNET ===\n'
"${ssh_lab[@]}" 'sudo id; sudo sh -lc "touch /root/mcp-lab-root-test && rm /root/mcp-lab-root-test"; systemctl is-active optiplex-lab-mcp.service; curl -fsS --max-time 10 https://example.com >/dev/null && echo PUBLIC_INTERNET_OK'

printf '\n=== PRIVATE DESTINATIONS MUST FAIL ===\n'
"${ssh_lab[@]}" 'python3 - <<"PY"
import socket
for host, port in [("192.168.50.1",80),("100.100.100.100",80),("172.17.0.1",80),("192.168.122.1",53),("10.0.0.1",80)]:
    s=socket.socket(); s.settimeout(2)
    try:
        s.connect((host,port)); print("UNEXPECTED_REACHABLE", host, port)
    except OSError:
        print("BLOCKED_OK", host, port)
    finally:
        s.close()
PY'

printf '\n=== HOST SERVICES MUST FAIL EXCEPT DHCP/DNS ===\n'
"${ssh_lab[@]}" 'python3 - <<"PY"
import socket
for port in (22,8790,8791,8931):
    s=socket.socket(); s.settimeout(2)
    try:
        s.connect(("192.168.127.1",port)); print("UNEXPECTED_HOST_REACHABLE", port)
    except OSError:
        print("HOST_BLOCKED_OK", port)
    finally:
        s.close()
PY'

printf '\n=== NO HOST MOUNTS / SOCKETS / TAILSCALE ===\n'
"${ssh_lab[@]}" 'mount | grep -E "9p|virtiofs|/home/mcp|/home/wan" && exit 10 || echo NO_HOST_FS_MOUNTS_OK; test ! -S /var/run/docker.sock && echo NO_HOST_DOCKER_SOCKET_OK || echo GUEST_DOCKER_SOCKET_PRESENT; test ! -S /run/libvirt/libvirt-sock && echo NO_HOST_LIBVIRT_SOCKET_OK || echo LIBVIRT_SOCKET_PRESENT; command -v tailscale >/dev/null && echo TAILSCALE_CLIENT_PRESENT || echo NO_TAILSCALE_CLIENT_OK'

printf '\n=== MCP ENDPOINT FROM HOST ===\n'
curl -sS -o /dev/null -w 'HTTP %{http_code}\n' --max-time 5 "http://$LAB_IP:8890/mcp" || true
MCP_PYTHON=${MCP_PYTHON:-/home/mcp/agent/.venv/bin/python}
[ -x "$MCP_PYTHON" ] || { echo "missing MCP-capable Python: $MCP_PYTHON" >&2; exit 1; }
"$MCP_PYTHON" "$(dirname "$0")/verify-lab-mcp.py" "http://$LAB_IP:8890/mcp"
