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
    document.querySelectorAll('[data-i18n-html]').forEach(function(el) {
        var key = el.getAttribute('data-i18n-html');
        var val = t(key);
        // Prefix the success title with checkmark
        if (key === 'setup_success_title') val = '\u2705 ' + val;
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
    if (adminPassword.length < 8) valid = false;

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

async function pollConnectStatus(ssid, attempts) {
    const maxAttempts = attempts || 20;
    let tries = 0;

    return new Promise((resolve, reject) => {
        const interval = setInterval(async () => {
            tries++;
            try {
                const res = await fetch('/api/setup/wifi/connect_status');
                if (!res.ok) {
                    if (tries >= maxAttempts) {
                        clearInterval(interval);
                        reject(new Error('Timed out waiting for connection result'));
                    }
                    return;
                }
                const data = await res.json();
                if (data.status === 'connected') {
                    clearInterval(interval);
                    resolve(data);
                } else if (data.status === 'failed') {
                    clearInterval(interval);
                    reject(new Error(data.message || 'Connection failed'));
                } else if (tries >= maxAttempts) {
                    clearInterval(interval);
                    reject(new Error('Timed out waiting for connection result'));
                }
            } catch (e) {
                if (tries >= maxAttempts) {
                    clearInterval(interval);
                    reject(new Error('Lost connection to device — check if it joined your network'));
                }
            }
        }, 1500);
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
        if (adminPassword.length < 8) {
            setMessage('Admin password must be at least 8 characters.', true);
            return;
        }
        if (adminPassword !== adminConfirm) {
            setMessage('Admin passwords do not match.', true);
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

        setMessage(t('setup_connecting'), false);

        const result = await pollConnectStatus(ssid);
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
