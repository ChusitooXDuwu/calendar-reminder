# 📬 mail-watcher

Vigila `tu@empresa.com` y **solo avisa lo importante** (tu jefe/VIPs, tu equipo, reenvíos de clientes, clientes directos).
Ignora sandbox, Linear, Apple, Stripe, statuspage, códigos de login, newsletters, etc.

Tres capas, para que nada se pase:

| Capa | Dónde corre | Frecuencia | Cómo avisa |
|---|---|---|---|
| **GitHub Actions** (`.github/workflows/watch.yml`) | nube | cada 15 min | Slack (bot → DM, sí suena) + push al celular con **ntfy** |
| **PC local** (`local/start.sh`) | tu Mac/Linux | cada 5 min | abre página roja **"CORREO LLEGÓ — LÉELO"** + notificación + sonido |
| **Routine de Claude** | claude.ai | cada hora | DM en Slack con resumen hecho por Claude |

No se repiten avisos: la nube pone la etiqueta **`Claude-Notificado`** en Gmail a lo que ya revisó; el modo local guarda sus vistos en `~/.mail-watcher/vistos.json`.
Nunca responde, borra, archiva ni marca como leído.

## Reglas (en orden)
1. `VIP_SENDERS` (ej. tu jefe) → 🔴 alta
2. Palabras de ruido (`sandbox`, códigos de verificación…) → ignorar
3. Remitentes automáticos (`noreply`, `notifications@`, `banking@`, linear, stripe, apple…) + `NOISE_SENDERS` → ignorar
4. Dominio en `IMPORTANT_DOMAINS` → 🟡 media (🔴 si es reenvío `Fwd:/RV:`)
5. Promos/social/listas de correo → ignorar
6. Cualquier otra persona real → 🟡 media

Prueba sin avisar: `python watcher.py --dry-run`

## Setup (≈10 min, una sola vez)

### 1. Token de Gmail
1. [console.cloud.google.com](https://console.cloud.google.com) → proyecto nuevo → **habilita Gmail API**.
2. *OAuth consent screen* → **Internal** (así el token no caduca a los 7 días).
3. *Credentials* → *Create OAuth client ID* → **Desktop app** → descarga como `client_secret.json` en esta carpeta.
4. `pip install google-auth-oauthlib && python get_refresh_token.py` → copia las 3 líneas que imprime.

### 2. Avisos
- **Slack (recomendado)**: [api.slack.com/apps](https://api.slack.com/apps) → *Create app* → *OAuth & Permissions* → scope `chat:write` → *Install* → copia el **Bot User OAuth Token** (`xoxb-…`). `SLACK_CHANNEL` = tu member ID de Slack (perfil → ⋯ → Copy member ID) (el bot te escribe por DM y te suena, a diferencia de mensajes que te mandas a ti mismo).
- **Celular (ntfy)**: instala la app *ntfy*, suscríbete a un topic largo y secreto (ej. `mail-8f3k29xq7`), y ponlo en `NTFY_TOPIC`. Prioridad urgente = suena aunque estés concentrado.

### 3. GitHub
*Settings → Secrets and variables → Actions*
- **Secrets**: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`, `SLACK_BOT_TOKEN`, `NTFY_TOPIC`
- **Variables**: `MY_EMAIL=tu@empresa.com`, `VIP_SENDERS=jefe@empresa.com`, `IMPORTANT_DOMAINS=empresa.com,cliente1.com,cliente2.com`, `NOISE_SENDERS=proveedor-ruidoso.com`, `SLACK_CHANNEL=UXXXXXXXXXX`

Luego *Actions → mail-watcher → Run workflow* para probar.

> ℹ️ Repo público = minutos de Actions gratis. Todo lo sensible va en Secrets/Variables, nunca en el código. Quieres más seguido? cambia el cron (mínimo `*/5`).

### 4. PC local
```bash
cp .env.example .env   # llena los valores
./local/start.sh       # deja corriendo; INTERVAL=120 ./local/start.sh para cada 2 min
```
macOS al iniciar sesión: ver `local/mailwatcher.plist`.
