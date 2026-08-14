# Architecture Diagrams

Standalone SVGs used by [ARCHITECTURE.md](../ARCHITECTURE.md). Each one is
self-contained: styles are inlined, no external fonts or scripts, no `var()`
in presentation attributes. They render identically on GitHub, in an offline
clone, and in a Markdown preview.

## Index

| File | Used in | Shows |
|---|---|---|
| [`topology-public-mempool.svg`](topology-public-mempool.svg) | Topology A | Default setup — the public mempool.space sees your IP and every query |
| [`topology-vpn.svg`](topology-vpn.svg) | Topology B | VPN as a partial mitigation: the IP changes, the queries do not |
| [`topology-self-hosted.svg`](topology-self-hosted.svg) | Topology C | Self-hosted mempool on your own node — nothing leaves the LAN |
| [`topology-tor.svg`](topology-tor.svg) | Topology D | mempool.space reached over Tor via its onion service |
| [`topology-tang-sealed.svg`](topology-tang-sealed.svg) | Topology E, and [Self-Hosting Guide](../SELF_HOSTING_GUIDE.md) Part 8 | Self-hosted mempool plus storage sealed to a Tang server — the key is off the device |
| [`fee-color-scale.svg`](fee-color-scale.svg) | [README](../../README.md) and [Config Reference](../CONFIG_REFERENCE.md#block-height-color-scale) | How the block-height colour is anchored to the rolling median fee, so the same sat/vB reads differently in different fee regimes |
| [`privacy-options-ranked.svg`](privacy-options-ranked.svg) | Summary | The four topologies ordered by privacy strength |
| [`latency-and-reliability.svg`](latency-and-reliability.svg) | Pros and cons | What Tor costs in round-trip time, and why it rarely matters here |
| [`mempool-host-dominance.svg`](mempool-host-dominance.svg) | What leaves the device | Why `mempool_host` is the single setting that decides exposure |
| [`codebase-component-map.svg`](codebase-component-map.svg) | Codebase map | Four layers: adapters, orchestrator, renderer, sinks |
| [`block-to-image-dataflow.svg`](block-to-image-dataflow.svg) | From new block to new image | Speculative pre-render, and the fan-out that never blocks the browser |
| [`topology-remote-access-oidc.svg`](topology-remote-access-oidc.svg) | Remote access | Traefik + Zitadel OIDC in front of the dashboard |

Every SVG in this directory is embedded in ARCHITECTURE.md, and some are reused
in other docs — the "Used in" column above is the full list of embed sites. If
you add one, add its row here; if you remove one, remove every embed too — an
unreferenced diagram is the kind of thing that silently rots.

## Editing

Edit the SVG directly; there is no build step. Two things bite:

- **A `<path>` with no `fill:none`** renders as a filled shape, not a line. This
  is the usual cause of a stray black bar appearing in a diagram.
- **CSS rules beat presentation attributes.** If a shape ignores its `fill=`
  attribute, something in the inline `<style>` block is overriding it.

After editing, open the file in a browser at a narrow window width — the
diagrams are embedded at `max-width: 100%` and text must not overflow its
containing shape when scaled down.
