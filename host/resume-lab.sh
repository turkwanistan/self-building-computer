#!/usr/bin/env bash
set -euo pipefail

LAB_NAME=${LAB_NAME:-mcp-lab}
LAB_IP=${LAB_IP:-192.168.127.10}
LAB_HUMAN_USER=${LAB_HUMAN_USER:-wan}
LIBVIRT_URI=qemu:///system
STATE_DIR=/var/lib/mcp-evolution
SSH_KEY=/home/${LAB_HUMAN_USER}/.ssh/mcp-lab_ed25519
KNOWN=$STATE_DIR/mcp-lab-known_hosts

fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "run with sudo"
virsh -c "$LIBVIRT_URI" dominfo "$LAB_NAME" >/dev/null 2>&1 || fail "domain $LAB_NAME does not exist"
[ -f "$SSH_KEY" ] || fail "missing SSH key: $SSH_KEY"

state=$(virsh -c "$LIBVIRT_URI" domstate "$LAB_NAME" | tr -d '\r')
if [ "$state" = "shut off" ]; then
  virsh -c "$LIBVIRT_URI" start "$LAB_NAME" >/dev/null
fi

echo "Waiting for SSH on $LAB_IP..."
for _ in $(seq 1 30); do
  if timeout 2 bash -c "</dev/tcp/$LAB_IP/22" 2>/dev/null; then
    break
  fi
  sleep 2
done
timeout 2 bash -c "</dev/tcp/$LAB_IP/22" 2>/dev/null || fail "SSH still unreachable on $LAB_IP:22"

ssh_opts=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$KNOWN" -o ConnectTimeout=10)

echo "Waiting for cloud-init and validating guest services..."
ssh "${ssh_opts[@]}" lab@"$LAB_IP" \
  'sudo cloud-init status --wait; sudo systemctl is-active ssh.service; sudo systemctl is-active optiplex-lab-mcp.service; id; sudo id'

if ! virsh -c "$LIBVIRT_URI" snapshot-list "$LAB_NAME" --name | grep -Fxq known-good; then
  echo "Creating known-good snapshot..."
  ssh "${ssh_opts[@]}" -o StrictHostKeyChecking=yes lab@"$LAB_IP" 'sudo systemctl poweroff' || true
  for _ in $(seq 1 60); do
    state=$(virsh -c "$LIBVIRT_URI" domstate "$LAB_NAME" 2>/dev/null | tr -d '\r' || true)
    [ "$state" = "shut off" ] && break
    sleep 2
  done
  [ "$(virsh -c "$LIBVIRT_URI" domstate "$LAB_NAME" | tr -d '\r')" = "shut off" ] || fail "guest did not power off for snapshot"
  virsh -c "$LIBVIRT_URI" snapshot-create-as "$LAB_NAME" known-good "Known-good isolated lab bootstrap"
  virsh -c "$LIBVIRT_URI" start "$LAB_NAME" >/dev/null

  echo "Waiting for SSH after snapshot restart..."
  for _ in $(seq 1 30); do
    if timeout 2 bash -c "</dev/tcp/$LAB_IP/22" 2>/dev/null; then
      break
    fi
    sleep 2
  done
  timeout 2 bash -c "</dev/tcp/$LAB_IP/22" 2>/dev/null || fail "SSH unreachable after snapshot restart"
else
  echo "known-good snapshot already exists; leaving it unchanged."
fi

echo "Resume complete."
echo "SSH: ssh -i ~/.ssh/mcp-lab_ed25519 lab@$LAB_IP"
echo "MCP: http://$LAB_IP:8890/mcp"
