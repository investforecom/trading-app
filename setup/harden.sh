#!/bin/bash
# Box hardening — run once as root on the OVH VPS immediately after first login.
# Creates a non-root sudo user, locks down SSH, and configures UFW.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/investforecom/dashboard/main/setup/harden.sh | \
#     sudo bash -s -- <username> "<ssh-public-key>"
#
# Example:
#   sudo bash harden.sh char "ssh-ed25519 AAAA... you@machine"

set -euo pipefail

USERNAME="${1:-}"
SSH_PUBKEY="${2:-}"

if [[ -z "$USERNAME" || -z "$SSH_PUBKEY" ]]; then
    echo "Usage: $0 <username> \"<ssh-public-key>\""
    exit 1
fi

echo "==> Creating user '$USERNAME' with sudo access"
id "$USERNAME" &>/dev/null || useradd -m -s /bin/bash "$USERNAME"
usermod -aG sudo "$USERNAME"

echo "==> Installing SSH public key for '$USERNAME'"
SSH_DIR="/home/$USERNAME/.ssh"
mkdir -p "$SSH_DIR"
echo "$SSH_PUBKEY" >> "$SSH_DIR/authorized_keys"
chmod 700 "$SSH_DIR"
chmod 600 "$SSH_DIR/authorized_keys"
chown -R "$USERNAME:$USERNAME" "$SSH_DIR"

echo "==> Hardening SSH config"
SSHD=/etc/ssh/sshd_config
cp "$SSHD" "${SSHD}.bak.$(date +%s)"
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/'            "$SSHD"
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD"
sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/'  "$SSHD"
sed -i 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' "$SSHD"
# Add if not present
grep -q "^PermitRootLogin"           "$SSHD" || echo "PermitRootLogin no"           >> "$SSHD"
grep -q "^PasswordAuthentication"    "$SSHD" || echo "PasswordAuthentication no"    >> "$SSHD"
grep -q "^PubkeyAuthentication"      "$SSHD" || echo "PubkeyAuthentication yes"     >> "$SSHD"

sshd -t  # validate config before restarting
systemctl reload ssh || systemctl reload sshd

echo "==> Configuring UFW firewall"
apt-get install -y ufw
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    comment 'SSH'
ufw allow 80/tcp    comment 'Metabase UI (plain HTTP until domain + Caddy added)'
# ufw allow 443/tcp comment 'HTTPS — uncomment when Caddy + domain are added'
# ufw allow 443/udp comment 'HTTP/3 — uncomment when Caddy + domain are added'
ufw --force enable
ufw status verbose

echo ""
echo "Done. BEFORE closing this session, open a new terminal and verify:"
echo "  ssh ${USERNAME}@<server-ip>"
echo "Confirm login works before logging out of root."
