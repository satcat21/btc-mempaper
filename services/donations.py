"""Lightning donation state: loading and saving history, selecting the one to
display, and the webhook-relay listener that receives new events.
"""

from utils.atomic_io import atomic_write_json
import json
import os
import threading


class DonationsMixin:
    """Lightning donation state: loading and saving history, selecting the one to"""

    def _load_donations(self):
        """Load persisted donation history from disk on startup."""
        try:
            if os.path.exists(self._donations_file):
                # read_file opens a sealed file and passes a clear-text one
                # straight through, so a history written before Tang was
                # enabled still loads.
                store = getattr(self, 'tang_store', None)
                if store is not None and store.is_enabled():
                    raw = store.read_file(self._donations_file)
                    data = json.loads(raw.decode('utf-8')) if raw else {}
                else:
                    with open(self._donations_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                self._donation_history = data.get("history", [])
                self._latest_donation = self._donation_history[0] if self._donation_history else None
                if self._donation_history:
                    self._highest_donation = None
                    for d in reversed(self._donation_history):
                        if (self._highest_donation is None or
                                d.get("amount_sats", 0) > self._highest_donation.get("amount_sats", 0)):
                            self._highest_donation = d
                self._latest_donation_block_height = data.get("latest_donation_block_height", None)
                print(f"⚡ Loaded {len(self._donation_history)} donation(s) from {self._donations_file}")
        except Exception as e:
            print(f"⚠️ Could not load donations file: {e}")

    def _get_active_donation(self):
        """Return the donation to display based on donation_display_mode config.

        Modes:
          latest  — always show the most-recent donation.
          highest — always show the all-time largest donation.
          auto    — show latest for 432 blocks after the last donation; fall back
                    to highest when 432 blocks have passed without a new donation.

        The returned dict always includes:
          _guaranteed — True for the first 144 blocks after the latest donation
                        (renderer pre-reserves space and shows unconditionally).
                        False afterwards (block competes with others for space).
        """
        mode = self.config.get("donation_display_mode", "latest")

        # Within 144 blocks (~24h) of the last received donation: guarantee display
        guaranteed = False
        if (self._latest_donation is not None
                and self._latest_donation_block_height is not None
                and self.current_block_height is not None):
            try:
                blocks_since = int(self.current_block_height) - int(self._latest_donation_block_height)
                guaranteed = blocks_since <= 144
            except (TypeError, ValueError):
                guaranteed = True  # safe default when comparison fails

        def _tag(d):
            if d is None:
                return None
            d = dict(d)
            d["_guaranteed"] = guaranteed
            return d

        if mode == "highest":
            return _tag(self._highest_donation)
        if mode == "auto":
            if self._latest_donation is None:
                d = self._highest_donation
                effective = "highest"
            else:
                donation_bh = self._latest_donation_block_height
                current_bh = self.current_block_height
                if donation_bh is None or current_bh is None:
                    d = self._latest_donation
                    effective = "latest"
                else:
                    try:
                        blocks_since = int(current_bh) - int(donation_bh)
                    except (TypeError, ValueError):
                        d = self._latest_donation
                        effective = "latest"
                    else:
                        if blocks_since <= 432:
                            d = self._latest_donation
                            effective = "latest"
                        else:
                            d = self._highest_donation
                            effective = "highest"
            if d is not None:
                d = dict(d)
                d["_effective_mode"] = effective
                d["_guaranteed"] = guaranteed
            return d
        # default: "latest"
        return _tag(self._latest_donation)

    def _save_donations(self):
        """Persist donation history to disk, sealed when Tang is enabled.

        Amounts and donor comments say something about who is behind the
        device, so this belongs in the sealed set rather than beside the
        public chain data.
        """
        payload = {
            "history": self._donation_history,
            "latest_donation_block_height": self._latest_donation_block_height,
        }
        store = getattr(self, 'tang_store', None)
        try:
            if store is not None and store.is_enabled():
                # Sealed writes go through the store, which refuses while the
                # Tang server is unreachable rather than silently producing
                # clear text. Losing one donation update is recoverable; a
                # plaintext history on a stolen card is not.
                store.write_file(
                    self._donations_file,
                    json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8'),
                    mode=0o600,
                )
            else:
                atomic_write_json(self._donations_file, payload,
                                  ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save donations file: {e}")

    def _process_donation_payload(self, data: dict):
        """Parse a raw LNbits payment payload and trigger display + socket updates."""
        from datetime import datetime as _dt

        # LNbits sends amount in millisatoshis.
        # For LNURL-pay the user's comment is in extra.comment (not memo).
        amount_msats = data.get("amount", 0)
        amount_sats = max(1, round(amount_msats / 1000)) if amount_msats else 0
        extra = data.get("extra") or {}
        message = (
            extra.get("comment")
            or extra.get("description")
            or data.get("memo")
            or data.get("comment")
            or ""
        ).strip()

        donation = {
            "amount_sats": amount_sats,
            "message": message,
            "timestamp": _dt.utcnow().isoformat(),
            "block_height": self.current_block_height,
        }
        self._latest_donation = donation
        self._donation_history.insert(0, donation)
        if (self._highest_donation is None or
                amount_sats > self._highest_donation.get("amount_sats", 0)):
            self._highest_donation = donation
        # Record block height for the "auto" display-mode countdown.
        self._latest_donation_block_height = self.current_block_height
        self._save_donations()

        print(f"⚡ Donation received: {amount_sats} sats — \"{message}\" (block height: {self._latest_donation_block_height})")

        if self.socketio:
            self.socketio.emit('donation_received', donation, room='authenticated')

        # Refresh the display if the donation block is enabled
        if self.config.get("show_donation_block", False):
            self.image_renderer._donation_data = self._get_active_donation()
            self.image_is_current = False
            # Invalidate pre-render so next block shows updated donation
            self._invalidate_prerender()
            threading.Thread(
                target=self._background_image_generation,
                kwargs={"force_eink": True, "use_cached_block": True, "force_new_meme": True},
                daemon=True
            ).start()

    def _start_webhook_site_listener(self):
        """Start a background thread that connects to a webhook relay via WebSocket.

        The thread reconnects automatically with exponential back-off whenever
        the connection drops.  Call _restart_webhook_site_listener() to force an
        immediate reconnect with a new URL (e.g. after config change).
        """
        import websocket as _ws

        self._webhook_site_wake = threading.Event()  # set to interrupt sleep
        self._webhook_site_ws = None                 # current WebSocketApp (for close on restart)

        def _run():
            # Wait for the startup Wi-Fi check to finish (connected or fell back to
            # setup hotspot) before the very first connect attempt — avoids a
            # guaranteed-to-fail DNS lookup (which itself blocks for several seconds
            # before failing) competing for CPU with other boot-time work while Wi-Fi
            # is still down. Only gates the first attempt; reconnects after a real
            # drop later use the existing backoff below, unaffected by this.
            self._startup_wifi_check_done.wait(timeout=90)

            backoff = 5
            while True:
                self._webhook_site_wake.clear()
                url = self.config.get("webhook_relay_ws_url", "").strip()
                if not url:
                    # No URL — wait up to 30 s or until woken by a config change
                    self._webhook_site_wake.wait(timeout=30)
                    continue

                print(f"⚡ webhook relay listener: connecting to {url}")

                def _on_message(ws, raw):
                    try:
                        outer = json.loads(raw)
                        # Check for payload field first (webhook relay format), then content/body
                        data = outer.get("payload")
                        if not data:
                            content = outer.get("content") or outer.get("body") or ""
                            data = json.loads(content) if content and isinstance(content, str) else content
                        print(f"⚡ webhook relay event — data: {str(data)[:300]!r}")
                        self._process_donation_payload(data)
                    except Exception as e:
                        print(f"⚠️ webhook relay parse error: {e} — raw: {raw[:200]!r}")

                def _on_open(ws):
                    backoff_ref[0] = 5  # reset back-off on successful connect
                    print("✅ webhook relay WebSocket connected")

                def _on_error(ws, err):
                    print(f"⚠️ webhook relay WebSocket error: {err}")

                def _on_close(ws, code, msg):
                    print(f"⚡ webhook relay WebSocket closed (code={code})")

                backoff_ref = [backoff]
                try:
                    ws = _ws.WebSocketApp(
                        url,
                        on_open=_on_open,
                        on_message=_on_message,
                        on_error=_on_error,
                        on_close=_on_close,
                    )
                    self._webhook_site_ws = ws
                    ws.run_forever(ping_interval=30, ping_timeout=10)
                except Exception as e:
                    print(f"⚠️ webhook relay listener exception: {e}")
                finally:
                    self._webhook_site_ws = None

                backoff = backoff_ref[0]
                # Wait before reconnecting, but allow early wake on URL change
                print(f"⚡ webhook relay listener: reconnecting in {backoff} s…")
                self._webhook_site_wake.wait(timeout=backoff)
                backoff = min(backoff * 2, 60)

        threading.Thread(target=_run, name="webhook-relay-listener", daemon=True).start()
        print("⚡ webhook relay listener thread started")

    def _restart_webhook_site_listener(self):
        """Force an immediate reconnect (e.g. after the WebSocket URL changes in config)."""
        ws = getattr(self, '_webhook_site_ws', None)
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        wake = getattr(self, '_webhook_site_wake', None)
        if wake:
            wake.set()  # interrupt any sleep
