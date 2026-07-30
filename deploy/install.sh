#!/usr/bin/env bash
# SMM Agent — server quraşdırma skripti (Ubuntu/Debian).
#
# İstifadə (serverdə, layihə qovluğunun içindən):
#   bash deploy/install.sh
#
# Skript idempotentdir — təkrar-təkrar işlədilə bilər, heç nə pozulmur.
set -euo pipefail

APPDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNUSER="${SUDO_USER:-$USER}"
SERVICE=smm-agent

# Skript hansı qovluqdan çağırılsa da, iş qovluğu layihənin kökü olsun
cd "$APPDIR"

echo "==> Layihə qovluğu: $APPDIR"
echo "==> İşlədəcək istifadəçi: $RUNUSER"

if [ ! -f "$APPDIR/.env" ]; then
    echo "XƏTA: $APPDIR/.env faylı yoxdur."
    echo "      .env faylını lokal kompüterdən köçürün (git-ə düşmür), sonra"
    echo "      bu skripti yenidən işə salın."
    exit 1
fi

echo "==> Sistem paketləri quraşdırılır..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-venv python3-pip

echo "==> Virtual mühit hazırlanır..."
if [ ! -d "$APPDIR/.venv" ]; then
    python3 -m venv "$APPDIR/.venv"
fi
"$APPDIR/.venv/bin/pip" install --quiet --upgrade pip
"$APPDIR/.venv/bin/pip" install --quiet -r "$APPDIR/requirements.txt"

echo "==> Konfiqurasiya yoxlanılır..."
# Açarlar çatışmırsa, servis qurulmadan burada dayanır
"$APPDIR/.venv/bin/python" - <<'PY'
import sys
from smm import config
missing = config.validate()
if missing:
    print("XƏTA: .env faylında çatışmır:", ", ".join(missing))
    sys.exit(1)
print("   .env qaydasındadır (AI:", config.AI_PROVIDER + ")")
PY

echo "==> systemd servisi qurulur..."
sed -e "s|__USER__|$RUNUSER|g" -e "s|__APPDIR__|$APPDIR|g" \
    "$APPDIR/deploy/$SERVICE.service" | sudo tee "/etc/systemd/system/$SERVICE.service" >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE" >/dev/null
sudo systemctl restart "$SERVICE"

sleep 3
echo
echo "==> Vəziyyət:"
sudo systemctl status "$SERVICE" --no-pager --lines=15 || true
echo
echo "Hazırdır. Faydalı əmrlər:"
echo "  sudo systemctl status $SERVICE     # vəziyyət"
echo "  sudo journalctl -u $SERVICE -f     # canlı loglar"
echo "  sudo systemctl restart $SERVICE    # yenidən başlat"
