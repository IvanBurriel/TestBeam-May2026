#!/bin/bash

# ============================================================
#  TestBeam May 2026
#  Full Environment Setup
#  Docker + InfluxDB + Grafana
#
#  External access enabled
#  (No SSH tunnels required)
# ============================================================

set -e

echo ""
echo "============================================================"
echo "        TestBeam May 2026 - Setup Starting"
echo "============================================================"
echo ""

# ------------------------------------------------------------
# 1. System Update
# ------------------------------------------------------------
echo "[1/7] Updating system packages..."

sudo dnf update -y

echo "System update completed."
echo ""

# ------------------------------------------------------------
# 2. Docker Installation
# ------------------------------------------------------------
echo "[2/7] Installing Docker and Docker Compose..."

sudo dnf config-manager --add-repo \
    https://download.docker.com/linux/centos/docker-ce.repo

sudo dnf install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-compose-plugin

sudo systemctl enable docker
sudo systemctl start docker

echo ""
echo "Docker successfully installed:"
docker --version
echo ""

# ------------------------------------------------------------
# 3. Firewall Configuration
# ------------------------------------------------------------
echo "[3/7] Configuring firewall for external access..."

# InfluxDB port
sudo firewall-cmd --permanent --add-port=8086/tcp

# Grafana port
sudo firewall-cmd --permanent --add-port=3000/tcp

sudo firewall-cmd --reload

echo ""
echo "Open firewall ports:"
sudo firewall-cmd --list-ports
echo ""

# ------------------------------------------------------------
# 4. Port Verification
# ------------------------------------------------------------
echo "[4/7] Checking listening services..."

sudo ss -tulpn | grep docker || true

echo ""

# ------------------------------------------------------------
# 5. Start Docker Services
# ------------------------------------------------------------
echo "[5/7] Starting DAQ services..."

docker compose up -d

echo ""
echo "Running containers:"
sudo docker ps
echo ""

# ------------------------------------------------------------
# 6. Access Information
# ------------------------------------------------------------
HOSTNAME=$(hostname -f)

echo "[6/7] Service Access URLs"
echo "------------------------------------------------------------"
echo "InfluxDB : http://${HOSTNAME}:8086"
echo "Grafana  : http://${HOSTNAME}:3000"
echo "------------------------------------------------------------"
echo ""

# ------------------------------------------------------------
# 7. Final Instructions
# ------------------------------------------------------------
echo "[7/7] Setup completed successfully."
echo ""

cat <<EOF

============================================================
                    NEXT STEPS
============================================================

1) Configure InfluxDB
------------------------------------------------------------

Open:
    http://${HOSTNAME}:8086

Create:
    - Organization
      Example: Newtile_Online-org

    - Bucket
      Example: Fers_bucket

    - API Token
      Recommended: All Access token


2) Configure Grafana
------------------------------------------------------------

Open:
    http://${HOSTNAME}:3000

Add a new InfluxDB data source with:

    Query Language : Flux
    URL            : http://localhost:8086

Fill in:
    - Organization
    - Bucket
    - Token

Then click:
    Save & Test


3) Run Python Monitoring Scripts
------------------------------------------------------------

Activate the Python virtual environment:

    source venv/bin/activate

Run the desired scripts:

    python fers_script.py
    python digi_script.py


============================================================
                    USEFUL COMMANDS
============================================================

Restart Grafana:
    sudo docker compose restart grafana

Restart all services:
    sudo docker compose restart

Clean unused Docker resources:
    sudo docker system prune -f

Recreate Grafana container:
    sudo docker compose up -d grafana


============================================================
               TestBeam Setup Finished
============================================================

EOF
