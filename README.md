
#!/bin/bash
# ============================================================
# TestBeam May 2026
# Full setup script: Docker + InfluxDB + Grafana
# External connection enabled (NO SSH tunnels)
# ============================================================
 
set -e
 
echo "=== TestBeam May 2026 setup start ==="
 
# ------------------------------------------------------------
# 1. System update
# ------------------------------------------------------------
echo "[1/7] Updating system..."
sudo dnf update -y
 
# ------------------------------------------------------------
# 2. Docker installation
# ------------------------------------------------------------
echo "[2/7] Installing Docker..."
 
sudo dnf config-manager --add-repo \
  https://download.docker.com/linux/centos/docker-ce.repo
 
sudo dnf install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-compose-plugin
 
sudo systemctl enable docker
sudo systemctl start docker
 
echo "Docker version:"
docker --version
 
# ------------------------------------------------------------
# 3. Firewall configuration (external access)
# ------------------------------------------------------------
echo "[3/7] Opening firewall ports..."
 
# InfluxDB
sudo firewall-cmd --permanent --add-port=8086/tcp
# Grafana
sudo firewall-cmd --permanent --add-port=3000/tcp
 
sudo firewall-cmd --reload
 
echo "Open ports:"
sudo firewall-cmd --list-ports
 
# ------------------------------------------------------------
# 4. Check listening ports
# ------------------------------------------------------------
echo "[4/7] Checking listening ports..."
sudo ss -tulpn | grep docker || true
 
# ------------------------------------------------------------
# 5. Start DAQ services
# ------------------------------------------------------------
echo "[5/7] Starting Docker services..."
docker compose up -d
 
echo "Running containers:"
sudo docker ps
 
# ------------------------------------------------------------
# 6. Access information
# ------------------------------------------------------------
HOSTNAME=$(hostname -f)
 
echo "[6/7] Access URLs:"
echo "InfluxDB : http://${HOSTNAME}:8086"
echo "Grafana  : http://${HOSTNAME}:3000"
 
# ------------------------------------------------------------
# 7. Final notes
# ------------------------------------------------------------
echo "[7/7] Setup completed successfully."
 
cat <<EOF
 
============================================================
NEXT STEPS (manual via browser)
============================================================
 
1) InfluxDB:
   http://${HOSTNAME}:8086
 
   - Create Organization (e.g. Newtile_Online-org)
   - Create Bucket (e.g. Fers_bucket)
   - Create API Token (All Access)
 
2) Grafana:
   http://${HOSTNAME}:3000
 
   - Add InfluxDB data source
   - Query language: Flux
   - URL: http://localhost:8086
   - Organization / Bucket / Token
   - Save & Test
 
3) Python scripts:
   source venv/bin/activate
   python fers_script.py
   python digi_script.py
 
============================================================
Grafana recovery:
  sudo docker compose restart grafana
 
If needed:
  sudo docker system prune -f
  sudo docker compose up -d grafana
============================================================
 
EOF
 
echo "=== TestBeam setup finished ==="
``
 
