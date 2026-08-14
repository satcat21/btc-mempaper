## Self-hosting with Traefik & OIDC authentication

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

### Part 1 — Set up Zitadel as your OIDC provider

Zitadel is a self-hosted identity platform that acts as the login gateway.

#### Deploy Zitadel

```yaml
# docker-compose.yml (Zitadel + Postgres)
services:
  zitadel:
    image: ghcr.io/zitadel/zitadel:v2.71.4   # pin exact version
    command: start --masterkey "${ZITADEL_MASTERKEY}" --tlsMode disabled
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
    security_opt:
      - no-new-privileges:true
    networks:
      - traefik-public
      - zitadel-internal

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
    security_opt:
      - no-new-privileges:true
    networks:
      - zitadel-internal

volumes:
  zitadel-db-data:

networks:
  traefik-public:
  zitadel-internal:
    internal: true   # DB unreachable from outside
```

> Set `ZITADEL_MASTERKEY` to a random 32-character string (`openssl rand -base64 24`).
> Expose Zitadel behind Traefik at `https://login.yourdomain.com` exactly like any other service.
> Full self-hosting docs: https://zitadel.com/docs/self-hosting/deploy/compose
>
> **First deploy only**: replace `start` with `start-from-init` to run database migrations.
> On subsequent starts, use `start` — it skips the init phase and starts faster.

#### Create the OIDC application in Zitadel

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

#### Enable role claims

In the project's **Settings**, enable:
- ☑ **Assert Roles on Authentication**
- ☑ **Check Authorization on Authentication**

Go to **Roles** → create a role named `mempaper`.
Go to **Users** → select a user → **Authorizations** → grant the `mempaper` role.

Zitadel will now include roles in the `urn:zitadel:iam:org:project:roles` claim of every
token issued to that user.

---

### Part 2 — Set up Traefik

#### `traefik.yml` (static config)

```yaml
api:
  dashboard: true
  insecure: false   # dashboard only accessible via a routed entrypoint with auth

log:
  level: INFO

accessLog:
  filePath: "/var/log/traefik/access.log"
  fields:
    headers:
      defaultMode: keep

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
        readTimeout: 60s
        writeTimeout: 60s
        idleTimeout: 180s
      lifeCycle:
        graceTimeOut: 10s
    forwardedHeaders:
      trustedIPs:
        - "10.0.0.1/32"     # placeholder — the address your tunnel/VPS connects from
      insecure: false        # NEVER trust X-Forwarded-For from arbitrary clients

certificatesResolvers:
  letsencrypt:
    acme:
      email: you@example.com
      storage: /letsencrypt/acme.json
      dnsChallenge:
        provider: YOUR_DNS_PROVIDER   # see https://doc.traefik.io/traefik/https/acme/#providers

experimental:
  plugins:
    traefik-oidc-auth:
      moduleName: "github.com/sevensolutions/traefik-oidc-auth"
      version: "v0.21.0"
```

> **Entrypoint timeouts** are set to tight defaults (60s) that protect against slowloris
> attacks. WebSocket persistence is handled per-service via `serversTransport` (see Part 4),
> not at the entrypoint level where it would affect all routes.
>
> **`forwardedHeaders.trustedIPs`** is required if a VPS, WireGuard tunnel, or CDN sits in
> front of Traefik. Without it, `ClientIP()` rules (LAN bypass) see the tunnel IP instead
> of the real client. Set `insecure: false` to reject spoofed `X-Forwarded-For` from
> untrusted sources. Remove the `forwardedHeaders` block entirely if Traefik faces the
> internet directly.
>
> The `10.0.0.1/32` above is a placeholder — substitute the address **your** proxy
> connects from, which for a WireGuard tunnel is its address inside the tunnel (`wg show`
> on either peer, or `ip -br addr` on the interface). List only that one host — widening it
> to a whole subnet, and `0.0.0.0/0` above all, hands everyone inside that range the ability
> to claim any client IP they like, which is exactly what the LAN bypass in Part 5 trusts.
> Traefik's own docs: https://doc.traefik.io/traefik/routing/entrypoints/#forwarded-headers
>
> **`accessLog`** records every request — essential for incident response and debugging
> auth failures. Mount a log volume or use Docker's logging driver to persist it.

#### `docker-compose.yml`

```yaml
services:
  traefik:
    image: traefik:v3.7.10
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./traefik.yml:/traefik.yml:ro
      - ./config:/config:ro
      - ./letsencrypt:/letsencrypt
    dns:
      - 9.9.9.9
      - 208.67.222.222
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    mem_limit: 256m
    healthcheck:
      test: ["CMD", "traefik", "healthcheck"]
      interval: 30s
      timeout: 5s
      retries: 3
```

> The Docker socket mount (`/var/run/docker.sock`) is omitted because this setup uses
> the file provider, not Docker labels. If you need the Docker provider, use a socket
> proxy like [tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy)
> instead of mounting the socket directly.

---

### Part 3 — TLS certificates

Traefik’s built-in ACME client handles certificate issuance and renewal automatically
via the `certificatesResolvers.letsencrypt` block in `traefik.yml` (see Part 2). No
cron jobs, no manual file copying.

To use it, set your DNS provider’s API credentials as environment variables on the
Traefik container (provider list: https://doc.traefik.io/traefik/https/acme/#providers).
Then reference the resolver in your routers with `tls: { certResolver: letsencrypt }`.

For a wildcard certificate covering all `*.yourdomain.com`:

```yaml
# In traefik.yml (already present from Part 2)
certificatesResolvers:
  letsencrypt:
    acme:
      email: you@example.com
      storage: /letsencrypt/acme.json
      dnsChallenge:
        provider: YOUR_DNS_PROVIDER
```

```yaml
# In any router definition
tls:
  certResolver: letsencrypt
  domains:
    - main: "yourdomain.com"
      sans:
        - "*.yourdomain.com"
```

#### Alternative: external LEGO

If you prefer managing certificates outside Traefik (e.g. sharing them with other
services), use [LEGO](https://go-acme.github.io/lego/) with a cron job:

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

The workaround is a **priority router** that matches `/socket.io/` with higher priority and
*no* OIDC middleware.

> **This exemption is only safe because mempaper authenticates the socket itself.**
> The tempting justification — that only browsers which completed OIDC login can reach
> this path — is wrong. `/socket.io/` is directly reachable by anyone who knows the
> hostname, and Socket.IO also serves a plain HTTP **long-polling** transport from the
> same path, so an attacker does not even need a WebSocket client: a single `curl` will
> do. Nothing about the priority router prevents that.
>
> What makes it acceptable is that mempaper applies the same rule to the socket as to
> the dashboard page: an unauthenticated connection is **refused** unless
> `public_dashboard` is enabled, and the handler that returns the rendered dashboard
> image re-checks it. Keep mempaper current — older versions accepted any socket and
> would hand the rendered image, wallet balances included when that block is enabled,
> to anyone who asked for it.
>
> If your reverse proxy can apply OIDC to WebSocket upgrades without breaking them,
> doing so as well is worth it — defence in depth costs nothing here.

#### `config/middlewares.yml`

```yaml
http:
  middlewares:

    oidc-auth:
      plugin:
        traefik-oidc-auth:
          Provider:
            Url: "https://login.yourdomain.com"
            ClientId: "${file:/run/secrets/oidc_client_id}"
            ClientSecret: "${file:/run/secrets/oidc_client_secret}"
          LogoutRedirectUri: "https://login.yourdomain.com/oidc/v1/end_session"
          Secret: "${file:/run/secrets/oidc_session_secret}"
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

    # Global security headers (HSTS + nosniff — apply to every router)
    security-headers:
      headers:
        stsSeconds: 31536000
        stsIncludeSubdomains: true
        stsPreload: true
        contentTypeNosniff: true

    # Privacy headers (selectively applied to services that should not be indexed)
    privacy-headers:
      headers:
        customResponseHeaders:
          Referrer-Policy: "no-referrer"
          X-Robots-Tag: "noindex, noimageindex"

    # Rate limit for auth-protected routes (brute-force protection)
    rate-limit:
      rateLimit:
        average: 5
        burst: 10
```

> **`${file:/path}` syntax** (new in traefik-oidc-auth v0.21.0) loads secrets from files
> at runtime. Create the secret files in a directory mounted into the Traefik container
> (e.g. `./secrets:/run/secrets:ro`) and keep them out of Git.
>
> **Alternative: envsubst template** — if you prefer a single `.env` file for all secrets
> (including Basic Auth hashes that aren't part of the plugin), keep a `.template` file
> with `${VAR}` placeholders and render it at deploy time:
> ```
> set -a; . ./.env; set +a
> envsubst '$ZITADEL_CLIENT_ID $ZITADEL_CLIENT_SECRET $OIDC_SESSION_SECRET' \
>   < config/dynamic.yml.template > config/dynamic.yml
> ```
> Pass an **explicit variable list** so `${1}` in any `redirectRegex` survives expansion.
> Validate the output for leftover `${...}` before reloading Traefik.
>
> Generate `Secret` with: `openssl rand -hex 16`

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
    # Socket.IO path — higher priority, NO OIDC middleware, because the OIDC
    # redirect breaks the upgrade. This path is reachable by anyone, including
    # over plain HTTP long-polling; mempaper authenticates the socket itself,
    # which is what makes the exemption acceptable. See the note above.
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
        - "security-headers"
        - "rate-limit"
        - "oidc-auth"
```

**Login flow**: Browser hits `https://mempaper.yourdomain.com` → Traefik's OIDC plugin
redirects to Zitadel → you log in → Zitadel redirects back to
`https://mempaper.yourdomain.com/oidc/callback` → plugin exchanges the code for tokens,
sets a session cookie, and forwards you into mempaper.

---

### Part 5 — Expose self-hosted mempool (optional)

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

# Generate a credential hash (replace YOUR_SECRET).
# -B selects bcrypt. Without it htpasswd emits $apr1$ (MD5-crypt), which is
# fast enough to brute-force offline if the config file ever leaks.
htpasswd -nbB mempool YOUR_SECRET
# Output: mempool:$2y$05$xxxxxxxx...
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
          - "mempool:$2y$05$..."   # paste htpasswd -nbB output here
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
        - "rate-limit"
        - "mempool-secret-auth"

    # Internet — REST API (Basic Auth)
    mempool-api:
      rule: "Host(`mempool.yourdomain.com`) && PathPrefix(`/api/`) && !PathPrefix(`/api/v1/ws`)"
      entryPoints: ["websecure"]
      service: mempool-service
      tls: {}
      priority: 90
      middlewares:
        - "rate-limit"
        - "mempool-secret-auth"

    # Internet — Frontend (Basic Auth)
    mempool:
      rule: "Host(`mempool.yourdomain.com`)"
      entryPoints: ["websecure"]
      service: mempool-service
      tls: {}
      middlewares:
        - "security-headers"
        - "rate-limit"
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

### Part 7 — Event-hub: relay Lightning donations over the internet (optional)

When mempaper runs outside the direct reach of your [LNbits](https://github.com/lnbits/lnbits)
server (e.g. the Pi is at home
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

#### Create a Zitadel application for event-hub

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
        - "security-headers"
        - "rate-limit"
```

> No OIDC middleware here — event-hub handles its own Zitadel login internally.
> `passHostHeader: true` is required: without it Traefik would forward the backend host to
> event-hub instead of `webhook.yourdomain.com`, breaking the auth callback URL that
> event-hub constructs. The `websocket-transport` (defined in `mempaper.yml`) keeps
> `/ws/{token}` connections alive indefinitely.

#### Create a webhook token

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

### Part 8 — Tang: network-bound encryption for wallet data (optional)

Everything mempaper encrypts on the Pi is protected by a key derived from the device
itself, so anyone holding the hardware can recompute it. That is fine against a copied
SD image and useless against physical theft. [Tang](https://github.com/latchset/tang) (the
server) and [Clevis](https://github.com/latchset/clevis) (the client that talks to it) fix
the theft case by keeping the key off the device: mempaper seals a random 256-bit key to a
Tang server on your LAN and can only unseal it while that server is reachable.

Carried off your network, the wallet data cannot be decrypted at all — not by guessing,
because there is nothing to guess. Recovery would require the Tang server's private key.

> **This protects a stolen device, not a compromised one.** Anyone with SSH or admin
> access on a running mempaper can simply ask it to unseal, exactly as the app does.
> Tang also cannot help while the thief is still on your LAN.

#### Do this before entering wallet data

**Enable Tang first, then add your xpubs.** Doing it in that order is the difference
between real protection and partial protection, and it costs nothing.

Deleting a file on an SD card does not erase it. Flash controllers do wear-levelling:
an updated file is written to fresh cells and the old ones are merely marked free, so
the previous contents stay physically present until those cells are reused. They remain
recoverable from the raw NAND, and a `dd` image copies them along with everything else.

So if you run for a while with addresses in clear text and enable Tang afterwards,
mempaper re-seals the live data but **cannot reach what was already committed to the
card**. Nothing in software can — that layer is owned by the controller.

If you are retrofitting Tang onto a device that already held wallet data:

| Option | Effect |
|---|---|
| Re-flash the card and set up with Tang enabled from the start | The only reliable erasure |
| `sudo fstrim /`, and enable `fstrim.timer` | Asks the controller to erase freed blocks — best effort, many cards ignore it |
| Do nothing | New data is sealed; the old plaintext may remain recoverable |

`install.sh` enables `fstrim.timer` automatically where the card supports it, and says so
when it does not.

#### What you need

An always-on host on the same LAN — a node, a NAS, or a small Proxmox LXC. Tang is
tiny: measured at **3.7 MiB RAM idle**, a 12 KB key store, and one short HTTP request
per unseal.

**Proxmox LXC sizing** (Debian 13, unprivileged, running Tang in Docker):

| Resource | Recommended | Minimum |
|---|---|---|
| CPU cores | 1 | 1 |
| RAM | 512 MB | 256 MB |
| Swap | 512 MB | 256 MB |
| Disk | 8 GB | 4 GB |

Almost all of that is the Docker daemon and the 87 MB image, not Tang. Running Tang
natively instead (`apt install tang && systemctl enable --now tangd.socket`) is simpler
in an LXC and fits comfortably in **256 MB RAM and 2 GB disk** — use that if you do not
already run containers on the host. The compose route below is worth it mainly if you
manage everything else on that host with compose.

#### `docker-compose.yml`

```yaml
services:
  tang:
    build: .
    image: mempaper-tang:latest
    container_name: tang
    restart: unless-stopped

    # Bind to the LAN interface only. Tang has no authentication by design -
    # reachability is the access control - so it must never be exposed to the
    # internet or forwarded through a router.
    ports:
      - "7500:7500"

    # The keys live here. Lose this volume and every sealed device loses its
    # wallet data permanently; back it up.
    volumes:
      - tang-keys:/var/lib/tang

    mem_limit: 128m
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true

    healthcheck:
      test: ["CMD", "sh", "-c", "socat -u OPEN:/dev/null TCP:127.0.0.1:7500 || exit 1"]
      interval: 60s
      timeout: 10s
      retries: 3
      start_period: 15s

volumes:
  tang-keys:
```

#### `Dockerfile`

```dockerfile
FROM debian:trixie-slim

# tang provides tangd and tangd-keygen; socat turns the inetd-style tangd
# into a TCP listener, which is what the upstream systemd unit does with
# socket activation. jose is only used to print key thumbprints at startup.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tang socat jose \
 && rm -rf /var/lib/apt/lists/*

VOLUME /var/lib/tang
EXPOSE 7500

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
```

#### `entrypoint.sh`

```sh
#!/bin/sh
# Start a Tang server, generating signing and exchange keys on first run.
set -eu

DB=${TANG_DB:-/var/lib/tang}
PORT=${TANG_PORT:-7500}
LIBEXEC=/usr/libexec

mkdir -p "$DB"

if [ -z "$(ls -A "$DB" 2>/dev/null)" ]; then
    echo "Generating Tang signing and exchange keys in $DB"
    "$LIBEXEC/tangd-keygen" "$DB"
fi

# tangd-keygen writes two keys: one for signing the advertisement and one for
# key exchange. clevis pins the signing key, so print only that one - printing
# both and leaving the choice to the reader is a coin flip, since the files are
# named after their thumbprints and sort arbitrarily.
echo "Pin this thumbprint in mempaper as tang_thumbprint:"
for jwk in "$DB"/*.jwk; do
    [ -e "$jwk" ] || continue
    if jose jwk use -i "$jwk" -r -u verify -o /dev/null 2>/dev/null; then
        printf '  %s\n' "$(jose jwk thp -i "$jwk")"
    fi
done

echo "Serving tangd on 0.0.0.0:$PORT (db=$DB)"
exec socat TCP-LISTEN:"$PORT",reuseaddr,fork,bind=0.0.0.0 EXEC:"$LIBEXEC/tangd $DB"
```

All three files are in [`deploy/tang/`](../deploy/tang/).

#### Start it and note the thumbprint

```bash
cd deploy/tang
docker compose up -d --build     # podman compose up -d --build works too
docker compose logs
```

```
Generating Tang signing and exchange keys in /var/lib/tang
Pin this thumbprint in mempaper as tang_thumbprint:
  Ik2_NDde06uwYnJxJl6llWFPzTtOO3PJFBwJsj7L9B8
Serving tangd on 0.0.0.0:7500 (db=/var/lib/tang)
```

Copy that thumbprint. Pinning it means mempaper verifies which server it is talking to
instead of trusting whatever answers on that address — without it, anything that can win
a race on your LAN could hand over its own key.

> `tangd-keygen` writes **two** keys, one for signing the advertisement and one for key
> exchange, but only the signing key's thumbprint is the one clevis pins. The entrypoint
> filters for it, and `tang-show-keys 7500` returns the same value.

#### Alternative: native install, no containers

Simpler in a Debian LXC, and what I would use if the host does not already run
containers. The two commands people usually quote are not sufficient on Debian — the
package ships **no keys** and the socket listens on **port 80**:

```bash
apt install tang

# 1. Generate the keys. The package ships none, and tangd serves nothing until
#    they exist. The directory differs by release - check which one your unit
#    actually reads rather than guessing:
#      Debian 13 (trixie):   /var/lib/tang
#      Debian 12 (bookworm): /var/db/tang
grep ExecStart /usr/lib/systemd/system/tangd@.service

/usr/libexec/tangd-keygen /var/lib/tang        # use the path printed above

# 2. Move off port 80 and bind to the LAN address.
systemctl edit tangd.socket
```

```ini
# The empty ListenStream= is required: it clears the inherited port 80 before
# the new values are added. Keep the loopback line - tang-show-keys hardcodes
# localhost, so binding only to the LAN address leaves local tools unable to
# reach a server that is in fact running fine.
[Socket]
ListenStream=
ListenStream=127.0.0.1:7500
ListenStream=192.168.1.50:7500
```

```bash
systemctl daemon-reload
systemctl restart tangd.socket        # restart, not just enable --now: systemd
systemctl enable tangd.socket         # warns that a changed socket needs one
systemctl status tangd.socket

# 3. Read the thumbprint to pin (this is the signing key, the value clevis wants)
tang-show-keys 7500
```

If you bound only to the LAN address, `tang-show-keys` fails with
`Failed to connect to localhost port 7500` even though the server is healthy.
Query it over the LAN address instead:

```bash
curl -sSf http://192.168.1.50:7500/adv \
  | jose fmt --json=- -g payload -y -o- \
  | jose jwk use -i- -r -u verify -o- \
  | jose jwk thp -i-
```

From here the verification steps and mempaper configuration below are identical —
substitute `systemctl stop tangd.socket` for `docker compose stop` when testing that
decryption fails.

To rotate keys later: `/usr/libexec/tangd-rotate-keys -d /var/lib/tang`. Rotation keeps
the old key readable so already-sealed devices keep working; it only stops the old key
being advertised for new seals.

#### Verify before pointing mempaper at it

```bash
curl -s http://tang-host-ip:7500/adv | head -c 100
```

A JSON advertisement means it is serving. To prove the protection actually works:

```bash
# Seal a test value, pinning the thumbprint
echo secret | clevis encrypt tang '{"url":"http://tang-host-ip:7500","thp":"PASTE-THUMBPRINT"}' > test.jwe

clevis decrypt < test.jwe        # -> secret

docker compose stop              # simulate the device leaving your network
clevis decrypt < test.jwe        # -> must FAIL: Error communicating with server

docker compose start
clevis decrypt < test.jwe        # -> secret, recovered automatically
```

The third command failing is the whole point. If it succeeds, the data is not protected.

#### Point mempaper at it

Tang is only the server half. It answers the key-exchange request and deliberately ships
no client, so the Pi needs **clevis**, the reference client that performs the exchange
and writes the sealed file:

```bash
sudo apt install clevis    # on the Pi, not the Tang host
```

Then in `config/config.json` on the Pi:

```json
{
  "tang_enabled": true,
  "tang_url": "http://tang-host-ip:7500",
  "tang_thumbprint": "UdzROszslgpklGvL0-9fDsayN1vXtzKTr-MJcBr0sCY"
}
```

Restart mempaper. Wallet data, the balance caches and the rendered images are re-sealed
under a key that no longer exists on the SD card.

#### Operational consequences — read before enabling

| Situation | Behaviour |
|---|---|
| Tang host down or LAN unreachable at boot | mempaper starts normally, wallet and donation blocks are disabled, the dashboard shows why |
| Tang host comes back | mempaper re-seals and restores those blocks automatically, no restart needed |
| `tang-keys` volume lost with no backup | **Sealed wallet data is unrecoverable.** Re-enter your xpubs |
| Device stolen, taken off your LAN | Sealed data cannot be decrypted |
| Tang enabled after xpubs were already saved | New writes are sealed; earlier plaintext may survive in freed flash blocks |
| Device stolen while still on your LAN | Not protected — Tang answers as normal |
| Attacker has SSH or admin access | Not protected — they can unseal exactly as mempaper does |

**Back up `tang-keys`.** It is 12 KB and it is the only copy of the key that unlocks
every device you have sealed.

> **The e-ink panel is bistable.** A stolen device is still physically displaying the
> last image, including any balance that was on it, with no power applied. No encryption
> changes that — if that matters to you, turn off the wallet block or enable OPSec mode.

---

### Security notes

| Topic | Detail |
|---|---|
| OIDC `Secret` | Signs the session cookie for **every** service behind the middleware, so whoever holds it can forge authenticated sessions for all of them — a worse exposure than the client secret. Generate with `openssl rand -hex 16`. Changing it logs everyone out, which is what you want after a leak. |
| Zitadel `ClientSecret` | Never commit to Git. Note that "use environment variables" is not directly possible here: Traefik's **file provider does not expand `${VAR}`** in dynamic configuration. Keep a `dynamic.yml.template` in Git and render the real file at deploy time (`envsubst`, sourcing a gitignored `.env`), or use Docker secrets. Pass an explicit variable list to `envsubst` so `${1}` in any `redirectRegex` survives. |
| Basic Auth hash | A hash, not the password — but generate it with `htpasswd -nbB` (bcrypt). The default `-nb` produces `$apr1$` MD5-crypt, which is cheap to crack offline if the file leaks. Keep it out of Git regardless. |
| `privacy-headers` | Suppresses `Referer` and search-engine indexing for private instances |
| `insecureSkipVerify: true` | Intentional: mempool's backend cert is self-signed on the LAN; Traefik handles public TLS |
| LAN bypass | Only works correctly if Traefik receives the real client IP — if a VPS or proxy sits in front, set `forwardedHeaders.trustedIPs` to its IP in `traefik.yml` |

> **Before every deployment**, review the pinned versions in your compose and config
> files against their upstream release pages for known CVEs and available patches.
> Deploy the latest **stable patch** of each component — not floating tags like `:latest`
> or minor-only pins like `:v3.7` that give you no control over what actually runs.
> Subscribe to release notifications for at least
> [traefik/traefik](https://github.com/traefik/traefik/releases),
> [traefik-oidc-auth](https://github.com/sevensolutions/traefik-oidc-auth/releases), and
> [zitadel/zitadel](https://github.com/zitadel/zitadel/releases) so you hear about
> security fixes before attackers do. The full component list is below.

---

### Upstream projects

Every version pinned in this guide was current when it was written and will not stay that
way. Nothing here is authoritative about the components themselves — go to the source
before you copy a config, and especially before you change one. Where this guide departs
from an upstream default it does so deliberately, and the last column says why, so you can
tell a hardening decision apart from a stale one when the upstream docs disagree.

| Component | Upstream | Documentation | Where this guide differs from defaults |
|---|---|---|---|
| Traefik | [traefik/traefik](https://github.com/traefik/traefik) | [doc.traefik.io](https://doc.traefik.io/traefik/) | Exact patch pin; no Docker socket mount; 60s responding timeouts; `forwardedHeaders.insecure: false`; `cap_drop: ALL` + `mem_limit` |
| traefik-oidc-auth (plugin) | [sevensolutions/traefik-oidc-auth](https://github.com/sevensolutions/traefik-oidc-auth) | [traefik-oidc-auth.sevensolutions.cc](https://traefik-oidc-auth.sevensolutions.cc/) | Secrets via `${file:…}` rather than inline; `CookieSecure`/`SameSite=lax`; 12h session timeout |
| Zitadel | [zitadel/zitadel](https://github.com/zitadel/zitadel) | [zitadel.com/docs/self-hosting](https://zitadel.com/docs/self-hosting/deploy/overview) | Postgres on an `internal: true` network; `--tlsMode disabled` behind Traefik only; role assertion enabled |
| PostgreSQL (image) | [docker-library/postgres](https://github.com/docker-library/postgres) | [hub.docker.com/_/postgres](https://hub.docker.com/_/postgres) | No published ports; healthcheck gate before Zitadel starts |
| LEGO (ACME client) | [go-acme/lego](https://github.com/go-acme/lego) | [go-acme.github.io/lego](https://go-acme.github.io/lego/) | Only as the alternative to Traefik's built-in resolver |
| docker-socket-proxy | [Tecnativa/docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy) | repo README | Recommended *instead of* a raw socket mount if you switch to the Docker provider |
| mempool | [mempool/mempool](https://github.com/mempool/mempool) | [mempool.space/docs](https://mempool.space/docs/api/rest) | `insecureSkipVerify` for the self-signed LAN cert; bcrypt Basic Auth with `removeHeader: true`; LAN bypass by `ClientIP()` |
| LNbits | [lnbits/lnbits](https://github.com/lnbits/lnbits) | [docs.lnbits.org](https://docs.lnbits.org/) | LNURLp pay link with comments enabled, webhook pointed at event-hub |
| LNURLp extension | [lnbits/lnurlp](https://github.com/lnbits/lnurlp) | in-app | — |
| event-hub | [satcat21/event-hub](https://github.com/satcat21/event-hub) | repo README | `passHostHeader: true`; own OIDC, so no Traefik OIDC middleware |
| Tang | [latchset/tang](https://github.com/latchset/tang) | [`tang(8)`](https://github.com/latchset/tang/blob/master/doc/tang.8.adoc) | Port 7500 instead of 80; LAN-bound socket; `read_only` container; keys generated explicitly (the Debian package ships none) |
| Clevis | [latchset/clevis](https://github.com/latchset/clevis) | [`clevis-encrypt-tang(1)`](https://github.com/latchset/clevis/blob/master/src/pins/tang/clevis-encrypt-tang.1.adoc) | Thumbprint always pinned — never a bare `url` |
| José (JWK tooling) | [latchset/jose](https://github.com/latchset/jose) | [`jose(1)`](https://github.com/latchset/jose/blob/master/doc/man/jose.1.adoc) | Used to filter for the *signing* key's thumbprint |
| socat | [socat homepage](http://www.dest-unreach.org/socat/) | [`socat(1)`](http://www.dest-unreach.org/socat/doc/socat.html) | Replaces systemd socket activation inside the Tang container |
| htpasswd (apache2-utils) | [apache/httpd](https://github.com/apache/httpd) | [`htpasswd`](https://httpd.apache.org/docs/current/programs/htpasswd.html) | `-B` (bcrypt), never the default `$apr1$` MD5-crypt |
