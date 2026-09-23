#!/usr/bin/env python3
"""Mail Watcher: revisa Gmail y avisa de todo lo que no sea promocional.

Modos:
  python watcher.py                 -> modo nube (GitHub Actions): avisa por Slack/ntfy
                                       y etiqueta en Gmail lo revisado (Claude-Notificado).
  python watcher.py --local         -> modo PC: abre una pagina "CORREO LLEGO, LEELO",
                                       notificacion del sistema y sonido. No etiqueta.
  python watcher.py --local --loop 300   -> igual, cada 5 minutos para siempre.
  python watcher.py --dry-run       -> solo imprime la clasificacion, no avisa ni etiqueta.

Toda la configuracion va por variables de entorno (o un archivo .env) para que el
repo pueda ser publico sin exponer nada. Ver README.md.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import platform
import re
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from email.utils import parseaddr
from pathlib import Path

import requests

GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
STATE_DIR = Path(os.environ.get("MAIL_WATCHER_HOME", Path.home() / ".mail-watcher"))

# Solo se ignora lo promocional (pestana "Promociones" de Gmail). Todo lo demas avisa.
# Si algo especifico molesta, agregalo a NOISE_SENDERS / NOISE_KEYWORDS (variables).
FORWARD_RE = re.compile(r"^\s*(fwd?|rv|reenviado|tr)\s*:", re.I)
PROMO_CATEGORIES = {"CATEGORY_PROMOTIONS"}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.environ.get(name, "")
    items = [x.strip().lower() for x in raw.split(",") if x.strip()]
    return (default or []) + items


@dataclass
class Config:
    me: str
    vip_senders: list[str]
    important_domains: list[str]
    noise_senders: list[str]
    noise_keywords: list[str]
    label_name: str = "Claude-Notificado"
    lookback: str = "1d"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            me=os.environ.get("MY_EMAIL", "").lower(),
            vip_senders=env_list("VIP_SENDERS"),
            important_domains=env_list("IMPORTANT_DOMAINS"),
            noise_senders=env_list("NOISE_SENDERS"),
            noise_keywords=env_list("NOISE_KEYWORDS"),
            label_name=os.environ.get("NOTIFIED_LABEL", "Claude-Notificado"),
            lookback=os.environ.get("LOOKBACK", "1d"),
        )


@dataclass
class Mail:
    id: str
    thread_id: str
    sender_name: str
    sender: str
    subject: str
    snippet: str
    label_ids: list[str]
    headers: dict[str, str] = field(default_factory=dict)
    priority: str = ""  # "alta" | "media" | "baja" | "" (= no avisar)
    reason: str = ""

    @property
    def url(self) -> str:
        return f"https://mail.google.com/mail/u/0/#all/{self.thread_id}"


# ---------------------------------------------------------------- Gmail

class Gmail:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {self._access_token()}"

    @staticmethod
    def _access_token() -> str:
        missing = [k for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN") if not os.environ.get(k)]
        if missing:
            sys.exit(f"Faltan variables: {', '.join(missing)}. Corre get_refresh_token.py (ver README).")
        r = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": os.environ["GMAIL_CLIENT_ID"],
            "client_secret": os.environ["GMAIL_CLIENT_SECRET"],
            "refresh_token": os.environ["GMAIL_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }, timeout=20)
        if r.status_code != 200:
            sys.exit(f"No pude renovar el token de Gmail ({r.status_code}): {r.text}")
        return r.json()["access_token"]

    def _get(self, path: str, **params):
        r = self.session.get(f"{GMAIL}/{path}", params=params, timeout=20)
        r.raise_for_status()
        return r.json()

    def list_ids(self, query: str, limit: int = 100) -> list[str]:
        data = self._get("messages", q=query, maxResults=limit)
        return [m["id"] for m in data.get("messages", [])]

    def get(self, msg_id: str) -> Mail:
        d = self._get(f"messages/{msg_id}", format="metadata",
                      metadataHeaders=["From", "Subject", "List-Unsubscribe", "Precedence", "Auto-Submitted"])
        headers = {h["name"].lower(): h["value"] for h in d.get("payload", {}).get("headers", [])}
        name, addr = parseaddr(headers.get("from", ""))
        return Mail(
            id=d["id"], thread_id=d["threadId"], sender_name=name or addr, sender=addr.lower(),
            subject=headers.get("subject", "(sin asunto)"), snippet=html.unescape(d.get("snippet", "")),
            label_ids=d.get("labelIds", []), headers=headers,
        )

    def label_id(self, name: str) -> str:
        for lbl in self._get("labels").get("labels", []):
            if lbl["name"] == name:
                return lbl["id"]
        r = self.session.post(f"{GMAIL}/labels", json={"name": name}, timeout=20)
        r.raise_for_status()
        return r.json()["id"]

    def add_label(self, ids: list[str], label_id: str) -> None:
        if ids:
            r = self.session.post(f"{GMAIL}/messages/batchModify",
                                  json={"ids": ids, "addLabelIds": [label_id]}, timeout=20)
            r.raise_for_status()


# ---------------------------------------------------------------- Clasificacion

def classify(m: Mail, cfg: Config) -> Mail:
    """Avisa todo menos lo promocional. La prioridad solo cambia el orden y el icono."""
    sender, domain = m.sender, m.sender.split("@")[-1]
    text = f"{m.subject} {m.snippet}".lower()
    forwarded = bool(FORWARD_RE.match(m.subject))

    if sender in cfg.vip_senders:
        m.priority, m.reason = "alta", "VIP"
    elif cfg.noise_senders and any(p in sender for p in cfg.noise_senders):
        m.reason = "silenciado (NOISE_SENDERS)"
    elif cfg.noise_keywords and any(k in text for k in cfg.noise_keywords):
        m.reason = "silenciado (NOISE_KEYWORDS)"
    elif PROMO_CATEGORIES & set(m.label_ids):
        m.reason = "promocional"
    elif forwarded:
        m.priority, m.reason = "alta", "reenvio"
    elif domain in cfg.important_domains:
        m.priority, m.reason = "media", f"dominio importante ({domain})"
    else:
        m.priority, m.reason = "baja", "otro"
    return m


# ---------------------------------------------------------------- Avisos

def slack_text(important: list[Mail], vip: set[str]) -> str:
    lines = [":rotating_light: *CORREO NUEVO — léelo* :rotating_light:"]
    for m in important[:15]:
        icon = {"alta": ":red_circle:", "media": ":large_yellow_circle:"}.get(m.priority, ":white_circle:")
        who = ":bust_in_silhouette: *VIP* — " if m.sender in vip else ""
        lines.append(f"\n{icon} {who}*{m.sender_name}* <{m.sender}>\n*{m.subject}*\n> {m.snippet[:220]}\n<{m.url}|Abrir en Gmail>")
    if len(important) > 15:
        lines.append(f"\n…y {len(important) - 15} más. <https://mail.google.com/mail/u/0/#inbox|Abrir Gmail>")
    return "\n".join(lines)


def notify_slack(important: list[Mail], cfg: Config) -> None:
    text = slack_text(important, set(cfg.vip_senders))
    token, channel = os.environ.get("SLACK_BOT_TOKEN"), os.environ.get("SLACK_CHANNEL")
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if token and channel:
        r = requests.post("https://slack.com/api/chat.postMessage", timeout=20,
                          headers={"Authorization": f"Bearer {token}"},
                          json={"channel": channel, "text": text, "unfurl_links": False})
        if not r.json().get("ok"):
            print(f"Slack error: {r.text}", file=sys.stderr)
    elif webhook:
        requests.post(webhook, json={"text": text}, timeout=20).raise_for_status()


def notify_ntfy(important: list[Mail], cfg: Config) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return
    top = important[0]
    level = "urgent" if any(m.priority == "alta" for m in important) else \
        "high" if any(m.priority == "media" for m in important) else "default"
    body = "\n".join(f"• {m.sender_name}: {m.subject}" for m in important)
    requests.post(f"{os.environ.get('NTFY_SERVER', 'https://ntfy.sh')}/{topic}", data=body.encode(), timeout=20,
                  headers={"Title": f"CORREO NUEVO ({len(important)})".encode(),
                           "Priority": level,
                           "Tags": "rotating_light,email", "Click": top.url}).raise_for_status()


def notify_local(important: list[Mail]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    page = STATE_DIR / "alerta.html"
    cards = "".join(
        f'<a class="card {m.priority}" href="{m.url}" target="_blank">'
        f'<div class="who">{html.escape(m.sender_name)} &lt;{html.escape(m.sender)}&gt;</div>'
        f'<div class="subj">{html.escape(m.subject)}</div>'
        f'<div class="snip">{html.escape(m.snippet[:280])}</div></a>'
        for m in important)
    page.write_text(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<title>CORREO LLEGÓ — LÉELO</title><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{margin:0;font-family:system-ui,sans-serif;background:#b00020;color:#fff;min-height:100vh}}
h1{{font-size:clamp(40px,9vw,110px);margin:0;padding:40px 24px 8px;text-align:center;animation:b 1s infinite}}
p.sub{{text-align:center;font-size:20px;margin:0 0 24px}}
@keyframes b{{50%{{opacity:.35}}}}
.wrap{{max-width:820px;margin:0 auto;padding:0 16px 40px}}
.card{{display:block;background:#fff;color:#111;border-radius:12px;padding:18px 20px;margin:12px 0;text-decoration:none;border-left:10px solid #f5b700}}
.card.alta{{border-left-color:#ff1744}} .card.baja{{border-left-color:#bbb}} .who{{font-weight:600}} .subj{{font-size:20px;margin:4px 0}} .snip{{color:#555}}
</style></head><body><h1>🚨 CORREO LLEGÓ — LÉELO 🚨</h1>
<p class="sub">{len(important)} correo(s) nuevo(s). Click para abrir en Gmail.</p>
<div class="wrap">{cards}</div></body></html>""")
    webbrowser.open(page.as_uri())

    title, msg = "CORREO IMPORTANTE", f"{important[0].sender_name}: {important[0].subject}"
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["osascript", "-e", f'display notification {json.dumps(msg)} with title {json.dumps(title)} sound name "Glass"'], check=False)
            subprocess.run(["afplay", "/System/Library/Sounds/Sosumi.aiff"], check=False)
        elif system == "Linux":
            subprocess.run(["notify-send", "-u", "critical", title, msg], check=False)
        elif system == "Windows":
            subprocess.run(["powershell", "-c", f"[console]::beep(1000,600); msg * {json.dumps(title + ': ' + msg)}"], check=False)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------- Main

def seen_state() -> tuple[set[str], Path]:
    path = STATE_DIR / "vistos.json"
    try:
        return set(json.loads(path.read_text())), path
    except (FileNotFoundError, ValueError):
        return set(), path


def run_once(args, cfg: Config) -> None:
    gmail = Gmail()
    query = f"in:inbox newer_than:{cfg.lookback} -in:sent"
    if cfg.me:
        query += f" -from:{cfg.me}"
    if not args.local:
        query += f' -label:"{cfg.label_name}"'
    ids = gmail.list_ids(query)

    seen, seen_path = seen_state() if args.local else (set(), None)
    ids = [i for i in ids if i not in seen]
    mails = [classify(gmail.get(i), cfg) for i in ids]
    important = sorted([m for m in mails if m.priority], key=lambda m: ("alta", "media", "baja").index(m.priority))

    for m in mails:
        print(f"[{m.priority or 'ruido':5}] {m.sender:40} {m.subject[:60]}  ({m.reason})")
    print(f"{len(mails)} nuevos, {len(important)} para avisar")
    if args.dry_run:
        return

    if important:
        if args.local:
            notify_local(important)
        else:
            notify_slack(important, cfg)
            notify_ntfy(important, cfg)

    if args.local:
        seen_path.parent.mkdir(parents=True, exist_ok=True)
        seen_path.write_text(json.dumps(sorted(seen | {m.id for m in mails})[-2000:]))
    else:
        gmail.add_label([m.id for m in mails], gmail.label_id(cfg.label_name))


def main() -> None:
    load_dotenv(Path(__file__).with_name(".env"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local", action="store_true", help="avisar en este PC (pagina + notificacion)")
    ap.add_argument("--loop", type=int, default=0, metavar="SEG", help="repetir cada SEG segundos")
    ap.add_argument("--dry-run", action="store_true", help="solo clasificar, sin avisar ni etiquetar")
    args = ap.parse_args()
    cfg = Config.from_env()

    while True:
        try:
            run_once(args, cfg)
        except requests.RequestException as e:
            print(f"Error de red: {e}", file=sys.stderr)
            if not args.loop:
                sys.exit(1)
        if not args.loop:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
