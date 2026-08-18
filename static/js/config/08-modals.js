// Meme and OPSec modals, and the config WebSocket connection.
// Part 8 of 8, split from config.js. Load order matters:
// these run as classic scripts sharing one global scope.

// --- OPSec Modal Functions ---
let currentModalOpsec = null;
let opsecToDelete = null;

function openOpsecModal(filename, url) {
    currentModalOpsec = { filename, url };

    const modalTitle = document.getElementById('opsec-modal-title');
    const modalImage = document.getElementById('opsec-modal-image');
    const modalDimensions = document.getElementById('opsec-modal-dimensions');
    const modalFilesize = document.getElementById('opsec-modal-filesize');
    const opsecModal = document.getElementById('opsec-modal');

    if (modalTitle) {
        const previewText = window.translations?.opsec_image_preview || 'OPSec Image Preview';
        modalTitle.textContent = `${previewText} - ${filename}`;
    }

    const modalFilenameDisplay = document.getElementById('opsec-modal-filename-display');
    if (modalFilenameDisplay) {
        modalFilenameDisplay.textContent = filename;
    }

    // Reset rename UI to display mode
    const filenameInput = document.getElementById('opsec-modal-filename-input');
    const editBtn = document.getElementById('opsec-modal-edit-btn');
    const saveBtn = document.getElementById('opsec-modal-save-btn');
    const cancelBtn = document.getElementById('opsec-modal-cancel-rename-btn');
    const renameActionsReset = document.getElementById('opsec-rename-actions');

    if (modalFilenameDisplay) modalFilenameDisplay.style.display = 'inline';
    if (editBtn) editBtn.style.display = 'inline-block';
    if (filenameInput) filenameInput.style.display = 'none';
    if (renameActionsReset) renameActionsReset.style.display = 'none';
    // Clear any stale inline display so buttons are visible when wrapper is shown
    if (saveBtn) { saveBtn.style.display = ''; saveBtn.disabled = false; saveBtn.classList.remove('rename-dirty', 'rename-clean'); }
    if (cancelBtn) cancelBtn.style.display = '';

    if (modalDimensions) {
        modalDimensions.textContent = window.translations?.loading || 'Loading...';
    }
    if (modalFilesize) {
        modalFilesize.textContent = window.translations?.loading || 'Loading...';
    }

    if (modalImage) {
        modalImage.onload = function() {
            if (modalDimensions) {
                modalDimensions.textContent = `${this.naturalWidth} × ${this.naturalHeight} px`;
            }
        };
        modalImage.onerror = function() {
            if (modalDimensions) {
                modalDimensions.textContent = 'Error loading image';
            }
        };
        modalImage.src = url;
    }

    if (opsecModal) {
        opsecModal.style.display = 'flex';
    }

    // Fetch file size
    fetch(url, { method: 'HEAD' })
        .then(response => {
            const contentLength = response.headers.get('content-length');
            const sizeEl = document.getElementById('opsec-modal-filesize');
            if (!sizeEl) return;
            if (contentLength) {
                sizeEl.textContent = formatFileSize(parseInt(contentLength));
            } else {
                return fetch(url, { method: 'GET', headers: { 'Range': 'bytes=0-1' } })
                    .then(r => {
                        const contentRange = r.headers.get('content-range');
                        if (contentRange) {
                            const match = contentRange.match(/\/(\d+)$/);
                            if (match) { sizeEl.textContent = formatFileSize(parseInt(match[1])); return; }
                        }
                        sizeEl.textContent = 'Unknown';
                    })
                    .catch(() => { sizeEl.textContent = 'Unknown'; });
            }
        })
        .catch(() => {
            const sizeEl = document.getElementById('opsec-modal-filesize');
            if (sizeEl) sizeEl.textContent = 'Unknown';
        });
}

function startRenameInOpsecModal() {
    if (!currentModalOpsec) return;

    const filenameDisplay = document.getElementById('opsec-modal-filename-display');
    const filenameInput = document.getElementById('opsec-modal-filename-input');
    const editBtn = document.getElementById('opsec-modal-edit-btn');
    const saveBtn = document.getElementById('opsec-modal-save-btn');
    const cancelBtn = document.getElementById('opsec-modal-cancel-rename-btn');
    const renameActions = document.getElementById('opsec-rename-actions');

    if (!filenameDisplay || !filenameInput || !editBtn || !saveBtn || !cancelBtn) return;

    const filename = currentModalOpsec.filename;
    const nameWithoutExt = filename.substring(0, filename.lastIndexOf('.'));

    filenameDisplay.style.display = 'none';
    editBtn.style.display = 'none';
    filenameInput.style.display = 'inline-block';
    if (renameActions) renameActions.style.display = 'flex';

    filenameInput.value = nameWithoutExt;
    filenameInput.focus();
    filenameInput.select();

    const _opsecOriginal = nameWithoutExt.trim();
    const validateOpsecInput = () => {
        const val = filenameInput.value.trim();
        const unchanged = val === _opsecOriginal;
        if (!val || unchanged) {
            saveBtn.disabled = true;
            saveBtn.classList.remove('rename-dirty');
            saveBtn.classList.add('rename-clean');
        } else {
            saveBtn.disabled = false;
            saveBtn.classList.remove('rename-clean');
            saveBtn.classList.add('rename-dirty');
        }
    };

    filenameInput._opsecValidate && filenameInput.removeEventListener('input', filenameInput._opsecValidate);
    filenameInput._opsecValidate = validateOpsecInput;
    filenameInput.addEventListener('input', validateOpsecInput);
    validateOpsecInput();

    filenameInput.onkeydown = (e) => {
        if (e.key === 'Enter') saveRenameInOpsecModal();
        else if (e.key === 'Escape') cancelRenameInOpsecModal();
    };
}

async function saveRenameInOpsecModal() {
    if (!currentModalOpsec) return;

    const filenameInput = document.getElementById('opsec-modal-filename-input');
    if (!filenameInput) return;

    const oldFilename = currentModalOpsec.filename;
    const extension = oldFilename.substring(oldFilename.lastIndexOf('.'));
    const nameWithoutExt = oldFilename.substring(0, oldFilename.lastIndexOf('.'));
    const newName = filenameInput.value.trim();

    if (!newName) {
        showNotification(window.translations?.please_enter_valid_name || 'Please enter a valid name', 'error');
        return;
    }

    if (newName === nameWithoutExt) {
        cancelRenameInOpsecModal();
        return;
    }

    const newFilename = newName + extension;
    await renameOpsecImage(oldFilename, newFilename);

    // Update modal with new filename
    currentModalOpsec.filename = newFilename;
    currentModalOpsec.url = assetUrl('/static/opsec/', newFilename);

    const filenameDisplay = document.getElementById('opsec-modal-filename-display');
    const modalTitle = document.getElementById('opsec-modal-title');
    if (filenameDisplay) filenameDisplay.textContent = newFilename;
    if (modalTitle) {
        const previewText = window.translations?.opsec_image_preview || 'OPSec Image Preview';
        modalTitle.textContent = `${previewText} - ${newFilename}`;
    }

    cancelRenameInOpsecModal();
}

function cancelRenameInOpsecModal() {
    const filenameDisplay = document.getElementById('opsec-modal-filename-display');
    const filenameInput = document.getElementById('opsec-modal-filename-input');
    const editBtn = document.getElementById('opsec-modal-edit-btn');
    const saveBtn = document.getElementById('opsec-modal-save-btn');
    const cancelBtn = document.getElementById('opsec-modal-cancel-rename-btn');
    const renameActions = document.getElementById('opsec-rename-actions');

    if (!filenameDisplay || !filenameInput || !editBtn || !saveBtn || !cancelBtn) return;

    filenameDisplay.style.display = 'inline';
    editBtn.style.display = 'inline-block';
    filenameInput.style.display = 'none';
    if (renameActions) renameActions.style.display = 'none';
    saveBtn.disabled = false;
    saveBtn.classList.remove('rename-dirty', 'rename-clean');
}

async function renameOpsecImage(oldFilename, newFilename) {
    try {
        const response = await fetch('/api/rename-opsec', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ old_filename: oldFilename, new_filename: newFilename })
        });
        const result = await response.json();
        if (result.success) {
            showNotification(window.translations?.opsec_image_renamed_successfully || 'OPSec image renamed successfully', 'success');
            // Update thumbnail in the grid
            const img = document.querySelector(`#opsec-images-list img[data-filename="${oldFilename}"]`);
            if (img) {
                img.dataset.filename = newFilename;
                img.src = assetUrl('/static/opsec/', newFilename);
                img.title = newFilename;
                const thumb = img.closest('.meme-thumbnail');
                if (thumb) {
                    const nameEl = thumb.querySelector('.meme-filename');
                    if (nameEl) nameEl.textContent = newFilename;
                    // Update action buttons to use new filename
                    const actionsDiv = thumb.querySelector('.meme-actions');
                    if (actionsDiv) {
                        actionsDiv.replaceChildren(
                            buildActionButton('download', window.translations?.download_meme || 'Download', '',
                                () => downloadOpsecImage(newFilename)),
                            buildActionButton('delete', window.translations?.delete_meme || 'Delete', 'delete',
                                () => showOpsecDeleteModal(newFilename))
                        );
                    }
                    // Update onclick to use new filename
                    img.onclick = () => openOpsecModal(newFilename, assetUrl('/static/opsec/', newFilename));
                }
            }
        } else {
            showNotification(result.message || window.translations?.opsec_image_rename_failed || 'Failed to rename OPSec image', 'error');
        }
    } catch (error) {
        showNotification((window.translations?.opsec_image_rename_failed || 'Failed to rename OPSec image') + ': ' + error.message, 'error');
    }
}

function downloadOpsecFromModal() {
    if (currentModalOpsec) {
        const a = document.createElement('a');
        a.href = assetUrl('/api/download-opsec/', currentModalOpsec.filename);
        a.download = currentModalOpsec.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
}

function deleteOpsecFromModal() {
    if (currentModalOpsec) {
        closeOpsecModal();
        showOpsecDeleteModal(currentModalOpsec.filename);
    }
}

function showOpsecDeleteModal(filename) {
    opsecToDelete = filename;
    const modal = document.getElementById('opsec-delete-modal');
    if (modal) modal.style.display = 'flex';
}

function hideOpsecDeleteModal() {
    opsecToDelete = null;
    const modal = document.getElementById('opsec-delete-modal');
    if (modal) modal.style.display = 'none';
}

// Wire up opsec delete modal buttons
document.addEventListener('DOMContentLoaded', () => {
    const opsecConfirmDelete = document.getElementById('opsec-confirm-delete');
    const opsecCancelDelete = document.getElementById('opsec-cancel-delete');
    if (opsecConfirmDelete) {
        opsecConfirmDelete.addEventListener('click', async () => {
            if (opsecToDelete) {
                await deleteOpsecImage(opsecToDelete);
                hideOpsecDeleteModal();
            }
        });
    }
    if (opsecCancelDelete) {
        opsecCancelDelete.addEventListener('click', hideOpsecDeleteModal);
    }

    // Close opsec modal when clicking outside
    const opsecModal = document.getElementById('opsec-modal');
    if (opsecModal) {
        opsecModal.addEventListener('click', function(event) {
            if (event.target === this) closeOpsecModal();
        });
    }
});

// Load cached wallet balances for display in config table
async function loadCachedWalletBalances(tbody) {
    try {
        let walletEntries = [];
        const rows = tbody.querySelectorAll('tr');
        
        // First check if we have config data with cached balances
        const configToUse = window.currentConfig || currentConfig;
        if (configToUse && configToUse.wallet_balance_addresses_with_comments) {
            const configEntries = configToUse.wallet_balance_addresses_with_comments;
            configEntries.forEach(entry => {
                if (entry.address) {
                    walletEntries.push({
                        address: entry.address,
                        comment: entry.comment || '',
                        type: detectAddressType(entry.address),
                        cached_balance: entry.cached_balance || 0.0  // Use cached balance from config
                    });
                }
            });
            
        } else {
            // Fallback: Try to get wallet entries from form inputs
            rows.forEach((row, index) => {
                const addressInput = row.querySelector('.wallet-address-input');
                const commentInput = row.querySelector('.wallet-comment-input');
                const address = addressInput ? addressInput.value.trim() : '';
                const comment = commentInput ? commentInput.value.trim() : '';
                 
                if (address) {
                    walletEntries.push({
                        address: address,
                        comment: comment,
                        type: detectAddressType(address)
                    });
                }
            });
        }
        
        // If no entries from either source, try fallback API
        if (walletEntries.length === 0) {
            
            try {
                const testResponse = await fetch('/api/test-wallet-config');
                if (testResponse.ok) {
                    const testData = await testResponse.json();
                    
                    if (testData.success && testData.wallet_addresses_from_regular_config) {
                        const apiEntries = testData.wallet_addresses_from_regular_config;
                        apiEntries.forEach(entry => {
                            if (entry.address) {
                                walletEntries.push({
                                    address: entry.address,
                                    comment: entry.comment || '',
                                    type: detectAddressType(entry.address)
                                });
                            }
                        });
                    }
                }
            } catch (apiError) {
                console.error('Test API error:', apiError);
            }
        }
        
        if (walletEntries.length === 0) {
            return;
        }
         
        // Check if we already have cached balances in the config
        const hasBalancesInConfig = walletEntries.some(entry => entry.cached_balance !== undefined);
        
        if (hasBalancesInConfig) {
            // Use cached balances directly from config
            await updateWalletTableWithEntries(tbody, walletEntries);
        } else {
            // Fetch balances from API
            await fetchAndUpdateBalances(tbody, walletEntries);
        }
        
    } catch (error) {
        console.error('Error loading cached wallet balances:', error);
    }
}

// Helper function to update wallet table with entries (including balances)
async function updateWalletTableWithEntries(tbody, walletEntries) {
    let currentRows = tbody.querySelectorAll('tr');
    
    // Add more rows if needed
    while (currentRows.length < walletEntries.length) {
                addWalletTableRow(tbody, { address: '', comment: '', balance: 0 });
        currentRows = tbody.querySelectorAll('tr');
    }
    
    // Update each row with the corresponding data
    walletEntries.forEach((entry, index) => {
        if (index < currentRows.length) {
            const row = currentRows[index];
            
            // Update the form inputs with the entry data
            const addressInput = row.querySelector('.wallet-address-input');
            const commentInput = row.querySelector('.wallet-comment-input');
            if (addressInput && !addressInput.value) {
                addressInput.value = entry.address;
                if (addressInput._refreshAddressMask) addressInput._refreshAddressMask();
            }
            if (commentInput && !commentInput.value) {
                commentInput.value = entry.comment;
                            }
            
            // Update the balance display
            const balanceDisplay = row.querySelector('.wallet-balance-display');
            if (balanceDisplay) {
                const balance = entry.cached_balance || 0.0;
                _setWalletBalanceText(balanceDisplay, `${balance.toFixed(8)}`);
                balanceDisplay.style.color = 'var(--accent)';
                // Add styling to indicate cached data
                if (balance > 0) {
                    balanceDisplay.style.opacity = '0.8';
                    balanceDisplay.title = 'Cached balance data from configuration';
                }
            }
        }
    });
}

// Helper function to fetch balances from API and update table
async function fetchAndUpdateBalances(tbody, walletEntries) {
    // Call the cached wallet balance API with credentials
    const response = await fetch('/api/wallet_balance_cached', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin', // Include cookies for authentication
        body: JSON.stringify({ addresses: walletEntries })
    });
    
    if (response.ok) {
        const balanceData = await response.json();
        
        // Add balances to entries
        if (balanceData.balances) {
            walletEntries.forEach((entry, index) => {
                if (index < balanceData.balances.length) {
                    entry.cached_balance = balanceData.balances[index];
                }
            });
        }
        
        // Update table with entries including balances
        await updateWalletTableWithEntries(tbody, walletEntries);
    } else {
        const errorText = await response.text();
    
        // Still update table with entries (without balances)
        await updateWalletTableWithEntries(tbody, walletEntries);
    }
}

// showNotification is provided by toast.js (glass-card style)

// WebSocket connection for real-time updates
let configSocket = null;
let reconnectingConfig = false;
let reconnectTimeoutConfig = null;

function connectConfigSocket() {
    if (typeof io === 'undefined') return;
    configSocket = io();
    setupConfigSocketHandlers();
}

function setupConfigSocketHandlers() {
    configSocket.on('connect', () => {
        reconnectingConfig = false;
        // Register this page for notifications
        registerPageForNotifications('config');
        // Subscribe to block notifications (always enabled)
        subscribeToBlockNotifications();
        // Re-sync preview cards (price/network/countdown/halving/bitaxe/wallet/donation).
        // Covers reconnects that happen without a full page reload — e.g. a brief drop —
        // where stale or never-populated preview data would otherwise only catch up via
        // change-triggered push events (which may be far off, like the next new block).
        if (window._previewData) _fetchPreviewData(1);
        // Detect any restart (auto-update or manual) by comparing the server's
        // process start time against what was captured at page load.
        if (window._restartPending || window._pageLoadStarted !== undefined) {
            fetch('/api/health', { cache: 'no-store' })
                .then(r => r.ok ? r.json() : null)
                .then(h => {
                    if (!h) return;
                    const oldStarted = window._restartPending
                        ? window._restartPending.oldStarted
                        : window._pageLoadStarted;
                    if (oldStarted && h.started > oldStarted) {
                        const _tag = window._restartPending?.tag;
                        const _isReboot = !!(window._pageLoadBootId && h.boot_id && h.boot_id !== window._pageLoadBootId);
                        window._restartPending = null;
                        _reloadAfterRestart(_tag, _isReboot);
                    }
                })
                .catch(() => {});
        }
    });

    configSocket.on('disconnect', () => {
        attemptConfigReconnect();
    });

    configSocket.on('connect_error', (error) => {
        console.error('🚫 Config Socket.IO connection error:', error);
        attemptConfigReconnect();
    });

    configSocket.on('error', (error) => {
        console.error('⚠️ Config Socket.IO transport error:', error);
        attemptConfigReconnect();
    });

    // Listen for wallet balance updates
    configSocket.on('wallet_balance_updated', (data) => {
        if (window._suppressWalletUpdates) return;
        updateWalletBalancesFromWebSocket(data);
        // Update wallet preview card with new totals
        if (data && data.total_btc != null) {
            window._previewData.wallet = window._previewData.wallet || {};
            window._previewData.wallet.total_btc = data.total_btc;
            const price = window._previewData.price?.price;
            if (price) window._previewData.wallet.fiat_value = data.total_btc * price;
            if (window._refreshWalletPreview) window._refreshWalletPreview(window._previewData.wallet);
        }
    });

    // Listen for live price updates
    configSocket.on('price_stats_updated', (data) => {
        if (!data) return;
        window._previewData.price = { ...window._previewData.price, ...data };
        // Also update wallet fiat with fresh price
        if (window._previewData.wallet?.total_btc != null && data.price) {
            window._previewData.wallet.fiat_value = window._previewData.wallet.total_btc * data.price;
            if (window._refreshWalletPreview) window._refreshWalletPreview(window._previewData.wallet);
        }
        if (window._refreshPricePreview) window._refreshPricePreview(window._previewData.price);
    });

    // Listen for date rollover (midnight, holiday change)
    configSocket.on('date_changed', (data) => {
        if (window._refreshHolidayPreview) window._refreshHolidayPreview();
    });

    // Listen for countdown/halving updates (triggered by new blocks)
    configSocket.on('countdown_updated', (data) => {
        if (!data) return;
        if (data.countdown) {
            window._previewData.countdown = { ...window._previewData.countdown, ...data.countdown };
            if (window._refreshCountdownPreview) window._refreshCountdownPreview(window._previewData.countdown);
            // The tip travels on this event already, but the block-height
            // colour preview reads it from a different key. Mirror it across
            // and repaint, so the sample follows the chain rather than holding
            // whatever the page was opened with.
            if (data.countdown.block_height) {
                window._previewData.blockHeight = data.countdown.block_height;
                if (window._refreshBlockHeightPreview) window._refreshBlockHeightPreview();
            }
        }
        if (data.halving) {
            window._previewData.halving = { ...window._previewData.halving, ...data.halving };
            if (window._refreshHalvingPreview) window._refreshHalvingPreview(window._previewData.halving);
        }
    });

    // Listen for network hashrate/difficulty updates
    // Wheel rebuilds run for hours after an update reported success, so the
    // device would otherwise look idle while it compiles. One toast when it
    // starts, one when it ends; the per-package progress only updates the
    // running toast's body rather than stacking a new one for each.
    // A rebuild runs for hours, so it needs somewhere to be watched and somewhere
    // to be ignored. The toast is the ambient signal; the log modal below opens
    // from it, and closing the modal changes nothing about the run. Lines are
    // buffered so opening it late still shows what already happened.
    let _wheelToast = null;
    let _wheelLog = [];
    let _wheelProgress = { index: 0, total: 0, current: null };

    function _renderWheelProgress() {
        const modal = document.getElementById('wheel-rebuild-modal');
        if (!modal) return;
        const { index, total, current } = _wheelProgress;
        const pct = total ? Math.round((index / total) * 100) : 0;
        const fill = modal.querySelector('.wheel-progress-fill');
        const label = modal.querySelector('.wheel-progress-label');
        if (fill) fill.style.width = pct + '%';
        if (label) {
            const t = window.translations || {};
            label.textContent = `${index} / ${total} (${pct}%)`
                + (current ? ' \u2014 ' + current : '');
        }
    }

    function _appendWheelLog(line) {
        _wheelLog.push(line);
        if (_wheelLog.length > 200) _wheelLog = _wheelLog.slice(-200);
        const log = document.querySelector('#wheel-rebuild-modal .system-update-log');
        if (!log) return;
        // Follow the tail only while the reader has not scrolled away.
        const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 24;
        const el = document.createElement('div');
        el.textContent = line;
        log.appendChild(el);
        if (atBottom) log.scrollTop = log.scrollHeight;
    }

    function openWheelRebuildModal() {
        const t = window.translations || {};
        document.getElementById('wheel-rebuild-modal')?.remove();

        const overlay = document.createElement('div');
        overlay.id = 'wheel-rebuild-modal';
        overlay.className = 'modal';
        overlay.style.display = 'flex';

        const box = document.createElement('div');
        box.className = 'modal-content system-update-dialog';

        const title = document.createElement('h3');
        const icon = document.createElement('img');
        icon.src = '/static/icons/update.svg';
        icon.alt = '';
        icon.className = 'modal-title-icon';
        const titleText = document.createElement('span');
        titleText.textContent = t.wheel_rebuild_title || 'Rebuilding packages';
        title.append(icon, ' ', titleText);

        // The package count is known up front, so the bar measures something
        // real rather than animating to look busy. Packages differ wildly in
        // build time, so it tracks packages completed, not elapsed time.
        const bar = document.createElement('div');
        bar.className = 'wheel-progress-bar';
        const fill = document.createElement('div');
        fill.className = 'wheel-progress-fill';
        bar.appendChild(fill);
        const label = document.createElement('div');
        label.className = 'wheel-progress-label system-update-hint';

        const log = document.createElement('div');
        log.className = 'system-update-log';
        log.setAttribute('aria-live', 'polite');
        _wheelLog.forEach(line => {
            const el = document.createElement('div');
            el.textContent = line;
            log.appendChild(el);
        });

        const note = document.createElement('div');
        note.className = 'system-update-status';
        note.textContent = t.wheel_rebuild_close_hint
            || 'You can close this and keep using the dashboard - the rebuild continues and you will be notified when it finishes.';

        const actions = document.createElement('div');
        actions.className = 'modal-actions';
        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'update-install-btn';
        closeBtn.textContent = t.close || 'Close';
        closeBtn.addEventListener('click', () => overlay.remove());
        actions.appendChild(closeBtn);

        box.append(title, bar, label, log, note, actions);
        overlay.appendChild(box);
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.remove();
        });
        document.body.appendChild(overlay);
        _renderWheelProgress();
        log.scrollTop = log.scrollHeight;
    }
    window.openWheelRebuildModal = openWheelRebuildModal;

    function _showWheelToast(total) {
        const t = window.translations || {};
        if (_wheelToast) _wheelToast.remove();

        // Three nodes, because progress rewrites only the first. One node would
        // wipe the power-off warning on the first update, which is exactly when
        // it starts to matter.
        const progressLine = document.createElement('div');
        progressLine.className = 'wheel-progress-line';
        progressLine.textContent = (t.wheel_rebuild_body || 'Update installed. {count} package(s) are being rebuilt for this device in the background - this can take hours. The dashboard stays available.')
            .replace('{count}', total);

        const warnLine = document.createElement('div');
        warnLine.style.cssText = 'margin-top:6px;font-weight:600;';
        warnLine.textContent = t.wheel_rebuild_keep_powered
            || 'Please leave the device powered on. An interruption resumes on the next start, but whichever package was building has to be redone.';

        const details = document.createElement('button');
        details.type = 'button';
        details.className = 'update-details-toggle';
        details.style.cssText = 'margin-top:8px;';
        details.textContent = t.show_details || 'Show details';
        // A click anywhere on a toast dismisses it, so opening the log must not
        // reach it - the toast is the only handle on a run lasting hours.
        details.addEventListener('click', (e) => {
            e.stopPropagation();
            openWheelRebuildModal();
        });

        _wheelToast = _buildLiveToast(
            [_toastIcon('update', 'accent'), ' ' + (t.wheel_rebuild_title || 'Rebuilding packages')],
            [progressLine, warnLine, details],
            '#f7931a',
            0
        );
    }

    function _setWheelProgressLine(name, index, total) {
        const t = window.translations || {};
        const line = _wheelToast?.querySelector('.wheel-progress-line');
        if (!line) return;
        line.textContent = (t.wheel_rebuild_progress || 'Rebuilding {name} ({index}/{total})...')
            .replace('{name}', name)
            .replace('{index}', index)
            .replace('{total}', total);
    }

    // A rebuild that began before this page loaded has no events left to send,
    // so ask where it got to instead of showing nothing.
    (async () => {
        try {
            const r = await fetch('/api/wheels/rebuild-status');
            if (!r.ok) return;
            const d = await r.json();
            if (d?.success && d.running) {
                _wheelLog = d.log || [];
                _wheelProgress = { index: d.index || 0, total: d.total || 0, current: d.current };
                _showWheelToast(d.total || 0);
                if (d.current) _setWheelProgressLine(d.current, d.index, d.total);
            }
        } catch (e) { /* status unavailable - the toast simply does not appear */ }
    })();

    configSocket.on('wheel_rebuild_started', (data) => {
        if (!data) return;
        _wheelLog = [];
        _wheelProgress = { index: 0, total: data.total || 0, current: null };
        _showWheelToast(data.total);
        _renderWheelProgress();
    });

    configSocket.on('wheel_rebuild_progress', (data) => {
        if (!data) return;
        const t = window.translations || {};
        // 'building' announces the start of a package; the completion event for
        // the same package carries ok/skipped. Only the latter advances the bar.
        if (data.building) {
            _wheelProgress = { index: data.index - 1, total: data.total, current: data.name };
            _appendWheelLog((t.wheel_rebuild_progress || 'Rebuilding {name} ({index}/{total})...')
                .replace('{name}', data.name)
                .replace('{index}', data.index)
                .replace('{total}', data.total));
        } else {
            _wheelProgress = { index: data.index, total: data.total, current: null };
            _appendWheelLog(data.name + ': '
                + (data.skipped ? (t.wheel_rebuild_skipped || 'already built for this device')
                   : data.ok ? (t.wheel_rebuild_ok || 'rebuilt')
                   : (t.wheel_rebuild_fail || 'could not be built')));
        }
        _setWheelProgressLine(data.name, data.index, data.total);
        _renderWheelProgress();
    });

    configSocket.on('wheel_rebuild_done', (data) => {
        if (!data) return;
        const t = window.translations || {};
        if (_wheelToast) { _wheelToast.remove(); _wheelToast = null; }

        const ok = (data.rebuilt || []).length;
        const bad = (data.failed || []).length;
        const lines = [(t.wheel_rebuild_done_body || '{count} package(s) rebuilt for this device.')
            .replace('{count}', ok)];
        if (bad) {
            lines.push(' ' + (t.wheel_rebuild_failed || 'Could not build: {names}')
                .replace('{names}', (data.failed || []).join(', ')));
        }
        if (data.restarting) {
            lines.push(' ' + (t.wheel_rebuild_restarting || 'Restarting the service to load them...'));
        }
        _buildLiveToast(
            [_toastIcon('update', bad ? 'accent' : 'success'), ' ' +
                (t.wheel_rebuild_done_title || 'Packages rebuilt')],
            lines,
            bad ? '#f7931a' : '#28a745',
            12000
        );
    });

    configSocket.on('network_stats_updated', (data) => {
        if (!data) return;
        window._previewData.network = { ...window._previewData.network, ...data };
        if (window._refreshNetworkPreview) window._refreshNetworkPreview(window._previewData.network);
    });

    // Listen for Bitaxe stats updates — aggregate miners for preview card
    configSocket.on('bitaxe_stats_updated', (data) => {
        if (!data?.miners) return;
        const miners = Object.values(data.miners);
        const online = miners.filter(m => m.online).length;
        const total  = miners.length;
        let bestDiff = 0;
        for (const m of miners) {
            if (m.best_diff > bestDiff) bestDiff = m.best_diff;
        }
        const agg = {
            hashrate_ths: data.hashrate_ths ?? (window._previewData.bitaxe?.hashrate_ths ?? 0),
            miners_online: online,
            miners_total: total,
            best_difficulty: bestDiff,
            valid_blocks: data.valid_blocks ?? (window._previewData.bitaxe?.valid_blocks ?? 0),
        };
        window._previewData.bitaxe = { ...window._previewData.bitaxe, ...agg };
        if (window._refreshBitaxePreview) window._refreshBitaxePreview(window._previewData.bitaxe);
    });

    // Listen for donation updates
    configSocket.on('donation_received', (data) => {
        if (!data) return;
        if (!data.header_text) {
            const cfg2 = window.currentConfig || {};
            const mode = cfg2['donation_display_mode'] || 'latest';
            const t2 = window.translations || {};
            const modeLabel = mode === 'highest' ? (t2.donation_mode_highest || 'Largest donation') : (t2.donation_mode_latest || 'Latest donation');
            const sats = data.amount_sats || 0;
            const amtFmt = _fmtNum(sats);
            const satLabel = sats === 1 ? 'Sat' : 'Sats';
            let ts = '';
            try { ts = data.timestamp ? new Date(data.timestamp).toLocaleString() : ''; } catch (e) {}
            data = { ...data, header_text: `${modeLabel}: ${amtFmt} ${satLabel}${ts ? ` (${ts})` : ''}` };
        }
        window._previewData.donation = data;
        if (window._refreshDonationPreview) window._refreshDonationPreview(data);
    });

    // Listen for block notifications
    configSocket.on('new_block_notification', (data) => {
        // Store latest block hash so holiday color preview can show it
        if (data?.block_hash_full || data?.block_hash) {
            window._previewData = window._previewData || {};
            const _fullHash = data.block_hash_full || data.block_hash;
            window._previewData.latestBlockHash = _fullHash;
            if (window._refreshDateHashPreview)    window._refreshDateHashPreview(_fullHash);
            if (window._refreshHolidayHashPreview) window._refreshHolidayHashPreview(_fullHash);
        }
        
        const state = getNotificationState();
        const now = Date.now();
        
        // Allow updates for the same block (enriched data) but prevent duplicate new blocks
        const isEnrichment = data.enriched === true;
        const isDifferentBlock = !state.lastBlockHeight || state.lastBlockHeight !== data.block_height;
        
        if (!isEnrichment && !isDifferentBlock && (now - state.lastNotification) < 10000) {
            return;
        }
        
        // Update state for new blocks (not enrichments)
        if (!isEnrichment || isDifferentBlock) {
            state.lastNotification = now;
            state.lastBlockHeight = data.block_height;
            setNotificationState(state);
        }

        // The block-height color preview is a picture of the tip: the height it
        // draws, the fee under it and — as days close — the median that fee is
        // judged against all moved when this block landed. Reload the scale so
        // the panel shows the block that just arrived rather than the one the
        // page was opened on. Only a genuinely new height starts a reload; the
        // enriched repeat of a block already seen carries pool and reward data,
        // none of which the scale is made of.
        if (isDifferentBlock && typeof _refreshBlockHeightScale === 'function') {
            _refreshBlockHeightScale(data.block_height);
        }

        showBlockToast(data);
        try {
            localStorage.setItem('mempaper_block_notification', JSON.stringify({
                timestamp: now,
                data: data
            }));
            setTimeout(() => {
                localStorage.removeItem('mempaper_block_notification');
            }, 1000);
        } catch (e) {
            console.warn('Could not broadcast notification to other pages:', e);
        }
    });

    configSocket.on('block_notification_error', (data) => {
        console.error('❌ [CONFIG] Block notification error:', data.error);
    });

    // Listen for notifications from other pages
    window.addEventListener('storage', function(e) {
        if (e.key === 'mempaper_block_notification') {
            try {
                const notificationData = JSON.parse(e.newValue);
                if (notificationData && notificationData.timestamp > Date.now() - 5000) {
                    showBlockToast(notificationData.data);
                }
            } catch (error) {
                console.warn('Error parsing cross-page notification:', error);
            }
        }
    });

    // Cleanup on page unload
    window.addEventListener('beforeunload', function() {
        unregisterPageForNotifications('config');
    });
}

function attemptConfigReconnect() {
    // Device was deliberately shut down (not restarted) — it isn't coming back
    // on its own, so don't keep trying.
    if (window._shuttingDown) return;
    if (reconnectingConfig) return;
    reconnectingConfig = true;
    if (reconnectTimeoutConfig) clearTimeout(reconnectTimeoutConfig);
    reconnectTimeoutConfig = setTimeout(() => {
        if (configSocket) configSocket.connect();
        reconnectingConfig = false;
    }, 2000);
}

// Initial connection
connectConfigSocket();

function updateWalletBalancesFromWebSocket(balanceData) {
    // Find all wallet tables on the page
    const walletTables = document.querySelectorAll('.wallet-table tbody');
    
    walletTables.forEach(tbody => {
        const rows = tbody.querySelectorAll('tr');
        
        rows.forEach(row => {
            const addressInput = row.querySelector('.wallet-address-input');
            const balanceDisplay = row.querySelector('.wallet-balance-display');
            
            if (addressInput && balanceDisplay) {
                const address = addressInput.value.trim();
                
                if (address && balanceData) {
                    let newBalance = null;
                    
                    // Check if address is in the balance data (using correct cache structure)
                    if (address.startsWith('xpub') || address.startsWith('zpub') || address.startsWith('ypub')) {
                        // Check xpub data (array format)
                        const xpubEntries = balanceData.xpubs || [];
                        for (const xpubEntry of xpubEntries) {
                            if (xpubEntry.xpub === address) {
                                newBalance = xpubEntry.balance_btc || 0.0;
                                break;
                            }
                        }
                    } else {
                        // Check address balances (array format)
                        const addressEntries = balanceData.addresses || [];
                        for (const addressEntry of addressEntries) {
                            if (addressEntry.address === address) {
                                newBalance = addressEntry.balance_btc || 0.0;
                                break;
                            }
                        }
                    }
                    
                    if (newBalance !== null) {
                        _setWalletBalanceText(balanceDisplay, `${newBalance.toFixed(8)}`);
                        balanceDisplay.style.color = 'var(--accent)';
                        balanceDisplay.style.opacity = '1';
                        balanceDisplay.title = 'Real-time balance data';
                        
                        // Add a subtle animation to indicate the update
                        balanceDisplay.style.transition = 'background-color 0.5s ease';
                        balanceDisplay.style.backgroundColor = 'rgba(40, 167, 69, 0.2)';
                        setTimeout(() => {
                            balanceDisplay.style.backgroundColor = '';
                        }, 2000);
                    }
                }
            }
        });
    });
}

// Setup responsive navigation buttons
function setupNavigationButtons() {
    // Back button functionality (both desktop and mobile)
    const setupBackButton = (buttonId) => {
        const button = document.getElementById(buttonId);
        if (button) {
            button.addEventListener('click', () => {
                window.location.href = '/';
            });
        }
    };
    
    // Save button functionality (both desktop and mobile)  
    const setupSaveButton = (buttonId) => {
        const button = document.getElementById(buttonId);
        if (button) {
            button.addEventListener('click', async () => {
                document.querySelectorAll('#desktop-save-button, #mobile-save-button').forEach(btn => {
                    btn.classList.remove('unsaved-changes');
                    btn.classList.add('saving');
                    btn.disabled = true;
                });
                // Keep original content, just disable the button
                
                try {
                    const formConfig = {};

                    // Collect all form values using the proper method that handles custom getValue() functions
                    document.querySelectorAll('[data-config-key]').forEach(element => {
                        const key = element.dataset.configKey;

                        if (element.getValue) {
                            formConfig[key] = element.getValue();
                        } else if (element.type === 'checkbox') {
                            formConfig[key] = element.checked;
                        } else if (element.type === 'number') {
                            const n = _numFieldValue(element);
                            if (n !== undefined) formConfig[key] = n;
                        } else {
                            formConfig[key] = element.value;
                        }
                    });

                    // If we have a pending language change, make sure it's included in formConfig
                    if (pendingLanguageChange) {
                        formConfig.language = pendingLanguageChange;
                    }

                    // Transport gate: Tor routing and .onion hosts travel together.
                    const _transportErr = typeof mempoolTransportError === 'function'
                        ? mempoolTransportError(formConfig) : null;
                    if (_transportErr) {
                        showNotification(_transportErr, 'error');
                        return false;
                    }

                    // Privacy gate: warn when mempool host changed and private checkbox is unchecked
                    const savedHost = (currentConfig.mempool_host || '').trim().toLowerCase();
                    const newHost = (formConfig.mempool_host || '').trim().toLowerCase();
                    if (newHost && newHost !== savedHost && !formConfig.mempool_is_private) {
                        const accepted = await _showPrivacyWarning();
                        if (!accepted) {
                            button.disabled = false;
                            return;
                        }
                    }

                    const response = await fetch('/api/config', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(formConfig)
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        // (oldDeviceName/oldDisplayEnabled no longer used — driver install always fires)

                        // Check if language was changed using pendingLanguageChange
                        const oldLanguage = currentConfig.language;
                        const newLanguage = pendingLanguageChange || formConfig.language;
                        const languageChanged = pendingLanguageChange !== null || (newLanguage && newLanguage !== oldLanguage);

                        // Update current config
                        currentConfig = { ...currentConfig, ...formConfig };

                        if (languageChanged) {
                            pendingLanguageChange = null;
                        }

                        // Save SSH keys if changed — must run before _markClean() so
                        // savedKeys is updated and _sshIsDirty() returns false.
                        if (typeof window._sshSaveHook === 'function') {
                            try { await window._sshSaveHook(); } catch (_) { /* error shown in SSH section */ }
                        }

                        showNotification(window.translations?.configuration_saved || 'Configuration saved successfully!', 'success');
                        _markClean();
                    } else {
                        showNotification(result.message || window.translations?.failed_to_save_configuration || 'Failed to save configuration', 'error');
                    }
                } catch (error) {
                    console.error('Error saving configuration:', error);
                    showNotification(window.translations?.failed_to_save_configuration || 'Failed to save configuration', 'error');
                } finally {
                    document.querySelectorAll('#desktop-save-button, #mobile-save-button').forEach(btn => {
                        btn.classList.remove('saving');
                        btn.disabled = false;
                    });
                }
            });
        }
    };

    // Logout button functionality (both desktop and mobile)
    const setupLogoutButton = (buttonId) => {
        const button = document.getElementById(buttonId);
        if (button) {
            button.addEventListener('click', async () => {
                const confirmed = await showConfirmModal({
                    title: window.translations?.logout || 'Logout',
                    message: window.translations?.are_you_sure_logout || window.translations?.confirm_logout || 'Are you sure you want to logout?',
                    confirmText: window.translations?.logout || 'Logout',
                    cancelText: window.translations?.cancel || 'Cancel',
                    danger: true,
                    icon: '/static/icons/logout.svg'
                });
                if (confirmed) {
                    try {
                        const response = await fetch('/api/logout', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' }
                        });
                        if (response.ok) {
                            const result = await response.json();
                            window.location.href = result.public_dashboard ? '/' : '/login';
                        } else {
                            window.location.href = '/login';
                        }
                    } catch {
                        window.location.href = '/login';
                    }
                }
            });
        }
    };
    
    // Setup all buttons
    setupBackButton('desktop-back-button');
    setupBackButton('mobile-back-button');
    setupSaveButton('desktop-save-button');
    setupSaveButton('mobile-save-button');
    _setupValidationClickInterceptor();
    setupLogoutButton('desktop-logout-button');
    setupLogoutButton('mobile-logout-button');
}

// Block notification subscription functions
// Global notification state management (shared across tabs/pages)
function getNotificationState() {
    try {
        const state = localStorage.getItem('mempaper_notification_state');
        return state ? JSON.parse(state) : { lastNotification: 0, subscribedPages: [] };
    } catch (e) {
        return { lastNotification: 0, subscribedPages: [] };
    }
}

function setNotificationState(state) {
    try {
        localStorage.setItem('mempaper_notification_state', JSON.stringify(state));
    } catch (e) {
        console.warn('Could not save notification state:', e);
    }
}

function registerPageForNotifications(pageType) {
    const state = getNotificationState();
    if (!state.subscribedPages.includes(pageType)) {
        state.subscribedPages.push(pageType);
        setNotificationState(state);
    }
}

function unregisterPageForNotifications(pageType) {
    const state = getNotificationState();
    state.subscribedPages = state.subscribedPages.filter(page => page !== pageType);
    setNotificationState(state);
}

function subscribeToBlockNotifications() {
    if (configSocket) {
        configSocket.emit('subscribe_block_notifications', { page: 'config' });
    }
}

function unsubscribeFromBlockNotifications() {
    if (configSocket) {
        configSocket.emit('unsubscribe_block_notifications');
    }
}

// Show block notification toast (adapted for config page)
function showBlockToast(blockData) {
    // Create toast container if it doesn't exist
    let toastContainer = document.getElementById('block-toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.id = 'block-toast-container';
        toastContainer.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 100100;
            font-family: 'Roboto', Arial, sans-serif;
            isolation: isolate;
        `;
        document.body.appendChild(toastContainer);
    }
    // Ensure toast container is always last child so it paints above nav elements
    if (toastContainer.nextSibling) document.body.appendChild(toastContainer);
    
    const blockHeight = blockData.block_height;
    const toastId = `toast-${blockHeight}`;
    
    // Check if toast already exists for this block (for enrichment updates)
    let toast = document.getElementById(toastId);
    const isUpdate = toast !== null;
    const isDark = document.body.classList.contains('dark-mode');

    if (!toast) {
        // Create new toast element
        toast = document.createElement('div');
        toast.id = toastId;
        const toastBg = isDark ? 'rgba(30, 30, 36, 0.92)' : 'rgba(255, 255, 255, 0.95)';
        const toastColor = isDark ? '#e8e8ec' : '#1a1a2e';
        const toastBorder = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.1)';
        const toastShadow = isDark
            ? '0 8px 32px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(255,255,255,0.06)'
            : '0 8px 32px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0,0,0,0.04)';
        const closeBtnBg = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
        const closeBtnColor = isDark ? '#9a9aaa' : '#555';
        const closeBtnHoverBg = isDark ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.12)';
        toast.style.cssText = `
            background: ${toastBg};
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            color: ${toastColor};
            padding: 16px 20px;
            border-radius: 14px;
            box-shadow: ${toastShadow};
            border: 1px solid ${toastBorder};
            margin-bottom: 10px;
            min-width: 320px;
            max-width: 400px;
            opacity: 0;
            transform: translateX(100%);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            position: relative;
            font-size: 14px;
            line-height: 1.4;
        `;

        // Create close button
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '×';
        closeBtn.setAttribute('aria-label', 'Close notification');
        closeBtn.style.cssText = `
            position: absolute;
            top: 8px;
            right: 8px;
            background: ${closeBtnBg};
            border: none;
            color: ${closeBtnColor};
            font-size: 18px;
            cursor: pointer;
            width: 28px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            transition: background-color 0.2s;
            font-weight: bold;
            z-index: 1;
            line-height: 1;
        `;

        // Close toast function
        const closeToast = () => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 400);
        };

        // Close button event listeners
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            closeToast();
        });
        closeBtn.addEventListener('mouseenter', () => {
            closeBtn.style.backgroundColor = closeBtnHoverBg;
        });
        closeBtn.addEventListener('mouseleave', () => {
            closeBtn.style.backgroundColor = closeBtnBg;
        });
        
        // Mobile-friendly: tap anywhere on toast to dismiss
        toast.addEventListener('click', closeToast);
        toast.style.cursor = 'pointer';
        
        // Append close button to toast
        toast.appendChild(closeBtn);
        
        // Store close function for auto-close
        toast.closeToast = closeToast;
    }
    
    // Format data (works for both new and enriched)
    const timestamp = new Date(blockData.timestamp * 1000);
    const timeString = timestamp.toLocaleTimeString();
    const heightFormatted = _fmtNum(blockData.block_height);
    const rewardFormatted = _fmtFixed(blockData.total_reward_btc, 8);
    const feesFormatted = _fmtFixed(blockData.total_fees_btc, 4);
    const medianFeeFormatted = _fmtFixed(blockData.median_fee_sat_vb, 1);
    
    // Find the content div or create toast content
    let contentDiv = toast.querySelector('.toast-content');
    if (!contentDiv) {
        contentDiv = document.createElement('div');
        contentDiv.className = 'toast-content';
        contentDiv.style.cssText = 'margin-right: 30px;';
        toast.appendChild(contentDiv);
    }
    
    // Update content (works for both new and enriched data)
    // Title/reward accents need to be darker & more saturated in light mode —
    // the dark-mode gold/light-green pair reads fine on the dark glass card
    // but is nearly illegible on the light card's near-white background.
    const titleAccent = isDark ? '#FFD700' : '#B7791F';
    const rewardAccent = isDark ? '#90EE90' : '#15803D';
    contentDiv.innerHTML = `
        <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px; color: ${titleAccent};">
            New Block ${heightFormatted}
        </div>
        <div style="margin-bottom: 4px;">
            <span style="opacity: 0.8;">Time:</span> <span style="font-weight: 500;">${timeString}</span>
        </div>
        <div style="margin-bottom: 4px;">
            <span style="opacity: 0.8;">Hash:</span> <span style="font-family: monospace; font-size: 12px;">${blockData.block_hash}</span>
        </div>
        <div style="margin-bottom: 4px;">
            <span style="opacity: 0.8;">Pool:</span> <span style="font-weight: 500;">${blockData.pool_name}</span>
        </div>
        <div style="margin-bottom: 4px;">
            <span style="opacity: 0.8;">Reward:</span> <span style="font-weight: 500; color: ${rewardAccent};">${rewardFormatted} BTC</span>
            <span style="font-size: 12px; opacity: 0.7;">(+${feesFormatted} fees)</span>
        </div>
        <div>
            <span style="opacity: 0.8;">Median Fee:</span> <span style="font-weight: 500;">${medianFeeFormatted} sat/vB</span>
        </div>
    `;
    
    if (!isUpdate) {
        // New toast - add to container and animate in
        toastContainer.appendChild(toast);
        
        // Animate in
        setTimeout(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        }, 10);
        
        // Auto-close after 30 seconds
        setTimeout(() => {
            if (toast.closeToast) {
                toast.closeToast();
            }
        }, 30000);
    }
}

// Initialize WebSocket when page loads
document.addEventListener('DOMContentLoaded', () => {
    // Remove any native title attribute from elements that use data-tooltip for CSS tooltips,
    // in case a previous setLanguage() call left one behind.
    document.querySelectorAll('[data-tooltip][title]').forEach(el => el.removeAttribute('title'));

    // Capture server process start time + boot_id so reconnect can detect any
    // restart, and tell an actual reboot (new boot_id) apart from a same-boot
    // service restart (e.g. triggered from the CLI, not this page).
    fetch('/api/health', { cache: 'no-store' })
        .then(r => r.ok ? r.json() : null)
        .then(h => {
            if (!h) return;
            window._pageLoadStarted = h.started;
            window._pageLoadBootId = h.boot_id;
        })
        .catch(() => {});

    // Show success toast if we just reloaded after a software update.
    const _updatedTag = sessionStorage.getItem('mempaper_updated_to');
    if (_updatedTag) {
        sessionStorage.removeItem('mempaper_updated_to');
        setTimeout(() => {
            const t = window.translations || {};
            const tagEl = document.createElement('strong');
            tagEl.textContent = _updatedTag;
            const body = document.createDocumentFragment();
            body.append((t.update_success_body || 'mempaper updated to') + ' ', tagEl);
            _buildLiveToast(
                [_toastIcon('update', 'success'), ' ' + (t.update_success_title || 'Update successful')],
                body,
                '#28a745',
                8000
            );
        }, 800);
    }

    // Show success toast after a plain restart/reboot (button click or a CLI
    // "systemctl restart/reboot" run by the user directly — detection doesn't
    // care who triggered it). Skipped entirely when an update just landed
    // (handled by the toast above instead, which already names the version).
    const _actionDone = sessionStorage.getItem('mempaper_action_done');
    if (_actionDone) {
        sessionStorage.removeItem('mempaper_action_done');
        setTimeout(() => {
            const t = window.translations || {};
            if (_actionDone === 'reboot') {
                _buildLiveToast(
                    [_toastIcon('reboot', 'success'), ' ' + (t.reboot_success_title || 'Device rebooted')],
                    [t.reboot_success_body || 'The device rebooted successfully.'],
                    '#28a745',
                    8000
                );
            } else {
                _buildLiveToast(
                    [_toastIcon('restart', 'success'), ' ' + (t.restart_success_title || 'Service restarted')],
                    [t.restart_success_body || 'The mempaper service restarted successfully.'],
                    '#28a745',
                    8000
                );
            }
        }, 800);
    }

    // Setup navigation buttons
    setupNavigationButtons();

    // Connect the WebSocket
    initializeWebSocket();
});

// Reload immediately when the tab becomes visible again if a service restart was detected.
// Covers both announced restarts (_restartPending) and silent ones (manual systemctl restart).
document.addEventListener('visibilitychange', () => {
    if (document.hidden) return;
    // Device was deliberately shut down (not restarted) — it isn't coming back
    // on its own, so don't keep checking.
    if (window._shuttingDown) return;
    if (!window._restartPending && window._pageLoadStarted === undefined) return;
    const oldStarted = window._restartPending
        ? window._restartPending.oldStarted
        : window._pageLoadStarted;
    fetch('/api/health', { cache: 'no-store' })
        .then(r => r.ok ? r.json() : null)
        .then(h => {
            if (h && oldStarted && h.started > oldStarted) {
                const _tag = window._restartPending?.tag;
                const _isReboot = !!(window._pageLoadBootId && h.boot_id && h.boot_id !== window._pageLoadBootId);
                window._restartPending = null;
                _reloadAfterRestart(_tag, _isReboot);
            }
        })
        .catch(() => {});
});

// Allow bfcache by closing the socket when the page is hidden and restoring on return
window.addEventListener('pagehide', () => {
    if (window.configSocket) window.configSocket.disconnect();
});
window.addEventListener('pageshow', (event) => {
    // Always verify session on every page show — covers both normal loads (where a
    // proxy may have served a cached copy) and bfcache restores.
    fetch('/api/auth-check', { credentials: 'same-origin' })
        .then(r => r.json())
        .then(d => {
            if (!d.authenticated) {
                window.location.replace('/login');
                return;
            }
            if (event.persisted) {
                if (window.configSocket && window.configSocket.disconnected) {
                    window.configSocket.connect();
                } else if (!window.configSocket) {
                    initializeWebSocket();
                }
            }
        })
        .catch(() => { window.location.replace('/login'); });
});


