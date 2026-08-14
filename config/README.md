# config/

| File | What it is |
| :--- | :--- |
| `config.json` | The live configuration. Created from `config.json.example` on install |
| `config.json.example` | The shipped defaults, copied verbatim by `install.sh` |
| `config.sensitive.json` | Wallet addresses, admin users, secrets. Sealed when Tang is on |
| `.config_key` | Device key for the sensitive half. Never copy it off the device |

## Every setting is documented in [../docs/CONFIG_REFERENCE.md](../docs/CONFIG_REFERENCE.md)

Description, type, default and accepted values for every key, grouped the way
the web UI groups them. The **Advanced (file-only)** section at the end covers
the keys with no web UI field — the ones you can only set here.

The documentation lives there rather than in comments beside each key because
`config.json` is strict JSON: a `//` line stops mempaper from starting, and
saving anything in the web dashboard rewrites this whole file from memory,
so a comment would not survive the first settings change anyway.

## Editing by hand

```bash
sudo systemctl stop mempaper
sudo -u mempaper nano /home/mempaper/btc-mempaper/config/config.json
sudo systemctl start mempaper
```

Stop the service first. It rewrites `config.json` whenever a setting is saved in
the dashboard, and it watches the file while running, so an edit made under a
running service can be reloaded half-written or overwritten outright.

A value that fails validation is dropped silently and the default applies — check
that a change took effect instead of assuming it did:

```bash
journalctl -u mempaper.service --since "-2 min"
```

The web dashboard is the recommended way to change anything it exposes. It
validates as you type and restarts the parts that need restarting.
