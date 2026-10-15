#!/usr/bin/env bash
# One-command install for BIOQUEST with Docker (PostgreSQL + PostGIS + API + web).
# Usage: ./install.sh            → uses this computer's LAN IP, so a phone on the same WiFi can open the app
#        ./install.sh localhost  → only this computer
set -e
cd "$(dirname "$0")"

command -v docker >/dev/null || { echo "Falta Docker. Instálalo desde https://docs.docker.com/get-docker/ y vuelve a ejecutar."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker no está corriendo. Ábrelo y vuelve a ejecutar."; exit 1; }

HOST_IP="${1:-}"
if [ -z "$HOST_IP" ]; then
  HOST_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  [ -z "$HOST_IP" ] && HOST_IP=$(ipconfig getifaddr en0 2>/dev/null || true)
  [ -z "$HOST_IP" ] && HOST_IP=localhost
fi

# Keep an existing .env (and its secret) if present; otherwise create one.
if [ ! -f .env ]; then
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  printf "BIOQUEST_HOST=%s\nBIOQUEST_SECRET_KEY=%s\n" "$HOST_IP" "$SECRET" > .env
  echo "Creado .env (host: $HOST_IP)"
else
  echo "Usando .env existente (edita BIOQUEST_HOST si cambió tu IP)."
fi

mkdir -p backend/data
docker compose up -d --build

echo
echo "BIOQUEST está corriendo."
echo "  En esta computadora: http://localhost:3000"
echo "  En el celular (mismo WiFi): http://$(grep ^BIOQUEST_HOST= .env | cut -d= -f2):3000"
echo "La primera cuenta que crees es administradora. Empieza en modo DEMO (Settings)."
