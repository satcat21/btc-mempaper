#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Persistent e-paper display worker process.

Stays alive between display operations so the Python interpreter, Waveshare
drivers and GPIO libraries are only initialised once, saving ~10s per block.

Protocol (newline-delimited JSON over stdin/stdout):
  Startup:   worker writes {"status": "ready"}
  Command:   caller writes {"image_path": "cache/current_eink.png"}
  Result:    worker writes {"success": true}  or  {"success": false, "error": "..."}
"""

import sys
import os
import json
import traceback


def main():
    # Import display module once at startup (this is where the ~10s cost lives)
    from display.waveshare_display import WaveshareDisplay
    from managers.config_manager import ConfigManager

    config = ConfigManager().config
    display = WaveshareDisplay(config=config)

    sys.stdout.write(json.dumps({"status": "ready"}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"success": False, "error": "invalid_json"}) + "\n")
            sys.stdout.flush()
            continue

        if cmd.get("action") == "quit":
            break

        image_path = cmd.get("image_path")
        if not image_path:
            sys.stdout.write(json.dumps({"success": False, "error": "no_image_path"}) + "\n")
            sys.stdout.flush()
            continue

        try:
            success = display.display_image(image_path)
            sys.stdout.write(json.dumps({"success": bool(success)}) + "\n")
        except Exception as e:
            sys.stdout.write(json.dumps({
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
