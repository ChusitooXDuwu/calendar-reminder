#!/usr/bin/env python3
"""Genera el GMAIL_REFRESH_TOKEN una sola vez (corre en tu PC, abre el navegador).

1. Google Cloud Console -> APIs & Services -> habilita "Gmail API".
2. OAuth consent screen -> User type "Internal" (si tu correo es Google Workspace; asi el token no expira a los 7 dias).
3. Credentials -> Create OAuth client ID -> "Desktop app" -> descarga el JSON como client_secret.json aqui.
4. pip install google-auth-oauthlib && python get_refresh_token.py
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]  # leer + poner etiqueta (no borra ni envia)

path = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline", login_hint=None)
info = json.load(open(path))
client = info.get("installed") or info.get("web")
print("\nPega esto en tu .env y en GitHub -> Settings -> Secrets -> Actions:\n")
print(f"GMAIL_CLIENT_ID={client['client_id']}")
print(f"GMAIL_CLIENT_SECRET={client['client_secret']}")
print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
