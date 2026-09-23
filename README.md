# 📬 mail-watcher

Vigila tu Gmail y **te avisa de todo lo que no sea promocional**. Lo de VIPs y reenvíos sale primero y en rojo.

Dos capas, para que nada se pase:

| Capa | Dónde corre | Frecuencia | Cómo avisa |
|---|---|---|---|
| **GitHub Actions** (`.github/workflows/watch.yml`) | nube | cada 15 min | Slack (bot → DM, sí suena) + push al celular con **ntfy** |
| **PC local** (`local/start.sh`) | tu Mac/Linux | cada 5 min | abre página roja **"CORREO LLEGÓ — LÉELO"** + notificación + sonido |

No se repiten avisos: la nube pone la etiqueta **`Claude-Notificado`** en Gmail a lo que ya revisó; el modo local guarda sus vistos en `~/.mail-watcher/vistos.json`.
Nunca responde, borra, archiva ni marca como leído.

## Reglas (en orden)
1. Remitente en `VIP_SENDERS` → 🔴 alta
2. Remitente en `NOISE_SENDERS` o texto con `NOISE_KEYWORDS` → silenciado (vacíos por defecto; úsalos si algo molesta)
3. Pestaña **Promociones** de Gmail → ignorado
4. Reenvío (`Fwd:` / `RV:` / `Reenviado:`) → 🔴 alta
5. Dominio en `IMPORTANT_DOMAINS` → 🟡 media
6. Todo lo demás → ⚪ baja (igual avisa)

Un solo mensaje por revisión con todos los correos nuevos, ordenados por prioridad.

Prueba sin avisar: `python watcher.py --dry-run`

## Setup (una sola vez)

Todo se configura en el repo → **Settings → Secrets and variables → Actions**.
*Secrets* = cosas privadas (tokens). *Variables* = configuración (correos, listas). Los valores van **sin comillas**; las listas separadas por coma.

### 1. Gmail → `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` (secrets)
1. [console.cloud.google.com/projectcreate](https://console.cloud.google.com/projectcreate) → crea proyecto `mail-watcher` (con tu cuenta del trabajo).
2. [Habilita la Gmail API](https://console.cloud.google.com/apis/library/gmail.googleapis.com) → **Enable**.
3. [OAuth consent screen / Branding](https://console.cloud.google.com/auth/branding) → nombre `mail-watcher`, tu correo → Audience: **Internal** (si es Google Workspace; si sale solo *External*, ponlo en *In production* o el token expira a los 7 días).
4. [Clients](https://console.cloud.google.com/auth/clients) → **Create client** → tipo **Desktop app** → **Download JSON** → guárdalo en la carpeta del repo como `client_secret.json` (está en `.gitignore`, no se sube).
5. En tu PC:
   ```bash
   pip install google-auth-oauthlib requests
   python get_refresh_token.py
   ```
   Se abre el navegador → entra con tu correo → *Allow*. Imprime 3 líneas → cada una es un secret.

### 2. Slack → `SLACK_BOT_TOKEN` (secret) + `SLACK_CHANNEL` (variable)
1. [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From a manifest** → tu workspace → pega `setup/slack-manifest.yml` → **Create**.
2. **Install to Workspace** → *Allow*.
3. *OAuth & Permissions* → copia **Bot User OAuth Token** (`xoxb-…`) → secret `SLACK_BOT_TOKEN`.
4. `SLACK_CHANNEL` = **tu member ID** (Slack → tu foto → *Profile* → ⋯ → *Copy member ID*, empieza con `U`). El bot te escribe por DM en la sección *Apps → Mail Watcher* y **sí te suena**. Si prefieres un canal, pon el ID del canal (`C…`) e invita al bot con `/invite @Mail Watcher`.

### 3. Celular (opcional) → `NTFY_TOPIC` (secret)
Instala **ntfy** (iOS/Android) → *Subscribe to topic* → inventa un nombre largo y raro (ej. `mail-8f3k29xq7`) → ese es el secret. Quien sepa el nombre puede leer los avisos, por eso largo y secreto.

### 4. Variables
| Variable | Ejemplo |
|---|---|
| `MY_EMAIL` | `tu@empresa.com` (para ignorar lo que tú envías) |
| `VIP_SENDERS` | `jefe@empresa.com, socio@empresa.com` |
| `IMPORTANT_DOMAINS` | `empresa.com, cliente1.com` |
| `SLACK_CHANNEL` | `UXXXXXXXXXX` |
| `NOISE_SENDERS` | *(opcional)* `muralpay.com, statuspage.io` |
| `NOISE_KEYWORDS` | *(opcional)* `sandbox` |

### 5. Probar
*Actions → mail-watcher → Run workflow*. En el log ves cada correo con su clasificación. La primera vez te llega todo lo del último día; después solo lo nuevo.

### 6. PC local (opcional, cada 5 min)
```bash
cp .env.example .env   # llena los valores
./local/start.sh       # deja corriendo; INTERVAL=120 ./local/start.sh para cada 2 min
```
macOS al iniciar sesión: ver `local/mailwatcher.plist`.
