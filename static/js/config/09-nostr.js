// Nostr posts: followed accounts and the prepared post cards.
// Part 9, loaded after the other config scripts and sharing their global
// scope (buildActionButton, showNotification, showConfirmModal).

function _nt(key, fallback) {
    return window.translations?.[key] || fallback;
}

// --- Durations ------------------------------------------------------------

// "45 Minuten", "2 Stunden", "3 Tage" in the page's language. Whole hours and
// days only once they divide evenly, so 90 minutes stays "90 Minuten".
function _nostrDuration(minutes) {
    const lang = document.documentElement.lang || undefined;
    let value = minutes, unit = 'minute';
    if (minutes >= 1440 && minutes % 1440 === 0) { value = minutes / 1440; unit = 'day'; }
    else if (minutes >= 60 && minutes % 60 === 0) { value = minutes / 60; unit = 'hour'; }
    try {
        return new Intl.NumberFormat(lang, { style: 'unit', unit, unitDisplay: 'long' }).format(value);
    } catch (e) {
        return `${value} ${unit}${value === 1 ? '' : 's'}`;
    }
}

// The pool window the server is working with, from the last pool reload.
// fromForm: the Show Posts For slider instead, saved or not - for the hint
// that explains the setting, which should follow the slider as it moves.
let _nostrWindowMinutes = null;
function _nostrWindowText(fromForm) {
    const saved = (typeof currentConfig !== 'undefined' && currentConfig?.nostr_pool_minutes) || 60;
    const form = fromForm && Number(document.querySelector('[data-config-key="nostr_pool_minutes"]')?.getValue?.());
    return _nostrDuration(form || _nostrWindowMinutes || saved);
}

function _nostrUpdatePoolHint() {
    const hint = document.getElementById('nostr-pool-hint');
    if (hint) {
        hint.textContent = _nt('nostr_pool_hint', 'In the order they will be shown. A post stays here for {window} after it was published.')
            .replace('{window}', _nostrWindowText(true));
    }
}

// A slider over fixed stops (field.stops, in minutes) rather than a straight
// scale: 10 minutes to 7 days in even steps would leave every short value
// crammed into the first few pixels. The value is a number of minutes.
function createDurationSliderInput(field, value) {
    const stops = (field.stops && field.stops.length) ? field.stops : [10, 30, 60, 180, 720, 1440, 10080];
    const nearest = (v) => stops.reduce((best, s, i) =>
        Math.abs(s - v) < Math.abs(stops[best] - v) ? i : best, 0);

    const container = document.createElement('div');
    container.className = 'duration-slider';
    const head = document.createElement('div');
    head.className = 'duration-slider-value';
    const slider = document.createElement('input');
    slider.type = 'range';
    slider.min = '0';
    slider.max = String(stops.length - 1);
    slider.step = '1';
    slider.value = String(nearest(Number(value ?? field.default ?? 60)));
    const scale = document.createElement('div');
    scale.className = 'duration-slider-scale';
    const lo = document.createElement('span');
    const hi = document.createElement('span');
    lo.textContent = _nostrDuration(stops[0]);
    hi.textContent = _nostrDuration(stops[stops.length - 1]);
    scale.append(lo, hi);

    // The pool hint follows too, on a reset of the form as well as a drag.
    const show = () => {
        head.textContent = _nostrDuration(stops[Number(slider.value)]);
        _nostrUpdatePoolHint();
    };
    slider.addEventListener('input', show);
    show();

    container.append(head, slider, scale);
    container.getValue = () => stops[Number(slider.value)];
    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (v) => { slider.value = String(nearest(Number(v))); show(); },
    });
    return container;
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
    values.forEach(entry => list.appendChild(_createNostrAccountRow(entry, changed, null, true)));
    setTimeout(() => _nostrResolveAll(list), 0);
    const expand = _createNostrListToggle(list);
    container.appendChild(expand);

    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'btn btn-outline-primary nostr-add-btn';
    addButton.textContent = _nt('nostr_add_account', 'Add Account');
    addButton.addEventListener('click', (e) => {
        e.preventDefault();
        const row = _createNostrAccountRow({ npub: '' }, changed);
        list.appendChild(row);
        expand.open();          // the new row is at the end, out of sight while collapsed
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
    container.appendChild(_createNostrImportForm(importButton, list, changed, () => expand.open()));

    container.getValue = () => Array.from(list.querySelectorAll('.nostr-account-row'))
        .map(row => {
            const entry = { npub: row.querySelector('.nostr-npub-input').value.trim() };
            if (row._imageOnly()) entry.image_only = true;
            return entry;
        })
        .filter(entry => entry.npub);

    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (newValues) => {
            list.innerHTML = '';
            (Array.isArray(newValues) ? newValues : [])
                .forEach(entry => list.appendChild(_createNostrAccountRow(entry, changed, null, true)));
            _nostrResolveAll(list);
        }
    });

    // Lets the pool refresh the per-account counts after a fetch.
    container.refreshProfiles = () => _nostrResolveAll(list);
    window._nostrAccountsInput = container;

    return container;
}

// Following many accounts, the list would run on for screens: it shows the
// first NOSTR_COLLAPSED_ROWS, and a toggle under the last row shown opens
// or closes the rest. Hidden by CSS, so rows added or removed need nothing
// but the toggle's label brought up to date.
const NOSTR_COLLAPSED_ROWS = 3;
function _createNostrListToggle(list) {
    list.classList.add('nostr-accounts-collapsed');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'nostr-list-toggle';
    btn.style.cssText = 'display:none; width:100%; align-items:center; justify-content:center; gap:6px; margin:-2px 0 10px; padding:6px; background:none; border:1px dashed var(--border-subtle); border-radius:8px; color:var(--text-secondary); font-size:0.85rem; cursor:pointer;';
    const icon = _createMaskIcon('/static/icons/chevron_down.svg', 18);
    icon.style.transition = 'transform 0.2s';
    const label = document.createElement('span');
    btn.append(icon, label);

    const update = () => {
        const count = list.querySelectorAll('.nostr-account-row').length;
        const collapsed = list.classList.contains('nostr-accounts-collapsed');
        btn.style.display = count > NOSTR_COLLAPSED_ROWS ? 'flex' : 'none';
        icon.style.transform = collapsed ? '' : 'rotate(180deg)';
        label.textContent = collapsed
            ? _nt('nostr_show_all_accounts', 'Show all {count} accounts').replace('{count}', count)
            : _nt('nostr_show_fewer_accounts', 'Show fewer');
    };
    btn.addEventListener('click', (e) => {
        e.preventDefault();
        const collapsing = !list.classList.contains('nostr-accounts-collapsed');
        list.classList.toggle('nostr-accounts-collapsed', collapsing);
        update();
        // Closing a long list moves the toggle far up: follow it, so the
        // page does not land somewhere further down the settings.
        if (collapsing) btn.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
    btn.open = () => {
        list.classList.remove('nostr-accounts-collapsed');
        update();
    };
    new MutationObserver(update).observe(list, { childList: true });
    update();
    return btn;
}

// Names and avatars of every row in one request. Stored profiles come back
// at once; while the server is still looking up missing ones it says so, and
// this asks again a few seconds later, for about a minute.
let _nostrResolveTimer = null;
async function _nostrResolveAll(list, round = 0) {
    clearTimeout(_nostrResolveTimer);
    const rows = Array.from(list.querySelectorAll('.nostr-account-row'))
        .filter(row => row.querySelector('.nostr-npub-input')?.value.trim());
    if (!rows.length) return;
    const keys = rows.map(row => row.querySelector('.nostr-npub-input').value.trim());
    try {
        const resp = await fetch('/api/nostr-profiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keys }),
        });
        const data = await resp.json();
        if (!data.success) throw new Error(data.message || resp.status);
        rows.forEach((row, i) => {
            const profile = data.profiles[keys[i]];
            if (!profile) {
                row._resolve?.();          // not a valid key: let the row say so
                return;
            }
            row._apply(profile);
            if (data.pending && !profile.name) row._looking();
        });
        if (data.pending && round < 15) {
            _nostrResolveTimer = setTimeout(() => _nostrResolveAll(list, round + 1), 4000);
        }
    } catch (err) {
        console.error('Nostr profile lookup failed:', err);
    }
}

// Inline form behind "Import follows": takes an npub, adds every account its
// contact list follows that is not in the list yet.
function _createNostrImportForm(toggleButton, list, onChange, onAdded) {
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
            // Open the list: the new accounts are at its end, to be looked over.
            if (added) onAdded?.();
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
// The account's profile on Primal, in a new tab - like the link to a Bitaxe
// miner's own page. The address is read when the link is used, so it follows
// whatever the field holds by then, typed or canonicalised.
function _createNostrProfileLink(input) {
    const link = document.createElement('a');
    link.className = 'nostr-open-link';
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.title = _nt('nostr_open_profile', 'Open profile on Primal');
    link.style.cssText = 'border:1px solid var(--border-subtle); border-radius:6px; padding:0 10px; display:inline-flex; align-items:center; flex:none; align-self:stretch;';
    link.appendChild(_createMaskIcon('/static/icons/open.svg', 16));
    const sync = () => {
        const key = input.value.trim();
        if (key) {
            link.href = 'https://primal.net/p/' + encodeURIComponent(key);
            link.style.opacity = '1';
            link.style.pointerEvents = 'auto';
        } else {
            link.removeAttribute('href');
            link.style.opacity = '0.3';
            link.style.pointerEvents = 'none';
        }
    };
    input.addEventListener('input', sync);
    ['mouseenter', 'focus', 'pointerdown'].forEach(ev => link.addEventListener(ev, sync));
    sync();
    return link;
}

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

// Post card or image only, per account: some accounts post pictures with
// nothing worth reading, and those look best on the panel bare, like a meme.
// Same classes as the settings form's switches. On: the post card.
function _createNostrStyleSwitch(entry, row, onChange) {
    const wrap = document.createElement('div');
    wrap.className = 'boolean-switch nostr-style-switch';
    wrap.style.cssText = 'margin-left:auto; flex:none; display:flex; align-items:center; gap:6px; font-size:0.8rem; color:var(--text-secondary); cursor:pointer;';
    wrap.title = _nt('nostr_style_hint', 'Show the post as a card with avatar, name and text, or only its image, like a meme.');
    const switchEl = document.createElement('div');
    switchEl.className = 'switch';
    const thumb = document.createElement('div');
    thumb.className = 'switch-thumb';
    switchEl.appendChild(thumb);
    const label = document.createElement('span');
    label.style.whiteSpace = 'nowrap';
    wrap.append(label, switchEl);

    const show = () => {
        label.textContent = switchEl.classList.contains('active')
            ? _nt('nostr_style_card', 'Show post') : _nt('nostr_style_image', 'Image only');
    };
    switchEl.classList.toggle('active', !entry.image_only);
    show();
    wrap.addEventListener('click', (e) => {
        e.preventDefault();
        switchEl.classList.toggle('active');
        show();
        onChange();
        // The prepared posts follow the switch before it is saved.
        if (typeof loadNostrPool === 'function') setTimeout(loadNostrPool, 50);
    });
    row._imageOnly = () => !switchEl.classList.contains('active');
    return wrap;
}

// profile: a profile already known (from an import), shown without asking
// the server again. deferred: the list resolves it with all the others in
// one request (_nostrResolveAll).
function _createNostrAccountRow(entry, onChange, profile, deferred) {
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
    countEl.title = _nt('nostr_account_pool_count', 'Posts within the set time window ({window}), ready to show')
        .replace('{window}', _nostrWindowText());
    countEl.style.cssText = 'font-size:0.75rem; padding:1px 7px; border-radius:10px; background:var(--accent); color:#fff; display:none;';
    nameLine.append(nameEl, countEl, _createNostrStyleSwitch(entry, row, onChange));

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
    removeButton.className = 'nostr-remove-icon';
    removeButton.title = _nt('nostr_remove_account', 'Remove account');
    removeButton.innerHTML = '<img src="/static/icons/delete.svg" alt="" class="table-delete-icon" />';
    removeButton.style.cssText = 'background:none; border:none; padding:4px; cursor:pointer; flex:none; display:inline-flex; align-items:center; border-radius:4px; transition:background-color 0.2s;';
    removeButton.addEventListener('click', (e) => {
        e.preventDefault();
        row.remove();
        onChange();
    });

    // In the input line rather than the row: centred on the whole row it sat
    // halfway up the name line, out of line with the copy button.
    inputs.append(npubInput, _createNostrCopyButton(npubInput), _createNostrProfileLink(npubInput), removeButton);
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
        nameEl.dataset.named = data.name ? '1' : '';
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
    row._apply = applyProfile;
    row._looking = () => {
        if (nameEl.dataset.named !== '1') {
            nameEl.textContent = _nt('nostr_looking_up', 'Looking up…');
            nameEl.style.color = 'var(--text-secondary)';
        }
    };
    if (profile) applyProfile(profile);
    else if (entry.npub && !deferred) row._resolve();
    else if (entry.npub) row._looking();

    return row;
}

// --- Prepared posts --------------------------------------------------------
// The pool the display picks from: posts of the last hour, rendered as the
// card the panel will show, in the order they would be picked.

let nostrStatusTimer = null;
let nostrPoolTimer = null;
let currentNostrModalPost = null;

// The theme selected in the form, saved or not, so the preview follows the
// switch straight away.
function _nostrTheme() {
    const toggle = document.querySelector('[data-config-key="nostr_card_theme"]');
    const value = toggle?.getValue?.();
    return value === 'dark' || value === 'light' ? value : ((typeof currentConfig !== 'undefined' && currentConfig?.nostr_card_theme) || 'light');
}

// Whether the post's account is set to image only in the form, saved or
// not, so the preview follows its switch straight away. An account no longer
// in the list keeps what the server says.
function _nostrImageOnly(post) {
    const row = Array.from(document.querySelectorAll('.nostr-account-row'))
        .find(r => r.querySelector('.nostr-npub-input')?.value.trim() === post.npub);
    return row ? row._imageOnly() : !!post.image_only;
}

function _nostrCardUrl(post, width) {
    // A stable address, so the browser keeps the card instead of asking the
    // Pi to render it again on every reload of the list.
    const style = _nostrImageOnly(post) ? 'image' : 'card';
    return `/api/nostr-card/${post.key}?theme=${_nostrTheme()}&style=${style}${width ? '&w=' + width : ''}`;
}

// What the list showed last, so a reload that changes nothing leaves it be.
let _nostrPoolSignature = null;

// Only the post the display shows at the next block is marked; the order of
// the cards already tells the rest.
function _nostrNextLabel(post) {
    return post.state === 'next' ? _nt('nostr_state_next', 'Next') : '';
}

// When a post was published: how long ago, and the date and time.
// "vor 5 Min. (14.10.26, 23:29 Uhr)". The age is worded by the browser in the
// page's language; the template around it, e.g. the German "Uhr", comes from
// the translations.
function _nostrAge(ts) {
    if (!ts) return '';
    const lang = document.documentElement.lang || undefined;
    const seconds = Math.max(0, Math.round(Date.now() / 1000 - ts));
    let ago;
    try {
        const rtf = new Intl.RelativeTimeFormat(lang, { numeric: 'auto', style: 'short' });
        if (seconds < 60) ago = rtf.format(0, 'second');
        else if (seconds < 3600) ago = rtf.format(-Math.floor(seconds / 60), 'minute');
        else if (seconds < 86400) ago = rtf.format(-Math.floor(seconds / 3600), 'hour');
        else ago = rtf.format(-Math.floor(seconds / 86400), 'day');
    } catch (e) {
        ago = `${Math.floor(seconds / 60)} min`;
    }
    const d = new Date(ts * 1000);
    const date = d.toLocaleDateString(lang, { day: '2-digit', month: '2-digit', year: '2-digit' });
    const time = d.toLocaleTimeString(lang, { hour: '2-digit', minute: '2-digit' });
    return _nt('nostr_post_age', '{ago} ({date}, {time})')
        .replace('{ago}', ago).replace('{date}', date).replace('{time}', time);
}

// Seconds until an age now `seconds` old reads differently. The wording steps
// per minute below an hour, per hour below a day, then per day - each post at
// its own moment, not on the clock's full minute: one published at 23:29:40
// turns from 5 to 6 minutes at 23:35:40.
function _nostrAgeStep(seconds) {
    const unit = seconds < 3600 ? 60 : seconds < 86400 ? 3600 : 86400;
    return unit - (seconds % unit);
}

// After a language switch: ages, the window in the hint and the pool texts
// again, in the new language.
window._nostrOnLanguageChange = () => {
    document.querySelectorAll('.nostr-age[data-ts]').forEach(el => {
        el.textContent = _nostrAge(Number(el.dataset.ts));
    });
    _nostrPoolSignature = null;
    if (document.getElementById('nostr-pool-list')) loadNostrPool();
    refreshNostrStatus();
};

// Every age on the page moves on by itself, between the minute-wise reloads:
// one timer, woken exactly when the next of them changes.
let _nostrAgeTimer = null;
function _nostrScheduleAges() {
    clearTimeout(_nostrAgeTimer);
    const stamps = Array.from(document.querySelectorAll('.nostr-age[data-ts]'), el => Number(el.dataset.ts));
    if (!stamps.length) return;
    const now = Date.now() / 1000;
    const wait = Math.min(...stamps.map(ts => _nostrAgeStep(Math.max(0, Math.round(now - ts)))));
    _nostrAgeTimer = setTimeout(() => {
        document.querySelectorAll('.nostr-age[data-ts]').forEach(el => {
            el.textContent = _nostrAge(Number(el.dataset.ts));
        });
        _nostrScheduleAges();
    }, Math.max(1, wait) * 1000 + 50);
}

function createNostrPostTile(post) {
    const tile = document.createElement('div');
    tile.className = 'nostr-post-tile';
    tile.style.cssText = 'display:flex; flex-direction:column; gap:6px; cursor:pointer;';
    tile.addEventListener('click', () => openNostrPreview(post));

    const frame = document.createElement('div');
    frame.style.cssText = 'position:relative; border:1px solid var(--border-subtle); border-radius:10px; overflow:hidden; background:var(--bg-input);';
    const img = document.createElement('img');
    img.src = _nostrCardUrl(post, 400);
    img.alt = post.name || '';
    img.loading = 'lazy';
    img.dataset.nostrKey = post.key;
    img.style.cssText = 'display:block; width:100%; height:auto;';
    frame.append(img);
    if (_nostrNextLabel(post)) {
        const badge = document.createElement('span');
        badge.textContent = _nostrNextLabel(post);
        badge.style.cssText = 'position:absolute; top:6px; left:6px; font-size:0.7rem; font-weight:600; padding:2px 8px; border-radius:10px; color:#fff; background:var(--accent);';
        frame.append(badge);
    }

    const detail = document.createElement('div');
    detail.className = 'nostr-age';
    detail.dataset.ts = post.created_at;
    detail.style.cssText = 'font-size:0.75rem; color:var(--text-secondary); text-align:center;';
    detail.textContent = _nostrAge(post.created_at);

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
        if (data.window_minutes) _nostrWindowMinutes = data.window_minutes;
        _nostrUpdatePoolHint();
        const count = document.getElementById('nostr-pool-count');
        if (count) count.textContent = `(${posts.length})`;
        const signature = JSON.stringify([_nostrTheme(), posts.map(p => [p.key, p.state, _nostrImageOnly(p)]),
                                          data.sample?.key || null]);
        if (signature === _nostrPoolSignature && list.children.length) return;
        _nostrPoolSignature = signature;
        list.replaceChildren();
        if (!posts.length) {
            const note = document.createElement('p');
            note.style.cssText = 'grid-column:1/-1; text-align:center; color:var(--text-secondary); margin:8px 0;';
            note.textContent = _nt('nostr_pool_empty', 'Nobody posted an image within the set time window ({window}), so memes are shown.')
                .replace('{window}', _nostrWindowText());
            list.appendChild(note);
            if (data.sample) {
                list.appendChild(createNostrPostTile({ ...data.sample, state: 'preview' }));
                _nostrScheduleAges();
            }
            return;
        }
        posts.forEach(post => list.appendChild(createNostrPostTile(post)));
        _nostrScheduleAges();
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
    const published = document.getElementById('nostr-modal-published');
    published.className = 'nostr-age';
    published.dataset.ts = post.created_at;
    published.textContent = _nostrAge(post.created_at);
    const state = document.getElementById('nostr-modal-state');
    state.textContent = _nostrNextLabel(post);
    state.closest('.meme-info-row').style.display = state.textContent ? '' : 'none';
    const image = document.getElementById('nostr-modal-image');
    image.alt = post.name || '';
    image.src = _nostrCardUrl(post);
    document.getElementById('nostr-modal-open-btn').style.display = post.note ? '' : 'none';
    modal.style.display = 'flex';
    _nostrScheduleAges();
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

// One fetch problem in the page's language. The server sends a code with
// its parameters and an English text, which stays the fallback for codes
// this page has no translation for.
function _nostrErrorText(e) {
    if (typeof e === 'string') return e;
    let text = window.translations?.['nostr_err_' + e.code] || e.text || e.code;
    Object.entries(e.params || {}).forEach(([k, v]) => { text = text.replace(`{${k}}`, v); });
    return `${e.source}: ${text}`;
}

// Under the relays in the advanced settings: how many are pushing new posts
// right now, and which, in the tooltip. Created on first use, and again
// after the form was built anew.
function _nostrShowLive(live) {
    let el = document.getElementById('nostr-live-status');
    if (!el) {
        const group = document.querySelector('[data-config-key="nostr_relays"]')?.closest('.form-group');
        if (!group) return;
        el = document.createElement('div');
        el.id = 'nostr-live-status';
        el.className = 'form-description';
        el.style.cssText = 'font-size:0.8rem; color:var(--text-secondary); margin-top:6px; cursor:help; width:fit-content;';
        group.appendChild(el);
    }
    if (!live || !live.total) {
        el.style.display = 'none';
        return;
    }
    el.style.display = '';
    el.textContent = _nt('nostr_live_status', 'Live: {connected} of {total} relays connected')
        .replace('{connected}', live.connected).replace('{total}', live.total);
    // The configured relays and the ones the followed accounts write to.
    const relays = Object.entries(live.relays || {});
    const up = relays.filter(([, ok]) => ok).map(([r]) => r).sort();
    const down = relays.filter(([, ok]) => !ok).map(([r]) => r).sort();
    const NL = '\n';
    let tip = up.length ? up.join(NL) : _nt('nostr_live_none', 'No relay connected');
    if (down.length) tip += NL + NL + _nt('nostr_live_not_connected', 'Not connected:') + NL + down.join(NL);
    el.title = tip;
}

// The status line: the sources the last fetch could not reach. Fetches
// need no button: one runs at start, on a timer, and whenever the Nostr
// settings are saved.
async function refreshNostrStatus() {
    const el = document.getElementById('nostr-fetch-status');
    if (!el) return null;
    try {
        const resp = await fetch('/api/nostr-status');
        const data = await resp.json();
        const s = data.status || {};
        const errList = document.getElementById('nostr-fetch-errors');
        const errors = s.running ? [] : (s.errors || []);
        if (errList) {
            errList.replaceChildren(...errors.map(e => {
                const li = document.createElement('li');
                li.textContent = _nostrErrorText(e);
                return li;
            }));
            if (!errors.length) errList.style.display = 'none';
        }
        el.replaceChildren();
        _nostrShowLive(data.live);
        if (errors.length && errList) {
            // The count opens the list underneath: a tooltip is out of
            // reach on a phone, and the reasons are what tell you what to fix.
            // Red only when the fetch failed. A relay or two not answering
            // while the rest delivered is a note, not an error.
            const failed = s.message && s.message !== 'ok';
            const toggle = document.createElement('a');
            toggle.href = '#';
            toggle.style.cssText = `color:${failed ? 'var(--danger)' : 'var(--text-secondary)'}; text-decoration:underline; cursor:pointer;`;
            toggle.textContent = (failed
                ? _nt('nostr_fetch_errors', '{count} error(s)')
                : _nt('nostr_fetch_notes', '{count} source(s) not reached'))
                .replace('{count}', errors.length);
            toggle.addEventListener('click', (e) => {
                e.preventDefault();
                errList.style.display = errList.style.display === 'none' ? 'block' : 'none';
            });
            if (el.textContent) el.append(' — ');
            el.append(toggle);
        }
        el.parentElement.style.display = el.childNodes.length ? '' : 'none';
        return s;
    } catch (err) {
        return null;
    }
}

// Follows a fetch the server is running - the one a save starts - and
// reloads the list and the account names once it is done.
function _nostrWatchFetch() {
    clearInterval(nostrStatusTimer);
    let sawRunning = false;
    const started = Date.now();
    nostrStatusTimer = setInterval(async () => {
        if (!document.getElementById('nostr-fetch-status')) {
            clearInterval(nostrStatusTimer);
            return;
        }
        const s = await refreshNostrStatus();
        if (s?.running) sawRunning = true;
        // Done once it has been seen running and stopped, or after a few
        // seconds if it never was: finished before the first poll, or no
        // Nostr setting changed and none was started.
        if (s && !s.running && (sawRunning || Date.now() - started > 4000)) {
            clearInterval(nostrStatusTimer);
            loadNostrPool();
            window._nostrAccountsInput?.refreshProfiles();
        }
    }, 2500);
}
window._nostrSaveHook = () => {
    if (document.getElementById('nostr-fetch-status')) _nostrWatchFetch();
};

function createNostrManagementInterface(field) {
    const container = document.createElement('div');
    container.className = 'meme-management-container';

    const statusRow = document.createElement('div');
    statusRow.style.cssText = 'display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:12px;';
    statusRow.style.display = 'none';
    const statusEl = document.createElement('span');
    statusEl.id = 'nostr-fetch-status';
    statusEl.style.cssText = 'font-size:0.85rem; color:var(--text-secondary);';
    statusRow.append(statusEl);

    const errorList = document.createElement('ul');
    errorList.id = 'nostr-fetch-errors';
    errorList.style.cssText = 'display:none; margin:-4px 0 12px; padding:8px 8px 8px 28px; font-size:0.8rem; font-family:var(--font-mono); color:var(--text-secondary); border:1px solid var(--border-subtle); border-radius:8px; max-height:200px; overflow-y:auto; word-break:break-all;';

    const label = document.createElement('label');
    label.className = 'form-label';
    label.innerHTML = `${escapeHtml(_nt('nostr_management', 'Current Posts'))} <span id="nostr-pool-count" style="color:var(--text-secondary); font-weight:400;"></span>`;
    const hint = document.createElement('div');
    hint.className = 'form-description';
    hint.id = 'nostr-pool-hint';
    hint.style.cssText = 'font-size:0.8rem; color:var(--text-secondary); margin-bottom:8px;';
    hint.textContent = _nt('nostr_pool_hint', 'In the order they will be shown. A post stays here for {window} after it was published.')
        .replace('{window}', _nostrWindowText(true));

    const list = document.createElement('div');
    list.id = 'nostr-pool-list';
    list.style.cssText = 'display:grid; grid-template-columns:repeat(auto-fill, minmax(160px, 1fr)); gap:12px; margin-top:8px; align-items:start;';
    const scroll = document.createElement('div');
    scroll.className = 'nostr-scroll-container';
    scroll.appendChild(list);

    container.append(statusRow, errorList, label, hint, scroll);

    setTimeout(() => {
        loadNostrPool();
        refreshNostrStatus().then(s => { if (s?.running) _nostrWatchFetch(); });
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
