// Section preview cards.
// Part 5 of 8, split from config.js. Load order matters:
// these run as classic scripts sharing one global scope.

// ── Section preview cards ──────────────────────────────────────────────────
// Cached preview data fetched from /api/config/preview-data after page load.
window._previewData = {};
// Live unsaved form values that affect preview structure (selects, toggles, etc.)
// Reset on each form render; accumulated as user edits without saving.
window._pendingConfigOverrides = {};

// Sets a preview-value element: animated dots when value is '…', plain text otherwise.
function _setPreviewValue(el, val) {
    if (val === '\u2026') {
        el.innerHTML = '<span class="mpa-dots"></span>';
    } else {
        el.textContent = val;
    }
}

// Build a single-theme info card matching the e-ink info block layout:
// two columns, each centered (label on top, large value below) with spacing.
// Uses the same Roboto font as the e-ink renderer (Regular for labels, Bold for values).
function _buildSingleThemeCard(leftLabel, leftVal, rightLabel, rightVal, dataColor, bg, labelColor) {
    const card = document.createElement('div');
    card.style.cssText = `flex:1;min-width:0;border:1px solid rgba(128,128,128,.2);border-radius:8px;background:${bg};color:${bg === '#fff' ? '#1a1a1e' : '#e8e8ec'};display:grid;grid-template-columns:1fr 1fr;font-family:'Roboto',Arial,sans-serif;`;
    const mkCell = (label, val) => {
        const cell = document.createElement('div');
        cell.style.cssText = 'display:flex;flex-direction:column;align-items:center;text-align:center;padding:12px 6px;';
        const lbl = document.createElement('div');
        lbl.style.cssText = `font-size:.72em;font-weight:400;color:${labelColor};margin-bottom:10px;line-height:1.3;`;
        lbl.textContent = label;
        const v = document.createElement('div');
        v.style.cssText = `font-size:1.12em;font-weight:700;color:${dataColor};`;
        v.className = 'preview-value';
        _setPreviewValue(v, val || '\u2014');
        cell.appendChild(lbl);
        cell.appendChild(v);
        return cell;
    };
    card.appendChild(mkCell(leftLabel, leftVal));
    card.appendChild(mkCell(rightLabel, rightVal));
    return card;
}

function _buildSectionPreview(categoryId, sectionEl) {
    const cfg = { ...(window.currentConfig || {}), ...(window._pendingConfigOverrides || {}) };
    const t = window.translations || {};

    // Returns a wrapper whose first two children are the light and dark theme
    // cards, tagged with .preview-theme-light / .preview-theme-dark.
    // Refresh functions close over the card elements directly so they survive
    // DOM reorganisation in renderConfigurationForm.
    function mkWrapper(lightCard, darkCard) {
        lightCard.classList.add('preview-theme-light');
        darkCard.classList.add('preview-theme-dark');
        const w = document.createElement('div');
        w.setAttribute('aria-hidden', 'true');
        w.appendChild(lightCard);
        w.appendChild(darkCard);
        return w;
    }

    // ── Price Stats ───────────────────────────────────────────────────────
    if (categoryId === 'price_stats') {
        const moscowUnit = cfg['moscow_time_unit'] || 'sats';
        const currency   = cfg['btc_price_currency'] || 'USD';
        const symbols = {'USD':'$','EUR':'€','GBP':'£','CAD':'C$','CHF':'CHF','AUD':'A$','JPY':'¥'};
        const sym = symbols[currency] || currency;
        const rl = moscowUnit === 'hour' ? (t.moscow_time || 'Moscow time') : `1 ${currency} =`;
        const clLight = cfg['color_btc_price_light'] || '#147A38';
        const clDark  = cfg['color_btc_price_dark']  || '#22C55E';
        const ll = t.btc_price || 'BTC price';

        function fmtPrice(p) { return p == null ? '…' : `${sym} ${_fmtNum(p)}`; }
        function fmtMoscow(m) {
            if (m == null) return '…';
            if (moscowUnit === 'hour') {
                const h = Math.floor(m / 100), min = m % 100;
                return `${String(h).padStart(2,'0')}:${String(min).padStart(2,'0')}`;
            }
            return `${_fmtNum(m)} sats`;
        }

        const pd = window._previewData.price;
        const lightCard = _buildSingleThemeCard(ll, fmtPrice(pd?.price), rl, fmtMoscow(pd?.moscow_time), clLight, '#fff', '#6a6a78');
        const darkCard  = _buildSingleThemeCard(ll, fmtPrice(pd?.price), rl, fmtMoscow(pd?.moscow_time), clDark,  '#111827', '#aaa');

        window._refreshPricePreview = (data) => {
            const pv = fmtPrice(data?.price);
            const mv = fmtMoscow(data?.moscow_time);
            [lightCard, darkCard].forEach(card => {
                const cells = card.querySelectorAll('.preview-value');
                if (cells.length >= 2) { _setPreviewValue(cells[0], pv); _setPreviewValue(cells[1], mv); }
            });
        };
        return mkWrapper(lightCard, darkCard);
    }

    // ── Bitaxe Stats ──────────────────────────────────────────────────────
    if (categoryId === 'bitaxe_stats') {
        const mode    = cfg['bitaxe_display_mode'] || 'blocks';
        const clLight = cfg['color_bitaxe_stats_light'] || '#8C6D0F';
        const clDark  = cfg['color_bitaxe_stats_dark']  || '#FFC400';
        const rl = mode === 'difficulty' ? (t.best_difficulty || 'Best diff') : (t.valid_blocks || 'Found blocks');

        const hasBitaxe = (cfg['bitaxe_miner_table'] || []).some(a => a.address?.trim());

        function fmtHashrate(ths) {
            if (ths == null) return hasBitaxe ? '…' : `0${_decMark()}0 kH/s`;
            if (ths >= 1000) return `${_fmtFixed(ths/1000, 2)} PH/s`;
            if (ths >= 1)    return `${_fmtFixed(ths, 2)} TH/s`;
            return `${_fmtFixed(ths*1000, 1)} GH/s`;
        }
        function fmtRight(val) {
            if (val == null) return hasBitaxe ? '…' : (mode === 'difficulty' ? '0.0K' : '0');
            return mode === 'difficulty' ? formatBitaxeDifficulty(val) : String(val);
        }

        const bd  = window._previewData.bitaxe;
        const onl = bd?.miners_online ?? '?';
        const tot = bd?.miners_total  ?? '?';
        const ll  = t.total_hashrate || 'Bitaxe Hashrate';
        const lv  = fmtHashrate(bd?.hashrate_ths);
        const rv  = fmtRight(mode === 'difficulty' ? bd?.best_difficulty : bd?.valid_blocks);

        const lightCard = _buildSingleThemeCard(ll, lv, rl, rv, clLight, '#fff', '#6a6a78');
        const darkCard  = _buildSingleThemeCard(ll, lv, rl, rv, clDark,  '#111827', '#aaa');

        window._refreshBitaxePreview = (data) => {
            const lv2 = fmtHashrate(data?.hashrate_ths);
            const rv2 = fmtRight(mode === 'difficulty' ? data?.best_difficulty : data?.valid_blocks);
            const ll2 = t.total_hashrate || 'Bitaxe Hashrate';
            [lightCard, darkCard].forEach(card => {
                const cells = card.querySelectorAll('.preview-value');
                const lbls  = card.querySelectorAll('[style*="font-size:.72em"]');
                if (cells.length >= 2) { _setPreviewValue(cells[0], lv2); _setPreviewValue(cells[1], rv2); }
                if (lbls.length >= 1)  lbls[0].textContent = ll2;
            });
        };
        return mkWrapper(lightCard, darkCard);
    }

    // ── Wallet Monitoring ─────────────────────────────────────────────────
    if (categoryId === 'wallet_monitoring') {
        const walletCurrency = cfg['wallet_balance_currency'] || 'EUR';
        const unit = cfg['wallet_balance_unit'] || 'btc';
        const symbols = {'USD':'$','EUR':'€','GBP':'£','CAD':'C$','CHF':'CHF','AUD':'A$','JPY':'¥'};
        const sym = symbols[walletCurrency] || walletCurrency;
        const hasWallets = (cfg['wallet_balance_addresses_with_comments'] || []).some(a => a.address?.trim());
        const clLight = cfg['color_wallets_light'] || '#00838F';
        const clDark  = cfg['color_wallets_dark']  || '#00BCD4';
        const ll = unit === 'sats' ? (t.wallet_balance_sats || 'Total (Sats)') : (t.total_balance || 'Total Balance');
        const rl = t.fiat_value || 'Fiat value';

        function fmtBtc(v) {
            if (v == null) return hasWallets ? '…' : (unit === 'sats' ? '0' : _fmtFixed(0, 8));
            return unit === 'sats' ? _fmtNum(v * 1e8) : _fmtFixed(v, 8);
        }
        function fmtFiat(fv, btcAmt) {
            if (fv != null) return `${_fmtNum(fv)} ${sym}`;
            // Fallback: compute from BTC price when backend fiat_value is null (currency mismatch)
            const btcPrice = window._previewData.price?.price;
            if (btcPrice && btcAmt != null) {
                return `${_fmtNum(btcAmt * btcPrice)} ${sym}`;
            }
            return hasWallets ? '…' : `${_fmtFixed(0, 2)} ${sym}`;
        }

        const wd = window._previewData.wallet;
        const lv = fmtBtc(wd?.total_btc ?? null);
        const rv = fmtFiat(wd?.fiat_value, wd?.total_btc ?? null);

        const lightCard = _buildSingleThemeCard(ll, lv, rl, rv, clLight, '#fff', '#6a6a78');
        const darkCard  = _buildSingleThemeCard(ll, lv, rl, rv, clDark,  '#111827', '#aaa');

        window._refreshWalletPreview = (data) => {
            const lv2 = fmtBtc(data?.total_btc);
            const rv2 = fmtFiat(data?.fiat_value, data?.total_btc);
            [lightCard, darkCard].forEach(card => {
                const cells = card.querySelectorAll('.preview-value');
                if (cells.length >= 2) { _setPreviewValue(cells[0], lv2); _setPreviewValue(cells[1], rv2); }
            });
        };
        return mkWrapper(lightCard, darkCard);
    }

    // ── Donation ──────────────────────────────────────────────────────────
    if (categoryId === 'donation') {
        const clLight = cfg['color_donation_light'] || '#B35C00';
        const clDark  = cfg['color_donation_dark']  || '#F7931A';
        const mode    = cfg['donation_display_mode'] || 'latest';

        function mkDonCard(bg, dataColor) {
            const card = document.createElement('div');
            card.style.cssText = `flex:1;min-width:0;border:1px solid rgba(128,128,128,.2);border-radius:8px;background:${bg};display:flex;flex-direction:column;align-items:center;text-align:center;padding:12px 8px;gap:10px;font-family:'Roboto',Arial,sans-serif;`;
            const hdr = document.createElement('div');
            hdr.style.cssText = `font-size:.72em;font-weight:400;color:${bg === '#fff' ? '#6a6a78' : '#aaa'};line-height:1.3;`;
            hdr.className = 'don-header';
            const msg = document.createElement('div');
            msg.style.cssText = `font-size:1.05em;font-weight:700;color:${dataColor};`;
            msg.className = 'don-msg';
            card.appendChild(hdr);
            card.appendChild(msg);
            return card;
        }

        const lightCard = mkDonCard('#fff', clLight);
        const darkCard  = mkDonCard('#111827', clDark);

        function pickDon(donData) {
            if (!donData) return null;
            // donData may be {latest, highest, auto} or a legacy single object
            if (donData.latest !== undefined || donData.highest !== undefined) {
                return donData[mode] || donData.auto || donData.latest || donData.highest || null;
            }
            return donData;
        }

        function refreshDonation(data) {
            const don    = pickDon(data);
            const header = don?.header_text || (t.donation_no_donations || 'No donations yet');
            const msg    = don?.message || '—';
            [lightCard, darkCard].forEach(card => {
                card.querySelector('.don-header').textContent = header;
                card.querySelector('.don-msg').textContent    = msg;
            });
        }
        refreshDonation(window._previewData.donation);

        window._refreshDonationPreview = refreshDonation;
        return mkWrapper(lightCard, darkCard);
    }

    // ── Countdown (BTC Supply) ────────────────────────────────────────────
    if (categoryId === 'countdown') {
        const clLight = cfg['color_countdown_light'] || '#C62828';
        const clDark  = cfg['color_countdown_dark']  || '#F02D2D';
        const ll = t.btc_remaining || 'BTC Remaining';
        const rl = t.pct_mined || '% Mined';

        function fmtRemaining(r) {
            if (r == null) return '…';
            return `${_fmtNum(r, 2)} BTC`;
        }
        function fmtPct(p) {
            if (p == null) return '…';
            for (let d = 2; d < 11; d++) {
                const s = p.toFixed(d);
                if (s !== (100).toFixed(d)) return `${_fmtFixed(p, d)}%`;
            }
            return `${_fmtFixed(p, 10)}%`;
        }

        const cd = window._previewData.countdown;
        const lightCard = _buildSingleThemeCard(ll, fmtRemaining(cd?.remaining_btc), rl, fmtPct(cd?.pct_mined), clLight, '#fff', '#6a6a78');
        const darkCard  = _buildSingleThemeCard(ll, fmtRemaining(cd?.remaining_btc), rl, fmtPct(cd?.pct_mined), clDark,  '#111827', '#aaa');

        window._refreshCountdownPreview = (data) => {
            const lv2 = fmtRemaining(data?.remaining_btc);
            const rv2 = fmtPct(data?.pct_mined);
            [lightCard, darkCard].forEach(card => {
                const cells = card.querySelectorAll('.preview-value');
                if (cells.length >= 2) { _setPreviewValue(cells[0], lv2); _setPreviewValue(cells[1], rv2); }
            });
        };
        return mkWrapper(lightCard, darkCard);
    }

    // ── Halving ───────────────────────────────────────────────────────────
    if (categoryId === 'halving') {
        const clLight = cfg['color_halving_light'] || '#1565C0';
        const clDark  = cfg['color_halving_dark']  || '#2979FF';
        const lang = window._pendingLanguage || cfg['language'] || 'en';
        const ll = t.halving_date || 'Next Halving';

        function fmtHalvingDate(isoStr) {
            if (!isoStr) return '…';
            try { return _formatSpecificDate(new Date(isoStr), lang); } catch (e) { return '…'; }
        }
        function fmtCountdown(hd) {
            if (!hd) return '…';
            return (hd.hours_remaining ?? 0) < 24
                ? `${_fmtFixed(hd.hours_remaining || 0, 1)}h`
                : `${Math.round(hd.days_remaining || 0)}d`;
        }

        const hd = window._previewData.halving;
        const rl = hd && (hd.hours_remaining ?? 999) < 24
            ? (t.halving_hours_left || 'Hours Until Halving')
            : (t.halving_days_left  || 'Days Until Halving');

        const lightCard = _buildSingleThemeCard(ll, fmtHalvingDate(hd?.estimated_date), rl, fmtCountdown(hd), clLight, '#fff', '#6a6a78');
        const darkCard  = _buildSingleThemeCard(ll, fmtHalvingDate(hd?.estimated_date), rl, fmtCountdown(hd), clDark,  '#111827', '#aaa');

        window._refreshHalvingPreview = (data) => {
            const lv2 = fmtHalvingDate(data?.estimated_date);
            const rv2 = fmtCountdown(data);
            [lightCard, darkCard].forEach(card => {
                const cells = card.querySelectorAll('.preview-value');
                if (cells.length >= 2) { _setPreviewValue(cells[0], lv2); _setPreviewValue(cells[1], rv2); }
            });
        };
        return mkWrapper(lightCard, darkCard);
    }

    // ── Network Stats ─────────────────────────────────────────────────────
    if (categoryId === 'network_stats') {
        const clLight = cfg['color_network_light'] || '#6A1B9A';
        const clDark  = cfg['color_network_dark']  || '#B23CE8';
        const ll = t.network_hashrate || 'Network Hashrate';
        const rl = t.network_difficulty || 'Difficulty';

        function fmtHashrate(hs) {
            if (hs == null) return '…';
            if (hs >= 1e18) return `${_fmtFixed(hs/1e18, 2)} EH/s`;
            if (hs >= 1e15) return `${_fmtFixed(hs/1e15, 2)} PH/s`;
            if (hs >= 1e12) return `${_fmtFixed(hs/1e12, 2)} TH/s`;
            if (hs >= 1e9)  return `${_fmtFixed(hs/1e9, 2)} GH/s`;
            return `${_fmtNum(hs)} H/s`;
        }
        function fmtDifficulty(d) {
            if (d == null) return '…';
            if (d >= 1e12) return `${_fmtFixed(d/1e12, 2)} T`;
            if (d >= 1e9)  return `${_fmtFixed(d/1e9, 2)} G`;
            if (d >= 1e6)  return `${_fmtFixed(d/1e6, 2)} M`;
            return `${_fmtNum(d)}`;
        }

        const nd = window._previewData.network;
        const lightCard = _buildSingleThemeCard(ll, fmtHashrate(nd?.hashrate), rl, fmtDifficulty(nd?.difficulty), clLight, '#fff', '#6a6a78');
        const darkCard  = _buildSingleThemeCard(ll, fmtHashrate(nd?.hashrate), rl, fmtDifficulty(nd?.difficulty), clDark,  '#111827', '#aaa');

        window._refreshNetworkPreview = (data) => {
            const lv2 = fmtHashrate(data?.hashrate);
            const rv2 = fmtDifficulty(data?.difficulty);
            [lightCard, darkCard].forEach(card => {
                const cells = card.querySelectorAll('.preview-value');
                if (cells.length >= 2) { _setPreviewValue(cells[0], lv2); _setPreviewValue(cells[1], rv2); }
            });
        };
        return mkWrapper(lightCard, darkCard);
    }

    return null;
}


// Fit a hash string into `span` without wrapping.
// Truncates symmetrically from the middle, inserting "…", using all available
// width inside the parent's padding.  Accounts for CSS letter-spacing.
function _fitHashSpan(span, fullHash) {
    if (!fullHash) return;
    span._fullHash = fullHash;
    const container = span.parentElement;
    if (!container) { span.textContent = fullHash; return; }

    // Subtract container padding so the hash stays within the visible frame
    const ccs = window.getComputedStyle(container);
    const hPad = parseFloat(ccs.paddingLeft || 0) + parseFloat(ccs.paddingRight || 0);
    const availWidth = container.clientWidth - hPad - 4; // 4px breathing room
    if (availWidth <= 0) { span.textContent = fullHash; return; }

    const canvas = (_fitHashSpan._cv = _fitHashSpan._cv || document.createElement('canvas'));
    const ctx = canvas.getContext('2d');
    const cs = window.getComputedStyle(span);
    ctx.font = `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;

    // Mirror letter-spacing so canvas measureText matches the rendered width.
    // ctx.letterSpacing is supported in Chrome 99+/Firefox 104+; fall back to
    // manual addition of per-character spacing for older engines.
    const letterSpacingPx = parseFloat(cs.letterSpacing) || 0;
    if ('letterSpacing' in ctx) {
        ctx.letterSpacing = cs.letterSpacing;
    }
    const measure = (text) => {
        const w = ctx.measureText(text).width;
        return ('letterSpacing' in ctx) ? w : w + letterSpacingPx * Math.max(text.length - 1, 0);
    };

    if (measure(fullHash) <= availWidth) {
        span.textContent = fullHash;
        return;
    }
    const ellipsis = '…';
    const budget = availWidth - measure(ellipsis);
    let lo = 0, hi = Math.floor(fullHash.length / 2);
    while (lo < hi) {
        const mid = Math.ceil((lo + hi) / 2);
        if (measure(fullHash.slice(0, mid) + fullHash.slice(-mid)) <= budget) {
            lo = mid;
        } else {
            hi = mid - 1;
        }
    }
    span.textContent = lo > 0
        ? fullHash.slice(0, lo) + ellipsis + fullHash.slice(-lo)
        : ellipsis;
}

function createDateColorGroup() {
    const t = window.translations || {};
    const cfg = window.currentConfig || {};
    const lang = cfg['language'] || 'en';

    const lightStart = cfg['color_date_start_light'] || '#1c82c0';
    const lightEnd   = cfg['color_date_end_light']   || '#c040a8';
    const darkStart  = cfg['color_date_start_dark']  || '#4FC3F7';
    const darkEnd    = cfg['color_date_end_dark']    || '#BA68C8';

    const previewText = _formatDateForPreview(lang);

    const wrapper = document.createElement('div');
    wrapper.style.width = '100%';

    // Genesis block hash — fallback when no live block hash is available yet
    const SAMPLE_HASH = '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f';

    function getDateHashChars() {
        return window._previewData?.latestBlockHash || SAMPLE_HASH;
    }

    function buildHashPreview(startVal, endVal) {
        const span = document.createElement('span');
        span.style.cssText = `font-family:'IBMPlexMono',monospace; font-size:0.58em; letter-spacing:0.02em; background:linear-gradient(90deg,${startVal},${endVal}); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; margin-top:6px; display:block; white-space:nowrap; overflow:hidden;`;
        requestAnimationFrame(() => _fitHashSpan(span, getDateHashChars()));
        if (typeof ResizeObserver !== 'undefined') {
            const ro = new ResizeObserver(() => _fitHashSpan(span, span._fullHash || getDateHashChars()));
            requestAnimationFrame(() => { if (span.parentElement) ro.observe(span.parentElement); });
        }
        return span;
    }

    function buildRow(themeLabel, startKey, endKey, startVal, endVal, bgColor, previewBg, previewShadow) {
        const row = document.createElement('div');
        row.className = 'date-color-row';
        row.style.background = bgColor;

        const label = document.createElement('div');
        label.style.cssText = 'width:100%; font-weight:600; font-size:0.95em; margin-bottom:4px; color:var(--text-primary)';
        label.textContent = themeLabel;
        row.appendChild(label);

        const startGroup = document.createElement('div');
        startGroup.style.cssText = 'display:flex; flex-direction:column; gap:4px;';
        const startLabel = document.createElement('span');
        startLabel.style.cssText = 'font-size:0.8em; color:var(--text-secondary)';
        startLabel.textContent = t.holiday_color_start || 'Start Color';
        startGroup.appendChild(startLabel);
        const startInput = createColorInput(startVal);
        startInput.dataset.configKey = startKey;
        startGroup.appendChild(startInput);
        row.appendChild(startGroup);

        const endGroup = document.createElement('div');
        endGroup.style.cssText = 'display:flex; flex-direction:column; gap:4px;';
        const endLabel = document.createElement('span');
        endLabel.style.cssText = 'font-size:0.8em; color:var(--text-secondary)';
        endLabel.textContent = t.holiday_color_end || 'End Color';
        endGroup.appendChild(endLabel);
        const endInput = createColorInput(endVal);
        endInput.dataset.configKey = endKey;
        endGroup.appendChild(endInput);
        row.appendChild(endGroup);

        const preview = document.createElement('div');
        preview.className = 'date-color-preview';
        preview.style.cssText = `flex:1; min-width:160px; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:10px 16px; border-radius:6px; background:${previewBg};`;
        if (previewShadow) preview.classList.add(previewShadow);
        const previewSpan = document.createElement('span');
        previewSpan.style.cssText = 'font-size:1.05em; font-weight:700; background:linear-gradient(90deg,' + startVal + ',' + endVal + '); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;';
        previewSpan.textContent = previewText;
        preview.appendChild(previewSpan);
        const hashSpan = buildHashPreview(startVal, endVal);
        preview.appendChild(hashSpan);
        row.appendChild(preview);

        function updatePreview() {
            const s = startInput.getValue ? startInput.getValue() : startVal;
            const e = endInput.getValue ? endInput.getValue() : endVal;
            const grad = `linear-gradient(90deg,${s},${e})`;
            previewSpan.style.background = grad;
            previewSpan.style.webkitBackgroundClip = 'text';
            previewSpan.style.backgroundClip = 'text';
            hashSpan.style.background = grad;
            hashSpan.style.webkitBackgroundClip = 'text';
            hashSpan.style.backgroundClip = 'text';
        }
        startInput.addEventListener('input', updatePreview);
        endInput.addEventListener('input', updatePreview);

        return { row, hashSpan };
    }

    const { row: lightRow, hashSpan: lightDateHashSpan } = buildRow(
        t.holiday_color_light_theme || 'Light Theme',
        'color_date_start_light', 'color_date_end_light',
        lightStart, lightEnd,
        'rgba(255,255,255,.04)', '#ffffff', 'preview-card-light'
    );
    wrapper.appendChild(lightRow);

    const { row: darkRow, hashSpan: darkDateHashSpan } = buildRow(
        t.holiday_color_dark_theme || 'Dark Theme',
        'color_date_start_dark', 'color_date_end_dark',
        darkStart, darkEnd,
        'rgba(0,0,0,.04)', '#1a1a2e', 'preview-card-dark'
    );
    wrapper.appendChild(darkRow);

    window._refreshDateHashPreview = (blockHash) => {
        const chars = blockHash || getDateHashChars();
        _fitHashSpan(lightDateHashSpan, chars);
        _fitHashSpan(darkDateHashSpan,  chars);
    };

    return wrapper;
}


function createHolidayColorGroup() {
    const t = window.translations || {};
    const wrapper = document.createElement('div');
    wrapper.style.width = '100%';

    // Read current values from the already-loaded config
    const cfg = window.currentConfig || {};
    const lightStart = cfg['color_holiday_start_light'] || '#D17300';
    const lightEnd   = cfg['color_holiday_end_light'] || '#C62828';
    const darkStart  = cfg['color_holiday_start_dark'] || '#F7931A';
    const darkEnd    = cfg['color_holiday_end_dark'] || '#FF6F6F';

    const _hLang = (window.currentConfig || {})['language'] || 'en';
    const { dateStr: _hDateStr, title: _hTitle, isToday: _todayIsHoliday } = _getHolidayPreview(_hLang);
    const previewText = `${_hDateStr}  ${_hTitle}`;

    // Genesis block hash — fallback when no live block hash is available yet
    const GENESIS_HASH = '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f';

    function getHashChars() {
        return window._previewData?.latestBlockHash || GENESIS_HASH;
    }

    function buildHashPreviewH(startVal, endVal) {
        const span = document.createElement('span');
        span.style.cssText = `font-family:'IBMPlexMono',monospace; font-size:0.58em; letter-spacing:0.02em; background:linear-gradient(90deg,${startVal},${endVal}); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; margin-top:6px; display:block; white-space:nowrap; overflow:hidden;`;
        requestAnimationFrame(() => _fitHashSpan(span, getHashChars()));
        if (typeof ResizeObserver !== 'undefined') {
            const ro = new ResizeObserver(() => _fitHashSpan(span, span._fullHash || getHashChars()));
            requestAnimationFrame(() => { if (span.parentElement) ro.observe(span.parentElement); });
        }
        return span;
    }

    function buildRow(themeLabel, startKey, endKey, startVal, endVal, bgColor, previewBg, previewShadow) {
        const row = document.createElement('div');
        row.className = 'date-color-row';
        row.style.background = bgColor;

        // Theme label spanning full width
        const label = document.createElement('div');
        label.style.cssText = 'width:100%; font-weight:600; font-size:0.95em; margin-bottom:4px; color:var(--text-primary)';
        label.textContent = themeLabel;
        row.appendChild(label);

        // Start color picker
        const startGroup = document.createElement('div');
        startGroup.style.cssText = 'display:flex; flex-direction:column; gap:4px;';
        const startLabel = document.createElement('span');
        startLabel.style.cssText = 'font-size:0.8em; color:var(--text-secondary)';
        startLabel.textContent = t.holiday_color_start || 'Start Color';
        startGroup.appendChild(startLabel);
        const startInput = createColorInput(startVal);
        startInput.dataset.configKey = startKey;
        startGroup.appendChild(startInput);
        row.appendChild(startGroup);

        // End color picker
        const endGroup = document.createElement('div');
        endGroup.style.cssText = 'display:flex; flex-direction:column; gap:4px;';
        const endLabel = document.createElement('span');
        endLabel.style.cssText = 'font-size:0.8em; color:var(--text-secondary)';
        endLabel.textContent = t.holiday_color_end || 'End Color';
        endGroup.appendChild(endLabel);
        const endInput = createColorInput(endVal);
        endInput.dataset.configKey = endKey;
        endGroup.appendChild(endInput);
        row.appendChild(endGroup);

        // Gradient preview (date/holiday text + hash sample line)
        const preview = document.createElement('div');
        preview.className = 'date-color-preview';
        preview.style.cssText = `flex:1; min-width:160px; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:10px 16px; border-radius:6px; background:${previewBg};`;
        if (previewShadow) preview.classList.add(previewShadow);
        const previewSpan = document.createElement('span');
        previewSpan.style.cssText = 'font-size:1.1em; font-weight:700; background:linear-gradient(90deg,' + startVal + ',' + endVal + '); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;';
        previewSpan.textContent = previewText;
        preview.appendChild(previewSpan);
        const hashSpan = buildHashPreviewH(startVal, endVal);
        preview.appendChild(hashSpan);
        row.appendChild(preview);

        // Live-update the gradient preview when colors change
        function updatePreview() {
            const s = startInput.getValue ? startInput.getValue() : startVal;
            const e = endInput.getValue ? endInput.getValue() : endVal;
            const grad = `linear-gradient(90deg,${s},${e})`;
            previewSpan.style.background = grad;
            previewSpan.style.webkitBackgroundClip = 'text';
            previewSpan.style.backgroundClip = 'text';
            hashSpan.style.background = grad;
            hashSpan.style.webkitBackgroundClip = 'text';
            hashSpan.style.backgroundClip = 'text';
        }
        startInput.addEventListener('input', updatePreview);
        endInput.addEventListener('input', updatePreview);

        return { row, previewSpan, hashSpan };
    }

    // Light theme row (first)
    const { row: lightRow, previewSpan: lightSpan, hashSpan: lightHashSpan } = buildRow(
        t.holiday_color_light_theme || 'Light Theme',
        'color_holiday_start_light', 'color_holiday_end_light',
        lightStart, lightEnd,
        'rgba(255,255,255,.04)', '#ffffff', 'preview-card-light'
    );
    wrapper.appendChild(lightRow);

    // Dark theme row (second)
    const { row: darkRow, previewSpan: darkSpan, hashSpan: darkHashSpan } = buildRow(
        t.holiday_color_dark_theme || 'Dark Theme',
        'color_holiday_start_dark', 'color_holiday_end_dark',
        darkStart, darkEnd,
        'rgba(0,0,0,.04)', '#1a1a2e', 'preview-card-dark'
    );
    wrapper.appendChild(darkRow);


    // Hook language-change refresh so preview text stays in sync
    window._refreshHolidayPreview = (overrideLang) => {
        const l = overrideLang || window._pendingLanguage || (window.currentConfig || {})['language'] || 'en';
        const { dateStr, title } = _getHolidayPreview(l);
        const text = `${dateStr}  ${title}`;
        lightSpan.textContent = text;
        darkSpan.textContent  = text;
    };

    window._refreshHolidayHashPreview = (blockHash) => {
        const chars = blockHash || getHashChars();
        _fitHashSpan(lightHashSpan, chars);
        _fitHashSpan(darkHashSpan,  chars);
    };

    return wrapper;
}


function createBlockHeightColorGroup() {
    const t = window.translations || {};
    const cfg = window.currentConfig || {};

    // The scale comes from the server - the same stop tables, median, neutral
    // band and floor the renderer maps with - and the page walks it here. It has
    // to: the fee is chosen by a slider now, so no set of pre-colored samples
    // can answer for the value the reader lands on. The tables themselves stay
    // defined in one place, lib/render/formatting.py, and arrive as data.
    const data = window.blockHeightPreview || {};
    // The stop tables and the two tone amounts are properties of the scale, so
    // they are read once. Everything downstream of the tip - the medians, the
    // fee each tier is at, the height under the gradient - is read through
    // live() instead, because a block landing replaces the payload wholesale and
    // this panel outlives it.
    const live = () => window.blockHeightPreview || data;
    const LIGHTEN = typeof data.lighten === 'number' ? data.lighten : 0.45;
    const DEEPEN  = typeof data.deepen  === 'number' ? data.deepen  : 0.85;
    const BAND    = typeof data.neutral_band === 'number' ? data.neutral_band : 0.05;
    const UNKNOWN = data.unknown || '#787882';

    // ── The tier being colored ───────────────────────────────────────────────
    // "Fee Used for the Block Height" now sits in this same panel, one field
    // above, and it is not a label: each tier carries its own 30-day median, and
    // fastestFee's is several times minimumFee's. The same 3 sat/vB is therefore
    // cool against one and warm against the other, and a preview that answered
    // for the saved tier while the reader picked another would show a color the
    // device will never draw. All five arrive together, so switching costs
    // nothing and needs no save.
    //
    // Read from the pending overrides first: that is where the form records an
    // edit that has not been saved, which is exactly the state being previewed.
    const DEFAULT_TIER = 'minimumFee';
    const currentTier = () =>
        (window._pendingConfigOverrides || {}).fee_parameter
        || cfg.fee_parameter || DEFAULT_TIER;

    let BASELINE = null;         // the tier's 30-day median, or null when thin
    let BASELINE_STATS = null;   // how much history that median rests on
    let CHEAP_FLOOR = 0;         // the network minimum, shared by every tier
    let TIER_FEE = null;         // what this tier costs at the current tip
    let TIER_PREV_FEE = null;    // and what it cost at the block before it

    function readTier() {
        const d = live();
        // The flat keys are the saved tier's entry, kept as the fallback for a
        // payload from before `tiers` travelled.
        const rec = (d.tiers || {})[currentTier()] || {
            baseline: d.baseline, stats: d.baseline_stats, current_fee: d.current_fee,
        };
        BASELINE = (typeof rec.baseline === 'number' && rec.baseline > 0)
            ? rec.baseline : null;
        BASELINE_STATS = rec.stats || null;
        TIER_FEE = Number.isFinite(rec.current_fee) ? rec.current_fee : null;
        TIER_PREV_FEE = Number.isFinite(rec.previous_fee) ? rec.previous_fee : null;
        CHEAP_FLOOR = typeof d.cheap_floor === 'number' ? d.cheap_floor : 0;
    }
    readTier();

    const parseHex = (hex) => {
        const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
        if (!m) return null;
        const n = parseInt(m[1], 16);
        return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
    };
    // Truncating, not rounding: Python's int() drops the fraction, and a channel
    // that disagrees by one is a channel that disagrees - the whole point of
    // shipping the tables rather than a lookalike is that the two agree exactly.
    const toHex = (rgb) => '#' + rgb
        .map(v => Math.trunc(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0'))
        .join('');
    const stopTable = (rows) => (rows || [])
        .map(([pos, hex]) => ({ pos, rgb: parseHex(hex) }))
        .filter(s => s.rgb);

    const COOL = stopTable((data.relative || {}).cool);
    const WARM = stopTable((data.relative || {}).warm);

    // Straight port of _interpolate: clamped at both ends, linear between the
    // two stops the position falls inside.
    const interpolate = (stops, pos) => {
        if (!stops.length) return parseHex(UNKNOWN);
        if (pos <= stops[0].pos) return stops[0].rgb;
        if (pos >= stops[stops.length - 1].pos) return stops[stops.length - 1].rgb;
        for (let i = 0; i < stops.length - 1; i++) {
            const a = stops[i], b = stops[i + 1];
            if (a.pos <= pos && pos <= b.pos) {
                const span = (b.pos - a.pos) || 1;
                const k = (pos - a.pos) / span;
                // Truncated here as well as in toHex, because the renderer
                // truncates at both steps too: an interpolated channel is an int
                // before it is ever lightened or deepened.
                return a.rgb.map((v, j) => Math.trunc(v + k * (b.rgb[j] - v)));
            }
        }
        return stops[stops.length - 1].rgb;
    };

    const MODE_HINTS = {
        constant: t.fee_mode_constant_desc ||
            'The block height always uses your color, as a gradient from top to bottom. Fees never change it.',
        relative: t.fee_mode_relative_desc ||
            'Compares the fee against what the same fee level has cost over the last 30 days. Cool means cheaper than usual, warm means dearer, your color means ordinary — so a cheap moment still looks cheap in a low-fee year.',
        manual: t.fee_mode_manual_desc ||
            'Fixed sat/vB thresholds you set yourself. No history involved, so the same fee always reads the same color.',
    };

    // Mode C's five thresholds. Only shown for that scale; they mean nothing to
    // the other two. The colors and defaults come from the server's own table,
    // so the swatch beside each field is the ink that field actually selects;
    // only the wording lives here. `hint` is shown on hover rather than under
    // the box: five sentences under five narrow number fields would crowd the
    // grid out of usefulness.
    const MANUAL_TEXT = {
        blue:   [t.fee_manual_blue   || 'Blue up to',
                 t.fee_manual_blue_desc   || 'Very cheap — a good moment for transactions and UTXO consolidation.'],
        green:  [t.fee_manual_green  || 'Green up to',
                 t.fee_manual_green_desc  || 'Cheap — comfortable for everyday transactions.'],
        yellow: [t.fee_manual_yellow || 'Yellow up to',
                 t.fee_manual_yellow_desc || 'Moderate — routine transactions are fine, consolidation can wait.'],
        orange: [t.fee_manual_orange || 'Orange up to',
                 t.fee_manual_orange_desc || 'Expensive — send only what cannot wait.'],
        red:    [t.fee_manual_red    || 'Red from',
                 t.fee_manual_red_desc    || 'Very expensive — wait unless it is urgent.'],
    };
    const MANUAL_ORDER = (data.manual_order && data.manual_order.length)
        ? data.manual_order
        : [['blue', '#005AFF', 0.5], ['green', '#00C846', 0.8],
           ['yellow', '#EBD700', 1.5], ['orange', '#FF8200', 3.0],
           ['red', '#D71919', 5.0]];
    const MANUAL_FIELDS = MANUAL_ORDER.map(([name, hex, dflt]) => {
        const [label, hint] = MANUAL_TEXT[name] || [name, ''];
        return { name, key: 'fee_manual_' + name, hex, dflt, label, hint };
    });

    // Declared here rather than beside the fields it collects: the theme rows
    // are built first and color themselves from these live values, so the
    // binding has to exist before the first paint.
    const manualInputs = {};

    const lighten = (hex) => {
        const rgb = parseHex(hex);
        if (!rgb) return hex;
        return toHex(rgb.map(v => v + LIGHTEN * (255 - v)));
    };
    const deepen = (hex) => {
        const rgb = parseHex(hex);
        if (!rgb) return hex;
        return toHex(rgb.map(v => v * DEEPEN));
    };

    // What the user has typed, right now — not what was last saved. The slider
    // is dragged while these are being edited, so reading the fields keeps the
    // color under the thumb answering to the numbers on screen.
    const manualThreshold = (f) => {
        const live = parseFloat(manualInputs[f.key] && manualInputs[f.key].value);
        if (Number.isFinite(live)) return Math.max(0, live);
        const saved = parseFloat(cfg[f.key]);
        return Math.max(0, Number.isFinite(saved) ? saved : f.dflt);
    };
    // Sorted, exactly as _manual_stops sorts: thresholds that cross over would
    // otherwise invert a section of the ramp, and a transposed digit should not
    // discard the other four numbers.
    const manualStops = () => MANUAL_FIELDS
        .map(f => ({ pos: manualThreshold(f), rgb: parseHex(f.hex) }))
        .filter(s => s.rgb)
        .sort((a, b) => a.pos - b.pos);

    // The port of _fee_color_for. null means "no signal" — the fee reads as
    // ordinary, or was never consulted — and the caller substitutes the picked
    // base color, which is precisely what the renderer does with its own null.
    const feeColorFor = (fee, mode) => {
        if (mode === 'constant') return null;
        if (fee === null || fee === undefined || !Number.isFinite(fee)) return UNKNOWN;
        if (mode === 'manual' || !BASELINE) return toHex(interpolate(manualStops(), fee));
        if (CHEAP_FLOOR && fee <= CHEAP_FLOOR && CHEAP_FLOOR < BASELINE) {
            return COOL.length ? toHex(COOL[0].rgb) : UNKNOWN;
        }
        const ratio = fee / BASELINE;
        if (ratio <= 0) return UNKNOWN;
        if (Math.abs(ratio - 1) <= BAND) return null;
        const pos = Math.log2(ratio);
        return toHex(interpolate(pos < 0 ? COOL : WARM, pos));
    };

    // ── Slider travel ────────────────────────────────────────────────────────
    // Two linear halves joined at the anchor, so the anchor sits under the
    // middle of the track whatever the range around it. Each scale needs a
    // different frame, and one linear sweep cannot serve them all: the constant
    // scale's 0-1000 sat/vB would put every fee ever paid in the first percent
    // of the travel, and 0-4x a median of 1.8 would give the whole cheap half of
    // the relative scale a quarter of it - the half that decides whether now is
    // a good moment to send. Where the two halves happen to be equal - the
    // manual scale - the mapping degenerates to linear on its own.
    const SLIDER_STEPS = 1000;
    const MANUAL_HEADROOM = typeof data.manual_headroom === 'number'
        ? data.manual_headroom : 1.1;
    // How far past the median the relative track runs. Four times it is log2 =
    // 2.0, the last stop of the warm ramp, so the track ends where the colors do.
    const SLIDER_HEADROOM = typeof data.slider_headroom === 'number'
        ? data.slider_headroom : 4.0;

    // The manual track is framed by the thresholds themselves, read live so it
    // re-frames while they are being typed rather than after a save: a tenth
    // past the top one, midpoint halfway, which leaves that track plain linear.
    // It can afford to be - it spans a handful of sat/vB rather than a thousand
    // - and above the top threshold the table has nothing further to say, so
    // travel spent up there could only show the same color again.
    const manualSliderRange = () => {
        const top = manualStops().reduce((a, s) => Math.max(a, s.pos), 0);
        if (!(top > 0)) return null;
        const max = top * MANUAL_HEADROOM;
        return { min: 0, anchor: max / 2, max };
    };

    const sliderRange = (mode) => {
        // The relative track is framed around the median of the tier currently
        // selected, computed here rather than taken from the payload: the server
        // can only frame the tier that was saved, and the dropdown beside this
        // slider changes which one that is without a save.
        if (mode === 'relative' && BASELINE) {
            return { min: 0, anchor: BASELINE, max: BASELINE * SLIDER_HEADROOM };
        }
        // Relative without a median colors from the manual table, so it takes
        // that table's frame too rather than a span around a median it does not
        // have.
        if (mode === 'manual' || mode === 'relative') {
            const framed = manualSliderRange();
            if (framed) return framed;
        }
        const r = (data.slider || {})[mode] || {};
        const min = Number.isFinite(r.min) ? r.min : 0;
        const max = Number.isFinite(r.max) && r.max > min ? r.max : 1000;
        const anchor = Number.isFinite(r.anchor) ? r.anchor : (min + max) / 2;
        return { min, max, anchor: Math.min(Math.max(anchor, min), max) };
    };
    const feeAtPosition = (pos, range) => {
        const half = SLIDER_STEPS / 2;
        return pos <= half
            ? range.min + (range.anchor - range.min) * (pos / half)
            : range.anchor + (range.max - range.anchor) * ((pos - half) / half);
    };
    const positionOfFee = (fee, range) => {
        const half = SLIDER_STEPS / 2;
        if (fee <= range.anchor) {
            const span = range.anchor - range.min;
            return span > 0 ? Math.round(((fee - range.min) / span) * half) : 0;
        }
        const span = range.max - range.anchor;
        return span > 0
            ? Math.round(half + ((fee - range.anchor) / span) * half)
            : SLIDER_STEPS;
    };

    // ── The track, painted in the scale it selects from ──────────────────────
    // The slider is the scale, so it may as well show it: every position is
    // already a fee, and every fee already has a color. Reading the ramp off
    // the track answers "where does green stop" without dragging to find out,
    // and makes the neutral band visible as the gap it is rather than something
    // the reader discovers by accident. It also exposes the shape of the travel
    // - the manual scale's five even bands look nothing like the relative
    // scale's long cool run into a short warm one.
    //
    // A range input's track can only be reached through vendor pseudo-elements,
    // which inline styles cannot set, so the ramp is handed over as a custom
    // property (those do inherit into pseudo-elements) and the rules are
    // injected once. Keeping them here rather than in config.css means the group
    // carries its own appearance, exactly as the rest of this panel does.
    const PANEL_STYLE_ID = 'fee-scale-slider-style';
    function ensurePanelStyles() {
        if (document.getElementById(PANEL_STYLE_ID)) return;
        const el = document.createElement('style');
        el.id = PANEL_STYLE_ID;
        el.textContent = `
.fee-scale-slider { -webkit-appearance:none; appearance:none; width:100%; height:20px;
    background:transparent; cursor:pointer; }
.fee-scale-slider:focus { outline:none; }
.fee-scale-slider::-webkit-slider-runnable-track { height:10px; border-radius:5px;
    background:var(--fee-scale-track,#888); border:1px solid rgba(127,127,127,.4); }
.fee-scale-slider::-moz-range-track { height:10px; border-radius:5px;
    background:var(--fee-scale-track,#888); border:1px solid rgba(127,127,127,.4); }
.fee-scale-slider::-webkit-slider-thumb { -webkit-appearance:none; width:18px; height:18px;
    margin-top:-5px; border-radius:50%; background:#fff; border:2px solid rgba(0,0,0,.6);
    box-shadow:0 1px 3px rgba(0,0,0,.45); }
.fee-scale-slider::-moz-range-thumb { width:18px; height:18px; border-radius:50%;
    background:#fff; border:2px solid rgba(0,0,0,.6); box-shadow:0 1px 3px rgba(0,0,0,.45); }
.fee-scale-slider:focus-visible::-webkit-slider-thumb { outline:2px solid var(--accent,#f7931a); outline-offset:2px; }
.fee-scale-slider:focus-visible::-moz-range-thumb { outline:2px solid var(--accent,#f7931a); outline-offset:2px; }

/* What each manual band means, on hover. Its own element rather than a title
   attribute: the browser holds a native tooltip back for about a second and
   pairs it with a help cursor, and neither is wanted on a label whose whole job
   is to be read. This one appears the moment the pointer arrives, leaves the
   cursor alone, and is real text in the DOM - so it reaches a screen reader,
   which a title attribute does not reliably do. :focus-within brings it up for
   the keyboard too, when the field beneath it is tabbed into. */
.fee-tip-host { position:relative; }
.fee-tip {
    position:absolute; left:50%; transform:translateX(-50%);
    bottom:calc(100% + 7px); z-index:40;
    width:max-content; max-width:min(260px,70vw); padding:7px 9px;
    border-radius:6px; font-size:0.95em; font-weight:400; line-height:1.35;
    text-align:left; white-space:normal;
    background:#22222c; color:#f2f2f6; border:1px solid rgba(255,255,255,.16);
    box-shadow:0 5px 16px rgba(0,0,0,.4);
    opacity:0; visibility:hidden; pointer-events:none; transition:none; }
.fee-tip::after {
    content:''; position:absolute; top:100%; left:50%; margin-left:-5px;
    border:5px solid transparent; border-top-color:#22222c; }
.fee-tip-host:hover > .fee-tip,
.fee-tip-host:focus-within > .fee-tip { opacity:1; visibility:visible; }`;
        document.head.appendChild(el);
    }

    // The picked color paints the stretch where the fee says nothing - the
    // neutral band, and the whole of the constant scale. Which of the two
    // pickers is the honest answer depends on the theme the *config page* is in,
    // since that is the background the track is being read against.
    const baseInputs = {};
    function neutralInk() {
        const key = document.body && document.body.classList.contains('dark-mode')
            ? 'dark' : 'light';
        const input = baseInputs[key] || baseInputs.light || baseInputs.dark;
        const picked = input && input.getValue ? input.getValue() : null;
        return parseHex(picked) ? picked : (key === 'dark' ? '#919191' : '#545454');
    }

    // Enough samples that the piecewise ramps read as continuous; both scales
    // are linear between stops, so nothing is lost between them.
    const TRACK_SAMPLES = 60;
    let sliderEl = null;
    function paintTrack() {
        if (!sliderEl) return;
        const mode = modeSelect.value;
        const range = sliderRange(mode);
        const neutral = neutralInk();
        const stops = [];
        for (let i = 0; i <= TRACK_SAMPLES; i++) {
            const pct = i / TRACK_SAMPLES;
            const fee = feeAtPosition(pct * SLIDER_STEPS, range);
            stops.push(`${feeColorFor(fee, mode) || neutral} ${(pct * 100).toFixed(2)}%`);
        }
        sliderEl.style.setProperty('--fee-scale-track',
            `linear-gradient(90deg,${stops.join(',')})`);
    }

    // The tip the device is actually on, from the same fee cache the colors are
    // read out of. The literal below is a last resort for a page opened before
    // the first block has been seen - a preview of a real height is the only one
    // whose digit count matches what the panel will draw.
    //
    // Grouped by the number_format setting, exactly as the renderer groups it.
    // Read at paint time rather than captured once, so switching the setting
    // repunctuates the sample instead of leaving it on the old separator.
    const sampleHeight = () => _fmtNum(
        live().block_height || window._previewData?.blockHeight
        || cfg.__block_height || 914427);

    const wrapper = document.createElement('div');
    wrapper.style.width = '100%';

    // ── Scale selector, above both theme rows ────────────────────────────────
    // No label of its own: the group is already headed "Block Height Color &
    // Scale", and a "Block Height Color Scale" caption under it said the same
    // thing twice before the reader reached the dropdown.
    const modeWrap = document.createElement('div');
    modeWrap.style.cssText = 'display:flex; flex-direction:column; gap:4px; margin-bottom:12px;';

    const modeSelect = document.createElement('select');
    modeSelect.className = 'form-select';
    modeSelect.dataset.configKey = 'fee_color_mode';
    [
        ['constant', t.fee_mode_constant || 'Constant — always your color'],
        // Marked in the option rather than the description: this is the choice
        // being made, so the steer belongs where the choosing happens.
        ['relative', (t.fee_mode_relative || 'Relative — cheap or dear (right now)')
                     + ' ' + (t.recommended || '(recommended)')],
        ['manual',   t.fee_mode_manual   || 'Manual — your own sat/vB thresholds'],
    ].forEach(([val, label]) => {
        const o = document.createElement('option');
        o.value = val;
        o.textContent = label;
        if ((cfg.fee_color_mode || 'relative') === val) o.selected = true;
        modeSelect.appendChild(o);
    });
    modeWrap.appendChild(modeSelect);

    const modeHint = document.createElement('span');
    modeHint.style.cssText = 'font-size:0.78em; color:var(--text-secondary); opacity:.8;';
    // Text is set per scale by syncMode() below, so the guidance always
    // describes the option actually selected rather than the feature at large.
    modeWrap.appendChild(modeHint);
    wrapper.appendChild(modeWrap);

    const rowUpdaters = [];

    // ── What the slider is showing ───────────────────────────────────────────
    // `curr` is where the thumb is; `prev` is where it was when the drag began.
    // The renderer's gradient is a move between two blocks - previous fee on
    // top, current underneath - so a preview that fed one fee to both ends would
    // draw the one thing the real digits never are: a flat fill. Holding the
    // drag's starting point at the top turns the slider into that move, and
    // letting go settles both ends together, which is what a quiet network
    // genuinely looks like.
    // Where the slider opens, and where it returns to whenever the tier changes
    // or a block lands: the two fees the device is drawing between right now.
    // Seating both from the payload rather than flattening them means the panel
    // opens on the gradient actually on the display, move and all.
    const seatFee = () => Number.isFinite(TIER_FEE) ? TIER_FEE : (BASELINE || 1);
    const seatPrevFee = () => Number.isFinite(TIER_PREV_FEE) ? TIER_PREV_FEE : seatFee();
    let currFee = seatFee();
    let prevFee = seatPrevFee();

    // The tier being colored, named as the panel names it under the digits.
    // A function, not a constant: the dropdown that decides it is in this same
    // panel, so the label has to follow it between renders.
    const TIER_LABELS = {
        fastestFee: t.fastest, halfHourFee: t.half_hour, hourFee: t.hour,
        economyFee: t.economy, minimumFee: t.minimum,
    };
    const feeTierLabel = () =>
        TIER_LABELS[currentTier()] || (t.minimum || 'Minimum');

    // The line under the digits: what this fee reads as on the selected scale.
    // Says why the digits look the way they do, which a color alone cannot.
    function readingFor(fee, mode) {
        if (mode === 'constant') return t.block_height_reading_constant || 'The fee is never consulted';
        if (mode === 'relative' && !BASELINE) {
            return t.block_height_median_pending
                || 'No 30-day median yet — falling back to the manual thresholds';
        }
        if (mode === 'manual') {
            // The band the fee has reached: the last threshold at or below it,
            // or the lowest one when it sits under them all. Sorted first, for
            // the same reason manualStops() sorts - a transposed pair of numbers
            // should not name a band the color did not come from.
            const ranked = MANUAL_FIELDS
                .map(f => ({ f, at: manualThreshold(f) }))
                .sort((a, b) => a.at - b.at);
            if (!ranked.length) return '';
            const hit = (ranked.filter(r => r.at <= fee).pop() || ranked[0]).f;
            return (MANUAL_TEXT[hit.name] || [hit.name])[0];
        }
        if (CHEAP_FLOOR && fee <= CHEAP_FLOOR && CHEAP_FLOOR < BASELINE) {
            return t.block_height_reading_floor
                || 'At the network minimum — nothing cheaper to wait for';
        }
        const ratio = fee / BASELINE;
        if (ratio <= 0) return '';
        if (Math.abs(ratio - 1) <= BAND) {
            return t.block_height_reading_ordinary || 'Ordinary — your base color';
        }
        return `${_fmtFee(Math.round(ratio * 100) / 100)}${t.block_height_reading_times || '× the median'}`;
    }

    function buildRow(themeLabel, themeKey, colorKey, colorVal, rowBg, previewBg, slotClass) {
        const row = document.createElement('div');
        row.className = 'date-color-row';
        row.style.background = rowBg;

        const label = document.createElement('div');
        label.style.cssText = 'width:100%; font-weight:600; font-size:0.95em; margin-bottom:4px; color:var(--text-primary)';
        label.textContent = themeLabel;
        row.appendChild(label);

        const pickGroup = document.createElement('div');
        pickGroup.style.cssText = 'display:flex; flex-direction:column; gap:4px;';
        const pickLabel = document.createElement('span');
        pickLabel.style.cssText = 'font-size:0.8em; color:var(--text-secondary)';
        pickLabel.textContent = t.block_height_base_color || 'Base Color';
        pickGroup.appendChild(pickLabel);
        const colorInput = createColorInput(colorVal);
        colorInput.dataset.configKey = colorKey;
        pickGroup.appendChild(colorInput);
        row.appendChild(pickGroup);
        // Registered so the slider can paint its neutral stretch in whichever of
        // the two the config page's own theme calls for.
        baseInputs[themeKey] = colorInput;

        const preview = document.createElement('div');
        preview.className = 'date-color-preview';
        preview.style.cssText = `flex:1; min-width:220px; display:flex; flex-direction:column; align-items:center; gap:2px; padding:12px 14px; border-radius:6px; background:${previewBg};`;
        if (slotClass) preview.classList.add(slotClass);

        // One sample rather than a row of scenarios: the slider is the thing
        // that varies now, so a second sample beside it would only show the same
        // fee twice. Laid out as the panel lays it out - digits, then the fee
        // label beneath them - because that pairing is the point. The label
        // color tracks the bottom of the gradient exactly as it does on the
        // device, where the two are read together.
        const cap = `font-size:0.7em; line-height:1.3; text-align:center; color:${themeKey === 'dark' ? '#c8c8d0' : '#4a4a55'};`;
        const digits = document.createElement('span');
        // background-clip:text over a vertical gradient is the browser's
        // equivalent of draw_vertical_gradient_text.
        digits.style.cssText = "font-family:'RobotoCondensed','Roboto Condensed','Arial Narrow',sans-serif; font-weight:800; font-size:2.6em; line-height:1.02; -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; color:transparent;";
        digits.textContent = sampleHeight();
        // Tagged so a new block can repaint the sample without rebuilding the
        // panel. Only the digits change with height - the gradient is a function
        // of the fee - so replacing the text is the whole repaint. Both theme
        // rows are built in this scope and share sampleHeight, so registering
        // from here resolves the same closure either time.
        digits.classList.add('bh-preview-digits');
        window._refreshBlockHeightPreview = () => {
            const next = sampleHeight();
            document.querySelectorAll('.bh-preview-digits')
                .forEach(el => { el.textContent = next; });
        };
        const feeLine = document.createElement('span');
        feeLine.style.cssText = 'font-size:0.78em; font-weight:600; line-height:1.3; text-align:center;';
        const reading = document.createElement('span');
        reading.style.cssText = cap + 'opacity:.7; margin-top:2px;';
        preview.appendChild(digits);
        preview.appendChild(feeLine);
        preview.appendChild(reading);
        row.appendChild(preview);

        function update() {
            const mode = modeSelect.value;
            const base = (colorInput.getValue ? colorInput.getValue() : colorVal) || colorVal;
            // The base color is the whole of the constant scale and the neutral
            // reading of the relative one, but says nothing in manual mode -
            // every band there has its own color - so the picker goes away.
            pickGroup.style.display = mode === 'manual' ? 'none' : 'flex';
            // null from feeColorFor means the fee reads as normal, or was never
            // consulted, so the picked color takes that end. Tone follows the
            // theme exactly as fee_to_colors tones it: on dark the top is raw and
            // the bottom lightened; on light the top is lightened and the bottom
            // deepened - except a neutral bottom, which is the anchor end and
            // renders the picked color exactly rather than an approximation.
            const isDark = themeKey === 'dark';
            const topRaw = feeColorFor(prevFee, mode);
            const botRaw = feeColorFor(currFee, mode);
            const top = topRaw === null
                ? (isDark ? base : lighten(base))
                : (isDark ? topRaw : lighten(topRaw));
            const bottom = botRaw === null
                ? (isDark ? lighten(base) : base)
                : (isDark ? lighten(botRaw) : deepen(botRaw));

            digits.textContent = sampleHeight();
            digits.style.background = `linear-gradient(180deg,${top},${bottom})`;
            digits.style.webkitBackgroundClip = 'text';
            digits.style.backgroundClip = 'text';
            feeLine.textContent = `${feeTierLabel()}: ${_fmtFee(currFee)} sat/vB`;
            feeLine.style.color = bottom;
            reading.textContent = readingFor(currFee, mode);
        }
        colorInput.addEventListener('input', () => { update(); paintTrack(); });
        rowUpdaters.push(update);
        update();

        return row;
    }

    wrapper.appendChild(buildRow(
        t.holiday_color_light_theme || 'Light Theme', 'light',
        'color_block_height_light', cfg.color_block_height_light || '#545454',
        'rgba(255,255,255,.04)', '#ffffff', 'preview-card-light'
    ));
    wrapper.appendChild(buildRow(
        t.holiday_color_dark_theme || 'Dark Theme', 'dark',
        'color_block_height_dark', cfg.color_block_height_dark || '#919191',
        'rgba(0,0,0,.04)', '#1a1a2e', 'preview-card-dark'
    ));

    // The group's own appearance - the painted slider track and the manual-band
    // tooltips - neither of which can be expressed as an inline style. Injected
    // here, before the first element that needs it.
    ensurePanelStyles();

    // ── The fee slider, driving both previews ────────────────────────────────
    // One control for both themes: it is the same fee either way, and a slider
    // per row would invite the reader to compare two different numbers.
    const sliderWrap = document.createElement('div');
    sliderWrap.style.cssText = 'display:flex; flex-direction:column; gap:5px; margin-top:14px;';

    const sliderHead = document.createElement('div');
    sliderHead.style.cssText = 'display:flex; justify-content:space-between; align-items:baseline; gap:10px; font-size:0.8em; color:var(--text-secondary);';
    const sliderLabel = document.createElement('span');
    sliderLabel.style.fontWeight = '600';
    sliderLabel.textContent = t.block_height_fee_slider || 'Try a fee';
    const sliderValue = document.createElement('span');
    sliderValue.style.cssText = 'font-variant-numeric:tabular-nums; color:var(--text-primary); font-weight:600;';
    sliderHead.appendChild(sliderLabel);
    sliderHead.appendChild(sliderValue);
    sliderWrap.appendChild(sliderHead);

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.min = '0';
    slider.max = String(SLIDER_STEPS);
    slider.step = '1';
    slider.className = 'fee-scale-slider';
    slider.setAttribute('aria-label', t.block_height_fee_slider || 'Try a fee');
    // Not a setting: it asks the scale a question, it does not answer one. The
    // flag keeps its events out of unsaved-change tracking, which otherwise
    // treats any input inside the form as a reason to re-check and - on a phone,
    // where a drag emits a long run of them - to light the Save button up over a
    // fee that was never going to be saved.
    slider.dataset.previewOnly = '1';
    sliderWrap.appendChild(slider);
    sliderEl = slider;

    // The two ends and the anchor, printed under the track so the travel is
    // readable without dragging it. The middle mark is the median on the
    // relative scale and the top threshold's neighbourhood on the manual one.
    const sliderScale = document.createElement('div');
    sliderScale.style.cssText = 'display:flex; justify-content:space-between; font-size:0.7em; color:var(--text-secondary); opacity:.65; font-variant-numeric:tabular-nums;';
    const scaleMin = document.createElement('span');
    const scaleMid = document.createElement('span');
    const scaleMax = document.createElement('span');
    sliderScale.appendChild(scaleMin);
    sliderScale.appendChild(scaleMid);
    sliderScale.appendChild(scaleMax);
    sliderWrap.appendChild(sliderScale);

    const sliderHint = document.createElement('span');
    sliderHint.style.cssText = 'font-size:0.76em; color:var(--text-secondary); opacity:.8;';
    sliderHint.textContent = t.block_height_slider_hint ||
        'Drag to try a fee. The top of the digits holds the fee you started from, so the gradient shows the move — the same way the panel shows one block against the last.';
    sliderWrap.appendChild(sliderHint);

    // Where the median actually is, and how much history it rests on. The one
    // number the color is judged against was previously readable only by
    // reverse-engineering an example fee.
    const medianLine = document.createElement('span');
    medianLine.style.cssText = 'font-size:0.76em; color:var(--text-secondary); opacity:.8;';
    sliderWrap.appendChild(medianLine);

    wrapper.appendChild(sliderWrap);

    function syncSliderScale() {
        const range = sliderRange(modeSelect.value);
        scaleMin.textContent = `${_fmtFee(range.min)} sat/vB`;
        scaleMid.textContent = _fmtFee(range.anchor);
        scaleMax.textContent = `${_fmtFee(range.max)} sat/vB`;
        // The fee is kept and its position recomputed, not the other way round:
        // switching scale should not silently move the fee being previewed.
        slider.value = String(Math.min(SLIDER_STEPS, Math.max(0,
            positionOfFee(currFee, range))));
        sliderValue.textContent = `${_fmtFee(currFee)} sat/vB`;
        // The track is the scale, so it is repainted whenever the scale moves:
        // a new mode, a new range, or an edited threshold.
        paintTrack();
    }

    function syncMedianLine() {
        const stats = BASELINE_STATS || {};
        if (!BASELINE) {
            medianLine.textContent = t.block_height_median_pending
                || 'No 30-day median yet — falling back to the manual thresholds';
            medianLine.style.display = modeSelect.value === 'relative' ? '' : 'none';
            return;
        }
        const days = Number(stats.days) || 0;
        const window = Number(stats.window_days) || 30;
        medianLine.textContent =
            `${t.block_height_median || '30-day median'}: ${_fmtFee(BASELINE)} sat/vB`
            + ` · ${days}/${window} ${t.block_height_median_days || 'days collected'}`;
        medianLine.style.display = modeSelect.value === 'relative' ? '' : 'none';
    }

    slider.addEventListener('input', () => {
        const range = sliderRange(modeSelect.value);
        currFee = feeAtPosition(Number(slider.value), range);
        sliderValue.textContent = `${_fmtFee(currFee)} sat/vB`;
        rowUpdaters.forEach(fn => fn());
    });
    // Letting go settles the move: the fee you landed on becomes the fee the
    // next drag departs from, so both ends agree and the digits render flat -
    // which is exactly what a network that has stopped moving looks like.
    ['change', 'pointerup', 'keyup'].forEach(ev =>
        slider.addEventListener(ev, () => {
            prevFee = currFee;
            rowUpdaters.forEach(fn => fn());
        }));

    // ── Manual thresholds, shown only for that scale ─────────────────────────
    const manualWrap = document.createElement('div');
    manualWrap.style.cssText = 'display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px; margin-top:12px;';
    MANUAL_FIELDS.forEach(({ key, label, hex, dflt, hint }) => {
        // The whole box is the hover target - swatch, words and field alike - so
        // the explanation is there wherever the pointer lands rather than only
        // over the four words that happen to carry it.
        const box = document.createElement('div');
        box.className = 'fee-tip-host';
        box.style.cssText = 'display:flex; flex-direction:column; gap:3px;';
        const tip = document.createElement('span');
        tip.className = 'fee-tip';
        tip.textContent = hint;
        box.appendChild(tip);
        const lab = document.createElement('span');
        lab.style.cssText = 'font-size:0.78em; font-weight:600; color:var(--text-secondary); display:flex; align-items:center; gap:6px;';
        const dot = document.createElement('span');
        dot.style.cssText = `width:10px; height:10px; border-radius:2px; background:${hex}; flex:none;`;
        lab.appendChild(dot);
        lab.appendChild(document.createTextNode(label));
        const input = document.createElement('input');
        input.type = 'number';
        input.className = 'form-input';
        input.step = '0.1';
        input.min = '0';
        input.dataset.configKey = key;
        input.value = (cfg[key] !== undefined && cfg[key] !== null) ? cfg[key] : dflt;
        manualInputs[key] = input;
        box.appendChild(lab);
        box.appendChild(input);
        manualWrap.appendChild(box);
    });
    const manualHint = document.createElement('span');
    manualHint.style.cssText = 'grid-column:1/-1; font-size:0.78em; color:var(--text-secondary); opacity:.8;';
    manualHint.textContent = t.fee_manual_hint ||
        'Each value is the fee, in sat/vB, at which that color takes over. The preview above follows whatever you type here.';
    manualWrap.appendChild(manualHint);
    wrapper.appendChild(manualWrap);

    // Typing a threshold recolors the sample immediately - manualStops() reads
    // the fields, not the saved config - and re-frames the slider, whose travel
    // is scaled to the bands being defined.
    Object.values(manualInputs).forEach(input => {
        input.addEventListener('input', () => {
            syncSliderScale();
            rowUpdaters.forEach(fn => fn());
        });
    });

    function syncMode() {
        const mode = modeSelect.value;
        manualWrap.style.display = mode === 'manual' ? 'grid' : 'none';
        modeHint.textContent = MODE_HINTS[mode] || '';
        // A scale change moves the ends of the track without moving the fee, so
        // both previews keep showing the same number under the new rules - which
        // is the comparison the dropdown is there to make.
        syncSliderScale();
        syncMedianLine();
        rowUpdaters.forEach(fn => fn());
    }
    modeSelect.addEventListener('change', syncMode);
    syncMode();

    // Refreshes without rebuilding the panel, which would discard color edits
    // the user has made but not yet saved.
    //
    // Plain call: repunctuate. That is a number_format change - the sample
    // height, the slider readout and the fee figures all regroup, nothing else
    // moves.
    //
    // `{reseat: true}`: the scale itself has changed under the panel - a
    // different fee tier was picked, or a block landed and brought new fees and
    // possibly a new median with it. The tier is re-read and both ends of the
    // gradient are put back on the fees that tier is now between, because the
    // pair shown before belonged to a scale that no longer exists.
    window._refreshBlockHeightPreview = (opts) => {
        if (opts && opts.reseat) {
            readTier();
            currFee = seatFee();
            prevFee = seatPrevFee();
        }
        syncSliderScale();
        syncMedianLine();
        rowUpdaters.forEach(fn => fn());
    };

    return wrapper;
}


function createColorSelect(value) {
    const container = document.createElement('div');
    container.className = 'color-select-container';
    
    // Create the select button
    const selectButton = document.createElement('div');
    selectButton.className = 'form-select color-select-trigger';
    selectButton.style.cursor = 'pointer';
    selectButton.style.userSelect = 'none';
    selectButton.style.display = 'flex';
    selectButton.style.alignItems = 'center';
    selectButton.style.gap = '8px';
    
    // Create dropdown list
    const dropdownList = document.createElement('div');
    dropdownList.className = 'color-select-options';
    dropdownList.style.display = 'none';
    dropdownList.style.position = 'absolute';
    dropdownList.style.top = '100%';
    dropdownList.style.left = '0';
    dropdownList.style.right = '0';
    dropdownList.style.backgroundColor = '#fff';
    dropdownList.style.border = '1px solid #ddd';
    dropdownList.style.borderRadius = '4px';
    dropdownList.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
    dropdownList.style.zIndex = '1000';
    dropdownList.style.maxHeight = '300px';
    dropdownList.style.overflowY = 'auto';
    
    container.style.position = 'relative';
    
    // Find the currently selected option
    let currentOption = colorOptions.find(opt => opt.value === value) || colorOptions[0];
    
    // Set initial button content
    function updateButtonDisplay(option) {
        if (option) {
            const colorDot = document.createElement('div');
            colorDot.style.width = '16px';
            colorDot.style.height = '16px';
            colorDot.style.borderRadius = '50%';
            colorDot.style.backgroundColor = option.preview_color;
            colorDot.style.border = '1px solid #ccc';
            colorDot.style.flexShrink = '0';
            
            const label = document.createElement('span');
            label.textContent = option.label;
            
            selectButton.innerHTML = '';
            selectButton.appendChild(colorDot);
            selectButton.appendChild(label);
        }
    }
    
    updateButtonDisplay(currentOption);
    
    // Group colors by category
    const colorsByCategory = {};
    colorOptions.forEach(option => {
        if (!colorsByCategory[option.category]) {
            colorsByCategory[option.category] = [];
        }
        colorsByCategory[option.category].push(option);
    });
    
    // Create options grouped by category
    Object.keys(colorsByCategory).forEach(category => {
        // Add category header
        const categoryHeader = document.createElement('div');
        categoryHeader.className = 'color-category-header';
        categoryHeader.textContent = category;
        categoryHeader.style.padding = '8px 12px';
        categoryHeader.style.fontWeight = 'bold';
        categoryHeader.style.fontSize = '0.9em';
        categoryHeader.style.color = '#666';
        categoryHeader.style.backgroundColor = '#f5f5f5';
        categoryHeader.style.borderBottom = '1px solid #eee';
        dropdownList.appendChild(categoryHeader);
        
        // Add colors in this category
        colorsByCategory[category].forEach(option => {
            const optionDiv = document.createElement('div');
            optionDiv.className = 'color-select-option';
            optionDiv.style.cursor = 'pointer';
            optionDiv.style.padding = '8px 12px';
            optionDiv.style.display = 'flex';
            optionDiv.style.alignItems = 'center';
            optionDiv.style.gap = '8px';
            optionDiv.style.borderBottom = '1px solid var(--border-color)';
            optionDiv.setAttribute('data-value', option.value);
            
            // Create color preview dot
            const colorDot = document.createElement('div');
            colorDot.style.width = '16px';
            colorDot.style.height = '16px';
            colorDot.style.borderRadius = '50%';
            colorDot.style.backgroundColor = option.preview_color;
            colorDot.style.border = '1px solid #ccc';
            colorDot.style.flexShrink = '0';
            
            const label = document.createElement('span');
            label.textContent = option.label;
            
            optionDiv.appendChild(colorDot);
            optionDiv.appendChild(label);
            
            // Mark current selection
            if (option.value === value) {
                optionDiv.classList.add('selected');
                optionDiv.style.backgroundColor = '#e3f2fd';
            }
            
            // Add hover effect
            optionDiv.addEventListener('mouseenter', function() {
                if (!this.classList.contains('selected')) {
                    this.style.backgroundColor = '#f5f5f5';
                }
            });
            
            optionDiv.addEventListener('mouseleave', function() {
                if (!this.classList.contains('selected')) {
                    this.style.backgroundColor = '';
                }
            });
            
            // Add click handler
            optionDiv.addEventListener('click', function(e) {
                e.stopPropagation();
                
                // Remove selected class from all options
                dropdownList.querySelectorAll('.color-select-option').forEach(opt => {
                    opt.classList.remove('selected');
                    opt.style.backgroundColor = '';
                });
                
                // Add selected class to clicked option
                optionDiv.classList.add('selected');
                optionDiv.style.backgroundColor = '#e3f2fd';
                
                // Update button display
                updateButtonDisplay(option);
                
                // Update hidden input
                hiddenInput.value = option.value;
                currentOption = option;
                
                // Hide dropdown
                dropdownList.style.display = 'none';
                container.classList.remove('open');
                
                // Trigger change event
                const event = new Event('change', { bubbles: true });
                hiddenInput.dispatchEvent(event);
            });
            
            dropdownList.appendChild(optionDiv);
        });
    });
    
    // Create hidden input for form compatibility
    const hiddenInput = document.createElement('input');
    hiddenInput.type = 'hidden';
    hiddenInput.value = value || (colorOptions[0] ? colorOptions[0].value : '');
    
    // Toggle dropdown on button click
    selectButton.addEventListener('click', function(e) {
        e.stopPropagation();
        
        const isOpen = dropdownList.style.display === 'block';
        
        // Close all other dropdowns
        document.querySelectorAll('.color-select-options').forEach(dropdown => {
            if (dropdown !== dropdownList) {
                dropdown.style.display = 'none';
                dropdown.parentNode.classList.remove('open');
            }
        });
        
        if (isOpen) {
            dropdownList.style.display = 'none';
            container.classList.remove('open');
        } else {
            dropdownList.style.display = 'block';
            container.classList.add('open');
        }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function() {
        dropdownList.style.display = 'none';
        container.classList.remove('open');
    });
    
    container.appendChild(selectButton);
    container.appendChild(dropdownList);
    container.appendChild(hiddenInput);
    
    // Add getValue method for form collection
    container.getValue = () => hiddenInput.value;
    
    return container;
}


function _checkRebootWindowConflict(input) {
    const rw = window._rebootWindow;
    const existing = input.parentNode?.querySelector('.reboot-window-warning');
    if (!rw || !input.value) {
        if (existing) existing.remove();
        input.classList.remove('input-invalid');
        _invalidInputs.delete(input);
        _updateFormValidity();
        return;
    }
    const [h, m] = input.value.split(':').map(Number);
    const candidate  = h * 60 + m;
    const reboot     = rw.hour * 60 + rw.minute;
    const blockStart = (reboot - 120 + 1440) % 1440;
    const blockEnd   = (reboot + 15) % 1440;
    const inWindow   = blockStart <= blockEnd
        ? candidate >= blockStart && candidate < blockEnd
        : candidate >= blockStart || candidate < blockEnd;
    if (inWindow) {
        const fmt = n => `${String(Math.floor(n/60)).padStart(2,'0')}:${String(n%60).padStart(2,'0')}`;
        const msg = (window.translations?.reboot_window_conflict
            || 'Conflicts with OS auto-reboot window ({start}–{end})')
            .replace('{start}', fmt(blockStart))
            .replace('{end}',   fmt(blockEnd));
        if (!existing) {
            const w = document.createElement('div');
            w.className = 'reboot-window-warning';
            w.style.cssText = 'color:#dc3545;font-size:12px;margin-top:4px;';
            w.textContent = msg;
            input.parentNode.appendChild(w);
        } else {
            existing.textContent = msg;
        }
        input.classList.add('input-invalid');
        _invalidInputs.add(input);
    } else {
        if (existing) existing.remove();
        input.classList.remove('input-invalid');
        _invalidInputs.delete(input);
    }
    _updateFormValidity();
}


function createBooleanSwitch(value) {
    const container = document.createElement('div');
    container.className = 'boolean-switch';
    
    // Ensure value is properly converted to boolean
    const boolValue = typeof value === 'string' ? (value.toLowerCase() === 'true' || value === '1') : Boolean(value);
    
    const switchEl = document.createElement('div');
    switchEl.className = `switch ${boolValue ? 'active' : ''}`;
    
    const thumb = document.createElement('div');
    thumb.className = 'switch-thumb';
    switchEl.appendChild(thumb);
    
    const label = document.createElement('span');
    label.textContent = boolValue ? (window.translations?.enabled || 'Enabled') : (window.translations?.disabled || 'Disabled');
    
    switchEl.addEventListener('click', () => {
        const isActive = switchEl.classList.toggle('active');
        label.textContent = isActive ? (window.translations?.enabled || 'Enabled') : (window.translations?.disabled || 'Disabled');
    });
    
    container.appendChild(switchEl);
    container.appendChild(label);
    
    // Add getter for value
    container.getValue = () => {
        return switchEl.classList.contains('active');
    };
    
    // Add setter for value (useful for programmatic updates)
    container.setValue = (newValue) => {
        const boolValue = Boolean(newValue);
        if (boolValue) {
            switchEl.classList.add('active');
        } else {
            switchEl.classList.remove('active');
        }
        label.textContent = boolValue ? (window.translations?.enabled || 'Enabled') : (window.translations?.disabled || 'Disabled');
    };
    
    return container;
}

function createToggleGroup(options, value) {
    const container = document.createElement('div');
    container.className = 'toggle-group';

    options.forEach(option => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `toggle-option ${value === option.value ? 'active' : ''}`;

        // Tooltip from _tk key (looked up in current translations)
        const tooltipText = option._tk ? (window.translations?.[option._tk] || '') : '';
        if (tooltipText) button.title = tooltipText;

        // Create proper icon HTML if icon is provided
        if (option.icon) {
            const iconImg = document.createElement('img');
            iconImg.src = option.icon;
            iconImg.alt = option.label;

            button.appendChild(iconImg);
            button.appendChild(document.createTextNode(option.label));
        } else {
            button.textContent = option.label;
        }
        
        button.addEventListener('click', () => {
            container.querySelectorAll('.toggle-option').forEach(btn => 
                btn.classList.remove('active'));
            button.classList.add('active');
        });
        
        container.appendChild(button);
    });
    
    // Add getter for value
    container.getValue = () => {
        const active = container.querySelector('.toggle-option.active');
        const index = Array.from(container.children).indexOf(active);
        return options[index]?.value;
    };

    // Programmatic counterpart, so code can drive a toggle the way a click
    // would. Returns false for an unknown value rather than clearing the
    // selection, which would leave getValue() returning undefined.
    container.setValue = (v) => {
        const index = options.findIndex(o => o.value === v);
        if (index < 0) return false;
        Array.from(container.children).forEach((btn, i) =>
            btn.classList.toggle('active', i === index));
        return true;
    };

    return container;
}

function createTagsInput(values, placeholder) {
    const container = document.createElement('div');
    container.className = 'tags-input';
    
    // Add existing tags
    values.forEach(value => addTag(container, value));
    
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'tag-input';
    input.placeholder = placeholder || 'Add item...';
    
    // Handle keyboard events
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            const value = input.value.trim();
            if (value) {
                addTag(container, value);
                input.value = '';
                // Trigger change event to notify form system
                container.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
        // Handle backspace to remove last tag when input is empty
        else if (e.key === 'Backspace' && input.value === '') {
            const tags = container.querySelectorAll('.tag');
            if (tags.length > 0) {
                tags[tags.length - 1].remove();
                container.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    });
    
    // Handle mobile keyboard events - different approach for mobile "Go", "Done", "Next" buttons
    input.addEventListener('keyup', (e) => {
        // Mobile keyboards might use different key codes
        if (e.key === 'Enter' || e.keyCode === 13) {
            e.preventDefault();
            const value = input.value.trim();
            if (value) {
                addTag(container, value);
                input.value = '';
                container.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    });
    
    // Auto-add tag when user types comma or semicolon (good for mobile)
    input.addEventListener('input', (e) => {
        const {value} = input;
        if (value.includes(',') || value.includes(';')) {
            const parts = value.split(/[,;]+/);
            const lastPart = parts.pop(); // Keep the last part in input
            
            // Add all complete parts as tags
            parts.forEach(part => {
                const trimmed = part.trim();
                if (trimmed) {
                    addTag(container, trimmed);
                }
            });
            
            input.value = lastPart.trim();
            if (parts.length > 0) {
                container.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
    });
    
    // Handle blur event (when user clicks outside)
    input.addEventListener('blur', (e) => {
        const value = input.value.trim();
        if (value) {
            addTag(container, value);
            input.value = '';
            container.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
    
    // Handle paste events
    input.addEventListener('paste', (e) => {
        e.preventDefault();
        const pastedText = (e.clipboardData || window.clipboardData).getData('text');
        const items = pastedText.split(/[,\n\r]+/).map(item => item.trim()).filter(item => item);
        
        items.forEach(item => {
            if (item) {
                addTag(container, item);
            }
        });
        
        if (items.length > 0) {
            container.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
    
    container.appendChild(input);
    
    // Create add button for mobile devices
    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'tag-add-button';
    addButton.title = (window.translations && window.translations.add_tag) || 'Add tag';
    addButton.disabled = true;
    const addIcon = document.createElement('span');
    addIcon.className = 'tag-add-icon';
    addIcon.setAttribute('aria-hidden', 'true');
    addButton.appendChild(addIcon);

    // Enable/disable add button based on input content
    input.addEventListener('input', () => {
        addButton.disabled = !input.value.trim();
    });

    // Add button click handler
    addButton.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const value = input.value.trim();
        if (value) {
            addTag(container, value);
            input.value = '';
            addButton.disabled = true;
            container.dispatchEvent(new Event('change', { bubbles: true }));
            input.focus(); // Keep focus on input for continuous adding
        }
    });
    
    container.appendChild(addButton);
    
    // Add getter for value (used by form system)
    container.getValue = () => {
        return Array.from(container.querySelectorAll('.tag'))
            .map(tag => tag.textContent.replace('×', '').trim())
            .filter(tag => tag); // Remove empty strings
    };
    
    // Add value property for compatibility
    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (newValues) => {
            // Clear existing tags
            container.querySelectorAll('.tag').forEach(tag => tag.remove());
            // Add new tags
            if (Array.isArray(newValues)) {
                newValues.forEach(value => addTag(container, value));
            }
        }
    });
    
    // Add addEventListener method for compatibility
    container.addEventListener = function(event, handler) {
        container.addEventListener(event, handler);
    };
    
    return container;
}

function addTag(container, value) {
    // Case-insensitive duplicate check against existing tags in the input
    const valueLower = value.toLowerCase();
    const existingTags = Array.from(container.querySelectorAll('.tag'))
        .map(tag => tag.textContent.replace('×', '').trim());

    if (existingTags.some(t => t.toLowerCase() === valueLower)) {
        return; // Don't add duplicate tags
    }

    // Also check against API tags (read-only pills rendered outside this input)
    if (container.dataset.apiTags) {
        try {
            const apiTags = JSON.parse(container.dataset.apiTags);
            if (apiTags.some(t => t.toLowerCase() === valueLower)) {
                return; // Already exists as an API tag
            }
        } catch (e) { /* ignore */ }
    }
    
    const tag = document.createElement('div');
    tag.className = 'tag';
    // `value` is user-entered and was previously parsed as HTML here.
    // append() with a string creates a text node, so it stays inert.
    tag.append(value + ' ');
    const tagRemoveBtn = document.createElement('button');
    tagRemoveBtn.type = 'button';
    tagRemoveBtn.className = 'tag-remove';
    tagRemoveBtn.textContent = '×';
    tag.appendChild(tagRemoveBtn);
    
    // Handle tag removal
    tag.querySelector('.tag-remove').addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        tag.remove();
        // Trigger change event when tag is removed
        container.dispatchEvent(new Event('change', { bubbles: true }));
    });
    
    const input = container.querySelector('.tag-input');
    container.insertBefore(tag, input);
}

function createWalletTableInput(values, field) {
    const container = document.createElement('div');
    container.className = 'wallet-table-container';
    
    // Initialize dataset for form compatibility
    if (!container.dataset) {
        container.dataset = {};
    }
    
    // Create table
    const table = document.createElement('table');
    table.className = 'wallet-table';
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.style.marginBottom = '15px';
    
    // Create table header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    
    const addressHeader = document.createElement('th');
    addressHeader.textContent = window.translations?.wallet_table_address || 'Address/XPUB/ZPUB';
    addressHeader.style.padding = '10px';
    addressHeader.style.border = '1px solid var(--border-subtle)';
    addressHeader.style.backgroundColor = '#2a2d3e';
    addressHeader.style.color = '#ffffff';
    addressHeader.style.width = '35%';
    
    const commentHeader = document.createElement('th');
    commentHeader.innerHTML = (window.translations?.wallet_table_comment || 'Comment/Label').replace('/', '/<br>');
    commentHeader.style.padding = '10px';
    commentHeader.style.border = '1px solid var(--border-subtle)';
    commentHeader.style.backgroundColor = '#2a2d3e';
    commentHeader.style.color = '#ffffff';
    commentHeader.style.width = '35%';
    
    const balanceHeader = document.createElement('th');
    balanceHeader.style.padding = '10px';
    balanceHeader.style.border = '1px solid var(--border-subtle)';
    balanceHeader.style.backgroundColor = '#2a2d3e';
    balanceHeader.style.color = '#ffffff';
    balanceHeader.style.width = '20%';
    balanceHeader.style.textAlign = 'center';

    const balanceHeaderInner = document.createElement('div');
    balanceHeaderInner.style.cssText = 'display:flex; align-items:center; justify-content:center; gap:6px;';

    const balanceHeaderLabel = document.createElement('span');
    balanceHeaderLabel.textContent = window.translations?.wallet_table_balance || 'Balance (BTC)';

    const balanceVisibilityBtn = document.createElement('button');
    balanceVisibilityBtn.type = 'button';
    balanceVisibilityBtn.className = 'wallet-balance-visibility-toggle';
    balanceVisibilityBtn.style.cssText = 'background:none; border:none; padding:2px; margin:0; cursor:pointer; display:flex; align-items:center; border-radius:4px;';
    const balanceVisibilityIcon = _createMaskIcon(
        window._walletBalancesHidden ? '/static/icons/visibility_off.svg' : '/static/icons/visibility.svg'
    );
    balanceVisibilityIcon.title = window._walletBalancesHidden
        ? (window.translations?.show_balances || 'Show balances')
        : (window.translations?.hide_balances || 'Hide balances');
    balanceVisibilityBtn.appendChild(balanceVisibilityIcon);
    balanceVisibilityBtn.addEventListener('click', () => _toggleWalletBalanceVisibility(balanceVisibilityIcon));

    balanceHeaderInner.appendChild(balanceHeaderLabel);
    balanceHeaderInner.appendChild(balanceVisibilityBtn);
    balanceHeader.appendChild(balanceHeaderInner);

    const actionsHeader = document.createElement('th');
    actionsHeader.textContent = '';
    actionsHeader.style.padding = '10px';
    actionsHeader.style.border = '1px solid var(--border-subtle)';
    actionsHeader.style.backgroundColor = '#2a2d3e';
    actionsHeader.style.color = '#ffffff';
    actionsHeader.style.width = '10%';
    
    headerRow.appendChild(addressHeader);
    headerRow.appendChild(commentHeader);
    headerRow.appendChild(balanceHeader);
    headerRow.appendChild(actionsHeader);
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    // Create table body
    const tbody = document.createElement('tbody');
    table.appendChild(tbody);
    
    // Add existing wallet entries
    values.forEach(entry => addWalletTableRow(tbody, entry));
    
    // Function to update table visibility
    function updateTableVisibility() {
        const hasRows = tbody.querySelectorAll('tr').length > 0;
        table.style.display = hasRows ? 'table' : 'none';
    }
    
    // Store reference for row removal callback
    container._updateTableVisibility = updateTableVisibility;
    
    // Initial visibility update
    updateTableVisibility();
    
    container.appendChild(table);
    
    // Create add button
    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'btn btn-outline-primary wallet-add-btn';
    addButton.textContent = window.translations?.wallet_table_add || 'Add Wallet';
    addButton.style.marginRight = '10px';
    
    addButton.addEventListener('click', async (e) => {
        e.preventDefault();
        // Privacy gate: warn when adding wallet addresses with public mempool
        if (_isPublicMempool()) {
            const accepted = await _showPrivacyWarning();
            if (!accepted) return;
        }
        addWalletTableRow(tbody, { address: '', comment: '', balance: 0 });
        updateTableVisibility();
        container.dispatchEvent(new Event('change', { bubbles: true }));
    });

    // Cache wipe button
    const clearCacheButton = document.createElement('button');
    clearCacheButton.type = 'button';
    clearCacheButton.className = 'btn btn-outline-primary wallet-clear-cache-btn';
    clearCacheButton.textContent = window.translations?.clear_wallet_cache || 'Clear Wallet Data';
    clearCacheButton.addEventListener('click', async (e) => {
        e.preventDefault();
        const t = window.translations || {};
        const ok = await showConfirmModal({
            title: t.clear_wallet_cache || 'Clear Wallet Data',
            message: t.clear_wallet_cache_confirm || 'This will permanently delete all cached wallet data and remove all configured wallet addresses. Continue?',
            confirmText: t.delete || 'Delete',
            cancelText: t.cancel || 'Cancel',
            danger: true
        });
        if (!ok) return;
        try {
            const resp = await fetch('/api/clear_wallet_cache', { method: 'POST', headers: { 'Content-Type': 'application/json' } });
            const result = await resp.json();
            if (result.success) {
                // Suppress incoming wallet socket updates while clearing
                window._suppressWalletUpdates = true;
                // Clear wallet table rows and hide table
                tbody.innerHTML = '';
                updateTableVisibility();
                // Update config
                if (currentConfig) currentConfig.wallet_balance_addresses_with_comments = [];
                // Save the cleared wallet list
                await saveConfigurationSilent({ ...currentConfig, wallet_balance_addresses_with_comments: [] });
                // Clear again in case a socket event repopulated rows during save
                tbody.innerHTML = '';
                updateTableVisibility();
                // Drop the cached balance too. Removing a single row already does
                // this; without it here, clearing *everything* left the preview
                // showing the last fetched total and its fiat value, and nothing
                // would correct it — wallet socket updates are suppressed for the
                // next few seconds precisely so they cannot repopulate the table.
                window._previewData.wallet = null;
                if (window._refreshWalletPreview) window._refreshWalletPreview(null);
                showNotification(t.clear_wallet_cache_success || 'Wallet data cleared successfully', 'success');
                _markClean();
                // Re-enable wallet updates after backend settles
                setTimeout(() => { window._suppressWalletUpdates = false; }, 3000);
            } else {
                showNotification(result.message || 'Failed to clear wallet data', 'error');
            }
        } catch (err) {
            showNotification('Failed to clear wallet data', 'error');
        }
    });

    const buttonContainer = document.createElement('div');
    buttonContainer.style.display = 'flex';
    buttonContainer.style.gap = '10px';
    buttonContainer.appendChild(addButton);
    buttonContainer.appendChild(clearCacheButton);
    container.appendChild(buttonContainer);
    
    // Add getter for value (used by form system)
    container.getValue = () => {
        const rows = tbody.querySelectorAll('tr');
        return Array.from(rows).map(row => {
            const addressInput = row.querySelector('.wallet-address-input');
            const commentInput = row.querySelector('.wallet-comment-input');
            const address = addressInput ? addressInput.value.trim() : '';
            const comment = commentInput ? commentInput.value.trim() : '';

            if (!address) return null; // Skip empty addresses

            return {
                address: address,
                comment: comment,
                type: detectAddressType(address)
            };
        }).filter(entry => entry !== null);
    };
    
    // Add value property for compatibility
    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (newValues) => {
            // Clear existing rows
            tbody.innerHTML = '';
            // Add new rows
            if (Array.isArray(newValues)) {
                newValues.forEach(entry => addWalletTableRow(tbody, entry));

                // Load cached balances for the newly added entries
                loadCachedWalletBalances(tbody);
            }
        }
    });

    return container;
}

function addWalletTableRow(tbody, entry) {
    const row = document.createElement('tr');
    
    // Address cell
    const addressCell = document.createElement('td');
    addressCell.style.padding = '8px';
    addressCell.style.border = '1px solid var(--border-subtle)';
    
    const addressInput = document.createElement('input');
    addressInput.type = 'text';
    addressInput.className = 'form-control wallet-address-input';
    addressInput.value = entry.address || '';
    addressInput.placeholder = window.translations?.wallet_table_placeholder_address || 'Enter BTC address, XPUB or ZPUB';
    addressInput.style.width = '100%';
    addressInput.style.border = 'none';
    addressInput.style.padding = '5px';
    
    addressInput.addEventListener('input', () => {
        _validateInput(addressInput, _isValidBtcAddressOrXpub, true);
        tbody.parentElement.parentElement.dispatchEvent(new Event('change', { bubbles: true }));
    });
    _trimOnBlur(addressInput);
    if (addressInput.value) _validateInput(addressInput, _isValidBtcAddressOrXpub, true);

    addressCell.appendChild(addressInput);
    _addAddressMaskOverlay(addressInput);

    // Comment cell
    const commentCell = document.createElement('td');
    commentCell.style.padding = '8px';
    commentCell.style.border = '1px solid var(--border-subtle)';

    const commentInput = document.createElement('input');
    commentInput.type = 'text';
    commentInput.className = 'form-control wallet-comment-input';
    commentInput.value = entry.comment || '';
    commentInput.placeholder = window.translations?.wallet_table_placeholder_comment || 'Enter description or label';
    commentInput.style.width = '100%';
    commentInput.style.border = 'none';
    commentInput.style.padding = '5px';
    
    commentInput.addEventListener('input', () => {
        tbody.parentElement.parentElement.dispatchEvent(new Event('change', { bubbles: true }));
    });
    
    commentCell.appendChild(commentInput);
    
    // Balance cell
    const balanceCell = document.createElement('td');
    balanceCell.style.padding = '8px';
    balanceCell.style.border = '1px solid var(--border-subtle)';
    balanceCell.style.textAlign = 'center';
    
    const balanceDisplay = document.createElement('span');
    balanceDisplay.className = 'wallet-balance-display';
    _setWalletBalanceText(balanceDisplay, entry.cached_balance ? `${entry.cached_balance.toFixed(8)}` : '0.00000000');
    balanceDisplay.style.fontFamily = 'var(--font-mono)';
    balanceDisplay.style.fontSize = '0.9em';
    balanceDisplay.style.fontWeight = 'bold';
    balanceDisplay.style.color = 'var(--accent)';
    
    balanceCell.appendChild(balanceDisplay);
    
    // Actions cell
    const actionsCell = document.createElement('td');
    actionsCell.style.padding = '8px';
    actionsCell.style.border = '1px solid var(--border-subtle)';
    actionsCell.style.textAlign = 'center';
    
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'wallet-remove-icon';
    removeButton.innerHTML = '<img src="/static/icons/delete.svg" alt="Delete" class="table-delete-icon" />';
    removeButton.title = window.translations?.wallet_table_remove || 'Remove';
    removeButton.style.background = 'none';
    removeButton.style.border = 'none';
    removeButton.style.padding = '4px';
    removeButton.style.color = 'white';
    removeButton.style.cursor = 'pointer';
    removeButton.style.borderRadius = '4px';
    removeButton.style.transition = 'color 0.2s, background-color 0.2s';
    
    // Add hover effects
    removeButton.addEventListener('mouseenter', () => {
        removeButton.style.color = '#ffffff';
        removeButton.style.backgroundColor = 'rgba(220, 53, 69, 0.8)';
    });
    
    removeButton.addEventListener('mouseleave', () => {
        removeButton.style.color = 'white';
        removeButton.style.backgroundColor = 'transparent';
    });
    
    removeButton.addEventListener('click', (e) => {
        e.preventDefault();
        row.remove();
        _updateFormValidity();
        // Update table visibility after removing row
        const container = tbody.closest('.wallet-table-container');
        if (container && container._updateTableVisibility) {
            container._updateTableVisibility();
        }
        // Invalidate the cached balance preview — it reflects the address list
        // as it was at last fetch, which no longer matches after a removal.
        // Without this the preview keeps showing the old (now-wrong) total.
        window._previewData.wallet = null;
        if (window._refreshWalletPreview) window._refreshWalletPreview(null);
        tbody.parentElement.parentElement.dispatchEvent(new Event('change', { bubbles: true }));
    });
    
    actionsCell.appendChild(removeButton);
    
    row.appendChild(addressCell);
    row.appendChild(commentCell);
    row.appendChild(balanceCell);
    row.appendChild(actionsCell);
    
    tbody.appendChild(row);
}

function detectAddressType(address) {
    if (!address) return 'address';
    
    const trimmed = address.trim();
    if (trimmed.startsWith('xpub')) return 'xpub';
    if (trimmed.startsWith('zpub')) return 'zpub';
    if (trimmed.startsWith('ypub')) return 'ypub';
    return 'address';
}

function createBitaxeTableInput(values, field) {
    const container = document.createElement('div');
    container.className = 'bitaxe-table-container';
    
    // Initialize dataset for form compatibility
    if (!container.dataset) {
        container.dataset = {};
    }
    
    // Create table
    const table = document.createElement('table');
    table.className = 'wallet-table'; // Reuse wallet table styling
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.style.marginBottom = '15px';
    
    // Create table header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    
    const addressHeader = document.createElement('th');
    addressHeader.textContent = window.translations?.bitaxe_table_address || 'IP Address';
    addressHeader.style.padding = '10px';
    addressHeader.style.border = '1px solid var(--border-subtle)';
    addressHeader.style.backgroundColor = '#2a2d3e';
    addressHeader.style.color = '#ffffff';
    addressHeader.style.width = '28%';

    const linkHeader = document.createElement('th');
    linkHeader.textContent = '';
    linkHeader.style.padding = '10px';
    linkHeader.style.border = '1px solid var(--border-subtle)';
    linkHeader.style.backgroundColor = '#2a2d3e';
    linkHeader.style.width = '4%';

    const commentHeader = document.createElement('th');
    commentHeader.innerHTML = (window.translations?.bitaxe_table_comment || 'Comment/Label').replace('/', '/<br>');
    commentHeader.style.padding = '10px';
    commentHeader.style.border = '1px solid var(--border-subtle)';
    commentHeader.style.backgroundColor = '#2a2d3e';
    commentHeader.style.color = '#ffffff';
    commentHeader.style.width = '22%';

    const hashrateHeader = document.createElement('th');
    hashrateHeader.className = 'bitaxe-hashrate-header';
    hashrateHeader.textContent = window.translations?.bitaxe_table_hashrate || 'Hashrate';
    hashrateHeader.style.padding = '10px';
    hashrateHeader.style.border = '1px solid var(--border-subtle)';
    hashrateHeader.style.backgroundColor = '#2a2d3e';
    hashrateHeader.style.color = '#ffffff';
    hashrateHeader.style.width = '20%';
    hashrateHeader.style.textAlign = 'center';

    const bestDiffHeader = document.createElement('th');
    bestDiffHeader.textContent = window.translations?.bitaxe_table_best_diff || 'Best Difficulty';
    bestDiffHeader.style.padding = '10px';
    bestDiffHeader.style.border = '1px solid var(--border-subtle)';
    bestDiffHeader.style.backgroundColor = '#2a2d3e';
    bestDiffHeader.style.color = '#ffffff';
    bestDiffHeader.style.width = '18%';
    bestDiffHeader.style.textAlign = 'center';

    const actionsHeader = document.createElement('th');
    actionsHeader.textContent = '';
    actionsHeader.style.padding = '10px';
    actionsHeader.style.border = '1px solid var(--border-subtle)';
    actionsHeader.style.backgroundColor = '#2a2d3e';
    actionsHeader.style.color = '#ffffff';
    actionsHeader.style.width = '8%';

    headerRow.appendChild(addressHeader);
    headerRow.appendChild(linkHeader);
    headerRow.appendChild(commentHeader);
    headerRow.appendChild(hashrateHeader);
    headerRow.appendChild(bestDiffHeader);
    headerRow.appendChild(actionsHeader);
    thead.appendChild(headerRow);
    table.appendChild(thead);
    
    // Create table body
    const tbody = document.createElement('tbody');
    table.appendChild(tbody);
    
    // Add existing bitaxe entries
    values.forEach(entry => addBitaxeTableRow(tbody, entry));
    
    // Function to update table visibility
    function updateTableVisibility() {
        const hasRows = tbody.querySelectorAll('tr').length > 0;
        table.style.display = hasRows ? 'table' : 'none';
    }
    
    // Store reference for row removal callback
    container._updateTableVisibility = updateTableVisibility;
    
    // Initial visibility update
    updateTableVisibility();
    
    container.appendChild(table);
    
    // Create add button
    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'btn btn-outline-primary bitaxe-add-btn';
    addButton.textContent = window.translations?.bitaxe_table_add || 'Add Miner';
    
    addButton.addEventListener('click', (e) => {
        e.preventDefault();
        addBitaxeTableRow(tbody, { address: '', comment: '' });
        updateTableVisibility();
        container.dispatchEvent(new Event('change', { bubbles: true }));
    });
    
    const buttonContainer = document.createElement('div');
    buttonContainer.appendChild(addButton);
    container.appendChild(buttonContainer);
    
    // Add getter for value (used by form system)
    container.getValue = () => {
        const rows = tbody.querySelectorAll('tr');
        return Array.from(rows).map(row => {
            const addressInput = row.querySelector('.bitaxe-address-input');
            const commentInput = row.querySelector('.bitaxe-comment-input');
            const address = addressInput ? addressInput.value.trim() : '';
            const comment = commentInput ? commentInput.value.trim() : '';

            if (!address) return null; // Skip empty addresses

            return {
                address: address,
                comment: comment
            };
        }).filter(entry => entry !== null);
    };
    
    // Add value property for compatibility
    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (newValues) => {

            // Clear existing rows
            tbody.innerHTML = '';
            // Add new rows
            if (Array.isArray(newValues)) {
                newValues.forEach(entry => addBitaxeTableRow(tbody, entry));
            } else {
            }
        }
    });
    
    return container;
}

function addBitaxeTableRow(tbody, entry) {
    const row = document.createElement('tr');
    
    // Address cell
    const addressCell = document.createElement('td');
    addressCell.style.padding = '8px';
    addressCell.style.border = '1px solid var(--border-subtle)';
    
    const addressInput = document.createElement('input');
    addressInput.type = 'text';
    addressInput.className = 'bitaxe-address-input';
    addressInput.value = entry.address || '';
    addressInput.placeholder = window.translations?.bitaxe_table_placeholder_address || 'Enter IP address (e.g., 192.168.1.100)';
    addressInput.style.width = '100%';
    addressInput.style.border = '1px solid rgba(255, 255, 255, 0.3) !important';
    addressInput.style.padding = '8px !important';
    addressInput.style.background = 'var(--bg-input) !important';
    addressInput.style.color = '#ffffff !important';
    addressInput.style.fontSize = '0.9em';
    addressInput.style.borderRadius = '4px !important';

    addressCell.appendChild(addressInput);

    // Link cell — icon linking to http://[ip] in a new tab
    const linkCell = document.createElement('td');
    linkCell.style.padding = '8px';
    linkCell.style.border = '1px solid var(--border-subtle)';
    linkCell.style.textAlign = 'center';
    linkCell.style.verticalAlign = 'middle';

    const linkAnchor = document.createElement('a');
    linkAnchor.className = 'bitaxe-open-link';
    linkAnchor.target = '_blank';
    linkAnchor.rel = 'noopener noreferrer';
    linkAnchor.style.display = 'inline-flex';
    linkAnchor.style.opacity = entry.address ? '1' : '0.3';
    linkAnchor.style.pointerEvents = entry.address ? 'auto' : 'none';
    if (entry.address) linkAnchor.href = `http://${entry.address}`;
    const linkIcon = _createMaskIcon('/static/icons/open.svg');
    linkIcon.classList.add('bitaxe-open-link-icon');
    linkIcon.title = 'Open';
    linkAnchor.appendChild(linkIcon);
    linkCell.appendChild(linkAnchor);

    // Keep link href in sync as the user types
    addressInput.addEventListener('input', () => {
        const ip = addressInput.value.trim();
        if (ip) {
            linkAnchor.href = `http://${sanitizeHost(ip)}`;
            linkAnchor.style.opacity = '1';
            linkAnchor.style.pointerEvents = 'auto';
        } else {
            linkAnchor.removeAttribute('href');
            linkAnchor.style.opacity = '0.3';
            linkAnchor.style.pointerEvents = 'none';
        }
    });

    // Comment cell
    const commentCell = document.createElement('td');
    commentCell.style.padding = '8px';
    commentCell.style.border = '1px solid var(--border-subtle)';
    
    const commentInput = document.createElement('input');
    commentInput.type = 'text';
    commentInput.className = 'bitaxe-comment-input';
    commentInput.value = entry.comment || '';
    commentInput.placeholder = 'Miner name/description';
    commentInput.style.width = '100%';
    commentInput.style.border = '1px solid rgba(255, 255, 255, 0.3) !important';
    commentInput.style.padding = '8px !important';
    commentInput.style.background = 'var(--bg-input) !important';
    commentInput.style.color = '#ffffff !important';
    commentInput.style.fontSize = '0.9em';
    commentInput.style.borderRadius = '4px !important';
    
    commentCell.appendChild(commentInput);

    // Hashrate cell
    const hashrateCell = document.createElement('td');
    hashrateCell.style.padding = '8px';
    hashrateCell.style.border = '1px solid var(--border-subtle)';
    hashrateCell.style.textAlign = 'center';

    const hashrateDisplay = document.createElement('span');
    hashrateDisplay.className = 'bitaxe-hashrate-display';
    hashrateDisplay.textContent = '-';
    hashrateDisplay.style.fontFamily = 'var(--font-mono)';
    hashrateDisplay.style.fontSize = '0.9em';
    hashrateDisplay.style.fontWeight = 'bold';
    hashrateDisplay.style.color = 'var(--text-muted)';
    hashrateCell.appendChild(hashrateDisplay);

    // Best Difficulty cell
    const bestDiffCell = document.createElement('td');
    bestDiffCell.style.padding = '8px';
    bestDiffCell.style.border = '1px solid var(--border-subtle)';
    bestDiffCell.style.textAlign = 'center';

    const bestDiffDisplay = document.createElement('span');
    bestDiffDisplay.className = 'bitaxe-best-diff-display';
    bestDiffDisplay.textContent = '-';
    bestDiffDisplay.style.fontFamily = 'var(--font-mono)';
    bestDiffDisplay.style.fontSize = '0.9em';
    bestDiffDisplay.style.fontWeight = 'bold';
    bestDiffDisplay.style.color = 'var(--text-muted)';
    bestDiffCell.appendChild(bestDiffDisplay);

    // Fetch both hashrate and best diff together; debounced on IP input
    let _bitaxeIpDebounce = null;
    addressInput.addEventListener('input', () => {
        _validateInput(addressInput, _RE_IPV4, true);
        clearTimeout(_bitaxeIpDebounce);
        const newIp = addressInput.value.trim();
        if (!newIp) {
            bestDiffDisplay.textContent = '-';
            bestDiffDisplay.style.color = 'var(--text-muted)';
            hashrateDisplay.textContent = '-';
            hashrateDisplay.style.color = 'var(--text-muted)';
            return;
        }
        // Wait until the field looks like a complete IPv4 address before fetching
        _bitaxeIpDebounce = setTimeout(() => {
            const ip = addressInput.value.trim();
            if (_RE_IPV4.test(ip)) {
                bestDiffDisplay.textContent = '...';
                bestDiffDisplay.style.color = 'var(--text-muted)';
                hashrateDisplay.textContent = '...';
                hashrateDisplay.style.color = 'var(--text-muted)';
                fetchBitaxeMinerInfo(ip, bestDiffDisplay, hashrateDisplay);
            }
        }, 1000);
    });
    _trimOnBlur(addressInput);
    if (addressInput.value) _validateInput(addressInput, _RE_IPV4, true);

    // Load initial values if IP is set
    if (entry.address) {
        bestDiffDisplay.textContent = '...';
        bestDiffDisplay.style.color = 'var(--text-muted)';
        hashrateDisplay.textContent = '...';
        hashrateDisplay.style.color = 'var(--text-muted)';
        fetchBitaxeMinerInfo(entry.address, bestDiffDisplay, hashrateDisplay);
    }

    // Actions cell
    const actionsCell = document.createElement('td');
    actionsCell.style.padding = '8px';
    actionsCell.style.border = '1px solid var(--border-subtle)';
    actionsCell.style.textAlign = 'center';

    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'bitaxe-remove-icon';
    removeButton.innerHTML = '<img src="/static/icons/delete.svg" alt="Delete" class="table-delete-icon" />';
    removeButton.title = window.translations?.bitaxe_table_remove || 'Remove';
    removeButton.style.background = 'none';
    removeButton.style.border = 'none';
    removeButton.style.padding = '4px';
    removeButton.style.color = 'white';
    removeButton.style.cursor = 'pointer';
    removeButton.style.borderRadius = '4px';
    removeButton.style.transition = 'color 0.2s, background-color 0.2s';

    // Add hover effects
    removeButton.addEventListener('mouseenter', () => {
        removeButton.style.color = '#ffffff';
        removeButton.style.backgroundColor = 'rgba(220, 53, 69, 0.8)';
    });

    removeButton.addEventListener('mouseleave', () => {
        removeButton.style.color = 'white';
        removeButton.style.backgroundColor = 'transparent';
    });

    removeButton.addEventListener('click', (e) => {
        e.preventDefault();
        row.remove();
        _updateFormValidity();
        // Update table visibility after removing row
        const container = tbody.closest('.bitaxe-table-container');
        if (container && container._updateTableVisibility) {
            container._updateTableVisibility();
        }
        // Invalidate the cached hashrate/diff preview — it reflects the miner list
        // as it was at last fetch, which no longer matches after a removal.
        window._previewData.bitaxe = null;
        if (window._refreshBitaxePreview) window._refreshBitaxePreview(null);
        container.dispatchEvent(new Event('change', { bubbles: true }));
    });

    actionsCell.appendChild(removeButton);

    // Assemble row
    row.appendChild(addressCell);
    row.appendChild(linkCell);
    row.appendChild(commentCell);
    row.appendChild(hashrateCell);
    row.appendChild(bestDiffCell);
    row.appendChild(actionsCell);
    tbody.appendChild(row);
}

function createBlockRewardTableInput(values, field) {
    const container = document.createElement('div');
    container.className = 'block-reward-table-container';
    
    // Initialize dataset for form compatibility
    if (!container.dataset) {
        container.dataset = {};
    }
    
    // Create table
    const table = document.createElement('table');
    table.className = 'wallet-table'; // Reuse wallet table styling
    table.style.width = '100%';
    table.style.borderCollapse = 'collapse';
    table.style.marginBottom = '15px';
    
    // Create table header
    const thead = document.createElement('thead');
    const headerRow = document.createElement('tr');
    
    const addressHeader = document.createElement('th');
    addressHeader.textContent = window.translations?.block_reward_table_address || 'BTC Address';
    addressHeader.style.padding = '10px';
    addressHeader.style.border = '1px solid var(--border-subtle)';
    addressHeader.style.backgroundColor = '#2a2d3e';
    addressHeader.style.color = '#ffffff';
    addressHeader.style.width = '40%';
    
    const commentHeader = document.createElement('th');
    commentHeader.innerHTML = (window.translations?.block_reward_table_comment || 'Comment/Label').replace('/', '/<br>');
    commentHeader.style.padding = '10px';
    commentHeader.style.border = '1px solid var(--border-subtle)';
    commentHeader.style.backgroundColor = '#2a2d3e';
    commentHeader.style.color = '#ffffff';
    commentHeader.style.width = '30%';
    
    const foundBlocksHeader = document.createElement('th');
    foundBlocksHeader.textContent = window.translations?.block_reward_table_found_blocks || 'Found Blocks';
    foundBlocksHeader.style.padding = '10px';
    foundBlocksHeader.style.border = '1px solid var(--border-subtle)';
    foundBlocksHeader.style.backgroundColor = '#2a2d3e';
    foundBlocksHeader.style.color = '#ffffff';
    foundBlocksHeader.style.width = '20%';
    foundBlocksHeader.style.textAlign = 'center';
    
    const actionsHeader = document.createElement('th');
    actionsHeader.textContent = '';
    actionsHeader.style.padding = '10px';
    actionsHeader.style.border = '1px solid var(--border-subtle)';
    actionsHeader.style.backgroundColor = '#2a2d3e';
    actionsHeader.style.color = '#ffffff';
    actionsHeader.style.width = '10%';
    
    headerRow.appendChild(addressHeader);
    headerRow.appendChild(commentHeader);
    headerRow.appendChild(foundBlocksHeader);
    headerRow.appendChild(actionsHeader);
    thead.appendChild(headerRow);
    
    // Create table body
    const tbody = document.createElement('tbody');
    
    // Add existing entries
    values.forEach(entry => {
        addBlockRewardTableRow(tbody, entry);
    });
    
    // Function to update table visibility
    function updateTableVisibility() {
        const hasRows = tbody.querySelectorAll('tr').length > 0;
        table.style.display = hasRows ? 'table' : 'none';
    }
    
    // Store reference for row removal callback
    container._updateTableVisibility = updateTableVisibility;
    
    // Initial visibility update
    updateTableVisibility();
    
    table.appendChild(thead);
    table.appendChild(tbody);
    
    // Create add button
    const addButton = document.createElement('button');
    addButton.type = 'button';
    addButton.className = 'btn btn-outline-success block-reward-add-btn';
    addButton.textContent = window.translations?.block_reward_table_add || 'Add Address';
    addButton.style.marginRight = '10px';

    addButton.addEventListener('click', async () => {
        // Privacy gate: warn when adding addresses with public mempool
        if (_isPublicMempool()) {
            const accepted = await _showPrivacyWarning();
            if (!accepted) return;
        }
        addBlockRewardTableRow(tbody, { address: '', comment: '' });
        updateTableVisibility();
    });
    
    // Clear block reward data button
    const clearRewardButton = document.createElement('button');
    clearRewardButton.type = 'button';
    clearRewardButton.className = 'btn btn-outline-primary wallet-clear-cache-btn';
    clearRewardButton.textContent = window.translations?.clear_block_reward_data || 'Clear Block Reward Data';
    clearRewardButton.addEventListener('click', async (e) => {
        e.preventDefault();
        const t = window.translations || {};
        const ok = await showConfirmModal({
            title: t.clear_block_reward_data || 'Clear Block Reward Data',
            message: t.clear_block_reward_data_confirm || 'This will remove all configured block reward monitoring addresses. Continue?',
            confirmText: t.delete || 'Delete',
            cancelText: t.cancel || 'Cancel',
            danger: true
        });
        if (!ok) return;
        tbody.innerHTML = '';
        updateTableVisibility();
        if (currentConfig) currentConfig.block_reward_addresses_table = [];
        await saveConfigurationSilent({ ...currentConfig, block_reward_addresses_table: [] });
        showNotification(t.clear_block_reward_data_success || 'Block reward data cleared successfully', 'success');
        _markClean();
    });

    container.appendChild(table);
    const buttonContainer = document.createElement('div');
    buttonContainer.style.display = 'flex';
    buttonContainer.style.gap = '10px';
    buttonContainer.appendChild(addButton);
    buttonContainer.appendChild(clearRewardButton);
    container.appendChild(buttonContainer);

    // Add getValue and setValue methods for form compatibility
    Object.defineProperty(container, 'value', {
        get: function() {
            const entries = [];
            const rows = tbody.querySelectorAll('tr');
            rows.forEach(row => {
                const addressInput = row.querySelector('.block-reward-address-input');
                const commentInput = row.querySelector('.block-reward-comment-input');
                
                if (addressInput && commentInput) {
                    const address = addressInput.value.trim();
                    const comment = commentInput.value.trim();
                    
                    if (address) {
                        entries.push({
                            address: address,
                            comment: comment || 'Block Reward Address'
                        });
                    }
                }
            });
            return entries;
        },
        set: function(newValues) {
            if (Array.isArray(newValues)) {
                // Clear existing rows
                tbody.innerHTML = '';
                
                // Add new rows
                newValues.forEach(entry => {
                    if (entry && typeof entry === 'object') {
                        addBlockRewardTableRow(tbody, entry);
                    }
                });
            }
        }
    });

    // Add getValue method for form collection
    container.getValue = () => {
        const entries = [];
        const rows = tbody.querySelectorAll('tr');

        rows.forEach((row) => {
            const addressInput = row.querySelector('.block-reward-address-input');
            const commentInput = row.querySelector('.block-reward-comment-input');

            if (addressInput && commentInput) {
                const address = addressInput.value.trim();
                const comment = commentInput.value.trim();

                if (address) {
                    entries.push({
                        address: address,
                        comment: comment || 'Block Reward Address'
                    });
                }
            }
        });

        return entries;
    };

    return container;
}

function addBlockRewardTableRow(tbody, entry) {
    const row = document.createElement('tr');
    
    // Address cell
    const addressCell = document.createElement('td');
    addressCell.style.padding = '8px';
    addressCell.style.border = '1px solid var(--border-subtle)';
    
    const addressInput = document.createElement('input');
    addressInput.type = 'text';
    addressInput.className = 'block-reward-address-input';
    addressInput.value = entry.address || '';
    addressInput.placeholder = window.translations?.block_reward_table_placeholder_address || 'Enter BTC address (e.g., bc1q...)';
    addressInput.style.width = '100%';
    addressInput.style.padding = '5px';
    addressInput.style.border = 'none';
    addressInput.style.background = 'transparent';
    addressInput.style.color = 'var(--text-primary)';
    addressInput.style.fontSize = '14px';
    addressInput.addEventListener('input', () => _validateInput(addressInput, _isValidBtcAddress, true));
    _trimOnBlur(addressInput);
    if (addressInput.value) _validateInput(addressInput, _isValidBtcAddress, true);

    addressCell.appendChild(addressInput);
    _addAddressMaskOverlay(addressInput);
    
    // Comment cell
    const commentCell = document.createElement('td');
    commentCell.style.padding = '8px';
    commentCell.style.border = '1px solid var(--border-subtle)';
    
    const commentInput = document.createElement('input');
    commentInput.type = 'text';
    commentInput.className = 'block-reward-comment-input';
    commentInput.value = entry.comment || '';
    commentInput.placeholder = 'Optional comment';
    commentInput.style.width = '100%';
    commentInput.style.padding = '5px';
    commentInput.style.border = 'none';
    commentInput.style.background = 'transparent';
    commentInput.style.color = 'var(--text-primary)';
    commentInput.style.fontSize = '14px';
    
    commentCell.appendChild(commentInput);
    
    // Found blocks cell
    const foundBlocksCell = document.createElement('td');
    foundBlocksCell.style.padding = '8px';
    foundBlocksCell.style.border = '1px solid var(--border-subtle)';
    foundBlocksCell.style.textAlign = 'center';
    foundBlocksCell.style.color = 'var(--accent)';
    foundBlocksCell.style.fontFamily = 'var(--font-mono)';
    foundBlocksCell.style.fontWeight = 'bold';
    foundBlocksCell.textContent = '-';
    foundBlocksCell.setAttribute('data-address', entry.address || '');
    
    // Actions cell
    const actionsCell = document.createElement('td');
    actionsCell.style.padding = '8px';
    actionsCell.style.border = '1px solid var(--border-subtle)';
    actionsCell.style.textAlign = 'center';
    
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'block-reward-remove-icon';
    removeButton.innerHTML = '<img src="/static/icons/delete.svg" alt="Delete" class="table-delete-icon" />';
    removeButton.title = window.translations?.block_reward_table_remove || 'Remove';
    removeButton.style.background = 'none';
    removeButton.style.border = 'none';
    removeButton.style.padding = '4px';
    removeButton.style.color = 'white';
    removeButton.style.cursor = 'pointer';
    removeButton.style.borderRadius = '4px';
    removeButton.style.transition = 'color 0.2s, background-color 0.2s';
    
    // Add hover effects
    removeButton.addEventListener('mouseenter', () => {
        removeButton.style.color = '#ffffff';
        removeButton.style.backgroundColor = 'rgba(220, 53, 69, 0.8)';
    });
    
    removeButton.addEventListener('mouseleave', () => {
        removeButton.style.color = 'white';
        removeButton.style.backgroundColor = 'transparent';
    });
    
    removeButton.addEventListener('click', () => {
        row.remove();
        _updateFormValidity();
        // Update table visibility after removing row
        const container = tbody.closest('.block-reward-table-container');
        if (container && container._updateTableVisibility) {
            container._updateTableVisibility();
        }
    });
    
    actionsCell.appendChild(removeButton);
    
    // Update found blocks cell when address changes
    addressInput.addEventListener('input', () => {
        const newAddress = addressInput.value.trim();
        foundBlocksCell.setAttribute('data-address', newAddress);
        if (newAddress) {
            foundBlocksCell.textContent = '...';
            // Trigger API call to get found blocks count
            fetchFoundBlocksCount(newAddress, foundBlocksCell);
        } else {
            foundBlocksCell.textContent = '-';
        }
    });
    
    // Load initial found blocks count if address exists
    if (entry.address) {
        foundBlocksCell.textContent = '...';
        fetchFoundBlocksCount(entry.address, foundBlocksCell);
    }
    
    row.appendChild(addressCell);
    row.appendChild(commentCell);
    row.appendChild(foundBlocksCell);
    row.appendChild(actionsCell);
    
    tbody.appendChild(row);
}

async function fetchFoundBlocksCount(address, cell) {
    try {
        const response = await fetch(`/api/block-rewards/${encodeURIComponent(address)}/found-blocks`);
        if (response.ok) {
            const data = await response.json();
            cell.textContent = data.found_blocks || '0';
            cell.style.color = 'var(--accent)';
        } else {
            cell.textContent = 'Error';
            cell.style.color = '#ff6b6b';
        }
    } catch (error) {
        console.error('Error fetching found blocks count:', error);
        cell.textContent = 'Error';
        cell.style.color = '#ff6b6b';
    }
}

function formatBitaxeDifficulty(value) {
    if (!value || value === 0) return '-';
    if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
    if (value >= 1e9) return `${(value / 1e9).toFixed(2)}G`;
    if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(2)}k`;
    return `${Math.round(value)}`;
}

function formatBitaxeHashrate(ghs) {
    if (!ghs || ghs === 0) return '-';
    if (ghs >= 1000) return `${(ghs / 1000).toFixed(2)} TH/s`;
    if (ghs >= 1)    return `${ghs.toFixed(2)} GH/s`;
    return `${(ghs * 1000).toFixed(2)} MH/s`;
}

async function fetchBitaxeMinerInfo(ip, bestDiffCell, hashrateCell) {
    try {
        const response = await fetch(`/api/bitaxe/${encodeURIComponent(ip)}/best-diff`);
        if (response.ok) {
            const data = await response.json();
            if (data.online) {
                if (bestDiffCell) {
                    bestDiffCell.textContent = formatBitaxeDifficulty(data.best_diff);
                    bestDiffCell.style.color = 'var(--accent)';
                }
                if (hashrateCell) {
                    hashrateCell.textContent = formatBitaxeHashrate(data.hashrate_avg_ghs);
                    hashrateCell.style.color = 'var(--accent)';
                }
            } else {
                if (bestDiffCell)  { bestDiffCell.textContent  = 'Offline'; bestDiffCell.style.color  = '#ff6b6b'; }
                if (hashrateCell)  { hashrateCell.textContent  = 'Offline'; hashrateCell.style.color  = '#ff6b6b'; }
            }
        } else {
            if (bestDiffCell)  { bestDiffCell.textContent  = 'Error'; bestDiffCell.style.color  = '#ff6b6b'; }
            if (hashrateCell)  { hashrateCell.textContent  = 'Error'; hashrateCell.style.color  = '#ff6b6b'; }
        }
    } catch (error) {
        console.error('Error fetching Bitaxe miner info:', error);
        if (bestDiffCell)  { bestDiffCell.textContent  = 'Error'; bestDiffCell.style.color  = '#ff6b6b'; }
        if (hashrateCell)  { hashrateCell.textContent  = 'Error'; hashrateCell.style.color  = '#ff6b6b'; }
    }
}

// Keep old name as alias so any callers outside this file continue to work
async function fetchBitaxeBestDiff(ip, cell) {
    return fetchBitaxeMinerInfo(ip, cell, null);
}

function createMemeManagementInterface(field) {
    const container = document.createElement('div');
    container.className = 'meme-management-container';
    
    // Upload section
    const uploadSection = document.createElement('div');
    uploadSection.className = 'form-group';
    uploadSection.style.marginBottom = '30px';
    
    const uploadLabel = document.createElement('label');
    uploadLabel.className = 'form-label';
    uploadLabel.textContent = window.translations?.upload_new_meme || 'Upload New Meme';
    uploadSection.appendChild(uploadLabel);
    
    const uploadArea = document.createElement('div');
    uploadArea.className = 'upload-area';
    uploadArea.id = 'upload-area';
    uploadArea.innerHTML = `
        <input type="file" id="file-input" accept="image/*" multiple style="display: none;">
        <div class="upload-placeholder">
            <img src="/static/icons/add_meme.svg" alt="Add Meme" class="upload-icon" style="width: 2rem; height: 2rem; margin-bottom: 10px;" />
            <p>${window.translations?.upload_placeholder || 'Click to select image(s) or drag & drop'}</p>
            <p style="font-size: 0.8rem; color: var(--accent);">${window.translations?.upload_formats || 'Supported: PNG, JPG, JPEG, GIF, WebP (Multiple files allowed)'}</p>
        </div>
    `;
    
    const uploadProgress = document.createElement('div');
    uploadProgress.id = 'upload-progress';
    uploadProgress.style.display = 'none';
    uploadProgress.style.marginTop = '10px';
    uploadProgress.innerHTML = `
        <div style="background: var(--bg-input); border-radius: 10px; overflow: hidden;">
            <div id="progress-bar" style="height: 8px; background: #F7931A; width: 100%; transform: scaleX(0); transform-origin: left; transition: transform 0.3s;"></div>
        </div>
        <p id="upload-status" style="margin-top: 5px; font-size: 0.9rem;"></p>
    `;
    
    uploadSection.appendChild(uploadArea);
    uploadSection.appendChild(uploadProgress);
    
    // Current memes section
    const memesSection = document.createElement('div');
    memesSection.className = 'form-group';
    
    const memesLabel = document.createElement('label');
    memesLabel.className = 'form-label';
    memesLabel.innerHTML = `${window.translations?.current_memes || 'Current Memes'} <span id="meme-image-count" style="color: var(--text-secondary); font-weight: 400;"></span>`;
    memesSection.appendChild(memesLabel);

    // Search input for filtering by tag/filename
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.className = 'form-input';
    searchInput.id = 'meme-search-input';
    searchInput.placeholder = window.translations?.search_memes || 'Search by tag or filename...';
    searchInput.style.cssText = 'margin-bottom: 10px; font-size: 0.85rem;';
    let memeSearchTimeout = null;
    searchInput.addEventListener('input', () => {
        clearTimeout(memeSearchTimeout);
        memeSearchTimeout = setTimeout(() => {
            const term = searchInput.value.trim();
            loadMemes(term);
        }, 350);
    });
    memesSection.appendChild(searchInput);
    
    const memesList = document.createElement('div');
    memesList.id = 'memes-list';
    memesList.style.display = 'grid';
    memesList.style.gridTemplateColumns = 'repeat(auto-fill, minmax(100px, 1fr))';
    memesList.style.gap = '10px';
    memesList.style.marginTop = '10px';

    // Wrap in scrollable container so user can scroll past the section
    const memesScrollContainer = document.createElement('div');
    memesScrollContainer.className = 'memes-scroll-container';
    memesScrollContainer.appendChild(memesList);
    memesSection.appendChild(memesScrollContainer);

    container.appendChild(uploadSection);
    container.appendChild(memesSection);

    // Initialize the meme management functionality
    setTimeout(() => {
        setupModals();
        setupUpload();
        loadMemes();
    }, 100);
    
    // Return a dummy getValue function since this isn't a form input
    container.getValue = () => null;
    
    return container;
}



