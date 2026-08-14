// Settings sections that manage device state: credentials, software
// update, Wi-Fi, display drivers, Tor, SSH access and device control.
// Part 3 of 8, split from config.js. Load order matters:
// these run as classic scripts sharing one global scope.

// ─── Current-user credential fields (injected into General section) ──────────

function createCurrentUserUsernameField() {
    const formGroup = document.createElement('div');
    formGroup.className = 'form-group';

    const label = document.createElement('label');
    label.className = 'form-label';
    label.textContent = window.translations?.admin_username || 'Admin Username';
    formGroup.appendChild(label);

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-input';
    input.value = configCurrentUser;
    input.setAttribute('autocomplete', 'one-time-code');
    input.setAttribute('data-1p-ignore', '');
    input.setAttribute('data-lpignore', 'true');
    input.setAttribute('data-form-type', 'other');
    input.setAttribute('data-config-key', 'admin_username');
    formGroup.appendChild(input);

    return formGroup;
}

function createCurrentUserPasswordField() {
    const formGroup = document.createElement('div');
    formGroup.className = 'form-group';

    const label = document.createElement('label');
    label.className = 'form-label';
    label.textContent = window.translations?.admin_password || 'Admin Password';
    formGroup.appendChild(label);

    const pwInterface = createCurrentUserPasswordInterface();
    formGroup.appendChild(pwInterface);
    return formGroup;
}

function createCurrentUserPasswordInterface() {
    const container = document.createElement('div');
    container.className = 'password-change-container';

    const buttonWrapper = document.createElement('div');
    buttonWrapper.className = 'password-button-wrapper';
    buttonWrapper.style.cssText = 'padding:15px;border:1px solid #ddd;border-radius:4px;background:var(--bg-color);text-align:center;';

    const changeButton = document.createElement('button');
    changeButton.type = 'button';
    changeButton.className = 'form-button';
    changeButton.style.cssText = 'background:#F7931A;color:white;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;';
    changeButton.textContent = window.translations?.change_password || 'Change Password';

    const passwordForm = document.createElement('form');
    passwordForm.className = 'password-change-form';
    passwordForm.style.cssText = 'display:none;margin-top:10px;padding:15px;border:1px solid #ddd;border-radius:4px;background:var(--bg-color);';
    passwordForm.onsubmit = e => e.preventDefault();
    // Hidden username field required by password managers / browser accessibility
    const _hiddenUser2 = document.createElement('input');
    _hiddenUser2.type = 'text'; _hiddenUser2.autocomplete = 'username';
    _hiddenUser2.setAttribute('aria-hidden', 'true'); _hiddenUser2.style.display = 'none';
    passwordForm.appendChild(_hiddenUser2);

    const newPasswordInput = document.createElement('input');
    newPasswordInput.type = 'password';
    newPasswordInput.className = 'form-input';
    newPasswordInput.placeholder = window.translations?.new_password || 'New Password';
    newPasswordInput.maxLength = 128;
    newPasswordInput.autocomplete = 'new-password';
    newPasswordInput.style.marginBottom = '6px';

    // Password strength checklist
    const pwFeedback2 = document.createElement('div');
    pwFeedback2.className = 'pw-strength';
    pwFeedback2.style.marginBottom = '10px';
    const tr2 = window.translations || {};
    const pwRules2 = [
        { re: null,            min: 16, label: tr2.pw_rule_min_length || 'At least 16 characters' },
        { re: /[A-Z]/,         min: 0,  label: tr2.pw_rule_uppercase  || 'Uppercase letter (A–Z)' },
        { re: /[a-z]/,         min: 0,  label: tr2.pw_rule_lowercase  || 'Lowercase letter (a–z)' },
        { re: /[0-9]/,         min: 0,  label: tr2.pw_rule_number     || 'Number (0–9)' },
        { re: /[^A-Za-z0-9]/, min: 0,  label: tr2.pw_rule_special    || 'Special character (!@#…)' },
    ];
    function renderPwStrength2(pw) {
        pwFeedback2.innerHTML = '';
        if (!pw) { pwFeedback2.style.display = 'none'; return; }
        pwRules2.forEach(r => {
            const ok = r.re ? r.re.test(pw) : pw.length >= r.min;
            const el = document.createElement('div');
            el.className = 'pw-rule' + (ok ? ' ok' : '');
            el.textContent = r.label;
            pwFeedback2.appendChild(el);
        });
        pwFeedback2.style.display = 'flex';
    }
    function updateSaveState2() {
        const pw = newPasswordInput.value;
        const conf = confirmPasswordInput.value;
        const allPass = pwRules2.every(r => r.re ? r.re.test(pw) : pw.length >= r.min);
        saveButton.disabled = !(allPass && conf.length > 0 && pw === conf);
    }

    const confirmPasswordInput = document.createElement('input');
    confirmPasswordInput.type = 'password';
    confirmPasswordInput.className = 'form-input';
    confirmPasswordInput.placeholder = window.translations?.confirm_password || 'Confirm Password';
    confirmPasswordInput.maxLength = 128;
    confirmPasswordInput.autocomplete = 'new-password';
    confirmPasswordInput.style.marginBottom = '6px';

    // Live match hint
    const matchHint2 = document.createElement('div');
    matchHint2.style.cssText = 'font-size:0.82rem;margin-bottom:10px;display:none;';
    function updateMatchHint2() {
        const a = newPasswordInput.value, b = confirmPasswordInput.value;
        if (!b) { matchHint2.style.display = 'none'; return; }
        const match = a === b;
        matchHint2.style.display = 'block';
        matchHint2.style.color = match ? 'var(--success)' : 'var(--danger)';
        matchHint2.textContent = match
            ? (window.translations?.passwords_match || 'Passwords match')
            : (window.translations?.passwords_do_not_match || 'Passwords do not match');
    }

    newPasswordInput.addEventListener('input', () => {
        renderPwStrength2(newPasswordInput.value);
        errorMessage.style.display = 'none';
        updateMatchHint2();
        updateSaveState2();
    });
    newPasswordInput.addEventListener('blur', () => {
        if (newPasswordInput.value) renderPwStrength2(newPasswordInput.value);
    });
    confirmPasswordInput.addEventListener('input', () => { updateMatchHint2(); updateSaveState2(); });

    const errorMessage = document.createElement('div');
    errorMessage.className = 'password-error';
    errorMessage.style.cssText = 'color:red;margin-bottom:10px;display:none;';

    const buttonContainer = document.createElement('div');
    buttonContainer.style.cssText = 'display:flex;gap:10px;';

    const saveButton = document.createElement('button');
    saveButton.type = 'button';
    saveButton.className = 'form-button pw-save-btn';
    saveButton.textContent = window.translations?.save || 'Save';
    saveButton.disabled = true;

    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'form-button';
    cancelButton.style.cssText = 'background:#666;color:white;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;';
    cancelButton.textContent = window.translations?.cancel || 'Cancel';

    changeButton.addEventListener('click', () => {
        passwordForm.style.display = 'block';
        buttonWrapper.style.display = 'none';
        saveButton.disabled = true;
        newPasswordInput.focus();
        if (!saveButton._widthSet) {
            requestAnimationFrame(() => {
                const label = saveButton.textContent;
                saveButton.style.visibility = 'hidden';
                saveButton.innerHTML = (window.translations?.saving || 'Saving')
                    + '<span style="display:inline-block;width:1.4em"></span>';
                saveButton.style.minWidth = saveButton.getBoundingClientRect().width + 'px';
                saveButton.textContent = label;
                saveButton.style.visibility = '';
                saveButton._widthSet = true;
            });
        }
    });
    cancelButton.addEventListener('click', () => {
        passwordForm.style.display = 'none';
        buttonWrapper.style.display = '';
        newPasswordInput.value = '';
        confirmPasswordInput.value = '';
        errorMessage.style.display = 'none';
        pwFeedback2.innerHTML = ''; pwFeedback2.style.display = 'none';
        matchHint2.style.display = 'none';
        saveButton.disabled = true;
    });
    saveButton.addEventListener('click', async () => {
        const newPassword = newPasswordInput.value;
        const confirmPassword = confirmPasswordInput.value;
        if (!newPassword || !confirmPassword) {
            errorMessage.textContent = 'Please fill in both password fields';
            errorMessage.style.display = '';
            return;
        }
        if (newPassword !== confirmPassword) {
            errorMessage.textContent = window.translations?.passwords_do_not_match || 'Passwords do not match';
            errorMessage.style.display = '';
            return;
        }
        const failedRules2 = pwRules2.filter(r => !(r.re ? r.re.test(newPassword) : newPassword.length >= r.min));
        if (failedRules2.length > 0) {
            renderPwStrength2(newPassword);
            errorMessage.textContent = window.translations?.password_too_short || 'Password does not meet requirements';
            errorMessage.style.display = '';
            return;
        }
        if (newPassword.length > 128) {
            errorMessage.textContent = window.translations?.password_too_long || 'Password too long (max 128 characters)';
            errorMessage.style.display = '';
            return;
        }
        errorMessage.style.display = 'none';
        saveButton.disabled = true;
        saveButton.innerHTML = `${window.translations?.saving || 'Saving'}<span class="mpa-dots"></span>`;
        try {
            const resp = await fetch(`/api/users/${encodeURIComponent(configCurrentUser)}/password`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({password: newPassword})
            });
            const result = await resp.json();
            if (result.success) {
                cancelButton.click();
                showNotification(window.translations?.password_changed_successfully || 'Password changed successfully', 'success');
            } else {
                errorMessage.textContent = result.message || 'Failed to change password';
                errorMessage.style.display = '';
            }
        } catch (e) {
            errorMessage.textContent = 'Request failed';
            errorMessage.style.display = '';
        } finally {
            saveButton.textContent = window.translations?.save || 'Save';
            updateSaveState2();
        }
    });

    buttonContainer.appendChild(saveButton);
    buttonContainer.appendChild(cancelButton);
    passwordForm.appendChild(newPasswordInput);
    passwordForm.appendChild(pwFeedback2);
    passwordForm.appendChild(confirmPasswordInput);
    passwordForm.appendChild(matchHint2);
    passwordForm.appendChild(errorMessage);
    passwordForm.appendChild(buttonContainer);
    buttonWrapper.appendChild(changeButton);
    container.appendChild(buttonWrapper);
    container.appendChild(passwordForm);
    return container;
}

// ── Software Update Section ──────────────────────────────────────────────

/** Lightweight line-by-line markdown→HTML for release notes. */
function _renderReleaseMarkdown(md) {
    if (!md) return '';
    const lines = md.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').split('\n');
    let html = '';
    let inList = false;
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const hMatch = line.match(/^(#{1,4})\s+(.*)/);
        const liMatch = line.match(/^[-*]\s+(.*)/);
        if (hMatch) {
            if (inList) { html += '</ul>'; inList = false; }
            const lvl = hMatch[1].length;
            html += `<h${lvl}>${_inlineMd(hMatch[2])}</h${lvl}>`;
        } else if (liMatch) {
            if (!inList) { html += '<ul>'; inList = true; }
            html += `<li>${_inlineMd(liMatch[1])}</li>`;
        } else if (line.trim() === '') {
            if (inList) { html += '</ul>'; inList = false; }
        } else {
            if (inList) { html += '</ul>'; inList = false; }
            html += `<p>${_inlineMd(line)}</p>`;
        }
    }
    if (inList) html += '</ul>';
    return html;
}
function _inlineMd(s) {
    return s
        .replace(/`([^`]+)`/g, '<code>$1</code>')
        .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
        .replace(/\*([^*]+)\*/g, '<em>$1</em>')
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

// ── WiFi Management Section ──────────────────────────────────────────
function createWifiSection() {
    const t = window.translations || {};
    const section = document.createElement('div');
    section.className = 'form-group wifi-management-section';

    // Header with title
    const label = document.createElement('label');
    label.className = 'form-label';
    label.textContent = t.wifi_saved_networks || 'Saved Networks';
    section.appendChild(label);

    // Saved networks container
    const savedList = document.createElement('div');
    savedList.id = 'wifi-saved-list';
    savedList.className = 'wifi-saved-list';
    savedList.innerHTML = `<div class="wifi-loading">${t.loading || 'Loading...'}</div>`;
    section.appendChild(savedList);

    // Add network form (collapsed by default)
    const addForm = document.createElement('form');
    addForm.className = 'wifi-add-form';
    addForm.id = 'wifi-add-form';
    addForm.style.display = 'none';
    addForm.onsubmit = e => e.preventDefault();
    addForm.innerHTML = `
        <div class="wifi-add-fields">
            <input type="text" class="form-input" id="wifi-add-ssid" placeholder="${t.wifi_ssid || 'Network name (SSID)'}" />
            <input type="password" class="form-input" id="wifi-add-password" placeholder="${t.wifi_password || 'Password'}" autocomplete="off" />
            <label class="wifi-hidden-label">
                <input type="checkbox" id="wifi-add-hidden" /> ${t.wifi_hidden_network || 'Hidden network'}
            </label>
        </div>
        <div class="wifi-add-actions">
            <button type="button" class="wifi-btn wifi-btn-save" id="wifi-add-save">${t.save || 'Save'}</button>
            <button type="button" class="wifi-btn wifi-btn-cancel" id="wifi-add-cancel">${t.cancel || 'Cancel'}</button>
        </div>
    `;
    section.appendChild(addForm);

    // Action buttons row
    const actions = document.createElement('div');
    actions.className = 'wifi-actions';
    actions.innerHTML = `
        <button type="button" class="wifi-btn wifi-btn-add" id="wifi-btn-add">${t.wifi_add_network || 'Add Network'}</button>
        <button type="button" class="wifi-btn wifi-btn-scan" id="wifi-btn-scan">${t.wifi_scan || 'Scan Nearby'}</button>
    `;
    section.appendChild(actions);

    // Scan results container (hidden by default)
    const scanResults = document.createElement('div');
    scanResults.id = 'wifi-scan-results';
    scanResults.className = 'wifi-scan-results';
    scanResults.style.display = 'none';
    section.appendChild(scanResults);


    // Wire up events after a tick (elements need to be in DOM)
    setTimeout(() => _initWifiEvents(), 0);

    return section;
}

function _initWifiEvents() {
    const t = window.translations || {};

    // Load saved networks
    _loadSavedWifi();

    // Add network button
    document.getElementById('wifi-btn-add')?.addEventListener('click', () => {
        const form = document.getElementById('wifi-add-form');
        form.style.display = form.style.display === 'none' ? 'block' : 'none';
        document.getElementById('wifi-scan-results').style.display = 'none';
        if (form.style.display === 'block') {
            document.getElementById('wifi-add-ssid')?.focus();
        }
    });

    // Cancel add
    document.getElementById('wifi-add-cancel')?.addEventListener('click', () => {
        document.getElementById('wifi-add-form').style.display = 'none';
        document.getElementById('wifi-add-ssid').value = '';
        document.getElementById('wifi-add-password').value = '';
        document.getElementById('wifi-add-hidden').checked = false;
    });

    // Save new network
    document.getElementById('wifi-add-save')?.addEventListener('click', () => _addWifi());

    // Scan button
    document.getElementById('wifi-btn-scan')?.addEventListener('click', () => _scanWifi());
}

// Track the server-side preferred UUID and the client-side pending selection
let _wifiServerPreferredUuid = null;
let _wifiPendingPreferredUuid = null;

function _loadSavedWifi() {
    const t = window.translations || {};
    const list = document.getElementById('wifi-saved-list');
    if (!list) return;

    list.innerHTML = `<div class="wifi-loading">${t.loading || 'Loading...'}</div>`;

    fetch('/api/wifi/saved', { credentials: 'same-origin' })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                list.innerHTML = `<div class="wifi-empty">${data.error || 'Failed to load'}</div>`;
                return;
            }
            if (!data.connections || data.connections.length === 0) {
                list.innerHTML = `<div class="wifi-empty">${t.wifi_no_saved || 'No saved WiFi networks'}</div>`;
                return;
            }

            // Determine server-side preferred
            const serverPreferred = data.connections.find(c => c.priority > 0);
            _wifiServerPreferredUuid = serverPreferred ? serverPreferred.uuid : null;
            // Initialize pending to server state if not already changed by user
            if (_wifiPendingPreferredUuid === null) {
                _wifiPendingPreferredUuid = _wifiServerPreferredUuid;
            }

            list.innerHTML = '';
            data.connections.forEach(conn => {
                const row = document.createElement('div');
                row.className = 'wifi-saved-row' + (conn.active ? ' wifi-active' : '');
                row.dataset.uuid = conn.uuid;

                const isPending = conn.uuid === _wifiPendingPreferredUuid;

                const savedSecurityIcon = `<span class="wifi-security-icon ${conn.open ? 'wifi-security-icon--open' : 'wifi-security-icon--secured'}" title="${conn.open ? (t.wifi_open || 'Open') : (t.wifi_secured || 'Secured')}"></span>`;

                row.innerHTML = `
                    <div class="wifi-row-info">
                        <button type="button" class="wifi-btn-icon wifi-btn-prefer${isPending ? ' wifi-prefer-active' : ''}" title="${t.wifi_set_preferred || 'Set as preferred'}">★</button>
                        <span class="wifi-ssid">${savedSecurityIcon}${_escHtml(conn.ssid)}</span>
                        ${conn.active ? `<span class="wifi-badge wifi-badge-connected">${t.wifi_connected || 'Connected'}</span>` : ''}
                        ${isPending ? `<span class="wifi-badge wifi-badge-preferred">${t.wifi_preferred || 'Preferred'}</span>` : ''}
                    </div>
                    <div class="wifi-row-actions">
                        ${!conn.active ? `<button type="button" class="wifi-btn-icon wifi-btn-delete" title="${t.delete || 'Delete'}">✕</button>` : ''}
                    </div>
                `;

                // Star click — toggle preferred (client-side only)
                row.querySelector('.wifi-btn-prefer').addEventListener('click', (e) => {
                    e.stopPropagation();
                    // Toggle: if already preferred, unset; otherwise set this one
                    _wifiPendingPreferredUuid = (_wifiPendingPreferredUuid === conn.uuid) ? null : conn.uuid;
                    _renderWifiPreferredState();
                    _updateWifiSaveButton();
                });

                // Delete
                row.querySelector('.wifi-btn-delete')?.addEventListener('click', (e) => {
                    e.stopPropagation();
                    _deleteWifi(conn.uuid);
                });

                list.appendChild(row);
            });

            _updateWifiSaveButton();
        })
        .catch(() => {
            list.innerHTML = `<div class="wifi-empty">${t.wifi_not_available || 'WiFi management not available on this device'}</div>`;
        });
}

function _renderWifiPreferredState() {
    const t = window.translations || {};
    const list = document.getElementById('wifi-saved-list');
    if (!list) return;

    list.querySelectorAll('.wifi-saved-row').forEach(row => {
        const uuid = row.dataset.uuid;
        const isPending = uuid === _wifiPendingPreferredUuid;
        const star = row.querySelector('.wifi-btn-prefer');
        if (star) star.classList.toggle('wifi-prefer-active', isPending);

        // Update or add/remove preferred badge
        const info = row.querySelector('.wifi-row-info');
        let badge = info.querySelector('.wifi-badge-preferred');
        if (isPending && !badge) {
            badge = document.createElement('span');
            badge.className = 'wifi-badge wifi-badge-preferred';
            badge.textContent = t.wifi_preferred || 'Preferred';
            info.appendChild(badge);
        } else if (!isPending && badge) {
            badge.remove();
        }
    });
}

function _updateWifiSaveButton() {
    const t = window.translations || {};
    let saveBtn = document.getElementById('wifi-save-preferred');
    const changed = _wifiPendingPreferredUuid !== _wifiServerPreferredUuid;

    if (changed && !saveBtn) {
        // Create save button
        saveBtn = document.createElement('button');
        saveBtn.type = 'button';
        saveBtn.id = 'wifi-save-preferred';
        saveBtn.className = 'wifi-btn wifi-btn-save';
        saveBtn.textContent = t.save || 'Save';
        saveBtn.addEventListener('click', () => _saveWifiPreferred());
        // Insert after the saved list
        const list = document.getElementById('wifi-saved-list');
        if (list) list.after(saveBtn);
    } else if (!changed && saveBtn) {
        saveBtn.remove();
    }
}

function _saveWifiPreferred() {
    const t = window.translations || {};
    const saveBtn = document.getElementById('wifi-save-preferred');
    if (saveBtn) saveBtn.disabled = true;

    // Reset all priorities to 0, then set the pending one to 100
    fetch('/api/wifi/saved', { credentials: 'same-origin' })
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            const resets = data.connections
                .filter(c => c.priority > 0 && c.uuid !== _wifiPendingPreferredUuid)
                .map(c => fetch('/api/wifi/priority', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ uuid: c.uuid, priority: 0 }),
                }));
            return Promise.all(resets);
        })
        .then(() => {
            if (_wifiPendingPreferredUuid) {
                return fetch('/api/wifi/priority', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ uuid: _wifiPendingPreferredUuid, priority: 100 }),
                }).then(r => r.json());
            }
            return { success: true };
        })
        .then(data => {
            if (data.success) {
                _wifiServerPreferredUuid = _wifiPendingPreferredUuid;
                _updateWifiSaveButton();
                showNotification(
                    t.wifi_preferred_saved || 'Preferred WiFi saved. Change takes effect on next reboot.',
                    'success'
                );
            } else {
                _wifiModal({ title: data.error || 'Failed to save preferred', confirmText: 'OK' });
                if (saveBtn) saveBtn.disabled = false;
            }
        });
}

function _wifiModal({ title, message, inputType, inputPlaceholder, confirmText, cancelText, danger }) {
    return new Promise((resolve) => {
        const t = window.translations || {};
        const overlay = document.createElement('div');
        overlay.className = 'confirm-modal-overlay';

        const dialog = document.createElement('div');
        dialog.className = 'confirm-modal-dialog';

        let html = `<h3 class="confirm-modal-title">${title}</h3>`;
        if (message) html += `<p class="confirm-modal-message">${message}</p>`;
        if (inputType) {
            html += `<input type="${inputType}" class="form-input wifi-modal-input" placeholder="${inputPlaceholder || ''}" style="margin-bottom: 20px; width: 100%; box-sizing: border-box;" />`;
        }
        html += `<div class="confirm-modal-buttons">
            <button type="button" class="confirm-modal-btn cancel">${cancelText || t.cancel || 'Cancel'}</button>
            <button type="button" class="confirm-modal-btn ${danger ? 'danger' : 'confirm'}">${confirmText || 'OK'}</button>
        </div>`;
        dialog.innerHTML = html;
        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        requestAnimationFrame(() => overlay.classList.add('visible'));

        const input = dialog.querySelector('.wifi-modal-input');
        if (input) input.focus();

        const close = (value) => {
            overlay.classList.remove('visible');
            setTimeout(() => overlay.remove(), 200);
            resolve(value);
        };

        dialog.querySelector('.confirm-modal-btn.cancel').addEventListener('click', () => close(null));
        dialog.querySelector('.confirm-modal-btn.confirm, .confirm-modal-btn.danger').addEventListener('click', () => {
            close(input ? input.value : true);
        });
        overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });
        if (input) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') close(input.value); });
    });
}

function _deleteWifi(uuid) {
    const t = window.translations || {};
    _wifiModal({
        title: t.wifi_delete_confirm || 'Delete this network?',
        confirmText: t.delete || 'Delete',
        cancelText: t.cancel || 'Cancel',
        danger: true,
    }).then(confirmed => {
        if (!confirmed) return;
        fetch(`/api/wifi/saved/${uuid}`, { method: 'DELETE', credentials: 'same-origin' })
            .then(r => r.json())
            .then(data => {
                if (data.success) _loadSavedWifi();
                else _wifiModal({ title: data.error || 'Delete failed', confirmText: 'OK' });
            });
    });
}


function _addWifi(ssid, password, hidden) {
    const t = window.translations || {};
    ssid = ssid || document.getElementById('wifi-add-ssid')?.value.trim();
    password = password || document.getElementById('wifi-add-password')?.value;
    hidden = hidden ?? document.getElementById('wifi-add-hidden')?.checked;

    if (!ssid) return;

    fetch('/api/wifi/add', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ssid, password, hidden }),
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                document.getElementById('wifi-add-form').style.display = 'none';
                document.getElementById('wifi-add-ssid').value = '';
                document.getElementById('wifi-add-password').value = '';
                document.getElementById('wifi-add-hidden').checked = false;
                _loadSavedWifi();
            } else {
                _wifiModal({ title: data.error || t.wifi_add_failed || 'Failed to add network', confirmText: 'OK' });
            }
        });
}

function _scanWifi() {
    const t = window.translations || {};
    const container = document.getElementById('wifi-scan-results');
    if (!container) return;

    document.getElementById('wifi-add-form').style.display = 'none';
    container.style.display = 'block';
    container.innerHTML = `<div class="wifi-loading">${t.wifi_scanning || 'Scanning...'}</div>`;

    fetch('/api/wifi/scan', { credentials: 'same-origin' })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                container.innerHTML = `<div class="wifi-empty">${data.error || 'Scan failed'}</div>`;
                return;
            }
            if (!data.networks || data.networks.length === 0) {
                container.innerHTML = `<div class="wifi-empty">${t.wifi_no_networks || 'No networks found'}</div>`;
                return;
            }

            let html = `<div class="wifi-scan-header">${t.wifi_nearby_networks || 'Nearby Networks'}</div>`;
            data.networks.forEach(net => {
                const signalBars = net.signal >= 70 ? '▂▄▆█' : net.signal >= 50 ? '▂▄▆' : net.signal >= 30 ? '▂▄' : '▂';
                const savedLabel = net.saved ? ` <span class="wifi-badge wifi-badge-saved">${t.wifi_saved || 'Saved'}</span>` : '';
                const connectedLabel = net.in_use ? ` <span class="wifi-badge wifi-badge-connected">${t.wifi_connected || 'Connected'}</span>` : '';
                const securityIcon = `<span class="wifi-security-icon ${net.open ? 'wifi-security-icon--open' : 'wifi-security-icon--secured'}" title="${net.open ? (t.wifi_open || 'Open') : (t.wifi_secured || 'Secured')}"></span>`;

                html += `
                    <div class="wifi-scan-row${net.saved ? ' wifi-scan-saved' : ''}" data-ssid="${_escHtml(net.ssid)}" data-open="${net.open}">
                        <div class="wifi-row-info">
                            <span class="wifi-ssid">${securityIcon}${_escHtml(net.ssid)}</span>
                            ${connectedLabel}${savedLabel}
                        </div>
                        <div class="wifi-row-actions">
                            <span class="wifi-signal" title="${net.signal}%">${signalBars}</span>
                            ${(!net.saved && !net.in_use) ? `<button type="button" class="wifi-btn wifi-btn-add-scan">+ ${t.wifi_add_short || 'Add'}</button>` : ''}
                        </div>
                    </div>
                `;
            });
            container.innerHTML = html;

            // Wire add buttons for scanned networks
            container.querySelectorAll('.wifi-btn-add-scan').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const row = e.target.closest('.wifi-scan-row');
                    const ssid = row.dataset.ssid;
                    const isOpen = row.dataset.open === 'true';
                    if (isOpen) {
                        _addWifi(ssid, '', false);
                    } else {
                        _wifiModal({
                            title: `${t.wifi_enter_password || 'Enter password for'} "${ssid}"`,
                            inputType: 'password',
                            inputPlaceholder: t.wifi_password || 'Password',
                            confirmText: t.wifi_add_short || 'Add',
                        }).then(pw => {
                            if (pw !== null && pw !== '') _addWifi(ssid, pw, false);
                        });
                    }
                });
            });
        })
        .catch(() => {
            container.innerHTML = `<div class="wifi-empty">${t.wifi_scan_failed || 'Scan failed'}</div>`;
        });
}

function _escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function createSoftwareUpdateSection() {
    const formGroup = document.createElement('div');
    formGroup.className = 'form-group software-update-section';

    const label = document.createElement('label');
    label.className = 'form-label';
    label.textContent = window.translations?.software_update || 'Software Update';
    formGroup.appendChild(label);

    const wrapper = document.createElement('div');
    wrapper.className = 'update-wrapper';

    // Current version display
    const versionRow = document.createElement('div');
    versionRow.className = 'update-version-row';
    versionRow.innerHTML = `
        <span class="update-version-label">${window.translations?.current_version || 'Current version'}:</span>
        <span class="update-version-value" id="update-current-version">...</span>
        <button type="button" class="check-updates-btn" id="check-updates-btn">${window.translations?.check_for_updates || 'Check for Updates'}</button>
        <a href="#" target="_blank" rel="noopener" class="update-github-link" id="update-repo-link" style="display:none">View on GitHub</a>
    `;
    wrapper.appendChild(versionRow);

    // Release selector row
    const selectorRow = document.createElement('div');
    selectorRow.className = 'update-selector-row';

    const releaseLabel = document.createElement('label');
    releaseLabel.htmlFor = 'update-release-select';
    releaseLabel.textContent = window.translations?.select_version || 'Select version';
    releaseLabel.className = 'sr-only';
    selectorRow.appendChild(releaseLabel);

    const select = document.createElement('select');
    select.className = 'form-select update-release-select';
    select.id = 'update-release-select';
    const loadingOpt = document.createElement('option');
    loadingOpt.textContent = window.translations?.loading_releases || 'Loading releases...';
    loadingOpt.disabled = true;
    loadingOpt.selected = true;
    select.appendChild(loadingOpt);

    const updateBtn = document.createElement('button');
    updateBtn.type = 'button';
    updateBtn.className = 'update-install-btn';
    updateBtn.textContent = window.translations?.update_now || 'Update';
    updateBtn.disabled = true;

    selectorRow.appendChild(select);
    selectorRow.appendChild(updateBtn);
    wrapper.appendChild(selectorRow);

    // Release notes area (collapsed by default)
    const notesContainer = document.createElement('div');
    notesContainer.className = 'update-release-notes';
    notesContainer.id = 'update-release-notes';
    notesContainer.style.display = 'none';
    wrapper.appendChild(notesContainer);

    // SSH fallback info (hidden by default, shown on failure)
    const sshInfo = document.createElement('div');
    sshInfo.className = 'update-ssh-info';
    sshInfo.id = 'update-ssh-info';
    sshInfo.style.display = 'none';
    sshInfo.innerHTML = `
        <div class="form-info-box">
            <strong>${window.translations?.manual_update || 'Manual Update via SSH'}:</strong><br>
            <code class="info-copyable">ssh pi@mempaper.local</code><br>
            <code class="info-copyable">cd ~/btc-mempaper</code><br>
            <code class="info-copyable">git fetch --tags && git checkout &lt;tag&gt;</code><br>
            <code class="info-copyable">.venv/bin/pip install -r requirements.txt --quiet</code><br>
            <code class="info-copyable">sudo systemctl restart mempaper.service</code>
        </div>
    `;
    wrapper.appendChild(sshInfo);

    formGroup.appendChild(wrapper);

    // Show release notes when selection changes
    select.addEventListener('change', () => {
        const selectedOpt = select.options[select.selectedIndex];
        const body = selectedOpt?.dataset?.body;
        if (body) {
            notesContainer.innerHTML = _renderReleaseMarkdown(body);
            notesContainer.style.display = '';
        } else {
            notesContainer.style.display = 'none';
        }
    });

    // Install button click handler
    updateBtn.addEventListener('click', async () => {
        const selectedTag = select.value;
        if (!selectedTag) return;

        const selectedName = select.options[select.selectedIndex]?.textContent || selectedTag;
        const confirmed = await showConfirmModal({
            title: window.translations?.confirm_update || 'Install update',
            message: selectedName,
            confirmText: window.translations?.update_now || 'Update',
            cancelText: window.translations?.cancel || 'Cancel',
            icon: '/static/icons/update.svg'
        });
        if (!confirmed) return;

        _performUpdate(selectedTag, updateBtn);
    });

    // Fetch data on creation (pass versionEl directly since formGroup isn't in DOM yet)
    const versionEl = versionRow.querySelector('.update-version-value');
    _loadUpdateData(select, updateBtn, versionEl, notesContainer);

    // "Check for Updates" button — re-fetches releases
    const checkBtn = versionRow.querySelector('#check-updates-btn');
    checkBtn.addEventListener('click', async () => {
        checkBtn.disabled = true;
        checkBtn.classList.add('checking');
        select.innerHTML = '';
        const opt = document.createElement('option');
        opt.disabled = true;
        opt.selected = true;
        opt.textContent = window.translations?.loading_releases || 'Loading releases...';
        select.appendChild(opt);
        updateBtn.disabled = true;
        notesContainer.style.display = 'none';
        await _loadUpdateData(select, updateBtn, versionEl, notesContainer);
        checkBtn.disabled = false;
        checkBtn.classList.remove('checking');
    });

    return formGroup;
}

async function _loadUpdateData(selectEl, updateBtn, versionEl, notesContainer) {

    try {
        // Fetch current version and releases in parallel
        const [versionResp, releasesResp] = await Promise.all([
            fetch('/api/update/current'),
            fetch('/api/update/releases')
        ]);

        const versionData = await versionResp.json();
        const releasesData = await releasesResp.json();

        // Display current version
        if (versionData.success) {
            const tag = versionData.current_tag;
            const commit = versionData.current_commit;
            if (versionEl) {
                versionEl.textContent = tag ? `${tag} (${commit})` : commit;
            }
        }

        // Update repo link dynamically
        if (releasesData.success && releasesData.repo_url) {
            const repoLink = document.getElementById('update-repo-link');
            if (repoLink) {
                const isGitLab = releasesData.platform === 'GitLab';
                repoLink.href = releasesData.repo_url + (isGitLab ? '/-/releases' : '/releases');
                repoLink.textContent = (window.translations?.view_on_platform || 'View on {platform}').replace('{platform}', releasesData.platform || 'GitHub');
                repoLink.style.display = '';
            }
        }

        // Populate release dropdown
        if (releasesData.success && releasesData.releases.length > 0) {
            selectEl.innerHTML = '';
            const releases = releasesData.releases.filter(r => !r.draft);

            const latestTag = releases[0]?.tag;
            const hasUpdate = versionData.success && latestTag && versionData.current_tag !== latestTag;

            const latestLabel = window.translations?.latest_release_label || 'latest release';

            releases.forEach((rel, i) => {
                const opt = document.createElement('option');
                opt.value = rel.tag;
                const date = rel.published_at ? new Date(rel.published_at).toLocaleDateString() : '';
                const pre = rel.prerelease ? ' (pre-release)' : '';
                const isLatest = i === 0;
                const isCurrent = versionData.success && versionData.current_tag === rel.tag;
                const latestSuffix = isLatest ? ` (${latestLabel})` : '';
                opt.textContent = `${rel.name || rel.tag}${pre}${latestSuffix} — ${date}`;
                // Bold + orange for newest uninstalled release; bold only for current installed
                if (isLatest && hasUpdate) {
                    opt.style.fontWeight = 'bold';
                    opt.style.color = '#f7931a';
                } else if (isCurrent) {
                    opt.style.fontWeight = 'bold';
                }
                opt.dataset.body = rel.body || '';
                opt.dataset.isNew = (isLatest && hasUpdate) ? '1' : '';
                if (i === 0) opt.selected = true;
                selectEl.appendChild(opt);
            });

            // Style the closed select: bold+orange when new uninstalled release is selected
            function _updateSelectStyle() {
                const isNew = selectEl.options[selectEl.selectedIndex]?.dataset?.isNew === '1';
                selectEl.style.fontWeight = isNew ? 'bold' : '';
                selectEl.style.color = isNew ? '#f7931a' : '';
            }
            selectEl.addEventListener('change', _updateSelectStyle);
            _updateSelectStyle();
            // Clear select color while dropdown is open so individual option colors show
            selectEl.addEventListener('focus', () => { selectEl.style.color = ''; });
            selectEl.addEventListener('blur', _updateSelectStyle);

            updateBtn.disabled = false;

            // Show notes for first release
            if (releases[0]?.body && notesContainer) {
                notesContainer.innerHTML = _renderReleaseMarkdown(releases[0].body);
                notesContainer.style.display = '';
            }

            // Show update indicator on nav pill
            _showUpdateNavIndicator(hasUpdate, latestTag);

            // Toast notification when a new update is available
            if (hasUpdate) {
                const t = window.translations || {};
                const msg = (t.update_available_hint || 'Update {version} available').replace('{version}', latestTag);
                const updateIcon = _mpaSvgIcon(
                    'M240-120v-80l40-40H160q-33 0-56.5-23.5T80-320v-440q0-33 23.5-56.5T160-840h320v80H160v440h640v-120h80v120q0 33-23.5 56.5T800-240H680l40 40v80H240Zm360-240L400-560l56-56 104 103v-327h80v327l104-103 56 56-200 200Z',
                    'currentColor', 16, 'margin-right:4px;'
                );
                _buildLiveToast(
                    [updateIcon, ' ' + (t.software_update || 'Software Update')],
                    [msg],
                    '#F7931A',
                    8000
                );
            }
        } else {
            selectEl.innerHTML = '<option disabled selected>No releases found</option>';
        }
    } catch (err) {
        console.error('Failed to load update data:', err);
        selectEl.innerHTML = '<option disabled selected>Failed to load releases</option>';
        if (versionEl) {
            versionEl.textContent = 'unknown';
        }
    }
}

async function _performUpdate(tag, updateBtn) {
    updateBtn.disabled = true;
    updateBtn.textContent = window.translations?.updating || 'Updating...';

    const socket = window.configSocket;
    if (!socket) {
        showNotification('Error: no socket connection', 'error', 8000);
        updateBtn.disabled = false;
        updateBtn.textContent = window.translations?.update_now || 'Update';
        return;
    }

    // Capture current process startup timestamp before triggering update
    let oldStarted = 0;
    try {
        const hResp = await fetch('/api/health', { cache: 'no-store' });
        if (hResp.ok) {
            const hData = await hResp.json();
            oldStarted = hData.started || 0;
        }
    } catch (_) {}

    // Show update progress modal
    const overlay = document.createElement('div');
    overlay.className = 'confirm-modal-overlay';
    document.documentElement.style.setProperty('--scroll-y', `-${window.scrollY}px`);
    document.body.classList.add('modal-open');

    const dialog = document.createElement('div');
    dialog.className = 'confirm-modal-dialog system-update-dialog';

    const heading = document.createElement('h3');
    heading.className = 'confirm-modal-title';
    // `tag` is a release tag from the update API — escape before it becomes markup.
    heading.innerHTML = `<img src="/static/icons/update.svg" alt="" class="modal-title-icon"> ${escapeHtml((window.translations?.updating_to || 'Updating to') + ' ' + tag)}`;

    const phaseBar = document.createElement('div');
    phaseBar.className = 'system-update-phase';
    phaseBar.textContent = window.translations?.starting_update || 'Starting update...';

    const progressBar = document.createElement('div');
    progressBar.className = 'update-progress-bar-container';
    progressBar.innerHTML = '<div class="update-progress-bar update-progress-bar-indeterminate"></div>';

    const statusBar = document.createElement('div');
    statusBar.className = 'system-update-status';
    statusBar.textContent = window.translations?.running || 'Running...';

    const detailsToggle = document.createElement('button');
    detailsToggle.className = 'update-details-toggle';
    detailsToggle.textContent = window.translations?.show_details || 'Show details';
    detailsToggle.addEventListener('click', () => {
        const isHidden = logArea.classList.toggle('update-log-visible');
        detailsToggle.textContent = logArea.classList.contains('update-log-visible')
            ? (window.translations?.hide_details || 'Hide details')
            : (window.translations?.show_details || 'Show details');
    });

    const logArea = document.createElement('pre');
    logArea.className = 'system-update-log update-log-hidden';
    logArea.textContent = '';

    dialog.appendChild(heading);
    dialog.appendChild(phaseBar);
    dialog.appendChild(progressBar);
    dialog.appendChild(statusBar);
    dialog.appendChild(detailsToggle);
    dialog.appendChild(logArea);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('visible'));

    const phaseLabels = {
        git: (window.translations?.checking_out_code || 'Checking out {tag}...').replace('{tag}', tag),
        apt: window.translations?.installing_system_deps || 'Installing system dependencies...',
        pip: window.translations?.installing_python_deps || 'Installing Python dependencies...',
    };

    const _updateLineI18n = {
        'Re-minifying JavaScript and CSS...':          () => window.translations?.reminifying_js_css,
        'JavaScript and CSS minified successfully':    () => window.translations?.js_css_minified_success,
        'Minification failed — app will use source files': () => window.translations?.minification_failed,
        // Emitted by the updater around the post-install step…
        'Applying post-install system configuration...': () => window.translations?.applying_postinstall,
        'Skipping post-install configuration — run "sudo bash tools/install_wifi_permissions.sh" over SSH once to enable it':
            () => window.translations?.skipping_postinstall,
        // …and by tools/postinstall.sh itself, whose output is streamed through
        // verbatim. Keyed without the ▶ / ✅ / ⚠️ marker, which _translateUpdateLine
        // splits off and puts back, so the marker keeps carrying the severity.
        'Periodic TRIM':                               () => window.translations?.postinstall_trim_step,
        'TRIM supported — fstrim.timer already enabled (weekly)': () => window.translations?.postinstall_trim_already_on,
        'TRIM supported — fstrim.timer enabled (weekly)':         () => window.translations?.postinstall_trim_enabled,
        "TRIM works but fstrim.timer could not be enabled — run 'sudo fstrim /' periodically":
            () => window.translations?.postinstall_trim_timer_failed,
        'This card does not support TRIM — freed blocks keep their old contents':
            () => window.translations?.postinstall_trim_unsupported,
        'If it ever held wallet data in clear text, only re-flashing erases it':
            () => window.translations?.postinstall_trim_unsupported_note,
        'Post-install system configuration complete':  () => window.translations?.postinstall_complete,
    };

    // Leading status marker, kept as-is while the text after it is translated.
    const _UPDATE_LINE_MARKER = /^([▶✅⚠️⚠️]+\s*)(.+)$/;

    function _translateUpdateLine(line) {
        const direct = _updateLineI18n[line];
        if (direct) return direct() || line;
        const m = _UPDATE_LINE_MARKER.exec(line);
        if (m) {
            const inner = _updateLineI18n[m[2]];
            if (inner) {
                const translated = inner();
                if (translated) return m[1] + translated;
            }
        }
        return line;
    }

    function onUpdateOutput(data) {
        const t = window.translations || {};
        const displayLine = _translateUpdateLine(data.line);
        if (data.header) {
            const b = document.createElement('strong');
            b.textContent = displayLine;
            logArea.appendChild(b);
            logArea.appendChild(document.createTextNode('\n'));
        } else {
            logArea.appendChild(document.createTextNode(displayLine + '\n'));
        }
        var atBottom = logArea.scrollHeight - logArea.scrollTop - logArea.clientHeight < 40;
        if (atBottom) logArea.scrollTop = logArea.scrollHeight;
        if (data.phase && phaseLabels[data.phase]) {
            phaseBar.textContent = phaseLabels[data.phase];
        }
    }

    function _stopProgressBar() {
        const bar = progressBar.querySelector('.update-progress-bar');
        if (bar) {
            bar.classList.remove('update-progress-bar-indeterminate');
            bar.classList.add('update-progress-bar-done');
        }
    }

    function onUpdateDone(data) {
        socket.off('update_output', onUpdateOutput);
        socket.off('update_done', onUpdateDone);
        _stopProgressBar();

        if (data.success) {
            // Integrate countdown into existing modal (keep log visible)
            const t = window.translations || {};
            phaseBar.textContent = '';
            statusBar.textContent = '';

            // Replace progress bar with countdown UI
            progressBar.innerHTML = '';
            const countdown = document.createElement('div');
            countdown.className = 'restart-countdown';
            const countdownNumber = document.createElement('div');
            countdownNumber.className = 'restart-countdown-number';
            const estimatedSeconds = 25;
            countdownNumber.textContent = _fmtCountdown(estimatedSeconds);
            const countdownLabel = document.createElement('div');
            countdownLabel.className = 'restart-countdown-label';
            countdownLabel.textContent = t.waiting_for_service || 'Waiting for service...';
            countdown.appendChild(countdownNumber);
            countdown.appendChild(countdownLabel);
            progressBar.appendChild(countdown);

            const restartBar = document.createElement('div');
            restartBar.className = 'restart-progress-bar';
            const progressFill = document.createElement('div');
            progressFill.className = 'restart-progress-fill';
            restartBar.appendChild(progressFill);
            progressBar.appendChild(restartBar);
            progressBar.classList.remove('update-progress-bar-container');

            // Start countdown + polling (reuse shared logic)
            let remaining = estimatedSeconds;
            let polling = false;
            const earlyPollStart = 10;
            const interval = setInterval(() => {
                remaining--;
                if (remaining >= 0) {
                    countdownNumber.textContent = _fmtCountdown(remaining);
                    progressFill.style.transform = 'scaleX(' + (1 - remaining / estimatedSeconds) + ')';
                }
                if (remaining <= earlyPollStart && !polling) {
                    polling = true;
                    _pollForService(overlay, countdownNumber, countdownLabel, progressFill, interval, tag, data.rollback_tag, data.rollback_commit, oldStarted, updateBtn);
                }
                if (remaining === 0) {
                    countdownLabel.textContent = t.checking_service || 'Checking service...';
                    countdownNumber.innerHTML = '<div class="restart-spinner"></div>';
                }
            }, 1000);
        } else {
            phaseBar.textContent = '';
            statusBar.textContent = (window.translations?.update_failed || 'Update failed') + ': ' + (data.error || '');
            statusBar.classList.add('system-update-error');
            logArea.classList.remove('update-log-hidden');
            logArea.classList.add('update-log-visible');
            detailsToggle.textContent = window.translations?.hide_details || 'Hide details';
            const closeBtn = document.createElement('button');
            closeBtn.className = 'confirm-modal-btn confirm';
            closeBtn.textContent = window.translations?.close || 'Close';
            closeBtn.addEventListener('click', () => {
                overlay.classList.remove('visible');
                overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
                setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 350);
                document.body.classList.remove('modal-open');
                var _sy = document.documentElement.style.getPropertyValue('--scroll-y');
                document.documentElement.style.removeProperty('--scroll-y');
                window.scrollTo(0, parseInt(_sy || '0') * -1);
            });
            const buttons = document.createElement('div');
            buttons.className = 'confirm-modal-buttons';
            buttons.appendChild(closeBtn);
            dialog.appendChild(buttons);
            updateBtn.disabled = false;
            updateBtn.textContent = window.translations?.update_now || 'Update';
        }
    }

    socket.on('update_output', onUpdateOutput);
    socket.on('update_done', onUpdateDone);

    try {
        const resp = await fetch('/api/update/install', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tag })
        });

        const data = await resp.json();

        if (!data.success) {
            socket.off('update_output', onUpdateOutput);
            socket.off('update_done', onUpdateDone);
            _stopProgressBar();
            logArea.textContent = data.message || 'Failed to start update';
            logArea.classList.remove('update-log-hidden');
            logArea.classList.add('update-log-visible');
            detailsToggle.textContent = window.translations?.hide_details || 'Hide details';
            statusBar.textContent = data.message || 'Failed';
            statusBar.classList.add('system-update-error');
            const closeBtn = document.createElement('button');
            closeBtn.className = 'confirm-modal-btn confirm';
            closeBtn.textContent = window.translations?.close || 'Close';
            closeBtn.addEventListener('click', () => {
                overlay.classList.remove('visible');
                overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
                setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 350);
                document.body.classList.remove('modal-open');
                var _sy = document.documentElement.style.getPropertyValue('--scroll-y');
                document.documentElement.style.removeProperty('--scroll-y');
                window.scrollTo(0, parseInt(_sy || '0') * -1);
            });
            const buttons = document.createElement('div');
            buttons.className = 'confirm-modal-buttons';
            buttons.appendChild(closeBtn);
            dialog.appendChild(buttons);
            updateBtn.disabled = false;
            updateBtn.textContent = window.translations?.update_now || 'Update';
        }
    } catch (err) {
        console.error('Update request failed:', err);
        socket.off('update_output', onUpdateOutput);
        socket.off('update_done', onUpdateDone);
        _stopProgressBar();
        logArea.textContent = 'Request failed: ' + err;
        logArea.classList.remove('update-log-hidden');
        logArea.classList.add('update-log-visible');
        detailsToggle.textContent = window.translations?.hide_details || 'Hide details';
        statusBar.textContent = 'Request failed';
        statusBar.classList.add('system-update-error');
        const closeBtn = document.createElement('button');
        closeBtn.className = 'confirm-modal-btn confirm';
        closeBtn.textContent = window.translations?.close || 'Close';
        closeBtn.addEventListener('click', () => {
            overlay.classList.remove('visible');
            overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
            setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 350);
        });
        const buttons = document.createElement('div');
        buttons.className = 'confirm-modal-buttons';
        buttons.appendChild(closeBtn);
        dialog.appendChild(buttons);
        updateBtn.disabled = false;
        updateBtn.textContent = window.translations?.update_now || 'Update';
    }
}

function _appendUpdateFailureInfo(dialogEl, rollbackTag, rollbackCommit) {
    const t = window.translations || {};
    const rollbackRef = rollbackTag || rollbackCommit || 'previous commit';
    const sshInfo = document.createElement('div');
    sshInfo.className = 'system-update-ssh-fallback';
    sshInfo.innerHTML = `
        <p>${t.connect_via_ssh || 'Connect via SSH to check'}:</p>
        <code>ssh pi@mempaper.local</code><br>
        <code>sudo systemctl status mempaper</code><br>
        <code>sudo journalctl -u mempaper -n 50</code>
        <p style="margin-top:8px">${t.to_rollback || 'To rollback'}:</p>
        <code>cd ~/btc-mempaper</code><br>
        <code>git checkout ${_escHtml(rollbackRef)}</code><br>
        <code>sudo systemctl restart mempaper</code>
    `;
    dialogEl.appendChild(sshInfo);
}

// ── Display Driver Install ──────────────────────────────────

let _driverInstallInProgress = false;

async function _installDisplayDrivers(deviceId) {
    // Called from two save paths — ignore the second concurrent call
    if (_driverInstallInProgress) return;
    _driverInstallInProgress = true;

    // Show installing toast
    const existing = document.getElementById('update-countdown-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.id = 'update-countdown-toast';
    toast.className = 'update-countdown-toast';
    toast.innerHTML = `
        <div class="update-toast-title">${window.translations?.installing_display_drivers || 'Installing display drivers'}...</div>
        <div class="update-toast-status" id="update-toast-status">${window.translations?.downloading_drivers || 'Downloading drivers for'} ${deviceId}</div>
        <div class="update-toast-progress">
            <div class="update-toast-progress-bar" style="width:100%;transform:scaleX(0.3);transition:transform 10s linear;transform-origin:left"></div>
        </div>
        <div class="update-toast-hint">${window.translations?.please_wait || 'Please wait'}</div>
    `;
    document.body.appendChild(toast);

    // Animate progress bar while waiting
    requestAnimationFrame(() => {
        const bar = toast.querySelector('.update-toast-progress-bar');
        if (bar) bar.style.transform = 'scaleX(0.8)';
    });

    try {
        const resp = await fetch('/api/display/install-drivers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_id: deviceId })
        });

        const data = await resp.json();
        const statusEl = toast.querySelector('#update-toast-status');
        const bar = toast.querySelector('.update-toast-progress-bar');

        if (data.success) {
            if (bar) bar.style.transform = 'scaleX(1)';

            if (data.spi_required) {
                const spiMsg = window.translations?.spi_not_enabled || 'SPI interface not enabled';
                const spiCmd = 'sudo raspi-config nonint do_spi 0 && sudo reboot';
                if (statusEl) statusEl.innerHTML =
                    `${spiMsg}:<br><code style="font-size:0.8em">${spiCmd}</code>`;
                toast.classList.add('update-toast-error');
                toast.innerHTML += `
                    <button class="update-toast-dismiss" onclick="this.closest('.update-countdown-toast').remove()">
                        ${window.translations?.dismiss || 'Dismiss'}
                    </button>
                `;
            } else if (data.restart_required) {
                if (statusEl) statusEl.innerHTML = '<span class="update-spinner"></span> ' + (window.translations?.drivers_installed_restarting || 'Drivers installed! Service restarting...');
                toast.classList.add('update-toast-success');
                // Poll for service to come back, then reload
                _startDriverHealthPolling(toast);
            } else if (!data.installed) {
                // Nothing was downloaded or installed — dismiss silently
                toast.remove();
            } else {
                if (statusEl) statusEl.textContent = data.message;
                toast.classList.add('update-toast-success');
                setTimeout(() => toast.remove(), 3000);
            }
        } else {
            if (bar) bar.style.transform = 'scaleX(1)';
            if (statusEl) statusEl.textContent = data.message || 'Driver installation failed';
            toast.classList.add('update-toast-error');
            toast.innerHTML += `
                <button class="update-toast-dismiss" onclick="this.closest('.update-countdown-toast').remove()">
                    ${window.translations?.dismiss || 'Dismiss'}
                </button>
            `;
        }
    } catch (err) {
        console.error('Driver install request failed:', err);
        const statusEl = toast.querySelector('#update-toast-status');
        if (statusEl) statusEl.textContent = 'Driver install request failed';
        toast.classList.add('update-toast-error');
        toast.innerHTML += `
            <button class="update-toast-dismiss" onclick="this.closest('.update-countdown-toast').remove()">
                ${window.translations?.dismiss || 'Dismiss'}
            </button>
        `;
    } finally {
        _driverInstallInProgress = false;
    }
}

function _startDriverHealthPolling(toast) {
    const statusEl = toast.querySelector('#update-toast-status');
    let attempts = 0;
    const maxAttempts = 60;

    const pollInterval = setInterval(async () => {
        attempts++;
        try {
            const hResp = await fetch('/api/health', { cache: 'no-store' });
            if (hResp.ok) {
                clearInterval(pollInterval);
                if (statusEl) statusEl.textContent = window.translations?.update_complete || 'Update complete!';
                setTimeout(() => location.reload(), 1500);
                return;
            }
        } catch (_) {}

        if (attempts >= maxAttempts) {
            clearInterval(pollInterval);
            if (statusEl) statusEl.textContent = window.translations?.service_not_responding || 'Service not responding';
            toast.classList.add('update-toast-error');
            toast.innerHTML += `
                <button class="update-toast-dismiss" onclick="this.closest('.update-countdown-toast').remove()">
                    ${window.translations?.dismiss || 'Dismiss'}
                </button>
            `;
        }
    }, 2000);
}

// ── Mempool over Tor ───────────────────────────────────────────

// Swap the host field's placeholder between a clearnet host and an .onion
// address, and attach the known-onion dropdown when Tor is on.
//
// A <datalist> rather than a <select>: it gives the dropdown of known
// addresses while leaving the field free-text, so anyone running their own
// hidden service can still type it. A select would force a "Custom…" branch.
function _applyTorHostHint(hostInput, torOn) {
    if (!hostInput) return;
    const t = window.translations || {};
    hostInput.placeholder = torOn
        ? (t.mempool_host_placeholder_tor || 'youronionaddress....onion')
        : '192.168.0.119 or mempool.mydomain.com';

    const LIST_ID = 'mempool-onion-presets';
    let list = document.getElementById(LIST_ID);

    if (!torOn) {
        hostInput.removeAttribute('list');
        if (list) list.remove();
        return;
    }

    const presets = (window.mempoolOnionPresets || []);
    if (!presets.length) return;

    if (!list) {
        list = document.createElement('datalist');
        list.id = LIST_ID;
        hostInput.parentNode.appendChild(list);
    }
    list.innerHTML = '';
    presets.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.host;
        opt.label = p.label;
        list.appendChild(opt);
    });
    hostInput.setAttribute('list', LIST_ID);
}

// Over Tor the TLS settings stop carrying their usual meaning: an onion service
// is already authenticated and encrypted by the circuit itself, and its address
// *is* the server's public key. Grey the TLS controls out rather than hiding
// them, so it stays visible that they were deliberately taken out of play.
// Mirrors the two transport slots in config_manager.validate_config: clearnet
// and Tor each keep their own ports, and the Tor toggle chooses which pair is
// live. Swapping the fields here means what the user sees always matches the
// slot that will actually be saved — without it the form would post clearnet
// ports on the save that turns Tor on.
const _TRANSPORT_SLOT_FALLBACK = {
    clearnet: { rest: 443, ws: 443 },
    tor:      { rest: 80,  ws: 80  },
};

function _transportEls() {
    return {
        rest:  document.querySelector('[data-config-key="mempool_rest_port"]'),
        ws:    document.querySelector('[data-config-key="mempool_ws_port"]'),
        https: document.querySelector('[data-config-key="mempool_use_https"]'),
    };
}

function _swapTransportSlot(torOn) {
    const cfg = window.currentConfig || (window.currentConfig = {});
    const els = _transportEls();
    const leaving  = torOn ? 'clearnet' : 'tor';
    const entering = torOn ? 'tor' : 'clearnet';

    // Stash whatever is on screen into the slot being left, so a port typed
    // just before flipping the toggle is not thrown away.
    if (els.rest) cfg[`mempool_rest_port_${leaving}`] = els.rest.value;
    if (els.ws)   cfg[`mempool_ws_port_${leaving}`]   = els.ws.value;
    if (leaving === 'clearnet' && els.https && typeof els.https.getValue === 'function') {
        cfg.mempool_use_https_clearnet = !!els.https.getValue();
    }

    const fb   = _TRANSPORT_SLOT_FALLBACK[entering];
    const rest = cfg[`mempool_rest_port_${entering}`] ?? fb.rest;
    const ws   = cfg[`mempool_ws_port_${entering}`]   ?? fb.ws;

    // 'input' keeps any listener watching these fields (dirty-tracking, the
    // Check Mempool button) in step with the programmatic change.
    if (els.rest) { els.rest.value = rest; els.rest.dispatchEvent(new Event('input', { bubbles: true })); }
    if (els.ws)   { els.ws.value   = ws;   els.ws.dispatchEvent(new Event('input', { bubbles: true })); }

    // Tor is always plain http — the onion address is the service's public key,
    // so the circuit already authenticates the endpoint.
    if (els.https && typeof els.https.setValue === 'function') {
        els.https.setValue(torOn ? false : (cfg.mempool_use_https_clearnet !== false));
    }

    const t = window.translations || {};
    const scheme = torOn ? 'http' : ((cfg.mempool_use_https_clearnet !== false) ? 'https' : 'http');
    const tpl = torOn
        ? (t.tor_ports_switched || 'Tor enabled — using {scheme} on port {port}. Your previous settings are kept for when you switch back.')
        : (t.clearnet_ports_restored || 'Tor disabled — restored {scheme} on port {port}.');
    if (typeof showNotification === 'function') {
        showNotification(tpl.replace('{scheme}', scheme).replace('{port}', rest), 'info');
    }
}

// null until the first render, so the initial paint does not look like a toggle
let _torModeLastApplied = null;

function _applyTorMode(torOn) {
    const t = window.translations || {};

    if (_torModeLastApplied !== null && _torModeLastApplied !== torOn) {
        _swapTransportSlot(torOn);
    }
    _torModeLastApplied = torOn;

    _applyTorHostHint(document.getElementById('mempool-host-input'), torOn);

    ['mempool_use_https', 'mempool_verify_ssl'].forEach(k => {
        const el = document.querySelector(`[data-config-key="${k}"]`);
        if (!el) return;
        const group = el.closest('.form-group') || el.parentElement;
        if (!group) return;
        group.style.opacity = torOn ? '0.45' : '';
        group.style.pointerEvents = torOn ? 'none' : '';
        group.title = torOn
            ? (t.tls_not_needed_over_tor || 'Not needed over Tor — the onion circuit already provides encryption and authentication.')
            : '';
    });

    // Basic Auth is redundant over Tor: an onion address is self-authenticating,
    // so the circuit already establishes both who the service is and that nobody
    // else can read it. Hide the credential fields to keep the form clean.
    //
    // Only when they are empty, though. A stored password that is invisible but
    // still sent on every request is worse than a little clutter, so an existing
    // value stays on screen, dimmed, and remains editable so it can be cleared.
    ['mempool_username', 'mempool_password'].forEach(k => {
        const el = document.querySelector(`[data-config-key="${k}"]`);
        if (!el) return;
        const group = el.closest('.form-group') || el.parentElement;
        if (!group) return;
        const hasValue = !!(typeof el.getValue === 'function' ? el.getValue() : el.value);
        group.style.display = (torOn && !hasValue) ? 'none' : '';
        group.style.opacity = (torOn && hasValue) ? '0.45' : '';
        group.title = (torOn && hasValue)
            ? (t.auth_not_needed_over_tor
               || 'Not needed over Tor — the onion address authenticates the service. '
                  + 'Clear this unless your onion mempool also requires Basic Auth.')
            : '';
    });

    ['tor_socks_host', 'tor_socks_port'].forEach(k => {
        const el = document.querySelector(`[data-config-key="${k}"]`);
        const group = el && (el.closest('.form-group') || el.parentElement);
        if (group) group.style.display = torOn ? '' : 'none';
    });
}

// ── Tang disable guard ─────────────────────────────────────────────────
// Switching Tang off has to unseal everything first, which needs the server.
// If it cannot be reached the sealed data can never be opened again, so the
// only way off is to delete it. That is not something to do on a stray click,
// and it must never happen silently, so the toggle is intercepted here and the
// operator is told exactly what would be destroyed.
async function _confirmTangDisable() {
    let preview;
    try {
        const resp = await fetch('/api/tang/disable-preview');
        if (!resp.ok) throw new Error('preview failed');
        preview = await resp.json();
    } catch (e) {
        // Cannot tell how bad this is, so assume the worst rather than
        // letting a silent failure delete anything.
        preview = { recoverable: false, items: [], reason: 'Could not reach mempaper.' };
    }

    if (preview.recoverable) return true;

    const t = window.translations || {};
    // Labels only. The path is still returned by the endpoint and goes to the
    // server log, but a filename in a confirmation dialog tells a non-technical
    // owner nothing about what they are losing.
    const list = (preview.items || []).map(i => `  • ${i.label}`).join('\n');
    const message =
        (t.tang_disable_unreachable
         || 'The Tang server cannot be reached, so this data cannot be decrypted and '
          + 'turning encryption off would delete it permanently.')
        + '\n\n' + (preview.reason || '')
        + '\n\n' + (t.tang_disable_will_delete || 'This will be deleted:')
        + '\n' + (list || (t.tang_nothing_sealed || '  (nothing sealed yet)'))
        + '\n\n' + (t.tang_disable_recover_hint
                    || 'Bring the Tang server back online and try again to keep it. '
                     + 'Wallet addresses would have to be entered again.');

    return await window.showConfirmModal({
        title: t.tang_disable_title || 'Delete encrypted data?',
        message,
        confirmText: t.tang_disable_confirm || 'Delete permanently',
        cancelText: t.cancel || 'Cancel',
        danger: true,
    });
}

function _initTangToggleWatch() {
    const toggle = document.querySelector('[data-config-key="tang_enabled"]');
    if (!toggle || toggle.dataset.tangGuard === '1') return;
    toggle.dataset.tangGuard = '1';

    const readState = () => {
        if (typeof toggle.getValue === 'function') return !!toggle.getValue();
        if (toggle.type === 'checkbox') return toggle.checked;
        return !!(window.currentConfig || {}).tang_enabled;
    };

    const wasEnabled = !!(window.currentConfig || {}).tang_enabled;
    if (!wasEnabled) return;   // nothing sealed, nothing to lose

    const restore = () => {
        if (typeof toggle.setValue === 'function') toggle.setValue(true);
        else if (toggle.type === 'checkbox') toggle.checked = true;
        else toggle.click();
    };

    ['change', 'click'].forEach(ev => toggle.addEventListener(ev, () => setTimeout(async () => {
        if (readState()) return;                     // being switched on, not off

        const proceed = await _confirmTangDisable();
        if (proceed !== true) { restore(); return; }

        // Unlike every other field on this page, this cannot wait for Save.
        // Turning sealing off has to rewrite each file in the clear, or delete
        // what can no longer be opened, and that is a server-side migration.
        // Merely flipping the flag and saving would leave the data sealed while
        // the app treated it as plain text - unreadable, with the key gone.
        // The endpoint performs the migration and persists tang_enabled itself.
        const t = window.translations || {};
        try {
            const resp = await fetch('/api/tang/disable', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ discard: true }),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.error || `HTTP ${resp.status}`);

            if (window.currentConfig) window.currentConfig.tang_enabled = false;
            const summary = data.deleted
                ? `${data.deleted} sealed file(s) deleted.`
                : `${data.unsealed || 0} file(s) decrypted and kept.`;
            if (typeof window.showNotification === 'function') {
                window.showNotification(`${t.tang_disabled || 'Tang encryption disabled'} — ${summary}`, 'success');
            }
        } catch (e) {
            // The migration did not complete, so the data is still sealed.
            // Leaving the toggle off would misrepresent that.
            restore();
            if (typeof window.showNotification === 'function') {
                window.showNotification(`${t.tang_disable_failed || 'Could not disable Tang'}: ${e.message}`, 'error');
            }
        }
    }, 0)));
}

function _initTorToggleWatch() {
    const toggle = document.querySelector('[data-config-key="mempool_use_tor"]');
    if (!toggle) return;

    const readState = () => {
        if (typeof toggle.getValue === 'function') return !!toggle.getValue();
        if (toggle.type === 'checkbox') return toggle.checked;
        return !!(window.currentConfig && window.currentConfig.mempool_use_tor);
    };

    // Re-rendering the form (a language change, say) rebuilds these elements.
    // Clear the sentinel first so the fresh paint is treated as an initial
    // render and not as the user flipping the toggle.
    _torModeLastApplied = null;
    _applyTorMode(readState());
    // Boolean switches here are div-based and emit 'change' on toggle; listen for
    // click too so the state is picked up either way.
    ['change', 'click'].forEach(ev =>
        toggle.addEventListener(ev, () => setTimeout(() => _applyTorMode(readState()), 0))
    );
}

// ── Display Select Hint ────────────────────────────────────────
function _setDisplayHint(hint, state) {
    // state: 'ok' | 'error'
    if (state === 'error') {
        hint.style.color = 'var(--danger,#ef4444)';
        hint.textContent = window.translations?.wrong_display_driver_detected ||
            'Wrong display driver detected — re-run install.sh to configure the correct display.';
    } else {
        hint.style.color = 'var(--text-muted,#888)';
        hint.textContent = window.translations?.display_change_via_install || 'To change display type, re-run install.sh on the Pi.';
    }
}

async function _enhanceDisplaySelect() {
    const selectEl = document.querySelector('[data-config-key="omni_device_name"]');
    if (!selectEl || selectEl.tagName !== 'SELECT') return;

    selectEl.title = window.translations?.display_change_via_install || 'Change display type by re-running install.sh on the Pi';

    let hint = document.getElementById('display-driver-hint');
    if (!hint) {
        hint = document.createElement('div');
        hint.id = 'display-driver-hint';
        hint.style.cssText = 'margin-top:6px;font-size:12px;padding:4px 8px;border-radius:6px;line-height:1.4;';
        selectEl.parentNode.insertBefore(hint, selectEl.nextSibling);
    }

    const statusData = await fetch('/api/display/status').then(r => r.ok ? r.json() : null).catch(() => null);
    _setDisplayHint(hint, statusData?.error ? 'error' : 'ok');
}

// ── System Package Update ────────────────────────────────────

function createSystemUpdateSection() {
    const formGroup = document.createElement('div');
    formGroup.className = 'form-group system-update-section';

    const label = document.createElement('label');
    label.className = 'form-label';
    label.textContent = window.translations?.system_packages || 'System Packages';
    formGroup.appendChild(label);

    const wrapper = document.createElement('div');
    wrapper.className = 'update-wrapper';

    const row = document.createElement('div');
    row.className = 'update-selector-row';

    const hint = document.createElement('span');
    hint.className = 'system-update-hint';
    hint.textContent = window.translations?.system_update_hint || 'Update Raspberry Pi system packages (apt upgrade)';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'update-install-btn';
    btn.textContent = window.translations?.update_packages || 'Update';

    row.appendChild(hint);
    row.appendChild(btn);
    wrapper.appendChild(row);
    formGroup.appendChild(wrapper);

    btn.addEventListener('click', async () => {
        const confirmed = await showConfirmModal({
            title: window.translations?.system_update || 'System Update',
            message: window.translations?.system_update_confirm || 'Run apt update && apt upgrade on this device? This may take several minutes.',
            confirmText: window.translations?.update_packages || 'Update',
            cancelText: window.translations?.cancel || 'Cancel',
            icon: '/static/icons/update.svg'
        });
        if (!confirmed) return;

        _startSystemUpdate(btn);
    });

    return formGroup;
}

// ── SSH Access (admin key management) ────────────────────────

function createSshAccessSection() {
    const t = window.translations || {};

    const KEY_TYPE_FILE = {
        'ssh-ed25519':                        'id_ed25519',
        'ssh-rsa':                            'id_rsa',
        'ssh-dss':                            'id_dsa',
        'ecdsa-sha2-nistp256':                'id_ecdsa',
        'ecdsa-sha2-nistp384':                'id_ecdsa',
        'ecdsa-sha2-nistp521':                'id_ecdsa',
        'sk-ssh-ed25519@openssh.com':         'id_ed25519_sk',
        'sk-ecdsa-sha2-nistp256@openssh.com': 'id_ecdsa_sk',
    };
    const VALID_KEY_TYPES = Object.keys(KEY_TYPE_FILE);
    // Use the global _RE_SSH_KEY so _validationMsg() can match by reference
    const SSH_KEY_RE = _RE_SSH_KEY;

    const formGroup = document.createElement('div');
    formGroup.className = 'form-group ssh-access-section';

    const label = document.createElement('label');
    label.className = 'form-label';
    label.textContent = t.ssh_access || 'SSH Access';
    formGroup.appendChild(label);

    const wrapper = document.createElement('div');
    wrapper.className = 'ssh-access-wrapper';

    const hint = document.createElement('p');
    hint.className = 'ssh-access-hint';
    hint.innerHTML = t.ssh_access_hint || 'Paste the contents of <code>~/.ssh/id_ed25519.pub</code> to grant SSH access to this device.';
    wrapper.appendChild(hint);

    // ── Table ─────────────────────────────────────────────────
    const table = document.createElement('table');
    table.className = 'ssh-table';

    const thead = document.createElement('thead');
    const hRow = document.createElement('tr');
    [t.ssh_col_key || 'Public Key', t.ssh_col_connect || 'SSH Connect Command', ''].forEach(txt => {
        const th = document.createElement('th');
        th.textContent = txt;
        hRow.appendChild(th);
    });
    thead.appendChild(hRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    table.appendChild(tbody);
    wrapper.appendChild(table);

    // ── Add Key button ─────────────────────────────────────────
    const addBtn = document.createElement('button');
    addBtn.type = 'button';
    addBtn.className = 'ssh-add-btn';
    addBtn.textContent = t.ssh_add_key || 'Add Key';
    wrapper.appendChild(addBtn);

    // ── Status message (inline feedback after main save) ───────
    const statusMsg = document.createElement('div');
    statusMsg.className = 'ssh-status-msg';
    wrapper.appendChild(statusMsg);

    formGroup.appendChild(wrapper);

    // ── State ──────────────────────────────────────────────────
    let savedKeys = [];
    let lanIp = null;

    fetch('/api/system/lan-ip')
        .then(r => r.json())
        .then(d => { if (d.success) { lanIp = d.ip; refreshAllCmds(); } })
        .catch(() => {});

    function showStatus(text, isError) {
        statusMsg.textContent = text;
        statusMsg.className = 'ssh-status-msg ' + (isError ? 'ssh-status-error' : 'ssh-status-ok');
        setTimeout(() => { statusMsg.textContent = ''; statusMsg.className = 'ssh-status-msg'; }, 4000);
    }

    function currentKeys() {
        return Array.from(tbody.querySelectorAll('.ssh-key-input'))
            .map(inp => inp.value.trim())
            .filter(v => v);
    }

    function buildSshCmd(keyLine) {
        const host = lanIp || window.location.hostname;
        const parts = keyLine.trim().split(/\s+/);
        const keyFile = KEY_TYPE_FILE[parts[0]] || 'id_ed25519';
        return `ssh -i ~/.ssh/${keyFile} pi@${host}`;
    }

    function updateCmdCell(cmdCell, keyText) {
        cmdCell.innerHTML = '';
        if (!keyText) return;
        const parts = keyText.trim().split(/\s+/);
        if (!VALID_KEY_TYPES.includes(parts[0]) || !parts[1]) {
            const hint = document.createElement('span');
            hint.className = 'ssh-unsaved-hint';
            hint.textContent = '…';
            cmdCell.appendChild(hint);
            return;
        }
        const cmd = buildSshCmd(keyText);
        const code = document.createElement('code');
        code.className = 'ssh-connect-cmd';
        code.textContent = cmd;
        code.title = t.click_to_copy || 'Click to copy';
        code.addEventListener('click', () => {
            const copy = () => {
                const ta = document.createElement('textarea');
                ta.value = cmd;
                ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;pointer-events:none';
                document.body.appendChild(ta);
                ta.focus(); ta.select();
                try { document.execCommand('copy'); } catch (_) {}
                document.body.removeChild(ta);
                code.classList.add('copied');
                setTimeout(() => code.classList.remove('copied'), 2000);
            };
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(cmd)
                    .then(() => { code.classList.add('copied'); setTimeout(() => code.classList.remove('copied'), 2000); })
                    .catch(copy);
            } else {
                copy();
            }
        });
        cmdCell.appendChild(code);
    }

    function refreshAllCmds() {
        tbody.querySelectorAll('tr').forEach(tr => {
            const inp = tr.querySelector('.ssh-key-input');
            const cmdCell = tr.querySelector('.ssh-cell-cmd');
            if (inp && cmdCell) updateCmdCell(cmdCell, inp.value.trim());
        });
    }

    function addRow(keyValue) {
        const tr = document.createElement('tr');

        // Col 1: editable key input
        const keyCell = document.createElement('td');
        keyCell.className = 'ssh-cell-key';
        const inp = document.createElement('input');
        inp.type = 'text';
        inp.className = 'ssh-key-input';
        inp.value = keyValue || '';
        inp.placeholder = t.ssh_key_placeholder || 'ssh-ed25519 AAAA…';
        inp.spellcheck = false;
        inp.autocomplete = 'off';
        keyCell.appendChild(inp);
        tr.appendChild(keyCell);

        // Col 2: derived connect command
        const cmdCell = document.createElement('td');
        cmdCell.className = 'ssh-cell-cmd';
        updateCmdCell(cmdCell, keyValue || '');
        tr.appendChild(cmdCell);

        // Col 3: delete
        const actCell = document.createElement('td');
        actCell.className = 'ssh-cell-actions';
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'ssh-remove-btn';
        removeBtn.title = t.remove || 'Remove';
        removeBtn.innerHTML = '<img src="/static/icons/delete.svg" alt="Remove" class="table-delete-icon" />';
        removeBtn.addEventListener('click', () => { tr.remove(); _updateFormValidity(); _checkDirty(); });
        actCell.appendChild(removeBtn);
        tr.appendChild(actCell);

        inp.addEventListener('input', () => {
            _validateInput(inp, SSH_KEY_RE, true);
            updateCmdCell(cmdCell, inp.value.trim());
        });
        inp.addEventListener('paste', () => {
            setTimeout(() => {
                inp.value = inp.value.trim();
                _validateInput(inp, SSH_KEY_RE, true);
                updateCmdCell(cmdCell, inp.value);
            }, 0);
        });

        if (inp.value) _validateInput(inp, SSH_KEY_RE, true);
        tbody.appendChild(tr);
        return inp;
    }

    addBtn.addEventListener('click', () => {
        const inp = addRow('');
        inp.focus();
    });

    // Expose dirty-check so _checkDirty() can reflect SSH changes without snapshot timing issues
    window._sshIsDirty = () => JSON.stringify(currentKeys()) !== JSON.stringify(savedKeys);

    // Register hook so the main Save button also saves SSH keys
    window._sshSaveHook = async () => {
        const keys = currentKeys();
        if (JSON.stringify(keys) === JSON.stringify(savedKeys)) return; // no change
        for (const key of keys) {
            if (!SSH_KEY_RE.test(key)) {
                showStatus((t.ssh_invalid_key || 'Invalid SSH key') + ': ' + key.slice(0, 40) + '…', true);
                throw new Error('Invalid SSH key');
            }
        }
        const resp = await fetch('/api/system/ssh-keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keys })
        });
        const data = await resp.json();
        if (data.success) {
            savedKeys = [...keys];
            showStatus(`${data.key_count} ${t.ssh_keys_saved || 'key(s) saved.'}`, false);
        } else {
            showStatus(data.error || t.ssh_save_error || 'Failed to save SSH keys.', true);
            throw new Error(data.error || 'Failed to save SSH keys');
        }
    };

    // Load existing keys
    fetch('/api/system/ssh-keys')
        .then(r => r.json())
        .then(data => {
            if (data.success && Array.isArray(data.keys)) {
                savedKeys = [...data.keys];
                savedKeys.forEach(key => addRow(key));
            }
        })
        .catch(() => {});

    return formGroup;
}

// ── Device Control (Restart / Reboot) ────────────────────────

function createDeviceControlSection() {
    const t = window.translations || {};
    const formGroup = document.createElement('div');
    formGroup.className = 'form-group device-control-section';

    const label = document.createElement('label');
    label.className = 'form-label';
    label.textContent = t.device_control || 'Device Control';
    formGroup.appendChild(label);

    const wrapper = document.createElement('div');
    wrapper.className = 'update-wrapper device-control-wrapper';

    // Restart Service button
    const restartBtn = document.createElement('button');
    restartBtn.type = 'button';
    restartBtn.className = 'device-control-btn';
    restartBtn.innerHTML = `<span class="device-control-icon"><svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 -960 960 960" width="18px" fill="currentColor"><path d="M480-160q-134 0-227-93t-93-227q0-134 93-227t227-93q69 0 132 28.5T720-690v-110h80v280H520v-80h168q-32-56-87.5-88T480-720q-100 0-170 70t-70 170q0 100 70 170t170 70q77 0 139-44t87-116h84q-28 106-114 173t-196 67Z"/></svg></span> ${t.restart_service || 'Restart Service'}`;

    restartBtn.addEventListener('click', async () => {
        const ok = await showConfirmModal({
            title: t.restart_service || 'Restart Service',
            message: t.restart_service_confirm || 'Restart the mempaper service? The page will reload when the service is back.',
            confirmText: t.restart || 'Restart',
            cancelText: t.cancel || 'Cancel',
            icon: '/static/icons/restart.svg',
        });
        if (!ok) return;
        _performSystemAction('/api/system/restart-service', t.restart_service || 'Restart Service', 25);
    });

    // Reboot Device button
    const rebootBtn = document.createElement('button');
    rebootBtn.type = 'button';
    rebootBtn.className = 'device-control-btn device-control-btn-danger';
    rebootBtn.innerHTML = `<span class="device-control-icon"><svg xmlns="http://www.w3.org/2000/svg" height="18px" viewBox="0 -960 960 960" width="18px" fill="currentColor"><path d="M324-111.5Q251-143 197-197t-85.5-127Q80-397 80-480t31.5-156Q143-709 197-763t127-85.5Q397-880 480-880t156 31.5Q709-817 763-763t85.5 127Q880-563 880-480t-31.5 156Q817-251 763-197t-127 85.5Q563-80 480-80t-156-31.5ZM707-253q93-93 93-227t-93-227q-93-93-227-93t-227 93q-93 93-93 227t93 227q93 93 227 93t227-93Zm-57-57q70-70 70-170 0-51-19-94.5T650-650l-57 57q22 22 34.5 51t12.5 62q0 66-47 113t-113 47q-66 0-113-47t-47-113q0-33 12.5-62t34.5-51l-57-57q-32 32-51 75.5T240-480q0 100 70 170t170 70q100 0 170-70ZM440-480h80v-240h-80v240Zm40 0Z"/></svg></span> ${t.reboot_device || 'Reboot Device'}`;

    rebootBtn.addEventListener('click', async () => {
        const ok = await showConfirmModal({
            title: t.reboot_device || 'Reboot Device',
            message: t.reboot_device_confirm || 'Reboot the entire device? This can take a couple of minutes (Wi-Fi reconnect time varies). The page will reload when the service is back.',
            confirmText: t.reboot || 'Reboot',
            cancelText: t.cancel || 'Cancel',
            danger: true,
            icon: '/static/icons/reboot.svg',
        });
        if (!ok) return;
        // A full device reboot (OS boot + service startup + Wi-Fi reconnect) can run
        // noticeably longer than a plain service restart, but how long varies a lot
        // run to run (Wi-Fi/DNS reconnect is the long pole and isn't consistent) — so
        // start checking for real early (30s in) rather than waiting almost the whole
        // estimate, and give polling a long runway after that before giving up with
        // "Service not responding".
        _performSystemAction('/api/system/reboot', t.reboot_device || 'Reboot Device', 180, 270, 30);
    });

    // Shutdown / Power Off button
    const shutdownBtn = document.createElement('button');
    shutdownBtn.type = 'button';
    shutdownBtn.className = 'device-control-btn device-control-btn-danger';
    shutdownBtn.innerHTML = `<span class="device-control-icon"><span style="display:inline-block;width:18px;height:18px;background-color:currentColor;-webkit-mask-image:url('/static/icons/power_off.svg');mask-image:url('/static/icons/power_off.svg');-webkit-mask-size:contain;mask-size:contain;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;vertical-align:middle"></span></span> ${t.shutdown_device || 'Shutdown'}`;

    shutdownBtn.addEventListener('click', async () => {
        const ok = await showConfirmModal({
            title: t.shutdown_device || 'Shutdown Device',
            message: t.shutdown_device_confirm ||
                'Shut down the device completely? Unlike reboot, it will NOT start back up on its own — ' +
                'you\'ll need to disconnect and reconnect power (or use a physical power switch) to turn it back on.',
            confirmText: t.shutdown || 'Shut Down',
            cancelText: t.cancel || 'Cancel',
            danger: true,
            icon: '/static/icons/power_off.svg',
        });
        if (!ok) return;
        _performShutdown();
    });

    wrapper.appendChild(restartBtn);
    wrapper.appendChild(rebootBtn);
    wrapper.appendChild(shutdownBtn);
    formGroup.appendChild(wrapper);
    return formGroup;
}

// Shutdown has no "come back online" phase to poll for, unlike restart/reboot —
// it counts down to an estimated safe-to-unplug point and then stops, and tells
// the rest of the page's reconnect logic to give up entirely (see _shuttingDown
// guards on attemptConfigReconnect and the visibilitychange handler).
function _performShutdown() {
    const t = window.translations || {};

    window._shuttingDown = true;
    if (window.configSocket) {
        window.configSocket.disconnect();
    }

    fetch('/api/system/shutdown', { method: 'POST', credentials: 'same-origin' })
        .catch(() => { /* connection will drop shortly regardless */ });

    const overlay = document.createElement('div');
    overlay.className = 'confirm-modal-overlay';
    document.documentElement.style.setProperty('--scroll-y', `-${window.scrollY}px`);
    document.body.classList.add('modal-open');

    const dialog = document.createElement('div');
    dialog.className = 'confirm-modal-dialog';

    const heading = document.createElement('h3');
    heading.className = 'confirm-modal-title';
    heading.innerHTML = `<img src="/static/icons/power_off.svg" alt="" class="modal-title-icon"> ${t.shutdown_device || 'Shutdown Device'}`;

    const countdown = document.createElement('div');
    countdown.className = 'restart-countdown';

    // Estimated time for a clean shutdown to actually finish (services stopped,
    // filesystems synced/unmounted) — generous relative to mempaper.service's own
    // 10s TimeoutStopSec, to leave real margin before telling the user it's safe.
    const shutdownSeconds = 30;

    const countdownNumber = document.createElement('div');
    countdownNumber.className = 'restart-countdown-number';
    countdownNumber.textContent = _fmtCountdown(shutdownSeconds);

    const countdownLabel = document.createElement('div');
    countdownLabel.className = 'restart-countdown-label';
    countdownLabel.textContent = t.shutting_down || 'Shutting down…';

    const progressBar = document.createElement('div');
    progressBar.className = 'restart-progress-bar';
    const progressFill = document.createElement('div');
    progressFill.className = 'restart-progress-fill';
    progressBar.appendChild(progressFill);

    countdown.appendChild(countdownNumber);
    countdown.appendChild(countdownLabel);

    dialog.appendChild(heading);
    dialog.appendChild(countdown);
    dialog.appendChild(progressBar);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => overlay.classList.add('visible'));

    let remaining = shutdownSeconds;
    const interval = setInterval(() => {
        remaining--;
        if (remaining >= 0) {
            countdownNumber.textContent = _fmtCountdown(remaining);
            progressFill.style.transform = 'scaleX(' + (1 - remaining / shutdownSeconds) + ')';
        }
        if (remaining <= 0) {
            clearInterval(interval);
            countdownNumber.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="restart-check-icon" viewBox="0 -960 960 960" fill="#28a745"><path d="M382-240 154-468l57-57 171 171 367-367 57 57-424 424Z"/></svg>';
            countdownNumber.classList.add('restart-countdown-success');
            countdownLabel.textContent = t.safe_to_disconnect || 'It is now safe to disconnect the power.';
            progressFill.style.transform = 'scaleX(1)';
        }
    }, 1000);
}

function _performSystemAction(apiUrl, title, estimatedSeconds, maxPollAttempts, pollStartSeconds) {
    // Show countdown modal immediately so the user sees feedback right away
    _showRestartCountdown(title, estimatedSeconds, null, null, null, null, null, maxPollAttempts, pollStartSeconds);

    // Fire the API call (response may never arrive if the service restarts)
    fetch(apiUrl, { method: 'POST', credentials: 'same-origin' })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                // Remove the countdown overlay and show error instead
                const countdownOverlay = document.querySelector('.confirm-modal-overlay');
                if (countdownOverlay) {
                    countdownOverlay.classList.remove('visible');
                    setTimeout(() => countdownOverlay.remove(), 200);
                    document.body.classList.remove('modal-open');
                    var _sy = document.documentElement.style.getPropertyValue('--scroll-y');
                    document.documentElement.style.removeProperty('--scroll-y');
                    window.scrollTo(0, parseInt(_sy || '0') * -1);
                }
                showAlertModal({ title: data.error || 'Action failed' });
            }
        })
        .catch(() => { /* Service restarted – countdown is already showing */ });
}

function _fmtCountdown(secs) {
    if (secs < 60) return String(secs);
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return m + ':' + String(s).padStart(2, '0');
}

function _showRestartCountdown(title, estimatedSeconds, updateTag, rollbackTag, rollbackCommit, oldStarted, updateBtn, maxPollAttempts, pollStartSeconds) {
    const t = window.translations || {};
    const overlay = document.createElement('div');
    overlay.className = 'confirm-modal-overlay';

    // Prevent background scrolling while modal is open
    document.documentElement.style.setProperty('--scroll-y', `-${window.scrollY}px`);
    document.body.classList.add('modal-open');

    const dialog = document.createElement('div');
    dialog.className = 'confirm-modal-dialog';

    const heading = document.createElement('h3');
    heading.className = 'confirm-modal-title';
    heading.innerHTML = title;

    const countdown = document.createElement('div');
    countdown.className = 'restart-countdown';

    const countdownNumber = document.createElement('div');
    countdownNumber.className = 'restart-countdown-number';
    countdownNumber.textContent = _fmtCountdown(estimatedSeconds);

    const countdownLabel = document.createElement('div');
    countdownLabel.className = 'restart-countdown-label';
    countdownLabel.textContent = t.waiting_for_service || 'Waiting for service...';

    const progressBar = document.createElement('div');
    progressBar.className = 'restart-progress-bar';
    const progressFill = document.createElement('div');
    progressFill.className = 'restart-progress-fill';
    progressBar.appendChild(progressFill);

    countdown.appendChild(countdownNumber);
    countdown.appendChild(countdownLabel);

    dialog.appendChild(heading);
    dialog.appendChild(countdown);
    dialog.appendChild(progressBar);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => overlay.classList.add('visible'));

    let remaining = estimatedSeconds;
    let elapsed = 0;
    let polling = false;
    // How long to let the countdown run before checking for real, as an elapsed
    // time from the click — NOT relative to the countdown's own length. Polling
    // start must stay independent of the displayed estimate: if it were pinned to
    // "N seconds before the countdown ends", a long/generous estimate (e.g. a
    // reboot's ~3 min, which allows for slow Wi-Fi reconnects) would delay the
    // first real check for just as long, even on a run that actually comes back
    // in a fraction of that time — the modal would sit there doing nothing
    // while the device is already reachable.
    const pollStartElapsed = pollStartSeconds != null ? pollStartSeconds : Math.max(estimatedSeconds - 10, 0);

    const interval = setInterval(() => {
        remaining--;
        elapsed++;
        if (remaining >= 0) {
            countdownNumber.textContent = _fmtCountdown(remaining);
            progressFill.style.transform = 'scaleX(' + (1 - remaining / estimatedSeconds) + ')';
        }

        // Start early background polling once enough time has passed to make an
        // attempt worthwhile — independent of when the countdown display ends.
        if (elapsed >= pollStartElapsed && !polling) {
            polling = true;
            _pollForService(overlay, countdownNumber, countdownLabel, progressFill, interval, updateTag, rollbackTag, rollbackCommit, oldStarted, updateBtn, maxPollAttempts);
        }

        // Switch to spinner UI once countdown reaches 0 (only once to preserve animation)
        if (remaining === 0) {
            countdownLabel.textContent = t.checking_service || 'Checking service...';
            countdownNumber.innerHTML = '<div class="restart-spinner"></div>';
        }
    }, 1000);
}

function _pollForService(overlay, countdownNumber, countdownLabel, progressFill, countdownInterval, updateTag, rollbackTag, rollbackCommit, oldStarted, updateBtn, maxPollAttempts) {
    const t = window.translations || {};
    let attempts = 0;
    const maxAttempts = maxPollAttempts || 60;
    let settled = false; // guards against duplicate terminal handling from throttled/queued ticks

    const pollInterval = setInterval(async () => {
        if (settled) return;
        attempts++;
        try {
            const resp = await fetch('/api/health', { cache: 'no-store' });
            if (settled) return; // another (overlapping) tick already reached a terminal state
            if (resp.ok) {
                const hData = await resp.json();

                // For update restarts: ensure this is a NEW process
                if (oldStarted && hData.started && hData.started <= oldStarted) return;

                // For update restarts: verify the new version (best-effort — skip on error, accept after 10 attempts)
                if (updateTag && attempts <= 10) {
                    try {
                        const vResp = await fetch('/api/update/current', { cache: 'no-store' });
                        if (vResp.ok) {
                            const vData = await vResp.json();
                            if (vData.current_tag !== updateTag) return;
                        }
                    } catch (_) { /* version endpoint not ready yet — accept health as sufficient */ }
                }
                if (settled) return; // another (overlapping) tick already reached a terminal state

                settled = true;
                clearInterval(pollInterval);
                clearInterval(countdownInterval);
                countdownNumber.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" class="restart-check-icon" viewBox="0 -960 960 960" fill="#28a745"><path d="M382-240 154-468l57-57 171 171 367-367 57 57-424 424Z"/></svg>';
                countdownNumber.classList.add('restart-countdown-success');
                countdownLabel.textContent = t.service_back_online || 'Service is back online!';
                progressFill.style.transform = 'scaleX(1)';
                document.body.classList.remove('modal-open');
                var _sy = document.documentElement.style.getPropertyValue('--scroll-y');
                document.documentElement.style.removeProperty('--scroll-y');
                window.scrollTo(0, parseInt(_sy || '0') * -1);
                const isReboot = !!(window._pageLoadBootId && hData.boot_id && hData.boot_id !== window._pageLoadBootId);
                setTimeout(() => _reloadAfterRestart(updateTag, isReboot), 500);
                return;
            }
        } catch (_) {}

        if (settled) return; // another (overlapping) tick already reached a terminal state
        if (attempts >= maxAttempts) {
            settled = true;
            clearInterval(pollInterval);
            clearInterval(countdownInterval);
            countdownNumber.innerHTML = '<span style="display:inline-block;width:0.85em;height:0.85em;background-color:var(--danger,#ef4444);-webkit-mask-image:url(\'/static/icons/error.svg\');mask-image:url(\'/static/icons/error.svg\');-webkit-mask-size:contain;mask-size:contain;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;vertical-align:middle"></span>';
            countdownNumber.classList.add('restart-countdown-error');
            countdownLabel.textContent = t.service_not_responding || 'Service not responding. Try refreshing manually.';
            progressFill.style.transform = 'scaleX(1)';
            progressFill.classList.add('restart-progress-error');

            const dialogEl = overlay.querySelector('.confirm-modal-dialog');

            // For update failures: show SSH rollback info
            if (updateTag && rollbackTag) {
                _appendUpdateFailureInfo(dialogEl, rollbackTag, rollbackCommit);
                if (updateBtn) {
                    updateBtn.disabled = false;
                    updateBtn.textContent = t.update_now || 'Update';
                }
            }

            // Add dismiss button
            const dismissBtn = document.createElement('button');
            dismissBtn.className = 'confirm-modal-btn confirm';
            dismissBtn.textContent = t.dismiss || 'Dismiss';
            dismissBtn.style.marginTop = '16px';
            dismissBtn.addEventListener('click', () => {
                document.body.classList.remove('modal-open');
                var _sy = document.documentElement.style.getPropertyValue('--scroll-y');
                document.documentElement.style.removeProperty('--scroll-y');
                window.scrollTo(0, parseInt(_sy || '0') * -1);
                overlay.classList.remove('visible');
                setTimeout(() => overlay.remove(), 200);
            });
            dialogEl.appendChild(dismissBtn);
        }
    }, 1000);
}

function _startSystemUpdate(btn) {
    btn.disabled = true;
    btn.textContent = window.translations?.updating || 'Updating...';

    // Create modal overlay with log output
    const overlay = document.createElement('div');
    overlay.className = 'confirm-modal-overlay';
    overlay.id = 'system-update-overlay';
    document.documentElement.style.setProperty('--scroll-y', `-${window.scrollY}px`);
    document.body.classList.add('modal-open');

    const dialog = document.createElement('div');
    dialog.className = 'confirm-modal-dialog system-update-dialog';

    const heading = document.createElement('h3');
    heading.className = 'confirm-modal-title';
    heading.innerHTML = `<img src="/static/icons/update.svg" alt="" class="modal-title-icon"> ${window.translations?.system_update || 'System Update'}`;

    const phaseBar = document.createElement('div');
    phaseBar.className = 'system-update-phase';
    phaseBar.textContent = window.translations?.fetching_package_list || 'Fetching package list...';

    const progressBar = document.createElement('div');
    progressBar.className = 'update-progress-bar-container';
    progressBar.innerHTML = '<div class="update-progress-bar update-progress-bar-indeterminate"></div>';

    const statusBar = document.createElement('div');
    statusBar.className = 'system-update-status';
    statusBar.textContent = window.translations?.running || 'Running...';

    const detailsToggle = document.createElement('button');
    detailsToggle.className = 'update-details-toggle';
    detailsToggle.textContent = window.translations?.show_details || 'Show details';
    detailsToggle.addEventListener('click', () => {
        logArea.classList.toggle('update-log-visible');
        logArea.classList.toggle('update-log-hidden');
        detailsToggle.textContent = logArea.classList.contains('update-log-visible')
            ? (window.translations?.hide_details || 'Hide details')
            : (window.translations?.show_details || 'Show details');
    });

    const logArea = document.createElement('pre');
    logArea.className = 'system-update-log update-log-hidden';
    logArea.textContent = '';

    const closeBtn = document.createElement('button');
    closeBtn.className = 'confirm-modal-btn confirm';
    closeBtn.textContent = window.translations?.close || 'Close';
    closeBtn.style.display = 'none';

    const buttons = document.createElement('div');
    buttons.className = 'confirm-modal-buttons';
    buttons.appendChild(closeBtn);

    dialog.appendChild(heading);
    dialog.appendChild(phaseBar);
    dialog.appendChild(progressBar);
    dialog.appendChild(statusBar);
    dialog.appendChild(detailsToggle);
    dialog.appendChild(logArea);
    dialog.appendChild(buttons);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('visible'));

    closeBtn.addEventListener('click', () => {
        overlay.classList.remove('visible');
        overlay.addEventListener('transitionend', () => overlay.remove(), { once: true });
        setTimeout(() => { if (overlay.parentNode) overlay.remove(); }, 350);
        document.body.classList.remove('modal-open');
        var _sy = document.documentElement.style.getPropertyValue('--scroll-y');
        document.documentElement.style.removeProperty('--scroll-y');
        window.scrollTo(0, parseInt(_sy || '0') * -1);
    });

    // Listen for SocketIO events
    const socket = window.configSocket;
    if (!socket) {
        logArea.textContent = 'Error: no socket connection';
        statusBar.textContent = 'Failed';
        closeBtn.style.display = '';
        btn.disabled = false;
        btn.textContent = window.translations?.update_packages || 'Update';
        return;
    }

    function _stopAptProgressBar() {
        const bar = progressBar.querySelector('.update-progress-bar');
        if (bar) {
            bar.classList.remove('update-progress-bar-indeterminate');
            bar.classList.add('update-progress-bar-done');
        }
    }

    function onAptOutput(data) {
        if (data.header) {
            const b = document.createElement('strong');
            b.textContent = data.line;
            logArea.appendChild(b);
            logArea.appendChild(document.createTextNode('\n'));
        } else {
            logArea.appendChild(document.createTextNode(data.line + '\n'));
        }
        var atBottom = logArea.scrollHeight - logArea.scrollTop - logArea.clientHeight < 40;
        if (atBottom) logArea.scrollTop = logArea.scrollHeight;
        const phaseLabels = {
            prepare:  window.translations?.remounting_filesystem || 'Remounting filesystem\u2026',
            update:   window.translations?.fetching_package_list || 'Fetching package list (apt update)\u2026',
            upgrade:  window.translations?.installing_upgrades || 'Installing upgrades (apt upgrade)\u2026',
            deps:     window.translations?.installing_mempaper_deps || 'Installing mempaper dependencies\u2026',
            cleanup:  window.translations?.restoring_readonly || 'Restoring read-only filesystem\u2026',
        };
        if (data.phase && phaseLabels[data.phase]) {
            phaseBar.textContent = phaseLabels[data.phase];
        }
    }

    function onAptDone(data) {
        socket.off('apt_output', onAptOutput);
        socket.off('apt_done', onAptDone);
        _stopAptProgressBar();
        phaseBar.textContent = '';
        if (data.success) {
            statusBar.textContent = window.translations?.system_update_complete || 'System update complete!';
            statusBar.classList.add('system-update-success');
        } else {
            statusBar.textContent = (window.translations?.system_update_failed || 'Update failed') + ': ' + (data.error || '');
            statusBar.classList.add('system-update-error');
            logArea.classList.remove('update-log-hidden');
            logArea.classList.add('update-log-visible');
            detailsToggle.textContent = window.translations?.hide_details || 'Hide details';
        }
        closeBtn.style.display = '';
        btn.disabled = false;
        btn.textContent = window.translations?.update_packages || 'Update';
    }

    socket.on('apt_output', onAptOutput);
    socket.on('apt_done', onAptDone);

    // Trigger the update
    fetch('/api/system/update-packages', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                _stopAptProgressBar();
                logArea.textContent = data.message || 'Failed to start update';
                logArea.classList.remove('update-log-hidden');
                logArea.classList.add('update-log-visible');
                detailsToggle.textContent = window.translations?.hide_details || 'Hide details';
                statusBar.textContent = data.message || 'Failed';
                statusBar.classList.add('system-update-error');
                closeBtn.style.display = '';
                btn.disabled = false;
                btn.textContent = window.translations?.update_packages || 'Update';
                socket.off('apt_output', onAptOutput);
                socket.off('apt_done', onAptDone);
            }
        })
        .catch(err => {
            _stopAptProgressBar();
            logArea.textContent = 'Request failed: ' + err;
            logArea.classList.remove('update-log-hidden');
            logArea.classList.add('update-log-visible');
            detailsToggle.textContent = window.translations?.hide_details || 'Hide details';
            statusBar.textContent = 'Request failed';
            statusBar.classList.add('system-update-error');
            closeBtn.style.display = '';
            btn.disabled = false;
            btn.textContent = window.translations?.update_packages || 'Update';
            socket.off('apt_output', onAptOutput);
            socket.off('apt_done', onAptDone);
        });
}

// (removed — user management is now inline in the General section)
function renderUserManagementSection(grid) { /* no-op */ }

// ── Update Available Indicator ───────────────────────────────────────
function _showUpdateNavIndicator(hasUpdate, latestTag) {
    const pill = document.querySelector('.section-nav-pill[data-target="section-updates"]');
    if (!pill) return;

    // Remove existing indicator
    const existing = pill.querySelector('.nav-update-dot');
    if (existing) existing.remove();
    pill.removeAttribute('title');

    if (!hasUpdate) return;

    // Add pulsing dot
    const dot = document.createElement('span');
    dot.className = 'nav-update-dot';
    pill.appendChild(dot);

    // Tooltip
    const tooltip = (window.translations?.update_available_hint || 'Update {version} available').replace('{version}', latestTag);
    pill.dataset.tooltip = tooltip;
}
