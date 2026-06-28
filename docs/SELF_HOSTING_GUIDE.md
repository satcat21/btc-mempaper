## Self-Hosting with Traefik & OIDC Authentication

This guide walks through exposing your mempaper instance — and optionally a
self-hosted mempool — to the internet, secured with OIDC login via
[Zitadel](https://zitadel.com).

### Architecture

```
Browser
  │
  ▼
Traefik (:443, TLS termination)
  ├─ mempaper.yourdomain.com
  │    ├─ /socket.io/* ──────────────────→ mempaper Pi :5000   (no OIDC — WebSocket)
  │    └─ /*     → OIDC login → Zitadel → mempaper Pi :5000
  │
  └─ mempool.yourdomain.com  (optional)
       ├─ LAN clients ──────────────────→ mempool :4081   (no auth)
       └─ Internet → Basic Auth ────────→ mempool :4081
```

- **Traefik** terminates TLS and runs the `traefik-oidc-auth` middleware plugin
- **Zitadel** (self-hosted) is the OIDC identity provider
- **mempaper** runs on your Raspberry Pi (default port 5000)
- **mempool** (optional) runs on a separate machine at HTTPS port 4081

---

### Prerequisites

| What | Why |
|---|---|
| Domain (e.g. `yourdomain.com`) | DNS-routable hostnames for Traefik |
| Server running Docker | Hosts Traefik and Zitadel |
| Ports **80** and **443** forwarded to that server | TLS termination |
| DNS provider with API support | Wildcard Let's Encrypt certificate via DNS challenge |
| mempaper running on your Pi | The upstream being exposed |

---

### Part 1 — Set Up Zitadel as Your OIDC Provider

Zitadel is a self-hosted identity platform that acts as the login gateway.

#### Deploy Zitadel

```yaml
# docker-compose.yml (Zitadel + Postgres)
services:
  zitadel:
    image: ghcr.io/zitadel/zitadel:latest
    command: start-from-init --masterkey "${ZITADEL_MASTERKEY}" --tlsMode disabled
    environment:
      ZITADEL_DATABASE_POSTGRES_HOST: zitadel-db
      ZITADEL_DATABASE_POSTGRES_PORT: "5432"
      ZITADEL_DATABASE_POSTGRES_DATABASE: zitadel
      ZITADEL_DATABASE_POSTGRES_USER_USERNAME: zitadel
      ZITADEL_DATABASE_POSTGRES_USER_PASSWORD: "${DB_PASSWORD}"
      ZITADEL_DATABASE_POSTGRES_ADMIN_USERNAME: postgres
      ZITADEL_DATABASE_POSTGRES_ADMIN_PASSWORD: "${DB_PASSWORD}"
      ZITADEL_EXTERNALSECURE: "true"
      ZITADEL_EXTERNALPORT: "443"
      ZITADEL_EXTERNALDOMAIN: "login.yourdomain.com"
    depends_on:
      zitadel-db:
        condition: service_healthy
    restart: unless-stopped

  zitadel-db:
    image: postgres:16
    environment:
      POSTGRES_DB: zitadel
      POSTGRES_USER: zitadel
      POSTGRES_PASSWORD: "${DB_PASSWORD}"
    volumes:
      - zitadel-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U zitadel"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  zitadel-db-data:
```

> Set `ZITADEL_MASTERKEY` to a random 32-character string (`openssl rand -base64 24`).
> Expose Zitadel behind Traefik at `https://login.yourdomain.com` exactly like any other service.
> Full self-hosting docs: https://zitadel.com/docs/self-hosting/deploy/docker

#### Create the OIDC Application in Zitadel

After Zitadel is running, open `https://login.yourdomain.com`:

1. **Create an Organization** (e.g. "Home")
2. **Create a Project** (e.g. "HomeServer")
3. Inside the project, add an **Application**:
   - Name: `mempaper`
   - Type: **Web**
   - Auth method: **Basic** (client ID + secret)
   - Grant type: **Authorization Code**
   - **Redirect URI**: `https://mempaper.yourdomain.com/oidc/callback`
   - **Post-Logout Redirect URI**: `https://mempaper.yourdomain.com`
4. Save — note the **Client ID** and generate a **Client Secret**

#### Enable Role Claims

In the project's **Settings**, enable:
- ☑ **Assert Roles on Authentication**
- ☑ **Check Authorization on Authentication**

Go to **Roles** → create a role named `mempaper`.
Go to **Users** → select a user → **Authorizations** → grant the `mempaper` role.

Zitadel will now include roles in the `urn:zitadel:iam:org:project:roles` claim of every
token issued to that user.

---

### Part 2 — Set Up Traefik

#### `traefik.yml` (static config)

```yaml
api:
  dashboard: true

log:
  level: INFO

providers:
  file:
    directory: /config
    watch: true

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https

  websecure:
    address: ":443"
    transport:
      respondingTimeouts:
        readTimeout: 0s    # Required: keeps WebSocket connections alive indefinitely
        writeTimeout: 0s
        idleTimeout: 0s

experimental:
  plugins:
    traefik-oidc-auth:
      moduleName: "github.com/sevensolutions/traefik-oidc-auth"
      version: "v0.18.0"
```

> **Why zero timeouts?** Both mempaper (Socket.IO) and mempool use long-lived WebSocket
> connections. A non-zero `readTimeout` or `writeTimeout` drops idle connections mid-session.

#### `docker-compose.yml`

```yaml
services:
  traefik:
    image: traefik:v3.7
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./traefik.yml:/traefik.yml:ro
      - ./config:/config:ro
      - ./letsencrypt:/letsencrypt
      - /var/run/docker.sock:/var/run/docker.sock:ro
    dns:
      - 9.9.9.9
      - 208.67.222.222
```

---

### Part 3 — TLS Certificates

Use [LEGO](https://go-acme.github.io/lego/) with your DNS provider to issue a wildcard
certificate (covers all `*.yourdomain.com` subdomains with one cert):

```bash
lego \
  --email you@example.com \
  --dns YOUR_DNS_PROVIDER \
  --domains "yourdomain.com" \
  --domains "*.yourdomain.com" \
  run
```

Copy the resulting `fullchain.pem` and `key.pem` to your `letsencrypt/` folder, then
reference them in a static TLS config file:

```yaml
# config/tls.yml
tls:
  certificates:
    - certFile: /letsencrypt/fullchain.pem
      keyFile: /letsencrypt/key.pem
```

Supported DNS providers: https://go-acme.github.io/lego/dns/

Set up a daily cron job to run `lego renew --days 30` and restart Traefik after renewal.

---

### Part 4 — Expose mempaper with OIDC

mempaper uses **Socket.IO** for real-time display updates. Socket.IO sends a standard HTTP
request to `/socket.io/?...` and negotiates a WebSocket upgrade. The OIDC middleware would
intercept this and redirect it to the login page — which breaks the WebSocket protocol.

The solution is a **priority router** that matches `/socket.io/` with higher priority and
*no* OIDC middleware. Only browsers that completed OIDC login on the main route will ever
load the page that triggers this WebSocket, so skipping OIDC on this path is safe.

#### `config/middlewares.yml`

```yaml
http:
  middlewares:

    oidc-auth:
      plugin:
        traefik-oidc-auth:
          Provider:
            Url: "https://login.yourdomain.com"
            ClientId: "YOUR_CLIENT_ID"           # from Zitadel application
            ClientSecret: "YOUR_CLIENT_SECRET"   # from Zitadel application
          LogoutRedirectUri: "https://login.yourdomain.com/oidc/v1/end_session"
          Secret: "RANDOM_32_CHAR_STRING"         # openssl rand -hex 16
          CookieName: "_traefik_oidc"
          CookieSameSite: "lax"
          CookieSecure: true
          CookiePath: "/"
          SessionTimeout: 43200                   # 12 hours in seconds
          Scopes:
            - openid
            - profile
            - email
            - urn:zitadel:iam:org:project:roles
          Headers:
            User: "sub"
            Email: "email"
            Name: "name"
            Username: "preferred_username"
            Roles: "urn:zitadel:iam:org:project:roles"

    privacy-headers:
      headers:
        customResponseHeaders:
          Referrer-Policy: "no-referrer"
          X-Robots-Tag: "noindex, noimageindex"
```

> `Secret` signs the OIDC session cookie — keep it private, never commit it.
> Generate it with: `openssl rand -hex 16`

#### `config/mempaper.yml`

```yaml
http:
  serversTransports:
    websocket-transport:
      dialTimeout: 30s
      responseHeaderTimeout: 0s   # Persistent WebSocket connections
      idleConnTimeout: 0s

  services:
    mempaper-service:
      loadBalancer:
        servers:
          - url: "http://192.168.0.x:5000"   # IP of your mempaper Raspberry Pi
        serversTransport: websocket-transport

  routers:
    # Socket.IO WebSocket path — higher priority, NO OIDC middleware.
    # Only browsers that completed OIDC login on the main route can load the
    # page that triggers this WebSocket, so skipping OIDC here is safe.
    mempaper-ws:
      rule: "Host(`mempaper.yourdomain.com`) && PathPrefix(`/socket.io/`)"
      entryPoints: ["websecure"]
      service: mempaper-service
      tls: {}
      priority: 100

    # Main app route — OIDC login required
    mempaper:
      rule: "Host(`mempaper.yourdomain.com`)"
      entryPoints: ["websecure"]
      service: mempaper-service
      tls: {}
      middlewares:
        - "privacy-headers"
        - "oidc-auth"
```

**Login flow**: Browser hits `https://mempaper.yourdomain.com` → Traefik's OIDC plugin
redirects to Zitadel → you log in → Zitadel redirects back to
`https://mempaper.yourdomain.com/oidc/callback` → plugin exchanges the code for tokens,
sets a session cookie, and forwards you into mempaper.

---

### Part 5 — Expose Self-Hosted mempool (optional)

If you run your own [mempool.space](https://github.com/mempool/mempool) instance, you can
expose it through Traefik as well. Two differences from mempaper:

1. **Backend runs HTTPS with a self-signed cert** — Traefik needs `insecureSkipVerify: true`
2. **Auth strategy is Basic Auth, not OIDC** — the mempool web UI works fine with OIDC, but
   the mobile app and mempaper's own API calls cannot follow OIDC redirects. A shared secret
   (Basic Auth) protects internet access, while LAN clients bypass auth entirely.

#### How the priority routing works

```
LAN client (192.168.0.x)    → mempool-lan     (priority 150, no auth) ✓
Internet client              → mempool         (default priority, Basic Auth)

LAN WebSocket               → mempool-ws-lan  (priority 200, no auth) ✓
Internet WebSocket           → mempool-ws      (priority 100, Basic Auth)
```

Traefik picks the first router whose rule fully matches. When two rules are equally specific,
`priority` decides. LAN routers have higher priority numbers, so a `192.168.0.x` request
matches the no-auth router even though the public router would also match.

#### Generate Basic Auth credentials

```bash
# Install apache2-utils if not present
apt install apache2-utils

# Generate a credential hash (replace YOUR_SECRET)
htpasswd -nb mempool YOUR_SECRET
# Output: mempool:$apr1$xxxxxxxx$...
```

Paste the output into the config below.

#### `config/mempool.yml`

```yaml
http:
  serversTransports:
    mempool-transport:
      insecureSkipVerify: true    # mempool backend uses a self-signed cert
      dialTimeout: 30s
      responseHeaderTimeout: 0s
      idleConnTimeout: 0s

  middlewares:
    mempool-secret-auth:
      basicAuth:
        users:
          - "mempool:$apr1$..."   # paste htpasswd output here
        removeHeader: true        # strip Authorization before forwarding to backend

  services:
    mempool-service:
      loadBalancer:
        servers:
          - url: "https://192.168.0.x:4081"   # your mempool host
        serversTransport: mempool-transport

  routers:
    # LAN bypass — WebSocket (highest priority)
    mempool-ws-lan:
      rule: "Host(`mempool.yourdomain.com`) && PathPrefix(`/api/v1/ws`) && ClientIP(`192.168.0.0/24`)"
      entryPoints: ["websecure"]
      service: mempool-service
      tls: {}
      priority: 200

    # LAN bypass — REST API
    mempool-api-lan:
      rule: "Host(`mempool.yourdomain.com`) && PathPrefix(`/api/`) && ClientIP(`192.168.0.0/24`)"
      entryPoints: ["websecure"]
      service: mempool-service
      tls: {}
      priority: 160

    # LAN bypass — Frontend
    mempool-lan:
      rule: "Host(`mempool.yourdomain.com`) && ClientIP(`192.168.0.0/24`)"
      entryPoints: ["websecure"]
      service: mempool-service
      tls: {}
      priority: 150

    # Internet — WebSocket (Basic Auth)
    mempool-ws:
      rule: "Host(`mempool.yourdomain.com`) && PathPrefix(`/api/v1/ws`)"
      entryPoints: ["websecure"]
      service: mempool-service
      tls: {}
      priority: 100
      middlewares:
        - "mempool-secret-auth"

    # Internet — REST API (Basic Auth)
    mempool-api:
      rule: "Host(`mempool.yourdomain.com`) && PathPrefix(`/api/`) && !PathPrefix(`/api/v1/ws`)"
      entryPoints: ["websecure"]
      service: mempool-service
      tls: {}
      priority: 90
      middlewares:
        - "mempool-secret-auth"

    # Internet — Frontend (Basic Auth)
    mempool:
      rule: "Host(`mempool.yourdomain.com`)"
      entryPoints: ["websecure"]
      service: mempool-service
      tls: {}
      middlewares:
        - "privacy-headers"
        - "mempool-secret-auth"
```

---

### Part 6 — Point mempaper to your mempool

Open mempaper's **Settings → Advanced → Mempool** and set:

| Field | Value |
|---|---|
| **Mempool Host** | `mempool.yourdomain.com` |
| **Mempool REST Port** | `443` |
| **Use HTTPS** | ☑ enabled |

**If mempaper is on the same LAN** (`192.168.0.0/24`), leave **Mempool Username** and
**Mempool Password** blank. Traefik's LAN bypass routers will forward requests without
requiring authentication.

**If mempaper is outside your LAN** (e.g. on a cloud server), also set:

| Field | Value |
|---|---|
| **Mempool Username** | `mempool` |
| **Mempool Password** | `YOUR_SECRET` |

mempaper sends these credentials as an `Authorization: Basic` header. Traefik's
`mempool-secret-auth` middleware validates the header and strips it (via `removeHeader: true`)
before forwarding to the mempool backend.

---

### Part 7 — Event-Hub: Relay Lightning Donations Over the Internet (Optional)

When mempaper runs outside the direct reach of your LNbits server (e.g. the Pi is at home
but LNbits is on a VPS, or both are on separate isolated LANs), LNbits cannot POST the payment webhook directly to
mempaper. [event-hub](https://github.com/satcat21/event-hub) solves this: LNbits POSTs to
event-hub, and mempaper connects to event-hub via WebSocket to receive donations in real time.

```
LNbits
  │
  └─ POST /hook/{token}
            │
            ▼
        event-hub  (public HTTPS, self-hosted)
            │
            └─ WS broadcast → mempaper  (WebSocket client, wherever it runs)
```

#### Deploy event-hub

```yaml
# docker-compose.yml
services:
  event-hub:
    build: .
    restart: unless-stopped
    env_file: .env
    ports:
      - "${APP_PORT}:${APP_PORT}"
    volumes:
      - ./data:/app/data
```

```bash
# .env
BASE_URL=https://webhook.yourdomain.com
APP_PORT=8080
SESSION_SECRET=RANDOM_64_CHAR_HEX        # openssl rand -hex 32
TOKENS_FILE=/app/data/tokens.json
ZITADEL_ISSUER=https://login.yourdomain.com
ZITADEL_CLIENT_ID=YOUR_CLIENT_ID
ZITADEL_CLIENT_SECRET=YOUR_CLIENT_SECRET  # leave empty for PKCE flow
```

```bash
docker compose up -d --build
```

> Generate `SESSION_SECRET` with `openssl rand -hex 32`.

#### Create a Zitadel Application for event-hub

In Zitadel, add a second application to your existing project:

1. Inside the project, add an **Application**:
   - Name: `event-hub`
   - Type: **Web**
   - Auth method: **Basic** (client ID + secret)
   - Grant type: **Authorization Code**
   - **Redirect URI**: `https://webhook.yourdomain.com/auth/callback`
   - **Post-Logout Redirect URI**: `https://webhook.yourdomain.com`
2. Save — note the **Client ID** and generate a **Client Secret**
3. Put both values into the `.env` above

#### Expose event-hub via Traefik

event-hub manages its own OIDC login internally, so no OIDC middleware is needed in Traefik.
The `/ws/{token}` path is a long-lived WebSocket — reference the existing `websocket-transport`
from `mempaper.yml`.

```yaml
# config/eventhub.yml
http:
  services:
    eventhub-service:
      loadBalancer:
        passHostHeader: true   # event-hub builds its Zitadel redirect URI from the Host header
        servers:
          - url: "http://192.168.0.x:8080"   # event-hub host
        serversTransport: websocket-transport   # reuse zero-timeout transport from mempaper.yml

  routers:
    # WebSocket path — higher priority, no middleware (persistent connections to /ws/{token})
    eventhub-ws:
      rule: "Host(`webhook.yourdomain.com`) && PathPrefix(`/ws/`)"
      entryPoints: ["websecure"]
      service: eventhub-service
      tls: {}
      priority: 100

    # All other paths: /auth/, /admin/, /hook/, etc.
    eventhub:
      rule: "Host(`webhook.yourdomain.com`)"
      entryPoints: ["websecure"]
      service: eventhub-service
      tls: {}
      middlewares:
        - "privacy-headers"
```

> No OIDC middleware here — event-hub handles its own Zitadel login internally.
> `passHostHeader: true` is required: without it Traefik would forward the backend host to
> event-hub instead of `webhook.yourdomain.com`, breaking the auth callback URL that
> event-hub constructs. The `websocket-transport` (defined in `mempaper.yml`) keeps
> `/ws/{token}` connections alive indefinitely.

#### Create a Webhook Token

1. Open `https://webhook.yourdomain.com/auth/login` and log in via Zitadel
2. Go to `https://webhook.yourdomain.com/admin`
3. Create a new token — you will receive a UUID, e.g. `550e8400-e29b-41d4-a716-446655440000`
4. Note the two resulting URLs:
   - **Webhook URL** (for LNbits): `https://webhook.yourdomain.com/hook/550e8400-…`
   - **WebSocket URL** (for mempaper): `wss://webhook.yourdomain.com/ws/550e8400-…`

#### Configure LNbits

In LNbits, enable the **LNURLp** extension (Pay Links) and create a donation link:

1. Open **Extensions** → enable **Pay Links (LNURLp)** if not already active
2. Go to **Pay Links → New Pay Link**
3. Fill in the basic fields (wallet, min/max amount, description)
4. Expand **Advanced options** and:
   - Enable **"Allow users to attach a comment to their payment"** — this is what populates the donation message shown on mempaper
   - Set **Webhook URL** to the event-hub hook URL:
     ```
     https://webhook.yourdomain.com/hook/550e8400-e29b-41d4-a716-446655440000
     ```
5. Save and share the generated LNURL or QR code

When a payment is made, LNbits POSTs the amount (in millisatoshis) and the payer's comment to event-hub, which broadcasts it to mempaper in real time.

#### Configure mempaper

In mempaper's **Settings → Advanced → Lightning Donation**:

| Field | Value |
|---|---|
| **Show Donation Block** | ☑ enabled |
| **Webhook Relay WebSocket URL** | `wss://webhook.yourdomain.com/ws/550e8400-…` |
| **Display Mode** | `auto` (shows latest donation for ~3 days, then falls back to highest) |

mempaper opens a persistent WebSocket to event-hub and reconnects automatically if the
connection drops. When a payment arrives, event-hub broadcasts it and mempaper displays it
on the dashboard within seconds.

> **Direct webhook alternative**: If mempaper and LNbits are on the same network, you can
> skip event-hub entirely and point LNbits directly at mempaper:
> `http://mempaper-ip:5000/api/donation-webhook`

---

### Security Notes

| Topic | Detail |
|---|---|
| OIDC `Secret` | Signs the session cookie — generate randomly with `openssl rand -hex 16`, keep private |
| Zitadel `ClientSecret` | Never commit to Git — use environment variables or Docker secrets |
| Basic Auth hash | Safe to store in config files; it is a bcrypt hash, not the secret itself |
| `privacy-headers` | Suppresses `Referer` and search-engine indexing for private instances |
| `insecureSkipVerify: true` | Intentional: mempool's backend cert is self-signed on the LAN; Traefik handles public TLS |
| LAN bypass | Only works correctly if Traefik receives the real client IP — if a VPS or proxy sits in front, set `forwardedHeaders.trustedIPs` to its IP in `traefik.yml` |
