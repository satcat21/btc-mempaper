// Form-level input validation: addresses, xpubs, SSH keys, colours,
// plus address masking and the wallet-balance privacy toggle.
// Part 1 of 8, split from config.js. Load order matters:
// these run as classic scripts sharing one global scope.

function _formatDonationTime(timestamp) {
    if (!timestamp) return '—';
    const d = new Date(timestamp + 'Z');
    const dateStr = d.toLocaleDateString();
    const timeStr = d.toLocaleTimeString();
    return `<span class="donation-time-date">${dateStr},</span> <span class="donation-time-clock">${timeStr}</span>`;
}

// ── Form-level input validation ───────────────────────────────
// Shared regexes
const _RE_IPV4        = /^\d{1,3}(\.\d{1,3}){3}$/;
const _RE_SSH_KEY     = /^(ssh-ed25519|ssh-rsa|ssh-dss|ecdsa-sha2-nistp(?:256|384|521)|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)\s+[A-Za-z0-9+/]+=*(\s+\S.*)?$/;
// Bitcoin address (P2PKH, P2SH, bech32/taproot) OR extended pub key (xpub/zpub/ypub/…)
const _RE_BTC_OR_XPUB = /^([13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{6,87}|[a-zA-Z]{1,4}pub[a-km-zA-HJ-NP-Z1-9]{100,120})$/;
// Block-reward monitoring accepts plain addresses only (no xpub/zpub)
const _RE_BTC_ADDR    = /^([13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{6,87})$/;
const _RE_HEX_COLOR   = /^#[0-9A-Fa-f]{6}$/;

// ── Checksum validation for Bitcoin addresses / xpub-ypub-zpub ─────────────
const _B58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';

// Decode a base58 string into its raw bytes (no checksum stripping). Returns
// null if the string contains characters outside the base58 alphabet.
function _base58Decode(str) {
    let num = 0n;
    for (const ch of str) {
        const idx = _B58_ALPHABET.indexOf(ch);
        if (idx === -1) return null;
        num = num * 58n + BigInt(idx);
    }
    let hex = num.toString(16);
    if (hex.length % 2) hex = '0' + hex;
    const bytes = [];
    if (num > 0n) {
        for (let i = 0; i < hex.length; i += 2) bytes.push(parseInt(hex.substr(i, 2), 16));
    }
    let leadingZeros = 0;
    for (const ch of str) { if (ch === '1') leadingZeros++; else break; }
    return new Uint8Array([...new Array(leadingZeros).fill(0), ...bytes]);
}

async function _sha256(bytes) {
    return new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
}

// Verify a base58check-encoded string (legacy P2PKH/P2SH addresses, and
// xpub/ypub/zpub/… extended keys all use this scheme): last 4 bytes must equal
// the first 4 bytes of SHA256(SHA256(payload)).
async function _isValidBase58Check(str) {
    const decoded = _base58Decode(str);
    if (!decoded || decoded.length < 5) return false;
    const payload = decoded.slice(0, -4);
    const checksum = decoded.slice(-4);
    const hash = await _sha256(await _sha256(payload));
    for (let i = 0; i < 4; i++) if (hash[i] !== checksum[i]) return false;
    return true;
}

// Bech32 (BIP-173) / Bech32m (BIP-350) checksum verification for bc1… segwit
// addresses — a different, non-hash-based checksum scheme from base58check,
// so it needs its own implementation. Reference algorithm from the BIPs.
const _BECH32_CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';

function _bech32Polymod(values) {
    const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
    let chk = 1;
    for (const v of values) {
        const b = chk >>> 25;
        chk = ((chk & 0x1ffffff) << 5) ^ v;
        for (let i = 0; i < 5; i++) if ((b >>> i) & 1) chk ^= GEN[i];
    }
    return chk >>> 0;
}

function _bech32HrpExpand(hrp) {
    const ret = [];
    for (let i = 0; i < hrp.length; i++) ret.push(hrp.charCodeAt(i) >> 5);
    ret.push(0);
    for (let i = 0; i < hrp.length; i++) ret.push(hrp.charCodeAt(i) & 31);
    return ret;
}

function _isValidBech32(addr) {
    const lower = addr.toLowerCase();
    if (addr !== lower && addr !== addr.toUpperCase()) return false; // mixed case not allowed
    const pos = lower.lastIndexOf('1');
    if (pos < 1 || pos + 7 > lower.length) return false;
    const hrp = lower.substring(0, pos);
    const data = [];
    for (const ch of lower.substring(pos + 1)) {
        const idx = _BECH32_CHARSET.indexOf(ch);
        if (idx === -1) return false;
        data.push(idx);
    }
    const values = _bech32HrpExpand(hrp).concat(data);
    const polymod = _bech32Polymod(values);
    return polymod === 1 || polymod === 0x2bc830a3; // bech32 (v0) or bech32m (v1+/taproot)
}

// Combined format + checksum check. Returns true (fully valid), false (fails
// the basic shape check), or 'checksum' (right shape, wrong checksum — most
// often a typo) so callers can show a more specific error message.
async function _checkBtcKeyOrAddress(val, formatRegex) {
    if (!formatRegex.test(val)) return false;
    const checksumOk = val.startsWith('bc1') ? _isValidBech32(val) : await _isValidBase58Check(val);
    return checksumOk ? true : 'checksum';
}

async function _isValidBtcAddressOrXpub(val) { return _checkBtcKeyOrAddress(val, _RE_BTC_OR_XPUB); }
async function _isValidBtcAddress(val)       { return _checkBtcKeyOrAddress(val, _RE_BTC_ADDR); }

// Set of currently-invalid input elements (auto-cleaned when element leaves DOM)
const _invalidInputs = new Set();

function _validationMsg(validator) {
    const t = window.translations || {};
    if (validator === _RE_SSH_KEY)             return t.validation_ssh_key     || 'Invalid SSH public key (expected: ssh-ed25519 AAAA… or ssh-rsa AAAA…)';
    if (validator === _RE_IPV4)                return t.validation_ipv4        || 'Invalid IP address (expected: 192.168.x.x)';
    if (validator === _RE_BTC_OR_XPUB
        || validator === _isValidBtcAddressOrXpub) return t.validation_btc_or_xpub || 'Invalid Bitcoin address or extended public key (xpub / zpub)';
    if (validator === _RE_BTC_ADDR
        || validator === _isValidBtcAddress)   return t.validation_btc_addr    || 'Invalid Bitcoin address';
    if (validator === _RE_HEX_COLOR)           return t.validation_hex_color   || 'Invalid color (expected: #RRGGBB)';
    return t.validation_invalid || 'Invalid value';
}

function _scrollToFirstError() {
    for (const el of _invalidInputs) {
        if (document.contains(el)) {
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => el.focus(), 300);
            return;
        }
    }
}

function _updateFormValidity() {
    for (const el of _invalidInputs) {
        if (!document.contains(el)) _invalidInputs.delete(el);
    }
    const hasErrors = _invalidInputs.size > 0;
    document.querySelectorAll('#desktop-save-button, #mobile-save-button').forEach(btn => {
        // Use a CSS class instead of disabled so click events still fire for scroll-to-error
        btn.classList.toggle('save-blocked-by-validation', hasErrors);
    });
}

function _applyValidationResult(el, valid, msg) {
    el.classList.toggle('input-invalid', !valid);

    // Find or create the error message span that lives right after the input
    let errEl = el.nextElementSibling;
    if (!errEl || !errEl.classList.contains('input-error-msg')) {
        errEl = document.createElement('span');
        errEl.className = 'input-error-msg';
        el.insertAdjacentElement('afterend', errEl);
    }
    errEl.textContent = valid ? '' : msg;
    errEl.hidden = valid;

    if (valid) { _invalidInputs.delete(el); } else { _invalidInputs.add(el); }
    _updateFormValidity();
}

// Mark an input valid or invalid; pass allowEmpty=true to treat empty value as valid.
// `validator` is either a RegExp (tested synchronously — format-only checks) or an
// async function `(val) => Promise<true|false|'checksum'>` for checks that need real
// crypto (base58check / bech32 checksum verification), which resolves the input's
// valid/invalid state shortly after typing rather than blocking the keystroke.
// 'checksum' means the shape matched but the checksum didn't — usually a typo.
function _validateInput(el, validator, allowEmpty = true) {
    const val = el.value.trim();
    if (val === '') {
        _applyValidationResult(el, allowEmpty, _validationMsg(validator));
        return allowEmpty;
    }
    if (validator instanceof RegExp) {
        const valid = validator.test(val);
        _applyValidationResult(el, valid, _validationMsg(validator));
        return valid;
    }
    // Async validator — apply the result once the checksum check resolves.
    const t = window.translations || {};
    validator(val).then(result => {
        const valid = result === true;
        const msg = result === 'checksum'
            ? (t.validation_checksum || 'Checksum does not match — please check for typos')
            : _validationMsg(validator);
        _applyValidationResult(el, valid, msg);
    });
    return true; // optimistic pending state; _invalidInputs updates once resolved
}

// Auto-trim on blur — pasted keys/addresses often carry a trailing space or
// newline from the clipboard, which shouldn't affect validation or matter for
// saving. Re-fires 'input' so validation and dirty-state tracking re-run
// against the cleaned-up value.
function _trimOnBlur(el) {
    el.addEventListener('blur', () => {
        const trimmed = el.value.trim();
        if (el.value !== trimmed) {
            el.value = trimmed;
            el.dispatchEvent(new Event('input', { bubbles: true }));
        }
    });
}

function _createMaskIcon(iconPath, size = 16) {
    const el = document.createElement('span');
    el.className = 'themed-mask-icon';
    el.style.width = size + 'px';
    el.style.height = size + 'px';
    el.style.webkitMaskImage = `url('${iconPath}')`;
    el.style.maskImage = `url('${iconPath}')`;
    return el;
}

// ── Address privacy masking ────────────────────────────────────────────────
// Shows a "zpub6r****…****roaa" preview over an address/xpub input while it
// isn't focused, so a sensitive value isn't fully visible at a glance while
// scrolling or screen-sharing — clicking it reveals the full value for
// editing.
const _MASK_PREFIX_LEN = 6;
const _MASK_SUFFIX_LEN = 2;
const _MASK_MIN_STARS = 3;

// Measures the real rendered width (px) of one monospace character
const _monoCharWidthCache = {};
function _monoCharWidthPx(referenceEl) {
    const cs = getComputedStyle(referenceEl);
    const fontKey = `${cs.fontSize} ${cs.fontFamily}`;
    if (_monoCharWidthCache[fontKey]) return _monoCharWidthCache[fontKey];
    if (!_monoCharWidthPx._canvas) _monoCharWidthPx._canvas = document.createElement('canvas');
    const ctx = _monoCharWidthPx._canvas.getContext('2d');
    ctx.font = fontKey;
    const width = ctx.measureText('0').width || 8;
    _monoCharWidthCache[fontKey] = width;
    return width;
}

// Builds the masked preview, sizing the run of '*' to fill however much of
// the column is actually available
function _maskAddressPreview(val, availableWidthPx, fontReferenceEl) {
    const minLen = _MASK_PREFIX_LEN + _MASK_SUFFIX_LEN + _MASK_MIN_STARS;
    if (!val || val.length <= minLen) return val; // too short to usefully mask

    const hiddenLen = val.length - _MASK_PREFIX_LEN - _MASK_SUFFIX_LEN;
    let starCount = hiddenLen; // fallback if width can't be measured: show it all
    if (availableWidthPx > 0 && fontReferenceEl) {
        const charWidth = _monoCharWidthPx(fontReferenceEl);
        if (charWidth > 0) {
            const maxChars = Math.floor(availableWidthPx / charWidth);
            starCount = maxChars - _MASK_PREFIX_LEN - _MASK_SUFFIX_LEN;
        }
    }
    starCount = Math.max(_MASK_MIN_STARS, Math.min(starCount, hiddenLen));

    return val.slice(0, _MASK_PREFIX_LEN) + '*'.repeat(starCount) + val.slice(-_MASK_SUFFIX_LEN);
}

function _addAddressMaskOverlay(inputEl) {
    const wrapper = document.createElement('span');
    wrapper.style.cssText = 'position:relative; display:block;';
    inputEl.parentNode.insertBefore(wrapper, inputEl);
    wrapper.appendChild(inputEl);

    const overlay = document.createElement('span');
    overlay.className = 'address-mask-overlay';
    overlay.style.cssText = `
        position: absolute; inset: 0; display: none; align-items: center;
        padding: 7px; font-family: var(--font-mono, monospace); font-size: 0.85rem;
        color: var(--text-primary); background: var(--bg-input);
        border-radius: var(--radius-sm); cursor: text;
        white-space: nowrap; overflow: hidden; text-overflow: clip;
    `;
    overlay.title = window.translations?.click_to_reveal || 'Click to view/edit the full value';

    function updateOverlay() {
        const val = inputEl.value.trim();
        if (val) {
            // inputEl stays laid out (only the overlay itself toggles display),
            // so its clientWidth is a reliable stand-in for the overlay's own
            // width even while the overlay is currently hidden. Subtract the
            // overlay's own left+right padding (7px each) to get the actual
            // space available for text.
            const availablePx = inputEl.clientWidth - 14;
            overlay.textContent = _maskAddressPreview(val, availablePx, overlay);
        } else {
            overlay.textContent = '';
        }
        overlay.style.display = (!val || document.activeElement === inputEl) ? 'none' : 'flex';
    }

    inputEl.addEventListener('input', updateOverlay);
    inputEl.addEventListener('blur', updateOverlay);
    inputEl.addEventListener('focus', () => { overlay.style.display = 'none'; });
    overlay.addEventListener('click', () => inputEl.focus());

    // Re-measure when the column width actually changes (window resize,
    // orientation change, sidebar toggle, etc.) so the star count stays
    // matched to the available space rather than the width at creation time.
    if (typeof ResizeObserver !== 'undefined') {
        new ResizeObserver(updateOverlay).observe(wrapper);
    } else {
        window.addEventListener('resize', updateOverlay);
    }

    // Code elsewhere that sets inputEl.value directly (e.g. populating a
    // pre-created empty row from cached data) doesn't fire an 'input' event,
    // so the overlay wouldn't otherwise notice the new value — expose a manual
    // refresh hook for those call sites.
    inputEl._refreshAddressMask = updateOverlay;

    wrapper.appendChild(overlay);
    updateOverlay();
}

// ── Wallet balance privacy toggle ───────────────────────────────────────────
// One global on/off switch (persisted across reloads) covering every balance
// figure in the wallet table, regardless of which code path last wrote it
// (initial render, cached-balance load, or a live websocket update) — all of
// them go through _setWalletBalanceText so a single toggle keeps them in sync.
window._walletBalancesHidden = localStorage.getItem('mempaper_hide_wallet_balances') === '1';

function _setWalletBalanceText(el, formattedValue) {
    el.dataset.realValue = formattedValue;
    el.textContent = window._walletBalancesHidden ? '******' : formattedValue;
}

function _refreshAllWalletBalanceDisplays() {
    document.querySelectorAll('.wallet-balance-display').forEach(el => {
        if (el.dataset.realValue !== undefined) {
            el.textContent = window._walletBalancesHidden ? '******' : el.dataset.realValue;
        }
    });
}

function _toggleWalletBalanceVisibility(iconEl) {
    window._walletBalancesHidden = !window._walletBalancesHidden;
    localStorage.setItem('mempaper_hide_wallet_balances', window._walletBalancesHidden ? '1' : '0');
    _refreshAllWalletBalanceDisplays();
    if (iconEl) {
        const newIconPath = window._walletBalancesHidden ? '/static/icons/visibility_off.svg' : '/static/icons/visibility.svg';
        iconEl.style.webkitMaskImage = `url('${newIconPath}')`;
        iconEl.style.maskImage = `url('${newIconPath}')`;
        iconEl.title = window._walletBalancesHidden
            ? (window.translations?.show_balances || 'Show balances')
            : (window.translations?.hide_balances || 'Hide balances');
    }
}

// Intercept clicks on the save buttons when validation errors exist.
// Registered in capture phase so it fires before the save handler.
function _setupValidationClickInterceptor() {
    document.querySelectorAll('#desktop-save-button, #mobile-save-button').forEach(btn => {
        btn.addEventListener('click', (e) => {
            // Clean stale entries first
            for (const el of _invalidInputs) {
                if (!document.contains(el)) _invalidInputs.delete(el);
            }
            if (_invalidInputs.size > 0) {
                e.stopImmediatePropagation();
                e.preventDefault();
                _scrollToFirstError();
                const t = window.translations || {};
                const firstErrEl = [..._invalidInputs].find(el => document.contains(el))
                    ?.nextElementSibling;
                const detail = (firstErrEl && firstErrEl.classList.contains('input-error-msg'))
                    ? firstErrEl.textContent : '';
                _buildLiveToast(
                    [_toastIcon('error', 'error'),
                        ' ' + (t.validation_save_blocked_title || 'Fix invalid fields before saving')],
                    [detail || (t.validation_save_blocked_body || 'One or more fields have invalid values.')],
                    '#ef4444', 6000
                );
            }
        }, true /* capture phase */);
    });
}

// ── End form-level validation ─────────────────────────────────

// Preload SVG icons that are only referenced via JS (mask-image set dynamically).
// Without this the browser lazy-fetches them on first use, causing a visible delay.
fetch('/static/icons/check.svg').catch(() => {});
fetch('/static/icons/add.svg').catch(() => {});

// Reload after a service restart, persisting enough state so the new page can
// show the right toast: a software update takes priority (its own toast already
// names the version — no need for a second one); otherwise tell the user whether
// this was a full reboot (new boot_id) or just a same-boot service restart, since
// only a reboot reliably pushes an e-ink refresh, and either can be triggered from
// the CLI as much as from this page's buttons.
function _reloadAfterRestart(tag, isReboot) {
    if (tag) {
        sessionStorage.setItem('mempaper_updated_to', tag);
    } else {
        sessionStorage.setItem('mempaper_action_done', isReboot ? 'reboot' : 'restart');
    }
    location.reload();
}

// Rebuild HTML for info_text fields that contain multiple translation strings.
// Called from setLanguage() so the HTML reflects the newly selected language.
function _buildInfoHtml(builder, t) {
    if (builder === 'donation_webhook') {
        const title  = t['webhook_options_title']      || 'Choose how to receive donations:';
        const aTitle = t['webhook_option_a_title']     || 'Option A — Direct webhook';
        const aSub   = t['webhook_option_a_subtitle']  || '(same network)';
        const aDesc  = t['webhook_option_a_desc']      || 'In LNbits open <em>Pay Links</em> &rarr; <em>New Pay Link</em> &rarr; <em>Advanced options</em> &rarr; <em>Webhook URL</em> and enter:';
        const aNote  = t['webhook_option_a_note']      || 'Click to copy &middot; Only works if mempaper is reachable from your wallet server.';
        const bTitle = t['webhook_option_b_title']     || 'Option B — Self-hosted webhook-tester';
        const bSub   = t['webhook_option_b_subtitle']  || '(works over the internet)';
        const bStep1 = t['webhook_option_b_step1']     || 'Deploy <a href="https://github.com/satcat21/event-hub" target="_blank" style="color:inherit">event-hub</a> on a server reachable from the internet.';
        const bStep2 = t['webhook_option_b_step2']     || 'Create a session — note the token UUID. Set the LNbits Webhook URL to <code>https://your-host/{token}</code>.';
        const bStep3 = t['webhook_option_b_step3']     || 'Paste the full WebSocket URL (e.g. <code>wss://your-host/ws/{token}</code>) in the field below.';

        const cfg = window.currentConfig || window.configData || {};
        const origin = window.location.origin;
        const webhookToken = cfg.donation_webhook_token || '';

        // Derive LAN IP URL when it differs from the current hostname (same-LAN setup)
        const lanIp = window._mpaLanIp || '';
        const curHostname = window.location.hostname;
        const portStr = window.location.port ? `:${window.location.port}` : '';
        const lanOrigin = lanIp && lanIp !== curHostname
            ? `${window.location.protocol}//${lanIp}${portStr}` : '';

        // Derive the LNbits HTTP URL for Option B from the configured WebSocket URL:
        // wss://host/ws/{token}  →  https://host/{token}
        const relayWsUrl = (cfg.webhook_relay_ws_url || '').trim();
        const optionBActive = !!relayWsUrl;
        const optionBLnbitsUrl = relayWsUrl
            ? relayWsUrl.replace(/^wss?:\/\//, 'https://').replace(/\/ws\//, '/')
            : '';

        const copySnippet = (url, label) => {
            const display = label ? `<span style="font-size:.75em;opacity:.6;margin-right:5px">${label}</span>` : '';
            return `<div style="margin-top:4px">${display}<code class="info-copyable" onclick="navigator.clipboard.writeText(this.textContent).then(()=>this.classList.add('copied'))" title="Click to copy">${url}</code></div>`;
        };

        const activeBadge = `<span style="font-size:.75em;font-weight:600;color:#22c55e;border:1px solid #22c55e;border-radius:4px;padding:1px 6px;vertical-align:middle;margin-left:6px">Active</span>`;

        let html = `<div style="margin-bottom:8px"><strong>${title}</strong></div>`;

        // Option A — always shown; token makes URL unguessable and secure
        html += `<div style="border:1px solid rgba(128,128,128,.3);border-radius:6px;padding:10px 12px;margin-bottom:10px">`;
        html += `<div style="font-weight:600;margin-bottom:4px">${aTitle} <small style="opacity:.65;font-weight:400">${aSub}</small>`;
        if (webhookToken) html += activeBadge;
        html += `</div>`;
        html += `<div style="margin-bottom:6px;font-size:.9em">${aDesc}</div>`;

        if (webhookToken) {
            const domainUrl = `${origin}/api/donation-webhook/${webhookToken}`;
            const aLanLabel = t['webhook_option_a_lan_label'] || 'LAN (same network):';
            const aDomainLabel = t['webhook_option_a_domain_label'] || 'Domain / internet:';
            if (lanOrigin) {
                // Show both: domain URL and LAN IP URL
                const lanUrl = `${lanOrigin}/api/donation-webhook/${webhookToken}`;
                html += copySnippet(lanUrl, aLanLabel);
                html += copySnippet(domainUrl, aDomainLabel);
            } else {
                html += copySnippet(domainUrl);
            }
        } else {
            // Token not yet generated — service restart needed
            const noToken = t['webhook_no_token'] || 'Token not yet generated. Restart the mempaper service to generate it.';
            html += `<div style="font-size:.85em;color:var(--danger,#ef4444);margin:4px 0">${noToken}</div>`;
        }

        html += `<div style="font-size:.8em;opacity:.6;margin-top:6px">${aNote}</div>`;
        html += `</div>`;

        // Option B
        html += `<div style="border:1px solid rgba(128,128,128,.3);border-radius:6px;padding:10px 12px">`;
        html += `<div style="font-weight:600;margin-bottom:6px">${bTitle} <small style="opacity:.65;font-weight:400">${bSub}</small>`;
        if (optionBActive) html += activeBadge;
        html += `</div>`;
        if (optionBActive) {
            const checkIcon = `<span style="display:inline-block;width:14px;height:14px;background-color:#22c55e;-webkit-mask-image:url('/static/icons/check.svg');mask-image:url('/static/icons/check.svg');-webkit-mask-size:contain;mask-size:contain;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;vertical-align:-2px;margin-right:4px"></span>`;
            const bConfigured = t['webhook_option_b_configured'] || 'Relay configured — use this URL in LNbits:';
            html += `<div style="margin-bottom:6px;font-size:.9em">${checkIcon}${bConfigured}</div>`;
            html += copySnippet(optionBLnbitsUrl);
        } else {
            html += `<ol style="margin:0;padding-left:1.4em;font-size:.9em;line-height:1.7">`;
            html += `<li>${bStep1}</li><li>${bStep2}</li><li>${bStep3}</li>`;
            html += `</ol>`;
        }
        html += `</div>`;
        return html;
    }
    return '';
}

// Apply a language switch without page reload — fully synchronous, no network request.
// Uses _lk / _dk keys baked into configSchema and categories by the server to update
// labels from window.allTranslations, then re-renders already-populated sections.
function setLanguage(lang) {
    const t = window.allTranslations?.[lang];
    if (!t) return;
    window.translations = t;

    // 1. Update static HTML elements tagged with data-i18n* attributes.
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const v = t[el.dataset.i18n];
        if (v !== undefined) el.textContent = v;
    });
    document.querySelectorAll('[data-i18n-html]').forEach(el => {
        const v = t[el.dataset.i18nHtml];
        if (v !== undefined) el.innerHTML = v;
    });
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
        const v = t[el.dataset.i18nTitle];
        if (v !== undefined) {
            if ('tooltip' in el.dataset) {
                // CSS tooltip — only update data-tooltip, never set native title (avoids double tooltip)
                el.dataset.tooltip = v;
            } else {
                el.title = v;
            }
        }
    });
    const titleEl = document.querySelector('[data-i18n-title-format]');
    if (titleEl) {
        const [k1, k2] = titleEl.dataset.i18nTitleFormat.split('|');
        document.title = `${t[k1] || k1} - ${t[k2] || k2}`;
    }
    if (typeof window._refreshHolidayPreview === 'function') {
        window._refreshHolidayPreview(lang);
    }

    // 2. Update in-memory schema labels/descriptions using the _lk/_dk keys from the server.
    if (configSchema) {
        Object.entries(configSchema).forEach(([, field]) => {
            if (field._lk && t[field._lk] !== undefined) field.label = t[field._lk];
            if (field._dk && t[field._dk] !== undefined) field.description = t[field._dk];
            if (field._lk_check && t[field._lk_check] !== undefined) field.label_check = t[field._lk_check];
            if (field._lk_open && t[field._lk_open] !== undefined) field.label_open = t[field._lk_open];
            if (field._html_builder) field.html = _buildInfoHtml(field._html_builder, t);
            if (field.options) {
                field.options.forEach(opt => {
                    if (opt._lk && t[opt._lk] !== undefined) opt.label = t[opt._lk];
                });
            }
        });
    }

    // 3. Update category labels and section-nav pills.
    if (categories) {
        categories.forEach(cat => {
            if (cat._lk && t[cat._lk] !== undefined) cat.label = t[cat._lk];
        });
        document.querySelectorAll('.section-nav-pill').forEach(pill => {
            const catId = pill.dataset.target?.replace('section-', '');
            const cat = categories.find(c => c.id === catId);
            if (!cat) return;
            pill.dataset.tooltip = cat.label;
            pill.setAttribute('aria-label', cat.label);
            const labelEl = pill.querySelector('.section-nav-label');
            if (labelEl) labelEl.textContent = cat.label;
        });
    }

    // 4. Re-render all sections that have already been populated so field labels refresh.
    //    Lazy sections (not yet visible) will use the updated schema when they are rendered.
    const savedScrollY = window.pageYOffset;
    currentConfig.language = lang; // so language dropdown re-renders with the pending selection

    document.querySelectorAll('.config-section[id]').forEach(section => {
        if (section.dataset.lazy === 'true') return;
        const catId = section.id.replace('section-', '');
        const cat = categories?.find(c => c.id === catId);
        if (!cat) return;
        section.innerHTML = '';
        section.dataset.lazy = 'true';
        _renderCategorySection(cat, section);
    });

    // Re-render rebuilds the display select from the raw schema (all options,
    // enabled) - re-lock it, same as the initial page load does.
    setTimeout(_enhanceDisplaySelect, 150);
    setTimeout(_initTorToggleWatch, 160);
    setTimeout(_initTangToggleWatch, 160);

    window.scrollTo({ top: savedScrollY, behavior: 'instant' });
}

// Fix: Define closeOpsecModal globally for HTML onclick handlers
function closeOpsecModal() {
    const opsecModal = document.getElementById('opsec-modal');
    if (opsecModal) {
        opsecModal.style.display = 'none';
        opsecModal.style.position = '';
        opsecModal.style.top = '';
        opsecModal.style.left = '';
        opsecModal.style.transform = '';
        opsecModal.style.margin = '';
    }
    window.currentModalOpsec = null;
}

// Fix: Define closeMemeModal globally for HTML onclick handlers
function closeMemeModal() {
    const memeModal = document.getElementById('meme-modal');
    if (memeModal) {
        memeModal.style.display = 'none';
        // Clear any inline styles that might interfere with centering
        memeModal.style.position = '';
        memeModal.style.top = '';
        memeModal.style.left = '';
        memeModal.style.transform = '';
        memeModal.style.margin = '';
    }
    window.currentModalMeme = null;
}
    function initializeWebSocket() {
        // Connect to backend using Socket.IO
        if (window.io) {
            const socket = window.io();
            window.configSocket = socket;

            socket.on('disconnect', function(reason) {
                console.warn('Config WebSocket disconnected:', reason);
            });

            socket.on('connect_error', function(error) {
                console.error('Config WebSocket connection error:', error);
            });

            // Live wallet balance updates from backend
            socket.on('wallet_balance_updated', function(data) {
                if (window._suppressWalletUpdates) return;
                const tbody = document.querySelector('.wallet-table tbody');
                if (!tbody) return;
                const allEntries = [].concat(data.addresses || [], data.xpubs || []);
                const prevAddrs = data.prev_addresses || [];
                const prevXpubs = data.prev_xpubs || [];
                const allPrev = [].concat(prevAddrs, prevXpubs);
                // Update table cells
                if (data.addresses) {
                    const rows = tbody.querySelectorAll('tr');
                    data.addresses.forEach((addrInfo, i) => {
                        if (i >= rows.length) return;
                        const display = rows[i].querySelector('.wallet-balance-display');
                        if (display) {
                            const bal = addrInfo.balance_btc || addrInfo.balance || addrInfo.cached_balance || 0;
                            _setWalletBalanceText(display, bal.toFixed(8));
                            display.style.color = 'var(--accent)';
                            display.style.opacity = '1';
                            display.title = 'Live balance data';
                        }
                    });
                }

                // Toast notifications per entry
                allEntries.forEach(entry => {
                    const label = entry.comment || entry.xpub_short || 'Wallet';
                    const bal = entry.balance_btc || 0;
                    const addr = entry.address || entry.xpub || '';
                    // Find previous balance
                    const prev = allPrev.find(p => (p.address || p.xpub) === addr);
                    const prevBal = prev ? (prev.balance_btc || 0) : -1;

                    var isStartup = data.startup_refresh || data.after_config_save || false;
                    if (prevBal < 0 || isStartup) {
                        // Skip toast on startup/config-save — only toast for genuinely new wallets
                    } else if (bal !== prevBal) {
                        showLiveToast(window.translations?.toast_wallet_title || 'Wallet', `'${label}' balance: ${prevBal.toFixed(8)} → ${bal.toFixed(8)} BTC`, 'color_wallets');
                    }
                });
            });

            // Live bitaxe stats updates from backend
            socket.on('bitaxe_stats_updated', function(data) {
                if (!data || !data.miners) return;
                const rows = document.querySelectorAll('.bitaxe-table-container tbody tr');
                rows.forEach(row => {
                    const ipInput = row.querySelector('.bitaxe-address-input');
                    const diffDisplay = row.querySelector('.bitaxe-best-diff-display');
                    if (!ipInput || !diffDisplay) return;
                    const ip = ipInput.value.trim();
                    const minerData = data.miners[ip];
                    if (!minerData) return;
                    if (minerData.online) {
                        diffDisplay.textContent = formatBitaxeDifficulty(minerData.best_diff);
                        diffDisplay.style.color = 'var(--accent)';
                    } else {
                        diffDisplay.textContent = 'Offline';
                        diffDisplay.style.color = '#ff6b6b';
                    }
                    // Toast for best diff changes — only when a real previous value exists
                    const label = minerData.label || ip;
                    if (minerData.best_diff > 0 && minerData.prev_best_diff > 0 && minerData.best_diff !== minerData.prev_best_diff) {
                        showLiveToast(window.translations?.toast_bitaxe_title || 'Bitaxe', `New best diff for ${label}: ${formatBitaxeDifficulty(minerData.best_diff)}`, 'color_bitaxe_stats');
                    }

                });
            });

            // Live found-blocks updates from backend
            socket.on('found_blocks_updated', function(data) {
                if (!data || !data.blocks) return;
                const rows = document.querySelectorAll('.block-reward-table-container tbody tr');
                rows.forEach(row => {
                    const addrInput = row.querySelector('.block-reward-address-input');
                    if (!addrInput) return;
                    const address = addrInput.value.trim();
                    const blockData = data.blocks[address];
                    if (!blockData) return;
                    let cell = row.querySelector('td[data-address]');
                    if (!cell) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 3) cell = cells[2];
                    }
                    if (cell) {
                        cell.textContent = blockData.count || '0';
                        cell.style.color = 'var(--accent)';
                    }
                    // Toast for new blocks found
                    if (blockData.count > blockData.prev_count) {
                        const diff = blockData.count - blockData.prev_count;
                        showLiveToast(window.translations?.toast_block_found_title || 'Block Found', `${blockData.label}: ${diff} new block${diff > 1 ? 's' : ''} found! (total: ${blockData.count})`, 'color_bitaxe_stats');
                    }
                })
            });

            socket.on('donation_received', function(donation) {
                // Prepend new row to table if it is currently visible
                const tbody = document.getElementById('donation-history-tbody');
                if (tbody) {
                    // Remove the "No donations yet" placeholder row if present
                    if (tbody.rows.length === 1 && tbody.rows[0].cells.length === 1) {
                        tbody.innerHTML = '';
                    }
                    const ts = _formatDonationTime(donation.timestamp);
                    const bh = donation.block_height != null ? donation.block_height.toLocaleString() : '—';
                    const sats = (donation.amount_sats || 0).toLocaleString();
                    const msg = donation.message
                        ? escapeHtml(donation.message) : '<em style="color:#888">—</em>';
                    const tr = document.createElement('tr');
                    tr.style.cssText = 'border-bottom:1px solid var(--border-color);';
                    tr.innerHTML = `
                        <td style="padding:5px 8px; white-space:nowrap;">${ts}</td>
                        <td style="padding:5px 8px; text-align:right; font-family:var(--font-mono); color:var(--text-secondary);">${bh}</td>
                        <td style="padding:5px 8px; text-align:right; font-weight:bold; color:var(--accent); font-family:var(--font-mono);">${sats}</td>
                        <td style="padding:5px 8px;">${msg}</td>`;
                    tbody.insertBefore(tr, tbody.firstChild);
                    // Update total
                    const totalEl = document.getElementById('donation-total-sats');
                    if (totalEl) {
                        const prev = parseInt(totalEl.dataset.total || '0', 10);
                        const next = prev + (donation.amount_sats || 0);
                        totalEl.dataset.total = next;
                        totalEl.textContent = next.toLocaleString() + ' sats';
                    }
                }
                // Toast notification
                showDonationToast(donation);
            });

            // Auto-update started — show toast notification
            socket.on('auto_update_started', function() {
                const t = window.translations || {};
                _buildLiveToast(
                    [_toastIcon('update', 'accent'), ' ' + (t.auto_update_started || 'Auto-update started')],
                    [t.auto_update_started_body || 'Checking for system and software updates...'],
                    '#F7931A',
                    10000
                );
            });

            // Display error — update hint below the display selector and show notification
            socket.on('display_update', function(data) {
                if (data.status !== 'error') return;
                const t = window.translations || {};
                const hint = document.getElementById('display-driver-hint');
                if (hint) _setDisplayHint(hint, 'error');
                _buildLiveToast(
                    [_toastIcon('error'), ' ' + (t.toast_error || 'Error')],
                    [t.wrong_display_driver_detected ||
                        'Wrong display driver detected — re-run install.sh to configure the correct display.'],
                    '#dc3545',
                    12000
                );
            });

            // Auto-update service restart — show countdown modal
            socket.on('service_restarting', function(data) {
                const t = window.translations || {};
                const _icon = '<img src="/static/icons/update.svg" alt="" class="modal-title-icon">';
                const title = data.reason === 'auto_update'
                    ? `${_icon} ${(t.auto_updating_to || 'Auto-updating to')} ${data.tag || ''}`
                    : (t.service_restarting || 'Service restarting...');
                // Capture current process start time so polling can detect a fresh process
                fetch('/api/health', { cache: 'no-store' })
                    .then(r => r.json())
                    .then(h => {
                        window._restartPending = { oldStarted: h.started, tag: data.tag };
                        _showRestartCountdown(title, data.estimated_seconds || 25, data.tag, null, null, h.started);
                    })
                    .catch(() => {
                        window._restartPending = { oldStarted: null, tag: data.tag };
                        _showRestartCountdown(title, data.estimated_seconds || 25, data.tag);
                    });
            });
        } else {
            console.error('Socket.IO client (window.io) not found. Make sure socket.io.min.js is loaded.');
        }
    }
