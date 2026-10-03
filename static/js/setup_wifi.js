/* ── i18n helpers ──────────────────────────────────────────────────────────── */

// SETUP_I18N is injected by the Jinja template as a global var.
var _currentLang = 'en';
var _adminVisible = false;  // track whether admin section is shown

function t(key) {
    var dict = (typeof SETUP_I18N !== 'undefined' && SETUP_I18N[_currentLang]) || {};
    var fallback = (typeof SETUP_I18N !== 'undefined' && SETUP_I18N['en']) || {};
    return dict[key] || fallback[key] || key;
}

function applyLanguage(lang) {
    _currentLang = lang || 'en';

    // Update all elements with data-i18n (textContent)
    document.querySelectorAll('[data-i18n]').forEach(function(el) {
        var key = el.getAttribute('data-i18n');
        el.textContent = t(key);
    });

    // Update all elements with data-i18n-html (innerHTML, for <strong>/<code> etc.)
    //
    // Only these keys may be rendered as markup. The attribute decides what gets
    // written into innerHTML, so restricting it to a fixed set keeps that
    // decision in this file rather than in whatever produced the DOM.
    var I18N_HTML_KEYS = ['setup_success_title', 'setup_success_hostname',
                          'setup_success_step1', 'setup_success_step2',
                          'setup_success_step3'];
    document.querySelectorAll('[data-i18n-html]').forEach(function(el) {
        var key = el.getAttribute('data-i18n-html');
        if (I18N_HTML_KEYS.indexOf(key) === -1) {
            el.textContent = t(key);
            return;
        }
        var val = t(key);
        // Prefix the success title with check icon
        if (key === 'setup_success_title') val = '<span style="display:inline-block;width:1.1em;height:1.1em;background-color:#22c55e;-webkit-mask-image:url(\'/static/icons/check.svg\');mask-image:url(\'/static/icons/check.svg\');-webkit-mask-size:contain;mask-size:contain;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;vertical-align:-0.15em;margin-right:4px"></span>' + val;
        el.innerHTML = val;
    });

    // Update all elements with data-i18n-placeholder
    document.querySelectorAll('[data-i18n-placeholder]').forEach(function(el) {
        var key = el.getAttribute('data-i18n-placeholder');
        el.placeholder = t(key);
    });

    // Update button text based on admin section visibility
    var connectBtn = document.getElementById('connect-button');
    if (connectBtn && connectBtn.style.display !== 'none') {
        connectBtn.textContent = _adminVisible ? t('setup_connect_admin_button') : t('setup_connect_button');
    }
}

/* ── Password strength ────────────────────────────────────────────────────── */

var _pwDebounce = null;

function _pwRules(pw) {
    return [
        { ok: pw.length >= 16,          label: t('pw_rule_min_length') || 'At least 16 characters' },
        { ok: /[A-Z]/.test(pw),         label: t('pw_rule_uppercase')  || 'Uppercase letter (A–Z)' },
        { ok: /[a-z]/.test(pw),         label: t('pw_rule_lowercase')  || 'Lowercase letter (a–z)' },
        { ok: /[0-9]/.test(pw),         label: t('pw_rule_number')     || 'Number (0–9)' },
        { ok: /[^A-Za-z0-9]/.test(pw),  label: t('pw_rule_special')    || 'Special character (!@#…)' },
    ];
}

function _renderPwStrength(container, pw) {
    if (!container) return;
    if (!pw) { container.style.display = 'none'; return; }
    var rules = _pwRules(pw);
    container.innerHTML = '';
    rules.forEach(function(r) {
        var el = document.createElement('div');
        el.className = 'pw-rule' + (r.ok ? ' ok' : '');
        el.textContent = r.label;
        container.appendChild(el);
    });
    container.style.display = 'flex';
}

function _initPwStrength(input, container) {
    function update() { _renderPwStrength(container, input.value); }
    input.addEventListener('input', update);
    input.addEventListener('blur', function() { if (input.value) update(); });
}

/* ── Live form validation ─────────────────────────────────────────────────── */

function validateForm() {
    var connectBtn = document.getElementById('connect-button');
    if (!connectBtn || connectBtn.style.display === 'none') return;

    // If admin section is not visible, no extra validation needed
    if (!_adminVisible) {
        connectBtn.disabled = false;
        return;
    }

    var username      = (document.getElementById('admin-username').value  || '').trim();
    var adminPassword =  document.getElementById('admin-password').value  || '';
    var adminConfirm  =  document.getElementById('admin-confirm').value   || '';
    var confirmHint   =  document.getElementById('admin-confirm-hint');

    var valid = true;

    if (username.length < 3) valid = false;
    if (!_pwRules(adminPassword).every(function(r) { return r.ok; })) valid = false;

    // Password match check (only show mismatch when confirm field has input)
    if (adminConfirm.length > 0 && adminPassword !== adminConfirm) {
        valid = false;
        if (confirmHint) {
            confirmHint.textContent = t('setup_admin_passwords_no_match') || 'Passwords do not match';
            confirmHint.style.display = 'block';
        }
    } else if (adminConfirm.length > 0 && adminPassword === adminConfirm) {
        if (confirmHint) {
            confirmHint.textContent = '';
            confirmHint.style.display = 'none';
        }
    } else {
        // Confirm empty — still invalid but don't show mismatch hint
        if (adminConfirm.length === 0) valid = false;
        if (confirmHint) {
            confirmHint.textContent = '';
            confirmHint.style.display = 'none';
        }
    }

    connectBtn.disabled = !valid;
}

/* ── Core functions ───────────────────────────────────────────────────────── */

async function fetchSetupStatus() {
    const res = await fetch('/api/setup/status');
    if (!res.ok) {
        throw new Error('Could not read setup status');
    }
    return res.json();
}

function setMessage(text, isError) {
    const box = document.getElementById('setup-message');
    if (!box) {
        return;
    }
    box.textContent = text;
    box.style.display = text ? 'block' : 'none';
    box.style.background = isError ? 'rgba(229, 62, 62, 0.1)' : 'rgba(56, 161, 105, 0.12)';
    box.style.color = isError ? 'var(--danger)' : 'var(--success)';
    box.style.borderLeft = isError ? '3px solid var(--danger)' : '3px solid var(--success)';
}

function renderNetworks(networks) {
    const select = document.getElementById('ssid-select');
    select.innerHTML = '';

    if (!Array.isArray(networks) || networks.length === 0) {
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = t('setup_no_networks');
        select.appendChild(empty);
        return;
    }

    for (const n of networks) {
        const option = document.createElement('option');
        option.value = n.ssid;
        const security = n.open ? 'open' : 'secured';
        option.textContent = `${n.ssid} (${n.signal}%, ${security})`;
        select.appendChild(option);
    }
}

function getSelectedSsid() {
    const hiddenToggle = document.getElementById('hidden-network-toggle');
    const hiddenInput = document.getElementById('hidden-ssid');
    const select = document.getElementById('ssid-select');
    const hidden = hiddenToggle && hiddenToggle.checked;

    if (hidden) {
        return {
            ssid: ((hiddenInput && hiddenInput.value) || '').trim(),
            hidden: true,
        };
    }

    return {
        ssid: ((select && select.value) || '').trim(),
        hidden: false,
    };
}

function syncHiddenNetworkMode() {
    const hiddenToggle = document.getElementById('hidden-network-toggle');
    const hiddenGroup = document.getElementById('hidden-ssid-group');
    const select = document.getElementById('ssid-select');
    if (!hiddenToggle || !hiddenGroup || !select) {
        return;
    }
    const hidden = hiddenToggle.checked;
    hiddenGroup.style.display = hidden ? 'block' : 'none';
    select.disabled = hidden;
}

async function loadNetworks() {
    const scanStatus = document.getElementById('scan-status');
    scanStatus.innerHTML = '<span class="scan-spinner"></span> <span data-i18n="setup_scanning">' + t('setup_scanning') + '</span>';

    const res = await fetch('/api/setup/wifi/scan');
    const data = await res.json();

    if (!res.ok || !data.success) {
        throw new Error(data.message || 'Failed to scan WiFi');
    }

    renderNetworks(data.networks || []);
    const count = (data.networks || []).length;
    scanStatus.textContent = t('setup_found_networks').replace('{count}', count);
}

// How long joining a network usually takes, end to end: the hotspot comes
// down, the device associates and gets an address, and the display redraws.
// Shown as a countdown so the wait reads as progress, not as a hang.
const CONNECT_ESTIMATE_S = 90;

// The countdown, the bar and the three steps under the connect button.
function connectProgress() {
    const panel = document.getElementById('connect-progress');
    const timeEl = document.getElementById('connect-progress-time');
    const fill = document.getElementById('connect-progress-fill');
    const title = document.getElementById('connect-progress-title');
    const spinner = document.getElementById('connect-progress-spinner');
    const step = name => panel.querySelector(`li[data-step="${name}"]`);
    let timer = null;
    let current = null;

    const fmt = s => Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');
    const activate = name => {
        if (current === name) return;
        if (current) { step(current).classList.remove('active'); step(current).classList.add('done'); }
        current = name;
        step(name).classList.add('active');
    };

    return {
        start() {
            panel.querySelectorAll('li').forEach(li => li.classList.remove('active', 'done'));
            current = null;
            title.textContent = t('setup_progress_title');
            spinner.style.display = '';
            panel.style.display = 'block';
            activate('send');
            const started = Date.now();
            timeEl.textContent = fmt(CONNECT_ESTIMATE_S);
            fill.style.transform = 'scaleX(0)';
            timer = setInterval(() => {
                const elapsed = Math.floor((Date.now() - started) / 1000);
                const left = Math.max(0, CONNECT_ESTIMATE_S - elapsed);
                timeEl.textContent = fmt(left);
                fill.style.transform = 'scaleX(' + Math.min(1, elapsed / CONNECT_ESTIMATE_S) + ')';
                if (elapsed >= 10) this.unreachable();   // the switch has begun either way
                if (left === 0) {
                    clearInterval(timer);
                    title.textContent = t('setup_progress_check_display');
                    spinner.style.display = 'none';
                    timeEl.textContent = '';
                }
            }, 1000);
        },
        sent() { activate('switch'); },
        // The phone can no longer reach the device: the hotspot is down and
        // the device is joining the home network. Expected, not an error.
        unreachable() { if (current !== 'display') { activate('switch'); activate('display'); } },
        hide() { clearInterval(timer); panel.style.display = 'none'; },
    };
}

// Ask the device how joining is going until it answers connected or failed,
// or until well past the estimate. Each request gives up after 4 seconds:
// once the hotspot is down a request has nowhere to go, and without a limit
// the browser held each one for minutes, which is why "disconnected" used to
// appear long after the phone had actually lost the network.
function pollConnectStatus(progress) {
    return new Promise((resolve, reject) => {
        const started = Date.now();
        const tick = async () => {
            const ctrl = new AbortController();
            const abort = setTimeout(() => ctrl.abort(), 4000);
            try {
                const res = await fetch('/api/setup/wifi/connect_status', { signal: ctrl.signal, cache: 'no-store' });
                clearTimeout(abort);
                if (res.ok) {
                    const data = await res.json();
                    if (data.status === 'connected') return resolve(data);
                    if (data.status === 'failed') return reject(new Error(data.message || 'Connection failed'));
                } else {
                    progress.unreachable();
                }
            } catch (e) {
                clearTimeout(abort);
                progress.unreachable();
            }
            if ((Date.now() - started) / 1000 > CONNECT_ESTIMATE_S + 60) {
                const err = new Error(t('setup_wifi_disconnected_expected'));
                err.expected = true;
                return reject(err);
            }
            setTimeout(tick, 2000);
        };
        tick();
    });
}

async function connectWifi() {
    const ssidSelection = getSelectedSsid();
    const ssid = ssidSelection.ssid;
    const hidden = ssidSelection.hidden;
    const password = document.getElementById('wifi-password').value || '';

    if (!ssid) {
        setMessage(hidden ? 'Please enter the hidden WiFi SSID.' : 'Please select a WiFi network.', true);
        return;
    }

    // --- Admin account creation (first-time only) ---
    const adminSection = document.getElementById('admin-setup-section');
    if (adminSection && adminSection.style.display !== 'none') {
        const username       = (document.getElementById('admin-username').value  || '').trim();
        const adminPassword  =  document.getElementById('admin-password').value  || '';
        const adminConfirm   =  document.getElementById('admin-confirm').value   || '';

        if (!username) {
            setMessage('Please enter an admin username.', true);
            return;
        }
        if (username.length < 3) {
            setMessage('Username must be at least 3 characters.', true);
            return;
        }
        if (!_pwRules(adminPassword).every(function(r) { return r.ok; })) {
            setMessage(t('password_too_short') || 'Password must be at least 16 characters', true);
            return;
        }
        if (adminPassword !== adminConfirm) {
            setMessage(t('passwords_do_not_match') || 'Passwords do not match', true);
            return;
        }

        try {
            const adminRes = await fetch('/api/setup/create_admin', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username,
                    password:         adminPassword,
                    confirm_password: adminConfirm,
                }),
            });
            const adminData = await adminRes.json().catch(() => ({}));
            if (!adminRes.ok || !adminData.success) {
                throw new Error(adminData.message || 'Failed to create admin user');
            }
        } catch (e) {
            setMessage(e.message || 'Admin account creation failed', true);
            return;
        }
    }
    // --- End admin creation ---

    const connectBtn = document.getElementById('connect-button');
    connectBtn.disabled = true;
    connectBtn.textContent = t('setup_connecting');
    const progress = connectProgress();
    progress.start();

    try {
        const language = (document.getElementById('language-select') || {}).value || 'en';
        let res;
        try {
            res = await fetch('/api/setup/wifi/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ssid, password, hidden, language }),
            });
        } catch (e) {
            // If even this request fails the hotspot may already be down — still poll
        }

        if (res && !res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.message || 'Request failed');
        }

        progress.sent();
        const result = await pollConnectStatus(progress);
        progress.hide();
        const connName = result.connection || ssid;
        setMessage('', false);
        document.getElementById('scan-status').textContent = connName;

        // Show success box
        const successBox = document.getElementById('success-box');
        const successNetwork = document.getElementById('success-network');
        if (successBox) {
            successNetwork.textContent = 'Network: ' + connName;
            successBox.style.display = 'block';
        }

        // Hide the form controls — setup is done
        document.getElementById('connect-button').style.display = 'none';
        document.getElementById('refresh-button').style.display = 'none';

    } catch (err) {
        if (err.expected) {
            // Nothing went wrong that this page can see: the phone simply has
            // no way back to the device. The panel keeps its last step, which
            // says to check the display.
            setMessage(err.message, false);
            return;
        }
        progress.hide();
        setMessage(err.message || 'Connection failed', true);
        connectBtn.disabled = false;
        connectBtn.textContent = _adminVisible ? t('setup_connect_admin_button') : t('setup_connect_button');
    }
}

/* ── Device Reset ─────────────────────────────────────────────────────────── */

async function resetDevice() {
    if (!confirm(t('setup_reset_confirm'))) {
        return;
    }

    const resetBtn = document.getElementById('reset-button');
    resetBtn.disabled = true;
    resetBtn.textContent = '...';

    try {
        const res = await fetch('/api/setup/reset_device', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await res.json().catch(() => ({}));

        if (!res.ok || !data.success) {
            throw new Error(data.message || 'Reset failed');
        }

        setMessage(t('setup_reset_success'), false);
        setTimeout(function() { location.reload(); }, 3000);
    } catch (e) {
        setMessage(e.message || 'Reset failed', true);
        resetBtn.disabled = false;
        resetBtn.textContent = t('setup_reset_button');
    }
}

/* ── Init ─────────────────────────────────────────────────────────────────── */

document.addEventListener('DOMContentLoaded', async () => {
    const refreshBtn = document.getElementById('refresh-button');
    const connectBtn = document.getElementById('connect-button');
    const hiddenToggle = document.getElementById('hidden-network-toggle');
    const langSelect = document.getElementById('language-select');
    const resetBtn = document.getElementById('reset-button');

    // Wire language selector
    if (langSelect) {
        langSelect.addEventListener('change', function() {
            applyLanguage(this.value);
        });
    }

    if (hiddenToggle) {
        hiddenToggle.addEventListener('change', syncHiddenNetworkMode);
        syncHiddenNetworkMode();
    }

    refreshBtn.addEventListener('click', async () => {
        try {
            await loadNetworks();
            setMessage('', false);
        } catch (err) {
            setMessage(err.message || 'Scan failed', true);
        }
    });

    connectBtn.addEventListener('click', connectWifi);

    if (resetBtn) {
        resetBtn.addEventListener('click', resetDevice);
    }

    try {
        const setupStatus = await fetchSetupStatus();
        if (!setupStatus.setup_mode) {
            setMessage('Setup mode is not active on this device.', true);
            connectBtn.disabled = true;
            refreshBtn.disabled = true;
            return;
        }

        // Show admin creation form only when no user exists yet
        try {
            const adminCheck = await fetch('/api/setup/admin_needed');
            if (adminCheck.ok) {
                const adminData = await adminCheck.json();
                const adminSection = document.getElementById('admin-setup-section');
                if (adminSection && adminData.admin_needed) {
                    adminSection.style.display = 'block';
                    _adminVisible = true;
                    connectBtn.textContent = t('setup_connect_admin_button');
                    connectBtn.disabled = true;  // disabled until validation passes

                    // Wire live validation on admin fields
                    ['admin-username', 'admin-password', 'admin-confirm'].forEach(function(id) {
                        var el = document.getElementById(id);
                        if (el) el.addEventListener('input', validateForm);
                    });
                    // Wire password strength checklist (debounced)
                    _initPwStrength(
                        document.getElementById('admin-password'),
                        document.getElementById('admin-pw-strength')
                    );
                }
            }
        } catch (_) {
            // Non-fatal: if the check fails just skip the admin section
        }

        await loadNetworks();
    } catch (err) {
        setMessage(err.message || 'Failed to initialize setup page', true);
    }
});
