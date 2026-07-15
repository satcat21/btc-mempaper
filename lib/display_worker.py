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
import atexit
import signal


def main():
    # Import display module once at startup (this is where the ~10s cost lives)
    from display.waveshare_display import WaveshareDisplay
    from managers.config_manager import ConfigManager

    config = ConfigManager().config
    display = WaveshareDisplay(config=config)

    def _cleanup():
        try:
            display.cleanup()
        except Exception:
            pass

    atexit.register(_cleanup)

    def _sigterm_handler(signum, frame):
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sigterm_handler)

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
            if success:
                sys.stdout.write(json.dumps({"success": True}) + "\n")
            else:
                # Display returned False - no exception but failed
                sys.stderr.write("Display returned False (check hardware/connection)\n")
                sys.stdout.write(json.dumps({
                    "success": False,
                    "error": "Display hardware returned False (check connection/power)"
                }) + "\n")
        except Exception as e:
            error_msg = str(e)
            tb = traceback.format_exc()
            # Log to stderr for debugging
            sys.stderr.write(f"Display exception: {error_msg}\n")
            sys.stderr.write(tb)
            # Return error via stdout JSON
            sys.stdout.write(json.dumps({
                "success": False,
                "error": error_msg,
                "traceback": tb,
            }) + "\n")
        sys.stdout.flush()
        sys.stderr.flush()


if __name__ == "__main__":
    main()
