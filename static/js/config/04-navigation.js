// The section navigation bar and its scroll-spy behaviour.
// Part 4 of 8, split from config.js. Load order matters:
// these run as classic scripts sharing one global scope.

// ── Section Navigation Bar ──────────────────────────────────────────
let _sectionNavObserver = null;

// Shared tooltip element for nav pills, appended to <body> so it renders
// outside the horizontally-scrollable track (which can't be escaped by a
// pseudo-element — see .section-nav-tooltip in config.css for why).
const _navHoverCapable = window.matchMedia('(hover: hover)').matches;
function _getNavTooltipEl() {
    let el = document.getElementById('section-nav-tooltip');
    if (!el) {
        el = document.createElement('div');
        el.id = 'section-nav-tooltip';
        el.className = 'section-nav-tooltip';
        document.body.appendChild(el);
    }
    return el;
}
function _attachNavTooltip(pill) {
    if (!_navHoverCapable) return;
    const tooltipEl = _getNavTooltipEl();
    pill.addEventListener('mouseenter', () => {
        const text = pill.dataset.tooltip;
        if (!text || pill.classList.contains('active')) return;
        const rect = pill.getBoundingClientRect();
        tooltipEl.textContent = text;
        tooltipEl.style.left = (rect.left + rect.width / 2) + 'px';
        // Always above the pill, regardless of whether the nav is pinned —
        // desktop users expect a consistent tooltip position.
        tooltipEl.style.top = (rect.top - 6) + 'px';
        tooltipEl.style.transform = 'translate(-50%, -100%)';
        tooltipEl.classList.add('visible');
    });
    pill.addEventListener('mouseleave', () => {
        tooltipEl.classList.remove('visible');
    });
}

function buildSectionNav(grid) {
    // Remove previous nav if re-rendering
    const old = document.getElementById('section-nav');
    if (old) old.remove();
    if (_sectionNavObserver) { _sectionNavObserver.disconnect(); _sectionNavObserver = null; }

    const sections = grid.querySelectorAll('.config-section[id]');
    if (sections.length === 0) return;

    // Build nav container
    const nav = document.createElement('nav');
    nav.id = 'section-nav';
    nav.className = 'section-nav';

    const track = document.createElement('div');
    track.className = 'section-nav-track';

    sections.forEach(sec => {
        // Match section id back to category
        const catId = sec.id.replace('section-', '');
        const cat = categories.find(c => c.id === catId);
        if (!cat) return;

        const pill = document.createElement('button');
        pill.type = 'button';
        pill.className = 'section-nav-pill';
        pill.dataset.target = sec.id;

        // Icon
        if (cat.icon && cat.icon.startsWith('/')) {
            const img = document.createElement('img');
            img.src = cat.icon;
            img.alt = '';
            img.className = 'section-nav-icon';
            pill.appendChild(img);
        }

        pill.dataset.tooltip = cat.label;
        pill.setAttribute('aria-label', cat.label);
        _attachNavTooltip(pill);

        const label = document.createElement('span');
        label.className = 'section-nav-label';
        label.textContent = cat.label;
        label.dataset.label = cat.label;
        pill.appendChild(label);

        pill.addEventListener('click', () => {
            const target = document.getElementById(sec.id);
            if (!target) return;
            // Force-render section immediately if still a lazy placeholder
            if (target.dataset.lazy === 'true' && window._lazySectionRenderMap) {
                const renderFn = window._lazySectionRenderMap.get(catId);
                if (renderFn) renderFn();
            }
            // Scroll so section top clears the whole pinned bar (header + nav
            // now stick together — nav's own height alone under-reserves the
            // offset, overshooting past the section's actual start).
            const stickyBarHeight = stickyTopBar.offsetHeight - 2;
            const top = target.getBoundingClientRect().top + window.pageYOffset - stickyBarHeight;
            window.scrollTo({ top, behavior: 'smooth' });
        });

        track.appendChild(pill);
    });

    nav.appendChild(track);

    // Mobile expand/collapse toggle
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'section-nav-toggle';
    toggle.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" fill="currentColor" class="section-nav-toggle-icon"><path d="M480-344 240-584l56-56 184 184 184-184 56 56-240 240Z"/></svg>';
    const t = window.translations || {};
    const setToggleLabel = () => {
        const expanded = nav.classList.contains('expanded');
        toggle.setAttribute('aria-expanded', String(expanded));
        toggle.setAttribute('aria-label', expanded
            ? (t.nav_collapse || 'Collapse navigation')
            : (t.nav_expand || 'Show all sections'));
    };
    setToggleLabel();
    toggle.addEventListener('click', () => {
        nav.classList.toggle('expanded');
        setToggleLabel();
    });
    nav.appendChild(toggle);

    // Forward horizontal touch drags on the non-scrollable parts of the nav
    // (e.g. the toggle button row) to the scrollable track.
    let _ntX = null, _ntY = null, _ntRelaying = false;
    nav.addEventListener('touchstart', (e) => {
        if (track.contains(e.target)) return; // track handles its own scroll
        _ntX = e.touches[0].clientX;
        _ntY = e.touches[0].clientY;
        _ntRelaying = true;
    }, { passive: true });
    nav.addEventListener('touchmove', (e) => {
        if (!_ntRelaying || _ntX === null) return;
        const dx = e.touches[0].clientX - _ntX;
        const dy = e.touches[0].clientY - _ntY;
        if (Math.abs(dx) > Math.abs(dy)) {
            track.scrollLeft -= dx;
            e.preventDefault(); // block page scroll for horizontal gesture
        }
        _ntX = e.touches[0].clientX;
        _ntY = e.touches[0].clientY;
    }, { passive: false });
    nav.addEventListener('touchend', () => { _ntRelaying = false; _ntX = null; }, { passive: true });
    nav.addEventListener('touchcancel', () => { _ntRelaying = false; _ntX = null; }, { passive: true });

    // Insert inside the sticky top bar, right after the header, so nav scrolls
    // pinned together with the title instead of alone.
    const stickyTopBar = document.querySelector('.sticky-top-bar');
    stickyTopBar.appendChild(nav);

    // ── IntersectionObserver for active state ──
    const pills = track.querySelectorAll('.section-nav-pill');
    let activePill = null;

    function setActive(pill) {
        if (activePill === pill) return;
        // Read geometry BEFORE any classList writes to avoid forced reflow
        const trackRect = track.getBoundingClientRect();
        const pillRect = pill.getBoundingClientRect();
        if (activePill) activePill.classList.remove('active');
        pill.classList.add('active');
        activePill = pill;
        // Scroll pill into view within the track (without affecting page scroll)
        const offset = pillRect.left - trackRect.left - (trackRect.width / 2) + (pillRect.width / 2);
        track.scrollBy({ left: offset, behavior: 'smooth' });
    }

    // Set first pill active initially
    if (pills.length) setActive(pills[0]);

    // Scroll-based active tracking — find the last section whose top has scrolled past the nav
    function updateActiveFromScroll() {
        // If scrolled to the bottom of the page, activate the last section
        if ((window.innerHeight + window.scrollY) >= (document.documentElement.scrollHeight - 30)) {
            const lastSec = sections[sections.length - 1];
            if (lastSec) {
                const pill = track.querySelector(`.section-nav-pill[data-target="${lastSec.id}"]`);
                if (pill) { setActive(pill); return; }
            }
        }
        const navBottom = nav.getBoundingClientRect().bottom + 10;
        let bestPill = null;
        for (let i = sections.length - 1; i >= 0; i--) {
            const sec = sections[i];
            if (sec.getBoundingClientRect().top <= navBottom) {
                const pill = track.querySelector(`.section-nav-pill[data-target="${sec.id}"]`);
                if (pill) bestPill = pill;
                break;
            }
        }
        if (bestPill) setActive(bestPill);
    }

    let _scrollTick = false;
    window.addEventListener('scroll', () => {
        if (!_scrollTick) {
            _scrollTick = true;
            requestAnimationFrame(() => {
                updateActiveFromScroll();
                _scrollTick = false;
            });
        }
    }, { passive: true });

    // Detect when the sticky top bar becomes pinned, to flip tooltip direction.
    // Must live in normal flow OUTSIDE .sticky-top-bar — inserting it inside
    // the wrapper (next to nav) would make it travel with the pinned bar
    // instead of marking the original scroll position, so it would never
    // report leaving the viewport.
    const sentinel = document.createElement('div');
    sentinel.style.height = '1px';
    sentinel.style.visibility = 'hidden';
    stickyTopBar.parentNode.insertBefore(sentinel, stickyTopBar);
    const stickyObs = new IntersectionObserver(([e]) => {
        nav.classList.toggle('stuck', !e.isIntersecting);
    }, { threshold: 0 });
    stickyObs.observe(sentinel);
}

function _renderCategorySection(category, section) {
    if (!section || section.dataset.lazy !== 'true') return;
    delete section.dataset.lazy;
    window._lazySectionRenderMap?.delete(category.id);

        const title = document.createElement('div');
        title.className = 'section-title';

        // Handle icon: if it's a path (starts with /), create an img tag, otherwise use as text
        let iconHtml;
        if (category.icon && category.icon.startsWith('/')) {
            iconHtml = `<img src="${category.icon}" alt="${category.label}" class="section-icon" style="width: 24px; height: 24px; margin-right: 10px; vertical-align: middle; transform: translateY(-2px);">`;
        } else {
            iconHtml = category.icon || '';
        }

        // Create title span for the text content
        const titleText = document.createElement('span');
        titleText.innerHTML = `${iconHtml} ${category.label}`;
        title.appendChild(titleText);

        // Add section toggle for categories that have enable/disable functionality
        const enableToggleKey = getSectionToggleKey(category.id);
        if (enableToggleKey) {
            const toggleContainer = document.createElement('div');
            toggleContainer.className = 'section-toggle';

            const toggleSwitch = document.createElement('div');
            toggleSwitch.className = 'section-toggle-switch';
            toggleSwitch.setAttribute('data-toggle-key', enableToggleKey);
            toggleSwitch.setAttribute('data-config-key', enableToggleKey);

            // Add getValue method for compatibility with form collection
            toggleSwitch.getValue = function() {
                return toggleSwitch.classList.contains('enabled');
            };

            // Set initial state
            const isEnabled = currentConfig[enableToggleKey];
            if (isEnabled) {
                toggleSwitch.classList.add('enabled');
            }

            // Add click handler
            toggleSwitch.addEventListener('click', async function() {
                const newValue = !toggleSwitch.classList.contains('enabled');

                // Privacy gate: warn when enabling wallet monitoring with a public mempool
                if (newValue && enableToggleKey === 'show_wallet_balances_block' && _isPublicMempool()) {
                    const accepted = await _showPrivacyWarning();
                    if (!accepted) return; // user declined — keep toggle off
                }

                // Privacy gate: warn when enabling bitaxe stats with block reward addresses on a public mempool
                if (newValue && enableToggleKey === 'show_bitaxe_block' && _isPublicMempool()) {
                    const addrs = currentConfig.block_reward_addresses_table || [];
                    if (addrs.length > 0 && addrs.some(e => e.address && e.address.trim())) {
                        const accepted = await _showPrivacyWarning();
                        if (!accepted) return;
                    }
                }

                toggleSwitch.classList.toggle('enabled', newValue);

                // Update configuration
                currentConfig[enableToggleKey] = newValue;

                // Update section disabled state
                section.classList.toggle('section-disabled', !newValue);

            });

            toggleContainer.appendChild(toggleSwitch);
            title.appendChild(toggleContainer);

            // Set initial disabled state if needed
            if (!isEnabled) {
                section.classList.add('section-disabled');
            }
        }

        section.appendChild(title);

        const _previewCategories = ['price_stats', 'countdown', 'halving', 'network_stats', 'bitaxe_stats', 'wallet_monitoring', 'donation'];
        const _sectionColorKeys = {
            price_stats:       ['color_btc_price_light',   'color_btc_price_dark'],
            countdown:         ['color_countdown_light',   'color_countdown_dark'],
            halving:           ['color_halving_light',     'color_halving_dark'],
            network_stats:     ['color_network_light',     'color_network_dark'],
            bitaxe_stats:      ['color_bitaxe_stats_light','color_bitaxe_stats_dark'],
            wallet_monitoring: ['color_wallets_light',     'color_wallets_dark'],
            donation:          ['color_donation_light',    'color_donation_dark'],
        };

        let fieldsAdded = 0;
        let advancedContainer = null;
        let hasAdvancedFields = false;

        // Add fields for this category (skip the enable/disable toggle as it's now in header)
        // Sort by order property if present, otherwise preserve original order
        const categoryFields = Object.entries(configSchema)
            .filter(([key, field]) => field.category === category.id && key !== enableToggleKey)
            .sort((a, b) => (a[1].order ?? 999) - (b[1].order ?? 999));
        categoryFields.forEach(([key, field]) => {
                //console.log(`Adding field: ${key} to category ${category.id}`);
                try {
                    const formGroup = createFormField(key, field, currentConfig[key]);
                    if (field.always_visible) {
                        formGroup.classList.add('form-group--always-visible');
                    }

                    if (field.advanced) {
                        // Create collapsible advanced container on first advanced field
                        if (!advancedContainer) {
                            advancedContainer = document.createElement('div');
                            advancedContainer.className = 'advanced-section';

                            const advancedToggle = document.createElement('div');
                            advancedToggle.className = 'advanced-section-toggle';
                            advancedToggle.innerHTML = `<span class="advanced-section-arrow"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" fill="currentColor" class="advanced-chevron-icon"><path d="M480-344 240-584l56-56 184 184 184-184 56 56-240 240Z"/></svg></span> ${window.translations?.advanced_settings || 'Advanced'}`;
                            advancedToggle.addEventListener('click', () => {
                                advancedContainer.classList.toggle('advanced-section--open');
                            });

                            const advancedContent = document.createElement('div');
                            advancedContent.className = 'advanced-section-content';

                            advancedContainer.appendChild(advancedToggle);
                            advancedContainer.appendChild(advancedContent);
                        }
                        advancedContainer.querySelector('.advanced-section-content').appendChild(formGroup);
                        hasAdvancedFields = true;
                    } else {
                        section.appendChild(formGroup);
                    }
                    fieldsAdded++;
                } catch (error) {
                    console.error(`Error creating field ${key}:`, error);
                }
        });

        // Append user credentials + SSH access into the General advanced section
        if (category.id === 'general') {
            if (!advancedContainer) {
                advancedContainer = document.createElement('div');
                advancedContainer.className = 'advanced-section';

                const advancedToggle = document.createElement('div');
                advancedToggle.className = 'advanced-section-toggle';
                advancedToggle.innerHTML = `<span class="advanced-section-arrow"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 -960 960 960" fill="currentColor" class="advanced-chevron-icon"><path d="M480-344 240-584l56-56 184 184 184-184 56 56-240 240Z"/></svg></span> ${window.translations?.advanced_settings || 'Advanced'}`;
                advancedToggle.addEventListener('click', () => {
                    advancedContainer.classList.toggle('advanced-section--open');
                });

                const advancedContent = document.createElement('div');
                advancedContent.className = 'advanced-section-content';

                advancedContainer.appendChild(advancedToggle);
                advancedContainer.appendChild(advancedContent);
                section.appendChild(advancedContainer);
            }
            const advancedContent = advancedContainer.querySelector('.advanced-section-content');
            if (configCurrentUser) {
                advancedContent.appendChild(createCurrentUserUsernameField());
                advancedContent.appendChild(createCurrentUserPasswordField());
                fieldsAdded += 2;
            }
            advancedContent.appendChild(createSshAccessSection());
            fieldsAdded += 1;
        }

        // Populate the WiFi section
        if (category.id === 'wifi') {
            section.appendChild(createWifiSection());
            fieldsAdded += 1;
        }

        // Populate the Updates section with software + system update
        if (category.id === 'updates') {
            section.appendChild(createSoftwareUpdateSection());
            section.appendChild(createSystemUpdateSection());
            section.appendChild(createDeviceControlSection());
            fieldsAdded += 3;
        }

        //console.log(`Category ${category.id} has ${fieldsAdded} fields`);

        // Build side-by-side [color picker | preview card] rows for info sections.
        // Color form-group elements are physically moved into the rows so the
        // layout matches createDateColorGroup / createHolidayColorGroup.
        if (_previewCategories.includes(category.id)) {
            const _previewWrapper = document.createElement('div');
            _previewWrapper.dataset.previewSection = category.id;
            _previewWrapper.style.width = '100%';
            section.appendChild(_previewWrapper);

            // ── One-time layout setup ────────────────────────────────────────────
            // Move the two color-picker form-groups into _previewWrapper ONCE,
            // next to fixed slot divs that will hold the preview cards.
            // Doing this here (not inside _reorganize) means form-groups are never
            // detached during user interaction → no focus loss on mobile.
            const colorKeys = _sectionColorKeys[category.id];
            const _tr = window.translations || {};
            if (colorKeys) {
                const lel = section.querySelector(`[data-config-key="${colorKeys[0]}"]`);
                const del = section.querySelector(`[data-config-key="${colorKeys[1]}"]`);
                const lightFG = lel?.closest('.form-group') ?? null;
                const darkFG  = del?.closest('.form-group') ?? null;
                [
                    [lightFG, 'rgba(255,255,255,.04)', _tr.holiday_color_light_theme || 'Light Theme', 'preview-card-light'],
                    [darkFG,  'rgba(0,0,0,.04)',        _tr.holiday_color_dark_theme  || 'Dark Theme',  'preview-card-dark'],
                ].forEach(([fg, rowBg, themeLabel, slotClass]) => {
                    if (!fg) return;
                    const formLabel = fg.querySelector('.form-label');
                    if (formLabel) {
                        // Store the schema base text on the label element so the suffix
                        // can be reliably applied even if this block runs more than once.
                        if (!formLabel.dataset.baseLabel) {
                            formLabel.dataset.baseLabel = formLabel.textContent.trim();
                        }
                        formLabel.textContent = `${formLabel.dataset.baseLabel} (${themeLabel})`;
                    }
                    fg.style.cssText += ';flex:1 1 0;min-width:0;';
                    const slot = document.createElement('div');
                    slot.className = slotClass;
                    slot.style.cssText = 'flex:1 1 0;min-width:0;';
                    const row = document.createElement('div');
                    row.className = 'preview-color-row';
                    row.style.cssText = `margin-bottom:10px;padding:12px 14px;border-radius:8px;background:${rowBg};`;
                    row.appendChild(fg);    // moved once — never touched again by _reorganize
                    row.appendChild(slot);
                    _previewWrapper.appendChild(row);
                });
            }

            // ── _reorganize: only refreshes preview card content ─────────────────
            // Fills (or replaces the inner content of) the slot divs above.
            // Never removes or re-inserts form-groups → safe while typing.
            const _reorganize = () => {
                let built = null;
                try { built = _buildSectionPreview(category.id, section); } catch(err) {}
                const lightCard = built?.querySelector('.preview-theme-light');
                const darkCard  = built?.querySelector('.preview-theme-dark');

                if (lightCard || darkCard) {
                    [['preview-card-light', lightCard], ['preview-card-dark', darkCard]].forEach(([cls, card]) => {
                        if (!card) return;
                        const slot = _previewWrapper.querySelector('.' + cls);
                        if (slot) { slot.innerHTML = ''; slot.appendChild(card); }
                    });
                } else if (built) {
                    // Fallback (no colorKeys): show preview without side-by-side layout.
                    _previewWrapper.innerHTML = '';
                    built.style.cssText = 'display:flex;gap:16px;margin:10px 0;flex-wrap:wrap;';
                    _previewWrapper.appendChild(built);
                }

                // Re-apply live data (closures updated by _buildSectionPreview above).
                const pd = window._previewData;
                if (!pd) return;
                const refreshMap = {
                    price_stats:       [pd.price,     window._refreshPricePreview],
                    bitaxe_stats:      [pd.bitaxe,    window._refreshBitaxePreview],
                    wallet_monitoring: [pd.wallet,    window._refreshWalletPreview],
                    donation:          [pd.donation,  window._refreshDonationPreview],
                    countdown:         [pd.countdown, window._refreshCountdownPreview],
                    halving:           [pd.halving,   window._refreshHalvingPreview],
                    network_stats:     [pd.network,   window._refreshNetworkPreview],
                };
                const entry = refreshMap[category.id];
                if (entry && entry[0] && entry[1]) entry[1](entry[0]);
            };

            // Published so a setting in *another* section can refresh this one.
            // number_format lives under General but repunctuates every figure in
            // every preview card, and _reorganize is otherwise a closure that
            // nothing outside this section can reach.
            (window._previewRefreshers ||= {})[category.id] = _reorganize;

            _reorganize();

            let _previewDebounce = null;
            // Structural changes (selects, toggles) → immediate rebuild.
            // Walk up from e.target in case the event fires on an inner element
            // (e.g. the hidden <input> inside a custom select container).
            section.addEventListener('change', (e) => {
                const keyEl = e.target?.dataset?.configKey
                    ? e.target
                    : e.target?.closest('[data-config-key]');
                const key = keyEl?.dataset?.configKey;
                if (!key) return;
                const val = keyEl.getValue ? keyEl.getValue()
                          : keyEl.type === 'checkbox' ? keyEl.checked
                          : keyEl.type === 'number'   ? _numFieldValue(keyEl)
                          : keyEl.value;
                window._pendingConfigOverrides[key] = val;
                // Text field blur in a color picker: skip _reorganize (same logic as input
                // listener). The input listener already updated _pendingConfigOverrides live;
                // _reorganize will run on the next swatch interaction or section change.
                if (e.target.type === 'text' && e.target.closest('.color-input-container')) return;
                clearTimeout(_previewDebounce);
                if (key === 'btc_price_currency' || key === 'wallet_balance_currency') {
                    const _cfg2 = { ...(window.currentConfig || {}), ...(window._pendingConfigOverrides || {}) };
                    const _params = new URLSearchParams();
                    _params.set('price_currency', _cfg2['btc_price_currency'] || 'USD');
                    _params.set('wallet_currency', _cfg2['wallet_balance_currency'] || 'EUR');
                    fetch('/api/config/preview-data?' + _params)
                        .then(r => r.ok ? r.json() : null)
                        .then(d => {
                            if (d?.price) window._previewData.price = d.price;
                            if (d?.wallet) window._previewData.wallet = d.wallet;
                            _reorganize();
                        })
                        .catch(() => { _reorganize(); });
                    return;
                }
                _reorganize();
            }, true);

            // Color drag → debounced rebuild to avoid excessive repaints.
            section.addEventListener('input', (e) => {
                const keyEl = e.target?.dataset?.configKey
                    ? e.target
                    : e.target?.closest('[data-config-key]');
                const key = keyEl?.dataset?.configKey;
                if (!key || !key.startsWith('color_')) return;
                window._pendingConfigOverrides[key] = keyEl.getValue ? keyEl.getValue() : keyEl.value;
                // Skip _reorganize while the user is actively typing in the hex text field.
                // Also skip when the native color swatch fires an input event caused by the
                // text↔swatch sync (some mobile browsers fire a synthetic input on the color
                // input when its value is set programmatically while the text field has focus).
                const container = e.target.closest('.color-input-container');
                if (container) {
                    if (e.target.type === 'text') return;
                    const textEl = container.querySelector('input[type="text"]');
                    if (textEl && document.activeElement === textEl) return;
                }
                clearTimeout(_previewDebounce);
                _previewDebounce = setTimeout(_reorganize, 60);
            }, true);
        }

        // Append advanced container at the very end — after preview rows and all other content
        if (advancedContainer && !advancedContainer.parentElement) {
            section.appendChild(advancedContainer);
        }

        // Remove section (and its nav pill) if it has no fields and no toggle
        if (fieldsAdded === 0 && !enableToggleKey) {
            document.querySelector(`.section-nav-pill[data-target="${section.id}"]`)?.remove();
            section.remove();
        }
}

// Settings whose effect is not confined to their own section.
//   number_format  repunctuates every figure in every preview card, but lives
//                  under General, whose section has no preview and therefore no
//                  change listener of its own — so the edit would sit invisible
//                  until a save and a page reload.
//   fee_parameter  picks the tier the block height is colored by, and each tier
//                  has its own median: a different one is a different scale, not
//                  a different caption. It sits in Theming right above the color
//                  group, but Theming has no preview listener either.
const _GLOBAL_PREVIEW_KEYS = ['number_format', 'fee_parameter'];

function _installGlobalPreviewListener() {
    if (window._globalPreviewListenerInstalled) return;
    window._globalPreviewListenerInstalled = true;
    document.addEventListener('change', (e) => {
        const el = e.target?.dataset?.configKey
            ? e.target
            : e.target?.closest?.('[data-config-key]');
        const key = el?.dataset?.configKey;
        if (!key || !_GLOBAL_PREVIEW_KEYS.includes(key)) return;
        // Record it first: every preview reads the pending overrides, so the
        // refresh below has to see the new value rather than the saved one.
        window._pendingConfigOverrides = window._pendingConfigOverrides || {};
        window._pendingConfigOverrides[key] = el.getValue ? el.getValue() : el.value;
        // Only the punctuation reaches the info-block cards; which fee tier the
        // block height reads is nobody else's business.
        if (key === 'number_format') {
            Object.values(window._previewRefreshers || {}).forEach(fn => {
                try { fn(); } catch (err) { /* one bad card must not stop the rest */ }
            });
        }
        if (typeof window._refreshBlockHeightPreview === 'function') {
            // A new tier brings a new median and a new fee, so the panel re-seats
            // its slider rather than merely regrouping the digits it already has.
            try { window._refreshBlockHeightPreview({ reseat: key === 'fee_parameter' }); }
            catch (err) { /* as above */ }
        }
    }, true);
}

function renderConfigurationForm() {
    window._pendingConfigOverrides = {}; // reset on every re-render
    _installGlobalPreviewListener();
    const container = document.getElementById('config-container');
    container.innerHTML = ''; // Clear any existing content
    const grid = document.createElement('div');
    grid.className = 'config-grid';
    
    // console.log('Rendering configuration form...');
    // console.log('Categories:', categories);
    // console.log('Schema:', configSchema);
    // console.log('Current config:', currentConfig);
    
    if (!categories || categories.length === 0) {
        console.error('No categories found!');
        container.innerHTML = '<p style="color: red;">Error: No configuration categories found</p>';
        return;
    }
    
    if (!configSchema || Object.keys(configSchema).length === 0) {
        console.error('No schema found!');
        container.innerHTML = '<p style="color: red;">Error: No configuration schema found</p>';
        return;
    }
    
    // Phase 1: create lightweight skeleton sections (just empty divs with correct IDs)
    // so scroll anchoring and nav pills work before sections are populated.
    window._lazySectionRenderMap = new Map();
    categories.forEach(category => {
        const section = document.createElement('div');
        section.className = 'config-section';
        section.id = 'section-' + category.id;
        if (category.id === 'meme_management' || category.id === 'opsec' || category.id === 'meme_sync') {
            section.classList.add('meme-management-section');
        }
        section.dataset.lazy = 'true';
        grid.appendChild(section);
        window._lazySectionRenderMap.set(
            category.id,
            () => _renderCategorySection(category, section)
        );
    });

    container.appendChild(grid);

    // ── Section Navigation Bar ──────────────────────────────────
    buildSectionNav(grid);

    // Phase 2: render the first section immediately (it's above the fold)
    _renderCategorySection(categories[0], grid.querySelector('#section-' + categories[0].id));

    // Phase 3: render remaining sections lazily during browser idle time
    let _lazyIdx = 0;
    const _lazyQueue = categories.slice(1);
    function _processLazyQueue(deadline) {
        while (_lazyIdx < _lazyQueue.length) {
            if (deadline && deadline.timeRemaining() < 8) break;
            const cat = _lazyQueue[_lazyIdx++];
            const sec = document.getElementById('section-' + cat.id);
            if (sec && sec.dataset.lazy === 'true') _renderCategorySection(cat, sec);
        }
        if (_lazyIdx < _lazyQueue.length) {
            if ('requestIdleCallback' in window) {
                requestIdleCallback(_processLazyQueue, { timeout: 3000 });
            } else {
                setTimeout(() => _processLazyQueue(null), 16);
            }
        }
    }
    if ('requestIdleCallback' in window) {
        requestIdleCallback(_processLazyQueue, { timeout: 500 });
    } else {
        setTimeout(() => _processLazyQueue(null), 0);
    }

    // Load cached balances for any existing wallet entries after form is rendered
    setTimeout(() => {
        const walletTable = document.querySelector('.wallet-table tbody');
        if (walletTable && walletTable.children.length > 0) {
            loadCachedWalletBalances(walletTable);
        }
    }, 100); // Small delay to ensure DOM is fully updated
    

    // Fetch live preview data on initial render.
    _fetchPreviewData(1);
}

// Fetch live preview data — retry with backoff
function _fetchPreviewData(attempt) {
    fetch('/api/config/preview-data')
        .then(r => r.ok ? r.json() : null)
        .then(d => {
            if (!d) return;
            const fields = ['price','bitaxe','wallet','donation','countdown','halving','network'];
            fields.forEach(k => { if (d[k]) window._previewData[k] = d[k]; });
            if (d.block_hash) {
                window._previewData.latestBlockHash = d.block_hash;
                if (window._refreshDateHashPreview)    window._refreshDateHashPreview(d.block_hash);
                if (window._refreshHolidayHashPreview) window._refreshHolidayHashPreview(d.block_hash);
            }
            if (d.price      && window._refreshPricePreview)      window._refreshPricePreview(d.price);
            if (d.bitaxe     && window._refreshBitaxePreview)     window._refreshBitaxePreview(d.bitaxe);
            if (d.wallet     && window._refreshWalletPreview)     window._refreshWalletPreview(d.wallet);
            if (d.donation   && window._refreshDonationPreview)   window._refreshDonationPreview(d.donation);
            if (d.countdown  && window._refreshCountdownPreview)  window._refreshCountdownPreview(d.countdown);
            if (d.halving    && window._refreshHalvingPreview)    window._refreshHalvingPreview(d.halving);
            if (d.network    && window._refreshNetworkPreview)    window._refreshNetworkPreview(d.network);

            const pd = window._previewData;
            const cfg = window.currentConfig || {};
            const stillMissing =
                !pd.price ||
                !pd.network ||
                (cfg.show_countdown_block !== false && !pd.countdown) ||
                (cfg.show_halving_block   !== false && !pd.halving) ||
                (cfg.show_bitaxe_block !== false && cfg.bitaxe_enabled !== false && !pd.bitaxe);

            if (stillMissing && attempt < 6) {
                setTimeout(() => _fetchPreviewData(attempt + 1), Math.min(1500 * attempt, 10000));
            }
        })
        .catch(() => {
            if (attempt < 6) setTimeout(() => _fetchPreviewData(attempt + 1), 3000);
        });
}

// Reload the block-height color scale after a block. Everything in that payload
// hangs off the tip — the fee each tier is at, the height the sample draws, the
// medians those fees are judged against — so a page left open colors a fee
// nobody is paying any more until it is fetched again.
//
// `minHeight` is the height the notification announced. The scale is read from
// the renderer's own fee cache, which the new block only lands in once the panel
// has been redrawn, so the first answer is often still the previous tip; rather
// than guess at a delay, ask again until the payload has caught up.
function _refreshBlockHeightScale(minHeight, attemptArg) {
    const attempt = attemptArg || 1;
    const again = () => {
        if (attempt < 6) {
            setTimeout(() => _refreshBlockHeightScale(minHeight, attempt + 1),
                       Math.min(3000 * attempt, 15000));
        }
    };
    fetch('/api/config/block-height-scale')
        .then(r => r.ok ? r.json() : null)
        .then(d => {
            if (!d || d.error) { again(); return; }
            window.blockHeightPreview = d;
            if (typeof window._refreshBlockHeightPreview === 'function') {
                // reseat: the fee on the slider belonged to the previous block.
                window._refreshBlockHeightPreview({ reseat: true });
            }
            if (minHeight && !(d.block_height >= minHeight)) again();
        })
        .catch(again);
}

// Cache and helper for loading SVG icons with a specific fill color
const _mpaIconCache = {};
['check', 'error'].forEach(name => {
    fetch(`/static/icons/${name}.svg`)
        .then(r => r.text())
        .then(svg => { _mpaIconCache[name] = svg; })
        .catch(() => {});
});

const _MPA_SVG_NS = 'http://www.w3.org/2000/svg';

// Element form of the cached icons. Toasts and the log modal build their
// content from nodes, so the icon has to be a node too - parsing the cached
// markup here (a first-party asset, image/svg+xml, no script execution)
// keeps the whole icon rather than reducing it to a single path.
function _mpaIcon(name, color, size) {
    const cached = _mpaIconCache[name];
    if (!cached) return null;
    const root = new DOMParser().parseFromString(cached, 'image/svg+xml').documentElement;
    if (!root || root.localName !== 'svg') return null;
    const svg = document.importNode(root, true);
    svg.setAttribute('fill', color);
    svg.style.cssText = `width:${size}px;height:${size}px;flex-shrink:0;vertical-align:-3px;`;
    return svg;
}

// Build an inline icon element from a single Material-symbol path, for icons
// that aren't in the fetched cache.
function _mpaSvgIcon(pathData, color, size, extraStyle) {
    const svg = document.createElementNS(_MPA_SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 -960 960 960');
    svg.setAttribute('fill', color);
    svg.style.cssText = `width:${size}px;height:${size}px;flex-shrink:0;vertical-align:-3px;` + (extraStyle || '');
    const path = document.createElementNS(_MPA_SVG_NS, 'path');
    path.setAttribute('d', pathData);
    svg.appendChild(path);
    return svg;
}

// `title` because both the mempool and the Tang check open this, and it used to
// be captioned "Mempool Connection Log" either way.
function _mpaShowLogModal(checks, heading) {
    const dark = document.body.classList.contains('dark-mode');
    const C = dark ? {
        bg:          'rgba(22, 22, 28, 0.97)',
        shadow:      '0 24px 64px rgba(0,0,0,0.5)',
        overlay:     'rgba(0,0,0,0.6)',
        border:      'rgba(255,255,255,0.09)',
        text:        '#e8e8ec',
        muted:       'rgba(232,232,236,0.72)',
        badge:       'rgba(255,255,255,0.07)',
        badgeBorder: 'rgba(255,255,255,0.12)',
        errBg:       'rgba(239,68,68,0.1)',
        errBorder:   'rgba(239,68,68,0.25)',
        errText:     '#f87171',
    } : {
        bg:          'rgba(255,255,255,0.98)',
        shadow:      '0 24px 64px rgba(0,0,0,0.18)',
        overlay:     'rgba(0,0,0,0.35)',
        border:      'rgba(0,0,0,0.1)',
        text:        '#1a1a1e',
        muted:       'rgba(30,30,40,0.58)',
        badge:       'rgba(0,0,0,0.05)',
        badgeBorder: 'rgba(0,0,0,0.12)',
        errBg:       'rgba(220,38,38,0.07)',
        errBorder:   'rgba(220,38,38,0.2)',
        errText:     '#b91c1c',
    };

    const overlay = document.createElement('div');
    overlay.style.cssText = `position:fixed;inset:0;z-index:200000;background:${C.overlay};display:flex;align-items:center;justify-content:center;padding:20px;`;

    const box = document.createElement('div');
    box.style.cssText = `background:${C.bg};backdrop-filter:blur(24px);-webkit-backdrop-filter:blur(24px);border:1px solid ${C.border};border-radius:14px;padding:24px;max-width:540px;width:100%;max-height:75vh;overflow-y:auto;box-shadow:${C.shadow};color:${C.text};`;

    const title = document.createElement('div');
    title.style.cssText = `font-weight:700;font-size:15px;margin-bottom:18px;color:${C.text};`;
    title.textContent = heading || (window.translations || {}).connection_log || 'Connection Log';
    box.appendChild(title);

    checks.forEach(c => {
        const row = document.createElement('div');
        row.style.cssText = `margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid ${C.border};`;

        const header = document.createElement('div');
        header.style.cssText = `display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:${c.ok ? '#22c55e' : '#ef4444'};`;
        const detailText = [c.detail, c.latency_ms != null ? `${c.latency_ms} ms` : null].filter(Boolean).join(' · ');
        const icon = c.ok ? _mpaIcon('check', '#22c55e', 14) : _mpaIcon('error', '#ef4444', 14);
        if (icon) header.appendChild(icon);
        header.appendChild(document.createTextNode(c.name));
        if (detailText) {
            const detailBadge = document.createElement('span');
            detailBadge.style.cssText = `margin-left:auto;font-weight:400;font-size:10px;color:${C.muted};background:${C.badge};padding:2px 7px;border-radius:4px;border:1px solid ${C.badgeBorder};white-space:nowrap;`;
            detailBadge.textContent = detailText;
            header.appendChild(detailBadge);
        }
        row.appendChild(header);

        if (c.url) {
            const urlEl = document.createElement('div');
            urlEl.style.cssText = `font-size:10px;color:${C.muted};margin-top:4px;word-break:break-all;padding-left:22px;font-family:monospace;`;
            urlEl.textContent = c.url;
            row.appendChild(urlEl);
        }

        if (!c.ok && c.error) {
            const errBox = document.createElement('div');
            errBox.style.cssText = `margin-top:7px;padding:8px 10px;background:${C.errBg};border-radius:6px;font-family:monospace;font-size:11px;white-space:pre-wrap;word-break:break-all;color:${C.errText};border:1px solid ${C.errBorder};line-height:1.5;`;
            errBox.textContent = c.error;
            row.appendChild(errBox);
        }
        box.appendChild(row);
    });

    const closeBtn = document.createElement('button');
    closeBtn.textContent = 'Close';
    closeBtn.style.cssText = `margin-top:16px;width:100%;padding:10px;background:transparent;border:1px solid ${C.border};border-radius:8px;color:${C.muted};cursor:pointer;font-size:13px;font-family:inherit;transition:border-color 0.15s,color 0.15s;`;
    closeBtn.addEventListener('mouseenter', () => { closeBtn.style.borderColor = 'var(--accent)'; closeBtn.style.color = 'var(--accent)'; });
    closeBtn.addEventListener('mouseleave', () => { closeBtn.style.borderColor = C.border; closeBtn.style.color = C.muted; });
    closeBtn.addEventListener('click', () => overlay.remove());
    box.appendChild(closeBtn);

    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    overlay.appendChild(box);
    document.body.appendChild(overlay);
}

function createFormField(key, field, value) {
    const formGroup = document.createElement('div');
    formGroup.className = 'form-group';
    const fieldId = 'cfg-' + key;

    // Add special class for color fields to allow side-by-side layout
    if (field.type === 'color' || field.type === 'color_select') {
        formGroup.classList.add('form-group-color');
    }

    // Skip adding label for self-managed interfaces and pure info boxes
    const skipLabel = field.type === 'meme_management' || field.type === 'donation_history' || field.type === 'info_text' || field.type === 'open_url_button' || field.type === 'connection_check' || field.type === 'mempool_actions' || field.type === 'tang_check' || field.type === 'hidden';
    if (!skipLabel) {
        const label = document.createElement('label');
        label.className = 'form-label';
        label.textContent = field.label;
        label.htmlFor = fieldId;
        formGroup.appendChild(label);
    }

    let input;
    
    switch (field.type) {
        case 'text':
        case 'string':  // Added support for 'string' type
            input = document.createElement('input');
            input.type = 'text';
            input.className = 'form-input';
            input.value = value !== undefined && value !== null ? value : '';
            input.placeholder = field.placeholder || '';
            // Trim on blur — this branch covers most free-text config fields users
            // paste into (mempool host, webhook relay URL, usernames, etc.); a
            // trailing space or newline from the clipboard shouldn't silently
            // change the saved value. Captured now, before the field may get
            // wrapped below (mempool_host / webhook_relay_ws_url), so it always
            // targets the actual <input>, not the wrapper div.
            _trimOnBlur(input);

            // Disable autocomplete for admin_username field
            if (key === 'admin_username') {
                input.setAttribute('autocomplete', 'off');
            }
            // Inline "private instance" checkbox for mempool_host
            if (key === 'mempool_host') {
                const hostInput = input; // keep reference to the actual text input
                const wrapper = document.createElement('div');
                wrapper.className = 'mempool-host-row';
                hostInput.style.flex = '1';
                hostInput.style.minWidth = '0';
                wrapper.appendChild(hostInput);
                // Forward value access to the text input so form collection works
                wrapper.getValue = function () { return hostInput.value; };
                Object.defineProperty(wrapper, 'value', {
                    get: () => hostInput.value,
                    set: (v) => { hostInput.value = v; }
                });

                const checkRow = document.createElement('label');
                checkRow.className = 'mempool-private-check';
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.checked = !!(currentConfig && currentConfig.mempool_is_private);
                cb.dataset.configKey = 'mempool_is_private';
                cb.getValue = function () { return cb.checked; };
                const span = document.createElement('span');
                const t = window.translations || {};
                span.textContent = t.mempool_is_private || 'Private/Self-Hosted Instance';
                checkRow.appendChild(cb);
                checkRow.appendChild(span);
                wrapper.appendChild(checkRow);

                // When host is edited, uncheck the private flag immediately
                hostInput.addEventListener('input', () => {
                    if (cb.checked) {
                        cb.checked = false;
                        if (window.currentConfig) window.currentConfig.mempool_is_private = false;
                        cb.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                });
                // Sync checkbox to currentConfig
                cb.addEventListener('change', () => {
                    if (window.currentConfig) window.currentConfig.mempool_is_private = cb.checked;
                });

                // Tor mode changes what belongs in this field, so keep the
                // placeholder and hint in step with the toggle.
                hostInput.id = 'mempool-host-input';
                _applyTorHostHint(hostInput, !!(currentConfig && currentConfig.mempool_use_tor));

                input = wrapper;
            }

            // WebSocket relay URL — add a "Test" button that opens a WS connection
            if (key === 'webhook_relay_ws_url') {
                const wsInput = input;
                wsInput.style.flex = '1';
                wsInput.style.minWidth = '0';

                const wrapper = document.createElement('div');
                wrapper.style.cssText = 'display:flex;gap:8px;align-items:center';
                wrapper.appendChild(wsInput);
                wrapper.getValue = () => wsInput.value;
                Object.defineProperty(wrapper, 'value', {
                    get: () => wsInput.value,
                    set: (v) => { wsInput.value = v; }
                });

                const testBtn = document.createElement('button');
                testBtn.type = 'button';
                testBtn.className = 'mempool-action-btn';
                testBtn.textContent = window.translations?.check_relay_connection || 'Check Relay Connection';
                testBtn.style.flexShrink = '0';

                testBtn.addEventListener('click', () => {
                    const url = wsInput.value.trim();
                    if (!url) {
                        _buildLiveToast([_mpaIcon('error', '#ef4444', 15), 'No URL'], ['Enter a WebSocket URL first.'], '#ef4444', 5000);
                        return;
                    }
                    const origLabel = testBtn.textContent;
                    testBtn.style.width = testBtn.offsetWidth + 'px';
                    testBtn.disabled = true;
                    testBtn.innerHTML = `${window.translations?.checking || 'Checking'}<span class="mpa-dots"></span>`;

                    const _t = window.translations || {};
                    let ws, done = false;
                    const finish = (ok, msg) => {
                        if (done) return;
                        done = true;
                        try { if (ws) ws.close(); } catch (_) {}
                        clearTimeout(timer);
                        testBtn.disabled = false;
                        testBtn.textContent = origLabel;
                        testBtn.style.width = '';
                        const color = ok ? '#22c55e' : '#ef4444';
                        _buildLiveToast(
                            [_mpaIcon(ok ? 'check' : 'error', color, 15),
                                ok ? (_t.relay_connected || 'Relay Connected') : (_t.relay_unreachable || 'Relay Unreachable')],
                            [msg], color, 8000
                        );
                    };
                    const timer = setTimeout(() => finish(false, _t.relay_connection_timeout || 'Connection timed out after 8 s'), 8000);
                    try {
                        ws = new WebSocket(url);
                        ws.onopen  = () => finish(true,  _t.relay_handshake_ok || 'WebSocket handshake successful.');
                        ws.onerror = () => finish(false, _t.relay_connection_refused || 'Connection refused or handshake failed.');
                    } catch (e) {
                        finish(false, e.message || (_t.relay_invalid_url || 'Invalid WebSocket URL.'));
                    }
                });

                wrapper.appendChild(testBtn);
                input = wrapper;
            }
            break;

        case 'password':
            if (key === 'admin_password' || key === 'mempool_password') {
                // Use dedicated change-password workflow (button + new/confirm validation).
                input = createPasswordChangeInterface(key, field);
            } else {
                // Regular password field
                input = document.createElement('input');
                input.type = 'password';
                input.className = 'form-input';
                input.value = value !== undefined && value !== null ? value : '';
                input.placeholder = field.placeholder || '';
                input.autocomplete = 'new-password';
            }
            break;
            
        case 'number':
            input = document.createElement('input');
            input.type = 'number';
            input.className = 'form-input';
            // Fall back to the schema's own default rather than leaving the
            // box empty: an empty box was collected as 0, which for a field
            // whose range excludes 0 was rejected on save, so the key stayed
            // missing and the box stayed empty - a loop that never settled.
            input.value = value !== undefined && value !== null
                ? value
                : (field.default !== undefined ? field.default : '');
            input.min = field.min || '';
            input.max = field.max || '';
            break;

        case 'time':
            input = document.createElement('input');
            input.type = 'time';
            input.className = 'form-input';
            input.value = value !== undefined && value !== null ? value : '';
            input.title = window.translations?.time_picker_tooltip || 'Select time';
            if (key === 'auto_update_time') {
                input.addEventListener('change', () => _checkRebootWindowConflict(input));
                setTimeout(() => _checkRebootWindowConflict(input), 0);
            }
            break;

        case 'select':
            // Check if this select has HTML flags (like language selector)
            const hasHtmlFlags = field.options.some(option => option.flag && option.flag.includes('<img'));
            
            if (hasHtmlFlags) {
                // Create custom select for HTML content
                input = createCustomSelect(field, value);
            } else {
                // Standard select for simple options
                input = document.createElement('select');
                input.className = 'form-select';
                field.options.forEach(option => {
                    const optionEl = document.createElement('option');
                    optionEl.value = option.value;
                    
                    if (option.flag) {
                        optionEl.textContent = `${option.flag} ${option.label}`;
                    } else {
                        optionEl.textContent = option.label;
                    }
                    
                    if (value === option.value) optionEl.selected = true;
                    input.appendChild(optionEl);
                });
            }

            if (field.disabled) input.disabled = true;

            // Special handling for language changes - remove immediate modal, save for later
            if (key === 'language') {
                input.addEventListener('change', (e) => {
                    const newLanguage = e.target.value;

                    if (newLanguage !== currentConfig.language) {
                        pendingLanguageChange = newLanguage;
                    } else {
                        pendingLanguageChange = null;
                    }
                    // Apply translations immediately — no page reload needed
                    window._pendingLanguage = newLanguage;
                    setLanguage(newLanguage);
                });
            }
            break;
            
        case 'color_select':
            input = createColorSelect(value);
            break;
            
        case 'color':
            input = createColorInput(value);
            break;

        case 'date_color_group':
            input = createDateColorGroup();
            break;

        case 'holiday_color_group':
            input = createHolidayColorGroup();
            break;

        case 'block_height_color_group':
            input = createBlockHeightColorGroup();
            break;
            
        case 'boolean':
            input = createBooleanSwitch(value);
            // Add dark mode listener if this is the dark mode toggle
            if (key === 'color_mode_dark') {
                const switchEl = input.querySelector('.switch');
                if (switchEl) {
                    switchEl.addEventListener('click', () => {
                        // Use setTimeout to ensure the toggle has updated
                        setTimeout(() => {
                            const isDarkMode = switchEl.classList.contains('active');
                            applyDarkMode(isDarkMode);
                        }, 10);
                    });
                }
            }
            break;
            
        case 'toggle':
            input = createToggleGroup(field.options, value);
            if (key === 'color_mode_dark') {
                input.querySelectorAll('.toggle-option').forEach(btn => {
                    btn.addEventListener('click', () => {
                        setTimeout(() => { applyDarkMode(input.getValue()); }, 10);
                    });
                });
            }
            break;
            
        case 'tags':
            input = createTagsInput(value || [], field.placeholder);
            break;
            
        case 'wallet_table':
            input = createWalletTableInput(value || [], field);
            break;
            
        case 'bitaxe_table':
            input = createBitaxeTableInput(value || [], field);
            break;
            
        case 'block_reward_table':
            input = createBlockRewardTableInput(value || [], field);
            break;
            
        case 'meme_management':
            input = createMemeManagementInterface(field);
            break;

        case 'opsec_management':
            input = createOpsecManagementInterface(field);
            break;

        case 'donation_history':
            input = createDonationHistoryInterface();
            break;

        case 'tang_check': {
            const row = document.createElement('div');
            row.className = 'mempool-action-row';

            const tangBtn = document.createElement('button');
            tangBtn.type = 'button';
            tangBtn.className = 'mempool-action-btn';
            tangBtn.textContent = field.label_check || 'Check Tang Connection';
            tangBtn.addEventListener('click', () => {
                // Test what is currently in the form rather than what was last
                // saved, so a value can be verified before committing to it.
                const urlEl = document.querySelector('[data-config-key="tang_url"]');
                const thpEl = document.querySelector('[data-config-key="tang_thumbprint"]');
                const url = (urlEl && urlEl.value || '').trim();
                const thp = (thpEl && thpEl.value || '').trim();

                const originalLabel = tangBtn.textContent;
                tangBtn.style.width = tangBtn.offsetWidth + 'px';
                tangBtn.disabled = true;
                tangBtn.innerHTML = `Checking<span class="mpa-dots"></span>`;

                const qs = new URLSearchParams();
                if (url) qs.set('url', url);
                if (thp) qs.set('thumbprint', thp);

                fetch('/api/tang/validate?' + qs.toString())
                    .then(r => r.ok ? r.json() : Promise.reject(r.status))
                    .then(data => {
                        const checks = data.checks || [];
                        const allOk = checks.length > 0 && checks.every(c => c.ok);
                        const accentColor = allOk ? '#22c55e' : '#ef4444';
                        const body = document.createDocumentFragment();

                        checks.forEach(c => {
                            const line = document.createElement('div');
                            line.style.cssText = 'display:flex;gap:8px;align-items:center;padding:2px 0;';
                            const icon = _mpaIcon(c.ok ? 'check' : 'error', c.ok ? '#22c55e' : '#ef4444', 13);
                            if (icon) line.appendChild(icon);
                            const name = document.createElement('span');
                            name.style.fontSize = '11px';
                            name.textContent = c.name;
                            line.appendChild(name);
                            body.appendChild(line);
                        });

                        // Nothing pinned yet: offer the value instead of making
                        // the operator read it off the server by hand.
                        const pinned = checks.some(c => c.key === 'thumbprint_pinned' && !c.ok);
                        if (pinned && data.suggested_thumbprint && thpEl) {
                            const fillBtn = document.createElement('button');
                            fillBtn.type = 'button';
                            fillBtn.textContent = (window.translations || {}).tang_use_thumbprint || 'Use this server’s thumbprint';
                            fillBtn.style.cssText = 'margin-top:8px;width:100%;padding:5px 10px;background:transparent;'
                                + 'border:1px solid rgba(128,128,128,0.3);border-radius:6px;color:inherit;cursor:pointer;'
                                + 'font-size:11px;font-family:inherit;';
                            fillBtn.addEventListener('click', e => {
                                e.stopPropagation();
                                thpEl.value = data.suggested_thumbprint;
                                thpEl.dispatchEvent(new Event('input', { bubbles: true }));
                                fillBtn.textContent = 'Filled in — remember to save';
                                fillBtn.disabled = true;
                            });
                            body.appendChild(fillBtn);
                        }

                        const logBtn = document.createElement('button');
                        logBtn.type = 'button';
                        logBtn.textContent = 'Open Log';
                        logBtn.style.cssText = 'margin-top:8px;width:100%;padding:5px 10px;background:transparent;'
                            + 'border:1px solid rgba(128,128,128,0.3);border-radius:6px;color:inherit;cursor:pointer;'
                            + 'font-size:11px;font-family:inherit;';
                        logBtn.addEventListener('click', e => {
                            e.stopPropagation();
                            _mpaShowLogModal(checks, (window.translations || {}).tang_connection_log || 'Tang Connection Log');
                        });
                        logBtn.addEventListener('mouseenter', () => {
                            logBtn.style.borderColor = accentColor;
                            logBtn.style.color = accentColor;
                        });
                        logBtn.addEventListener('mouseleave', () => {
                            logBtn.style.borderColor = 'rgba(128,128,128,0.3)';
                            logBtn.style.color = 'inherit';
                        });
                        body.appendChild(logBtn);

                        _buildLiveToast(
                            [_mpaIcon(allOk ? 'check' : 'error', accentColor, 15),
                             allOk ? 'Tang — All OK' : 'Tang — Issues Found'],
                            body, accentColor, 15000);
                    })
                    .catch(() => {
                        _buildLiveToast(
                            [_mpaIcon('error', '#ef4444', 15), 'Tang Check Failed'],
                            ['Could not reach the server.'], '#ef4444', 30000);
                    })
                    .finally(() => {
                        tangBtn.disabled = false;
                        tangBtn.textContent = originalLabel;
                        tangBtn.style.width = '';
                    });
            });

            row.appendChild(tangBtn);
            row.getValue = () => null;
            input = row;
            break;
        }
        // _mempool_actions declares label_check and label_open, which is what
        // this case builds. It used to fall through into 'tang_check' instead,
        // so the mempool button queried /api/tang/validate and reported on
        // clevis - on a device with Tang switched off entirely.
        case 'mempool_actions':
        case 'connection_check':
        case 'open_url_button': {
            const row = document.createElement('div');
            row.className = 'mempool-action-row';

            // Check Connection button
            const checkBtn = document.createElement('button');
            checkBtn.type = 'button';
            checkBtn.className = 'mempool-action-btn';
            checkBtn.textContent = field.label_check || field.label || 'Check Connection';
            checkBtn.addEventListener('click', () => {
                const originalLabel = checkBtn.textContent;
                checkBtn.style.width = checkBtn.offsetWidth + 'px';
                checkBtn.disabled = true;
                checkBtn.innerHTML = `Checking<span class="mpa-dots"></span>`;

                fetch('/api/mempool/validate')
                    .then(r => r.ok ? r.json() : Promise.reject(r.status))
                    .then(data => {
                        const allOk = data.checks.every(c => c.ok);
                        const accentColor = allOk ? '#22c55e' : '#ef4444';
                        const titleIcon = _mpaIcon(allOk ? 'check' : 'error', accentColor, 15);

                        const body = document.createDocumentFragment();
                        data.checks.forEach(c => {
                            const line = document.createElement('div');
                            line.style.cssText = 'display:flex;gap:8px;align-items:center;padding:2px 0;';
                            const icon = _mpaIcon(c.ok ? 'check' : 'error', c.ok ? '#22c55e' : '#ef4444', 13);
                            if (icon) line.appendChild(icon);
                            const name = document.createElement('span');
                            name.style.fontSize = '11px';
                            name.textContent = c.name;
                            line.appendChild(name);
                            body.appendChild(line);
                        });

                        const logBtn = document.createElement('button');
                        logBtn.type = 'button';
                        logBtn.textContent = 'Open Log';
                        logBtn.style.cssText = 'margin-top:8px;width:100%;padding:5px 10px;background:transparent;' +
                            'border:1px solid rgba(128,128,128,0.3);border-radius:6px;color:inherit;cursor:pointer;' +
                            'font-size:11px;font-family:inherit;';
                        logBtn.addEventListener('click', e => {
                            // The toast closes on any click inside it - keep this one for the modal
                            e.stopPropagation();
                            _mpaShowLogModal(data.checks, (window.translations || {}).mempool_connection_log || 'Mempool Connection Log');
                        });
                        logBtn.addEventListener('mouseenter', () => {
                            logBtn.style.borderColor = accentColor;
                            logBtn.style.color = accentColor;
                        });
                        logBtn.addEventListener('mouseleave', () => {
                            logBtn.style.borderColor = 'rgba(128,128,128,0.3)';
                            logBtn.style.color = 'inherit';
                        });
                        body.appendChild(logBtn);

                        _buildLiveToast(
                            [titleIcon, allOk ? 'Mempool — All OK' : 'Mempool — Issues Found'],
                            body, accentColor, 15000
                        );
                    })
                    .catch(() => {
                        _buildLiveToast(
                            [_mpaIcon('error', '#ef4444', 15), 'Mempool Check Failed'],
                            ['Could not reach the server.'], '#ef4444', 30000
                        );
                    })
                    .finally(() => {
                        checkBtn.disabled = false;
                        checkBtn.textContent = originalLabel;
                        checkBtn.style.width = '';
                    });
            });

            // Open Mempool link
            const openBtn = document.createElement('a');
            openBtn.className = 'mempool-action-btn';
            openBtn.target = '_blank';
            openBtn.rel = 'noopener noreferrer';
            openBtn.textContent = field.label_open || field.label || 'Open Mempool';
            openBtn.addEventListener('click', () => {
                const hostEl = document.querySelector('[data-config-key="mempool_host"]');
                const httpsEl = document.querySelector('[data-config-key="mempool_use_https"]');
                const host = (hostEl && hostEl.value.trim()) || (window.currentConfig || {})['mempool_host'] || '127.0.0.1';
                const useHttps = httpsEl && typeof httpsEl.getValue === 'function'
                    ? httpsEl.getValue()
                    : !!(window.currentConfig || {})['mempool_use_https'];
                openBtn.href = `${useHttps ? 'https' : 'http'}://${sanitizeHost(host)}`;
            });

            row.appendChild(checkBtn);
            row.appendChild(openBtn);
            row.getValue = () => null;
            input = row;
            break;
        }

        case 'info_text': {
            const infoBox = document.createElement('div');
            infoBox.className = 'form-info-box';
            const _rebuildInfoBox = () => {
                const h = field._html_builder
                    ? _buildInfoHtml(field._html_builder, window.translations || {})
                    : (field.html || field.text || '');
                infoBox.innerHTML = h.replace(/\{BASE_URL\}/g, window.location.origin);
            };
            _rebuildInfoBox();
            // For donation_webhook: fetch LAN IP once and re-render to show the IP-based URL
            if (field._html_builder === 'donation_webhook' && !window._mpaLanIp) {
                fetch('/api/system/lan-ip')
                    .then(r => r.ok ? r.json() : null)
                    .then(d => { if (d?.success && d.ip) { window._mpaLanIp = d.ip; _rebuildInfoBox(); } })
                    .catch(() => {});
            }
            // Not a config value — excluded from saves
            infoBox.getValue = () => null;
            input = infoBox;
            break;
        }

        case 'multiselect': {
            const msContainer = document.createElement('div');
            msContainer.className = 'multiselect-buttons';
            const selected = new Set(Array.isArray(value) ? value : (field.default || []));
            field.options.forEach(option => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'multiselect-btn' + (selected.has(option.value) ? ' active' : '');
                btn.textContent = option.label;
                btn.dataset.value = option.value;
                btn.addEventListener('click', () => btn.classList.toggle('active'));
                msContainer.appendChild(btn);
            });
            msContainer.getValue = () => {
                return Array.from(msContainer.querySelectorAll('.multiselect-btn.active'))
                    .map(b => b.dataset.value);
            };
            input = msContainer;
            break;
        }

        case 'hidden':
            // Create hidden input; hide the whole row so no empty label/description gap shows
            formGroup.style.display = 'none';
            input = document.createElement('input');
            input.type = 'hidden';
            input.value = value !== undefined && value !== null ? value : '';
            break;
            
        case 'hidden_boolean':
            // Rendered inline by another field (e.g. mempool_is_private inside mempool_host)
            formGroup.style.display = 'none';
            input = document.createElement('span');
            break;

        default:
            // Fallback for unknown field types
            input = document.createElement('input');
            input.type = 'text';
            input.className = 'form-input';
            input.value = value !== undefined && value !== null ? value : '';
            console.warn(`Unknown field type: ${field.type} for field ${key}`);
            break;
    }
    
    if (input) {
        // Ensure the input has the data-config-key attribute for form collection
        // (skip for composite widgets and hidden_boolean fields managed inline by another field)
        if (field.type !== 'date_color_group' && field.type !== 'holiday_color_group' && field.type !== 'block_height_color_group' && field.type !== 'hidden_boolean' && field.type !== 'open_url_button' && field.type !== 'info_text' && field.type !== 'connection_check' && field.type !== 'mempool_actions' && field.type !== 'tang_check') {
            if (input.dataset) {
                input.dataset.configKey = key;
            } else {
                input.setAttribute('data-config-key', key);
            }
        }
    } else {
        console.warn(`Failed to create input for field ${key} of type ${field.type}`);
        // Create a fallback input
        input = document.createElement('input');
        input.type = 'text';
        input.className = 'form-input';
        input.value = value !== undefined && value !== null ? value : '';
        input.dataset.configKey = key;
    }
    
    // Associate the native input with the label via id
    if (input && !skipLabel) {
        // Always look for a native control inside first (handles color picker containers etc.)
        const inner = input.querySelector && input.querySelector('input, select, textarea');
        if (inner) {
            if (!inner.id) inner.id = fieldId;
        } else if (!input.id) {
            input.id = fieldId;
        }
    }

    formGroup.appendChild(input);

    // Long opaque values are visual noise in a settings form. Reuse the same
    // overlay the wallet tables use: a shortened preview at rest, the real
    // value on focus. Applied after appendChild because the overlay inserts a
    // wrapper around the element and needs it to already have a parent.
    if (field.masked && input.tagName === 'INPUT'
        && typeof _addAddressMaskOverlay === 'function') {
        _addAddressMaskOverlay(input);
    }

    if (field.description) {
        const description = document.createElement('div');
        description.className = 'form-description';
        description.innerHTML = field.description;
        formGroup.appendChild(description);
    }

    return formGroup;
}


function createColorInput(value) {
    const container = document.createElement('div');
    container.className = 'color-input-container';
    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.gap = '10px';

    const colorInput = document.createElement('input');
    colorInput.type = 'color';
    colorInput.value = value || '#000000';
    colorInput.className = 'form-color-picker';
    colorInput.style.height = '40px';
    colorInput.style.width = '60px';
    colorInput.style.cursor = 'pointer';
    colorInput.style.padding = '0';
    colorInput.style.border = '1px solid #ddd';
    colorInput.style.borderRadius = '4px';

    const textInput = document.createElement('input');
    textInput.type = 'text';
    textInput.value = value || '#000000';
    textInput.className = 'form-input';
    textInput.style.width = '100px';
    textInput.placeholder = '#RRGGBB';

    // Sync inputs
    colorInput.addEventListener('input', () => {
        textInput.value = colorInput.value.toUpperCase();
        _validateInput(textInput, _RE_HEX_COLOR, false);
    });

    textInput.addEventListener('input', () => {
        const val = textInput.value;
        _validateInput(textInput, _RE_HEX_COLOR, false);
        if (_RE_HEX_COLOR.test(val)) {
            colorInput.value = val;
        }
    });
    _trimOnBlur(textInput);

    // Wrap text input in a column so the error message renders below it
    const textWrapper = document.createElement('div');
    textWrapper.style.cssText = 'display:flex;flex-direction:column;';
    textWrapper.appendChild(textInput);

    container.appendChild(colorInput);
    container.appendChild(textWrapper);
    
    // Config collector uses getValue() if available
    container.getValue = function() {
        return textInput.value;
    };

    return container;
}


function _formatSpecificDate(date, lang) {
    try {
        if (lang === 'en') {
            const day = date.getDate();
            const v = day % 100;
            const suffix = (v >= 11 && v <= 13) ? 'th' : (['th','st','nd','rd'][day % 10] || 'th');
            const month = date.toLocaleString('en-US', { month: 'long' });
            return `${month} ${day}${suffix}, ${date.getFullYear()}`;
        }
        const localeMap = { de: 'de', es: 'es', fr: 'fr', it: 'it' };
        const locale = localeMap[lang] || 'en';
        return new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', year: 'numeric' }).format(date);
    } catch (e) {
        return date.toISOString().slice(0, 10);
    }
}

function _formatDateForPreview(lang) {
    return _formatSpecificDate(new Date(), lang);
}

// Returns {dateStr, title} for today's holiday, or Bitcoin Whitepaper Day (Oct 31, current year) as fallback.
// btcHolidays shape from backend: {"MM-DD": {"en": "Title", "de": "...", ...}, ...}
function _getHolidayPreview(lang) {
    const today = new Date();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    const key = mm + '-' + dd;
    const holidays = window.btcHolidays || {};
    if (holidays[key]) {
        const entry = holidays[key];
        const title = entry[lang] || entry['en'] || Object.values(entry)[0] || '';
        return { dateStr: _formatSpecificDate(today, lang), title, isToday: true };
    }
    const fb = holidays['10-31'] || {};
    return {
        dateStr: _formatSpecificDate(new Date(new Date().getFullYear(), 9, 31), lang),
        title: fb[lang] || fb['en'] || 'Bitcoin Whitepaper Day',
        isToday: false,
    };
}
