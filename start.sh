#!/usr/bin/env bash
# Render start script for Telegram bot

set -o errexit  # exit on first error
set -o pipefail
set -o nounset

echo "[start.sh] Installing dependencies..."
pip install --no-cache-dir -r requirements.txt

echo "[start.sh] Starting Telegram bot..."
exec python bot.py
