"""
Disk cache for the WebP-SIGILL subprocess probes.

lib/image_renderer.py and mempaper_app.py each spawn a subprocess at import
time to check whether this machine's Pillow/libwebp build SIGILLs on WebP
encode/decode (a known issue on ARMv6 with NEON-compiled libwebp). That's a
fixed property of the installed Pillow build, not something that changes
between process restarts, so re-running the probe on every boot/restart
wastes several seconds for no reason. This caches the result to disk, keyed
on Pillow's version so an upgrade automatically invalidates it.
"""

import json
import os

_CACHE_PATH = os.path.join('cache', 'webp_probe.json')


def cached_probe(key: str, probe_fn) -> bool:
    """Return the cached bool for *key*, running and caching probe_fn() if needed."""
    try:
        import PIL
        pil_version = PIL.__version__
    except Exception:
        pil_version = None

    try:
        with open(_CACHE_PATH) as f:
            data = json.load(f)
    except Exception:
        data = {}

    if data.get('pil_version') == pil_version and key in data:
        return data[key]

    result = probe_fn()

    if data.get('pil_version') != pil_version:
        data = {'pil_version': pil_version}
    data[key] = result

    try:
        os.makedirs(os.path.dirname(_CACHE_PATH) or '.', exist_ok=True)
        with open(_CACHE_PATH, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass

    return result
