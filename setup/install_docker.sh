#!/bin/bash
# Install Docker Engine + Compose plugin on Ubuntu.
# Run as the non-root sudo user (not root).
# https://docs.docker.com/engine/install/ubuntu/
set -euo pipefail

echo "==> Removing any old Docker packages"
for pkg in docker.io docker-doc docker-compose docker-compose-v2 podman-docker containerd runc; do
    sudo apt-get remove -y "$pkg" 2>/dev/null || true
done

echo "==> Installing Docker prerequisites"
sudo apt-get update
sudo apt-get install -y ca-certificates curl

echo "==> Adding Docker's official GPG key and apt repo"
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "==> Installing Docker Engine and Compose plugin"
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin

echo "==> Adding $USER to the docker group (re-login required)"
sudo usermod -aG docker "$USER"

echo "==> Enabling Docker to start on boot"
sudo systemctl enable docker
sudo systemctl start docker

echo ""
echo "Done. Log out and back in, then verify with: docker run hello-world"
echo "Compose is available as: docker compose version"
