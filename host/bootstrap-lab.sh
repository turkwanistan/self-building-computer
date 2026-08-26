#!/usr/bin/env bash
set -euo pipefail

LAB_NAME=${LAB_NAME:-mcp-lab}
LAB_NET=${LAB_NET:-mcp-lab-net}
LAB_BRIDGE=${LAB_BRIDGE:-virbr127}
LAB_SUBNET=${LAB_SUBNET:-192.168.127.0/24}
LAB_GATEWAY=${LAB_GATEWAY:-192.168.127.1}
LAB_IP=${LAB_IP:-192.168.127.10}
LAB_MAC=${LAB_MAC:-52:54:00:7f:00:10}
LAB_RAM_MB=${LAB_RAM_MB:-2048}
LAB_VCPUS=${LAB_VCPUS:-2}
LAB_DISK_GB=${LAB_DISK_GB:-30}
LAB_HUMAN_USER=${LAB_HUMAN_USER:-wan}
IMAGE_URL=${IMAGE_URL:-https://cloud-images.ubuntu.com/jammy/current/jammy-server-cloudimg-amd64.img}
IMAGE_NAME=jammy-server-cloudimg-amd64.img
LIBVIRT_URI=qemu:///system
IMAGE_DIR=/var/lib/libvirt/images
BASE_DIR=$IMAGE_DIR/base
DISK=$IMAGE_DIR/${LAB_NAME}.qcow2
SEED=$IMAGE_DIR/${LAB_NAME}-seed.iso
STATE_DIR=/var/lib/mcp-evolution
NETWORK_XML=$STATE_DIR/${LAB_NET}.xml
USER_DATA=$STATE_DIR/${LAB_NAME}-user-data.yaml
META_DATA=$STATE_DIR/${LAB_NAME}-meta-data.yaml
SSH_KEY=/home/${LAB_HUMAN_USER}/.ssh/mcp-lab_ed25519
REPO=/home/mcp/projects/projects/self-building-computer

fail() { echo "ERROR: $*" >&2; exit 1; }
[ "$(id -u)" -eq 0 ] || fail "run with sudo"
getent passwd "$LAB_HUMAN_USER" >/dev/null || fail "human user not found: $LAB_HUMAN_USER"
[ -f "$REPO/lab_mcp/server.py" ] || fail "missing $REPO/lab_mcp/server.py"

for cmd in virsh virt-install qemu-img curl sha256sum iptables systemctl python3; do
  command -v "$cmd" >/dev/null || fail "missing required command: $cmd"
done
if ! command -v cloud-localds >/dev/null; then
  echo "Installing cloud-image-utils (cloud-localds)..."
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y cloud-image-utils
fi

# Fail closed if this subnet already belongs to anything except our intended bridge/network.
if ip route | grep -F "$LAB_SUBNET" | grep -vq "dev $LAB_BRIDGE"; then
  fail "$LAB_SUBNET already has a conflicting host route"
fi
if virsh -c "$LIBVIRT_URI" dominfo "$LAB_NAME" >/dev/null 2>&1; then
  fail "domain $LAB_NAME already exists; inspect it rather than overwriting"
fi

install -d -m 0755 "$BASE_DIR"
install -d -m 0750 "$STATE_DIR"
install -d -m 0700 -o "$LAB_HUMAN_USER" -g "$LAB_HUMAN_USER" "/home/$LAB_HUMAN_USER/.ssh"
if [ ! -f "$SSH_KEY" ]; then
  sudo -u "$LAB_HUMAN_USER" ssh-keygen -q -t ed25519 -N '' -f "$SSH_KEY" -C mcp-lab
fi
PUBKEY=$(cat "${SSH_KEY}.pub")

if [ ! -f "$BASE_DIR/$IMAGE_NAME" ]; then
  tmp=$(mktemp "$BASE_DIR/.${IMAGE_NAME}.XXXXXX")
  curl -fL --retry 3 "$IMAGE_URL" -o "$tmp"
  sums=$(mktemp)
  curl -fL --retry 3 "${IMAGE_URL%/$IMAGE_NAME}/SHA256SUMS" -o "$sums"
  expected=$(awk -v f="$IMAGE_NAME" '$2==f || $2=="*"f {print $1; exit}' "$sums")
  [ -n "$expected" ] || fail "could not find $IMAGE_NAME in SHA256SUMS"
  actual=$(sha256sum "$tmp" | awk '{print $1}')
  [ "$actual" = "$expected" ] || fail "Ubuntu cloud image checksum mismatch"
  mv "$tmp" "$BASE_DIR/$IMAGE_NAME"
  rm -f "$sums"
fi

cp --reflink=auto --sparse=always "$BASE_DIR/$IMAGE_NAME" "$DISK"
qemu-img resize "$DISK" "${LAB_DISK_GB}G"
chown libvirt-qemu:kvm "$DISK" 2>/dev/null || true
chmod 0600 "$DISK"

cat > "$NETWORK_XML" <<NETEOF
<network>
  <name>$LAB_NET</name>
  <forward mode='nat'/>
  <bridge name='$LAB_BRIDGE' stp='on' delay='0'/>
  <ip address='$LAB_GATEWAY' netmask='255.255.255.0'>
    <dhcp>
      <range start='192.168.127.100' end='192.168.127.200'/>
      <host mac='$LAB_MAC' name='$LAB_NAME' ip='$LAB_IP'/>
    </dhcp>
  </ip>
</network>
NETEOF

if ! virsh -c "$LIBVIRT_URI" net-info "$LAB_NET" >/dev/null 2>&1; then
  virsh -c "$LIBVIRT_URI" net-define "$NETWORK_XML"
fi
virsh -c "$LIBVIRT_URI" net-start "$LAB_NET" >/dev/null 2>&1 || true
virsh -c "$LIBVIRT_URI" net-autostart "$LAB_NET"

cat > /usr/local/sbin/mcp-lab-firewall <<'FWEOF'
#!/usr/bin/env bash
set -euo pipefail
BRIDGE=${LAB_BRIDGE:-virbr127}
SUBNET=${LAB_SUBNET:-192.168.127.0/24}
GATEWAY=${LAB_GATEWAY:-192.168.127.1}

iptables -N MCP_LAB_INPUT 2>/dev/null || true
iptables -F MCP_LAB_INPUT
iptables -A MCP_LAB_INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A MCP_LAB_INPUT -p udp --dport 67 -j ACCEPT
iptables -A MCP_LAB_INPUT -d "$GATEWAY" -p udp --dport 53 -j ACCEPT
iptables -A MCP_LAB_INPUT -d "$GATEWAY" -p tcp --dport 53 -j ACCEPT
iptables -A MCP_LAB_INPUT -j DROP
iptables -C INPUT -i "$BRIDGE" -j MCP_LAB_INPUT 2>/dev/null || iptables -I INPUT 1 -i "$BRIDGE" -j MCP_LAB_INPUT

iptables -N MCP_LAB_FWD 2>/dev/null || true
iptables -F MCP_LAB_FWD
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 169.254.0.0/16; do
  iptables -A MCP_LAB_FWD -d "$net" -j REJECT --reject-with icmp-net-unreachable
done
iptables -A MCP_LAB_FWD -j ACCEPT
iptables -C FORWARD -s "$SUBNET" -j MCP_LAB_FWD 2>/dev/null || iptables -I FORWARD 1 -s "$SUBNET" -j MCP_LAB_FWD

if command -v ip6tables >/dev/null; then
  ip6tables -C INPUT -i "$BRIDGE" -j DROP 2>/dev/null || ip6tables -I INPUT 1 -i "$BRIDGE" -j DROP
  ip6tables -C FORWARD -i "$BRIDGE" -j DROP 2>/dev/null || ip6tables -I FORWARD 1 -i "$BRIDGE" -j DROP
fi
FWEOF
chmod 0755 /usr/local/sbin/mcp-lab-firewall
cat > /etc/systemd/system/mcp-lab-firewall.service <<'FWUNIT'
[Unit]
Description=Isolation firewall for disposable mcp-lab VM
After=network-online.target libvirtd.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/mcp-lab-firewall
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
FWUNIT
systemctl daemon-reload
systemctl enable --now mcp-lab-firewall.service

SERVER_B64=$(base64 -w0 "$REPO/lab_mcp/server.py")
cat > "$META_DATA" <<METAEOF
instance-id: $LAB_NAME
local-hostname: $LAB_NAME
METAEOF
cat > "$USER_DATA" <<USERHEAD
#cloud-config
hostname: $LAB_NAME
manage_etc_hosts: true
ssh_pwauth: false
disable_root: true
users:
  - default
  - name: lab
    groups: [adm, sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - $PUBKEY
package_update: true
packages:
  - openssh-server
  - qemu-guest-agent
  - python3-venv
  - python3-pip
  - git
  - curl
  - ca-certificates
  - build-essential
write_files:
  - path: /etc/sysctl.d/99-mcp-lab-ipv6.conf
    permissions: '0644'
    content: |
      net.ipv6.conf.all.disable_ipv6=1
      net.ipv6.conf.default.disable_ipv6=1
  - path: /opt/optiplex-lab/server.py
    permissions: '0644'
    encoding: b64
    content: $SERVER_B64
  - path: /etc/systemd/system/optiplex-lab-mcp.service
    permissions: '0644'
    content: |
      [Unit]
      Description=Unrestricted MCP inside isolated mcp-lab guest
      After=network-online.target
      Wants=network-online.target

      [Service]
      Type=simple
      User=root
      Group=root
      WorkingDirectory=/root
      ExecStart=/opt/optiplex-lab/venv/bin/python /opt/optiplex-lab/server.py
      Restart=always
      RestartSec=2
      Environment=LAB_MCP_HOST=0.0.0.0
      Environment=LAB_MCP_PORT=8890

      [Install]
      WantedBy=multi-user.target
  - path: /etc/default/grub.d/99-mcp-lab-serial.cfg
    permissions: '0644'
    content: |
      GRUB_CMDLINE_LINUX_DEFAULT="console=tty1 console=ttyS0,115200n8"
runcmd:
  - [sysctl, --system]
  - [python3, -m, venv, /opt/optiplex-lab/venv]
  - [/opt/optiplex-lab/venv/bin/pip, install, --disable-pip-version-check, "mcp[cli]>=1.3.0,<2"]
  - [mkdir, -p, /var/lib/optiplex-lab/jobs]
  - [update-grub]
  - [systemctl, daemon-reload]
  - [systemctl, enable, --now, ssh.service]
  - [systemctl, enable, serial-getty@ttyS0.service]
  - [systemctl, enable, --now, qemu-guest-agent.service]
  - [systemctl, enable, --now, optiplex-lab-mcp.service]
final_message: "mcp-lab cloud-init complete"
USERHEAD

rm -f "$SEED"
cloud-localds "$SEED" "$USER_DATA" "$META_DATA"
chown libvirt-qemu:kvm "$SEED" 2>/dev/null || true
chmod 0600 "$SEED"

virt-install \
  --connect "$LIBVIRT_URI" \
  --name "$LAB_NAME" \
  --memory "$LAB_RAM_MB" \
  --vcpus "$LAB_VCPUS" \
  --cpu host-passthrough \
  --import \
  --disk "path=$DISK,format=qcow2,bus=virtio" \
  --disk "path=$SEED,device=cdrom" \
  --network "network=$LAB_NET,mac=$LAB_MAC,model=virtio" \
  --graphics none \
  --console pty,target_type=serial \
  --noautoconsole \
  --os-variant ubuntu22.04
virsh -c "$LIBVIRT_URI" autostart "$LAB_NAME"

echo "Waiting for fixed DHCP lease $LAB_IP and cloud-init..."
for _ in $(seq 1 90); do
  if timeout 2 bash -c "</dev/tcp/$LAB_IP/22" 2>/dev/null; then break; fi
  sleep 2
done
KNOWN=$STATE_DIR/mcp-lab-known_hosts
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$KNOWN" -o ConnectTimeout=10 lab@"$LAB_IP" 'sudo cloud-init status --wait; sudo systemctl is-active optiplex-lab-mcp.service; id; sudo id'

# Snapshot a clean completed guest while powered off; host remains in control.
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN" lab@"$LAB_IP" 'sudo systemctl poweroff' || true
for _ in $(seq 1 60); do
  state=$(virsh -c "$LIBVIRT_URI" domstate "$LAB_NAME" 2>/dev/null || true)
  [ "$state" = "shut off" ] && break
  sleep 2
done
[ "$(virsh -c "$LIBVIRT_URI" domstate "$LAB_NAME")" = "shut off" ] || fail "guest did not power off for snapshot"
virsh -c "$LIBVIRT_URI" snapshot-create-as "$LAB_NAME" known-good "Known-good isolated lab bootstrap"
virsh -c "$LIBVIRT_URI" start "$LAB_NAME"

echo
echo "Lab created. Human access from OptiPlex:"
echo "  ssh -i ~/.ssh/mcp-lab_ed25519 lab@$LAB_IP"
echo "Fallback console:"
echo "  sudo virsh -c qemu:///system console $LAB_NAME"
echo "Lab MCP endpoint from host: http://$LAB_IP:8890/mcp"
