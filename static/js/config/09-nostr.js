// Nostr posts: followed accounts and the prepared post cards.
// Part 9, loaded after the other config scripts and sharing their global
// scope (buildActionButton, showNotification, showConfirmModal).

function _nt(key, fallback) {
    return window.translations?.[key] || fallback;
}

// --- Followed accounts ---------------------------------------------------

function createNostrAccountsInput(values, field) {
    const container = document.createElement('div');
    container.className = 'nostr-accounts-container';

    const list = document.createElement('div');
    list.className = 'nostr-accounts-list';
    list.style.cssText = 'display:flex; flex-direction:column; gap:8px; margin-bottom:10px;';
    container.appendChild(list);

    const changed = () => container.dispatchEvent(new Event('change', { bubbles: true }));
    values.forEach(entry => list.appendChild(_createNostrAccountRow(entry, changed)));

    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'btn btn-outline-primary nostr-add-btn';
    addButton.textContent = _nt('nostr_add_account', 'Add Account');
    addButton.addEventListener('click', (e) => {
        e.preventDefault();
        const row = _createNostrAccountRow({ npub: '' }, changed);
        list.appendChild(row);
        row.querySelector('.nostr-npub-input')?.focus();
        changed();
    });
    const importButton = document.createElement('button');
    importButton.type = 'button';
    importButton.className = 'btn btn-outline-primary nostr-add-btn';
    importButton.style.marginLeft = '8px';
    importButton.textContent = _nt('nostr_import_follows', 'Import follows');
    importButton.title = _nt('nostr_import_follows_hint', 'Add every account an npub follows; remove the ones you do not want, then save.');

    const buttons = document.createElement('div');
    buttons.append(addButton, importButton);
    container.appendChild(buttons);
    container.appendChild(_createNostrImportForm(importButton, list, changed));

    container.getValue = () => Array.from(list.querySelectorAll('.nostr-account-row'))
        .map(row => ({ npub: row.querySelector('.nostr-npub-input').value.trim() }))
        .filter(entry => entry.npub);

    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (newValues) => {
            list.innerHTML = '';
            (Array.isArray(newValues) ? newValues : [])
                .forEach(entry => list.appendChild(_createNostrAccountRow(entry, changed)));
        }
    });

    // Lets the pool refresh the per-account counts after a fetch.
    container.refreshProfiles = () => list.querySelectorAll('.nostr-account-row')
        .forEach(row => row._resolve && row._resolve());
    window._nostrAccountsInput = container;

    return container;
}

// Inline form behind "Import follows": takes an npub, adds every account its
// contact list follows that is not in the list yet.
function _createNostrImportForm(toggleButton, list, onChange) {
    const form = document.createElement('div');
    form.style.cssText = 'display:none; gap:6px; align-items:center; margin-top:10px; flex-wrap:wrap;';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'form-input';
    input.placeholder = _nt('nostr_import_placeholder', 'Your npub');
    input.spellcheck = false;
    input.style.cssText = 'flex:1 1 220px; min-width:0; font-family:var(--font-mono); font-size:0.85em;';
    const go = document.createElement('button');
    go.type = 'button';
    go.className = 'btn btn-outline-primary nostr-add-btn';
    go.textContent = _nt('nostr_import_go', 'Import');
    const status = document.createElement('div');
    status.style.cssText = 'flex-basis:100%; font-size:0.8rem; color:var(--text-secondary);';
    form.append(input, go, status);

    toggleButton.addEventListener('click', (e) => {
        e.preventDefault();
        form.style.display = form.style.display === 'none' ? 'flex' : 'none';
        if (form.style.display === 'flex') input.focus();
    });

    const run = async () => {
        const key = input.value.trim();
        if (!key) return;
        go.disabled = true;
        status.style.color = 'var(--text-secondary)';
        status.textContent = _nt('nostr_import_loading', 'Loading follow list…');
        try {
            const resp = await fetch('/api/nostr-follows?key=' + encodeURIComponent(key));
            const data = await resp.json();
            if (!data.success) throw new Error(data.message || resp.status);
            const present = new Set(Array.from(list.querySelectorAll('.nostr-npub-input'))
                .map(el => el.value.trim()));
            let added = 0;
            data.follows.forEach(f => {
                if (present.has(f.npub)) return;
                list.appendChild(_createNostrAccountRow({ npub: f.npub }, onChange, f));
                added += 1;
            });
            onChange();
            status.textContent = _nt('nostr_import_done', '{added} accounts added, {skipped} already in the list. Remove the ones you do not want, then save.')
                .replace('{added}', added)
                .replace('{skipped}', data.follows.length - added);
            input.value = '';
        } catch (err) {
            status.style.color = 'var(--danger)';
            status.textContent = _nt('nostr_import_failed', 'Could not load the follow list') + ': ' + err.message;
        }
        go.disabled = false;
    };
    go.addEventListener('click', (e) => { e.preventDefault(); run(); });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); run(); } });
    return form;
}

// Copies the npub, to reuse or share it. Falls back to
// execCommand because navigator.clipboard only exists in secure contexts, and
// the device is usually reached over plain HTTP on the LAN.
function _createNostrCopyButton(input) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.title = _nt('click_to_copy', 'Click to copy');
    btn.style.cssText = 'background:none; border:1px solid var(--border-subtle); border-radius:6px; padding:0 10px; cursor:pointer; display:inline-flex; align-items:center; flex:none; align-self:stretch;';
    const copyIcon = _createMaskIcon('/static/icons/copy.svg', 16);
    const doneIcon = _createMaskIcon('/static/icons/check.svg', 16);
    btn.appendChild(copyIcon);

    const markCopied = () => {
        btn.replaceChildren(doneIcon);
        setTimeout(() => btn.replaceChildren(copyIcon), 1500);
    };
    const fallbackCopy = (text) => {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;pointer-events:none';
        document.body.appendChild(ta);
        ta.select();
        try { if (document.execCommand('copy')) markCopied(); } catch (_) {}
        ta.remove();
    };
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(markCopied).catch(() => fallbackCopy(text));
        } else {
            fallbackCopy(text);
        }
    });
    return btn;
}

// profile: a profile already known (from an import), shown without asking
// the server again.
function _createNostrAccountRow(entry, onChange, profile) {
    const row = document.createElement('div');
    row.className = 'nostr-account-row';
    row.style.cssText = 'display:flex; align-items:center; gap:10px; padding:8px; border:1px solid var(--border-subtle); border-radius:8px;';

    const avatar = document.createElement('img');
    avatar.className = 'nostr-avatar';
    avatar.alt = '';
    avatar.style.cssText = 'width:56px; height:56px; border-radius:50%; object-fit:cover; flex:none; background:var(--bg-input); visibility:hidden;';

    const middle = document.createElement('div');
    middle.style.cssText = 'flex:1; min-width:0; display:flex; flex-direction:column; gap:4px;';

    const nameLine = document.createElement('div');
    nameLine.style.cssText = 'display:flex; align-items:center; gap:6px; min-height:1.2em;';
    const nameEl = document.createElement('span');
    nameEl.className = 'nostr-account-name';
    nameEl.style.cssText = 'font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;';
    const countEl = document.createElement('span');
    countEl.className = 'nostr-account-count';
    countEl.title = _nt('nostr_account_pool_count', 'Posts from the last 60 minutes, ready to show');
    countEl.style.cssText = 'font-size:0.75rem; padding:1px 7px; border-radius:10px; background:var(--accent); color:#fff; display:none;';
    nameLine.append(nameEl, countEl);

    const inputs = document.createElement('div');
    inputs.style.cssText = 'display:flex; gap:6px; align-items:center;';
    const npubInput = document.createElement('input');
    npubInput.type = 'text';
    npubInput.className = 'form-input nostr-npub-input';
    npubInput.placeholder = 'npub1…';
    npubInput.value = entry.npub || '';
    npubInput.spellcheck = false;
    npubInput.style.cssText = 'flex:1 1 220px; min-width:0; font-family:var(--font-mono); font-size:0.85em;';
    middle.append(nameLine, inputs);

    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.title = _nt('nostr_remove_account', 'Remove account');
    removeButton.innerHTML = '<img src="/static/icons/delete.svg" alt="" class="table-delete-icon" />';
    removeButton.style.cssText = 'background:none; border:none; padding:4px; cursor:pointer; flex:none; display:inline-flex; align-items:center;';
    removeButton.addEventListener('click', (e) => {
        e.preventDefault();
        row.remove();
        onChange();
    });

    // In the input line rather than the row: centred on the whole row it sat
    // halfway up the name line, out of line with the copy button.
    inputs.append(npubInput, _createNostrCopyButton(npubInput), removeButton);
    row.append(avatar, middle);

    // As tall as the name line and the npub field together, whatever the
    // fonts and padding come to - and on a phone, where the name may wrap.
    if (window.ResizeObserver) {
        new ResizeObserver(() => {
            const size = Math.round(middle.getBoundingClientRect().height);
            if (size > 0) {
                avatar.style.width = size + 'px';
                avatar.style.height = size + 'px';
            }
        }).observe(middle);
    }

    const applyProfile = (data) => {
        npubInput.classList.remove('input-invalid');
        // Store the canonical form, whatever was pasted (hex, nprofile, nostr: URI).
        if (data.npub && npubInput.value.trim() !== data.npub) {
            npubInput.value = data.npub;
            onChange();
        }
        // No profile published: the npub itself, shortened, is the best name there is.
        nameEl.textContent = data.name
            || (data.npub ? data.npub.slice(0, 12) + '…' + data.npub.slice(-6) : _nt('nostr_no_profile', 'No profile found'));
        nameEl.style.color = data.name ? '' : 'var(--text-secondary)';
        if (data.avatar) {
            avatar.src = `/api/nostr-avatar/${data.pubkey}`;
            avatar.style.visibility = 'visible';
        }
        // Only when it has something in the pool; a zero on every quiet
        // account would just be noise.
        if (data.count) {
            countEl.textContent = String(data.count);
            countEl.style.display = 'inline-block';
        }
    };

    let requestId = 0;
    row._resolve = async () => {
        const key = npubInput.value.trim();
        const myId = ++requestId;
        avatar.style.visibility = 'hidden';
        countEl.style.display = 'none';
        if (!key) {
            nameEl.textContent = '';
            npubInput.classList.remove('input-invalid');
            return;
        }
        nameEl.textContent = _nt('nostr_looking_up', 'Looking up…');
        nameEl.style.color = 'var(--text-secondary)';
        try {
            const resp = await fetch('/api/nostr-profile?key=' + encodeURIComponent(key));
            const data = await resp.json();
            if (myId !== requestId) return;
            if (!data.success) {
                nameEl.textContent = _nt('nostr_invalid_key', 'Not a valid npub');
                nameEl.style.color = 'var(--danger)';
                npubInput.classList.add('input-invalid');
                return;
            }
            applyProfile(data);
        } catch (err) {
            if (myId === requestId) {
                nameEl.textContent = _nt('nostr_lookup_failed', 'Profile lookup failed');
                nameEl.style.color = 'var(--text-secondary)';
            }
        }
    };

    let debounce = null;
    npubInput.addEventListener('input', () => {
        clearTimeout(debounce);
        debounce = setTimeout(row._resolve, 700);
    });
    if (profile) applyProfile(profile);
    else if (entry.npub) row._resolve();

    return row;
}

// --- Prepared posts --------------------------------------------------------
// The pool the display picks from: posts of the last hour, rendered as the
// card the panel will show, in the order they would be picked.

let nostrStatusTimer = null;
let nostrPoolTimer = null;
let currentNostrModalPost = null;

function _nostrDate(ts) {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: '2-digit' })
        + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

// The theme selected in the form, saved or not, so the preview follows the
// switch straight away.
function _nostrTheme() {
    const toggle = document.querySelector('[data-config-key="nostr_card_theme"]');
    const value = toggle?.getValue?.();
    return value === 'dark' || value === 'light' ? value : ((typeof currentConfig !== 'undefined' && currentConfig?.nostr_card_theme) || 'light');
}

function _nostrCardUrl(key, width) {
    // The age printed on the card moves; the timestamp keeps the browser from
    // showing a stale copy.
    return `/api/nostr-card/${key}?theme=${_nostrTheme()}${width ? '&w=' + width : ''}&t=${Date.now()}`;
}

function _nostrStateLabel(post) {
    if (post.state === 'next') return _nt('nostr_state_next', 'Next');
    if (post.state === 'waiting') return _nt('nostr_state_waiting', 'Waiting');
    if (post.state === 'preview') return _nt('nostr_state_preview', 'Preview only');
    return _nt('nostr_state_queued', 'Queued');
}

function _nostrPostDetail(post) {
    if (post.state === 'preview') return _nostrDate(post.created_at);
    const shown = _nt('nostr_shown_times', 'Shown {count}×').replace('{count}', post.shown || 0);
    const left = _nt('nostr_minutes_left', '{minutes} min left')
        .replace('{minutes}', Math.max(1, Math.round((post.expires_in || 0) / 60)));
    return `${shown} · ${left}`;
}

function createNostrPostTile(post) {
    const tile = document.createElement('div');
    tile.className = 'nostr-post-tile';
    tile.style.cssText = 'display:flex; flex-direction:column; gap:6px; cursor:pointer;';
    tile.addEventListener('click', () => openNostrPreview(post));

    const frame = document.createElement('div');
    frame.style.cssText = 'position:relative; border:1px solid var(--border-subtle); border-radius:10px; overflow:hidden; background:var(--bg-input);';
    const img = document.createElement('img');
    img.src = _nostrCardUrl(post.key, 400);
    img.alt = post.name || '';
    img.loading = 'lazy';
    img.dataset.nostrKey = post.key;
    img.style.cssText = 'display:block; width:100%; height:auto;';
    const badge = document.createElement('span');
    badge.textContent = _nostrStateLabel(post);
    const badgeColor = post.state === 'next' ? 'var(--accent)'
        : post.state === 'waiting' || post.state === 'preview' ? '#6c757d' : '#28a745';
    badge.style.cssText = `position:absolute; top:6px; left:6px; font-size:0.7rem; font-weight:600; padding:2px 8px; border-radius:10px; color:#fff; background:${badgeColor};`;
    frame.append(img, badge);

    const detail = document.createElement('div');
    detail.style.cssText = 'font-size:0.75rem; color:var(--text-secondary); text-align:center;';
    detail.textContent = _nostrPostDetail(post);

    tile.append(frame, detail);
    return tile;
}

async function loadNostrPool() {
    const list = document.getElementById('nostr-pool-list');
    if (!list) return;
    try {
        const resp = await fetch('/api/nostr-pool');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        const posts = data.posts || [];
        const count = document.getElementById('nostr-pool-count');
        if (count) count.textContent = `(${posts.length})`;
        list.replaceChildren();
        if (!posts.length) {
            const note = document.createElement('p');
            note.style.cssText = 'grid-column:1/-1; text-align:center; color:var(--text-secondary); margin:8px 0;';
            note.textContent = _nt('nostr_pool_empty', 'Nobody posted an image in the last 60 minutes, so memes are shown.');
            list.appendChild(note);
            if (data.sample) {
                list.appendChild(createNostrPostTile({ ...data.sample, state: 'preview' }));
            }
            return;
        }
        posts.forEach(post => list.appendChild(createNostrPostTile(post)));
    } catch (err) {
        list.innerHTML = `<p style="grid-column:1/-1; text-align:center; color:var(--danger);">${escapeHtml(_nt('nostr_load_failed', 'Error loading Nostr posts'))}</p>`;
    }
}

// --- Post modal: same frame as the meme modal ------------------------------

function openNostrPreview(post) {
    currentNostrModalPost = post;
    const modal = document.getElementById('nostr-modal');
    if (!modal) return;
    document.getElementById('nostr-modal-author').textContent = post.name || post.npub || '';
    document.getElementById('nostr-modal-published').textContent = _nostrDate(post.created_at);
    document.getElementById('nostr-modal-state').textContent =
        `${_nostrStateLabel(post)} · ${_nostrPostDetail(post)}`;
    const image = document.getElementById('nostr-modal-image');
    image.alt = post.name || '';
    image.src = _nostrCardUrl(post.key);
    document.getElementById('nostr-modal-open-btn').style.display = post.note ? '' : 'none';
    modal.style.display = 'flex';
}

function closeNostrModal() {
    const modal = document.getElementById('nostr-modal');
    if (modal) modal.style.display = 'none';
    currentNostrModalPost = null;
}

function openNostrNoteFromModal() {
    if (currentNostrModalPost?.note) {
        window.open('https://njump.me/' + currentNostrModalPost.note, '_blank', 'noopener');
    }
}

async function dismissNostrFromModal() {
    const post = currentNostrModalPost;
    if (!post) return;
    const ok = await showConfirmModal({
        title: _nt('nostr_dismiss_title', 'Remove post?'),
        message: _nt('nostr_dismiss_message', 'The post will not be shown on the display.'),
        confirmText: _nt('nostr_dismiss', 'Remove'),
        danger: true,
    });
    if (!ok) return;
    try {
        const resp = await fetch('/api/nostr-dismiss/' + encodeURIComponent(post.key), { method: 'POST' });
        const result = await resp.json();
        if (!result.success) throw new Error(result.message || resp.status);
        closeNostrModal();
        loadNostrPool();
        window._nostrAccountsInput?.refreshProfiles();
    } catch (err) {
        showNotification(_nt('nostr_dismiss_failed', 'Could not remove post') + ': ' + err.message, 'error');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('nostr-modal');
    modal?.addEventListener('click', (e) => { if (e.target === modal) closeNostrModal(); });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal?.style.display === 'flex') closeNostrModal();
    });
    // Re-render the previews when the card style is switched.
    document.addEventListener('click', (e) => {
        if (e.target.closest?.('[data-config-key="nostr_card_theme"]')) setTimeout(loadNostrPool, 50);
    });
});

// --- Fetch status ------------------------------------------------------------

async function refreshNostrStatus() {
    const el = document.getElementById('nostr-fetch-status');
    const btn = document.getElementById('nostr-fetch-btn');
    if (!el) return null;
    try {
        const resp = await fetch('/api/nostr-status');
        const data = await resp.json();
        const s = data.status || {};
        if (btn) btn.disabled = !!s.running;
        const errList = document.getElementById('nostr-fetch-errors');
        const errors = s.running ? [] : (s.errors || []);
        if (errList) {
            errList.replaceChildren(...errors.map(text => {
                const li = document.createElement('li');
                li.textContent = text;
                return li;
            }));
            if (!errors.length) errList.style.display = 'none';
        }
        if (s.running) {
            el.textContent = _nt('nostr_fetching', 'Fetching…');
        } else if (s.last_run) {
            let text = _nt('nostr_last_fetch', 'Last fetch {time}: {added} new, {duplicates} duplicates skipped')
                .replace('{time}', _nostrDate(s.last_run))
                .replace('{added}', s.added || 0)
                .replace('{duplicates}', s.duplicates || 0);
            if (s.message && s.message !== 'ok') text += ' — ' + s.message;
            el.textContent = text;
            if (errors.length && errList) {
                // The count opens the list underneath: a tooltip is out of
                // reach on a phone, and the reasons are what tell you what to fix.
                const toggle = document.createElement('a');
                toggle.href = '#';
                toggle.style.cssText = 'color:var(--danger); text-decoration:underline; cursor:pointer;';
                toggle.textContent = _nt('nostr_fetch_errors', '{count} error(s)').replace('{count}', errors.length);
                toggle.addEventListener('click', (e) => {
                    e.preventDefault();
                    errList.style.display = errList.style.display === 'none' ? 'block' : 'none';
                });
                el.append(' — ', toggle);
            }
        } else {
            el.textContent = _nt('nostr_never_fetched', 'Not fetched yet since the last restart. Fetches run every 5 minutes.');
        }
        return s;
    } catch (err) {
        return null;
    }
}

async function startNostrFetch() {
    const btn = document.getElementById('nostr-fetch-btn');
    if (btn) btn.disabled = true;
    try {
        await fetch('/api/nostr-fetch', { method: 'POST' });
    } catch (err) {
        if (btn) btn.disabled = false;
        return;
    }
    clearInterval(nostrStatusTimer);
    let sawRunning = false;
    const started = Date.now();
    nostrStatusTimer = setInterval(async () => {
        const s = await refreshNostrStatus();
        if (s?.running) sawRunning = true;
        // Done once it has been seen running and stopped, or after the first
        // poll if it was already finished by then.
        if (s && !s.running && (sawRunning || Date.now() - started > 4000)) {
            clearInterval(nostrStatusTimer);
            loadNostrPool();
            window._nostrAccountsInput?.refreshProfiles();
        }
    }, 2500);
}

function createNostrManagementInterface(field) {
    const container = document.createElement('div');
    container.className = 'meme-management-container';

    const statusRow = document.createElement('div');
    statusRow.style.cssText = 'display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:12px;';
    const fetchBtn = document.createElement('button');
    fetchBtn.type = 'button';
    fetchBtn.id = 'nostr-fetch-btn';
    fetchBtn.className = 'mempool-action-btn';
    fetchBtn.textContent = _nt('nostr_fetch_now', 'Fetch now');
    fetchBtn.title = _nt('nostr_fetch_now_hint', 'Uses the saved settings - save first after changing accounts.');
    fetchBtn.addEventListener('click', startNostrFetch);
    const statusEl = document.createElement('span');
    statusEl.id = 'nostr-fetch-status';
    statusEl.style.cssText = 'font-size:0.85rem; color:var(--text-secondary);';
    statusRow.append(fetchBtn, statusEl);

    const errorList = document.createElement('ul');
    errorList.id = 'nostr-fetch-errors';
    errorList.style.cssText = 'display:none; margin:-4px 0 12px; padding:8px 8px 8px 28px; font-size:0.8rem; font-family:var(--font-mono); color:var(--text-secondary); border:1px solid var(--border-subtle); border-radius:8px; max-height:200px; overflow-y:auto; word-break:break-all;';

    const label = document.createElement('label');
    label.className = 'form-label';
    label.innerHTML = `${escapeHtml(_nt('nostr_management', 'Prepared Posts'))} <span id="nostr-pool-count" style="color:var(--text-secondary); font-weight:400;"></span>`;
    const hint = document.createElement('div');
    hint.className = 'form-description';
    hint.style.cssText = 'font-size:0.8rem; color:var(--text-secondary); margin-bottom:8px;';
    hint.textContent = _nt('nostr_pool_hint', 'In the order the display will pick them. Each post stays for 60 minutes after it was published.');

    const list = document.createElement('div');
    list.id = 'nostr-pool-list';
    list.style.cssText = 'display:grid; grid-template-columns:repeat(auto-fill, minmax(160px, 1fr)); gap:12px; margin-top:8px; align-items:start;';
    const scroll = document.createElement('div');
    scroll.className = 'nostr-scroll-container';
    scroll.appendChild(list);

    container.append(statusRow, errorList, label, hint, scroll);

    setTimeout(() => {
        loadNostrPool();
        refreshNostrStatus().then(s => { if (s?.running) startNostrFetch(); });
        // States and minutes left move on their own; a fetch in the
        // background may have added posts.
        clearInterval(nostrPoolTimer);
        nostrPoolTimer = setInterval(() => {
            if (document.getElementById('nostr-pool-list')) {
                loadNostrPool();
                refreshNostrStatus();
            }
        }, 60000);
    }, 100);

    container.getValue = () => null;
    return container;
}
