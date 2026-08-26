#!/usr/bin/env bash
set -u

section() { printf '\n===== %s =====\n' "$1"; }
run() { printf '+ %q ' "$@"; printf '\n'; "$@" 2>&1 || true; }

section IDENTITY
run uname -a
run cat /etc/os-release
run id
run getent passwd wan
run nproc
run free -h
run df -h /

section VIRTUALIZATION
for c in virsh virt-install qemu-img cloud-localds kvm-ok; do command -v "$c" || true; done
run ls -l /dev/kvm
run systemctl is-active libvirtd
run systemctl is-enabled libvirtd
run virsh -c qemu:///system list --all
run virsh -c qemu:///system net-list --all
run virsh -c qemu:///system pool-list --all
run virsh -c qemu:///system net-dumpxml default

section NETWORK
run ip -br addr
run ip route
run ip -6 route
run command -v iptables
run iptables --version
run iptables -S INPUT
run iptables -S FORWARD
run iptables -t nat -S
if command -v ip6tables >/dev/null; then run ip6tables -S INPUT; run ip6tables -S FORWARD; fi
if command -v nft >/dev/null; then run nft list tables; fi

section EXISTING_SERVICES
for s in mcp-agent.service mcp-tunnel.service mcp-playwright.service docker.service tailscaled.service; do
  run systemctl is-active "$s"
  run systemctl is-enabled "$s"
done
run ss -lntup

section TUNNEL_CLIENT
run command -v tunnel-client
if command -v tunnel-client >/dev/null; then
  run tunnel-client --help
  run tunnel-client run --help
fi

section CREDENTIAL_LOCATIONS_METADATA_ONLY
for p in \
  /home/mcp/projects/projects/optiplex-mcp-agent/tunnel-profiles/optiplex.yaml \
  /home/mcp/agent/tunnel-profiles/optiplex.yaml \
  /home/mcp/.config/tunnel-client/optiplex.yaml \
  /etc/mcp-agent/tunnel.env \
  /home/mcp/credentials/git; do
  if [ -e "$p" ]; then run ls -ld "$p"; else echo "MISSING $p"; fi
done

section SSH
run ls -ld /home/wan/.ssh
for p in /home/wan/.ssh/id_ed25519.pub /home/wan/.ssh/id_rsa.pub /home/wan/.ssh/mcp-lab_ed25519.pub; do
  if [ -f "$p" ]; then run ls -l "$p"; fi
done

section PROJECT_STATE
run git -C /home/mcp/projects/projects/optiplex-mcp-agent status --short --branch
run git -C /home/mcp/projects/projects/self-building-computer status --short --branch
