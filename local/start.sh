#!/usr/bin/env bash
# Corre el watcher en tu PC cada 5 min: abre "CORREO LLEGO — LEELO" + notificacion + sonido.
cd "$(dirname "$0")/.."
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
exec python watcher.py --local --loop "${INTERVAL:-300}"
