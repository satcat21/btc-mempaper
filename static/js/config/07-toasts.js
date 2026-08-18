// Live toast helpers and unsaved-changes tracking.
// Part 7 of 8, split from config.js. Load order matters:
// these run as classic scripts sharing one global scope.

// ── Live toast helpers ────────────────────────────────────────────────────────

// Resolve the configured section color for the current theme
function _getLiveToastColor(keyBase) {
    const isDark = document.body.classList.contains('dark-mode');
    const cfg = window.currentConfig || {};
    return cfg[isDark ? keyBase + '_dark' : keyBase + '_light'] || '#F7931A';
}

// _getLiveToastContainer and _buildLiveToast are provided by toast.js

function showDonationToast(donation) {
    const sats     = _fmtNum(donation.amount_sats || 0);
    const satLabel = donation.amount_sats === 1 ? 'sat' : 'sats';

    const amountEl = document.createElement('strong');
    amountEl.textContent = `${sats} ${satLabel}`;
    const lines = [amountEl];

    if (donation.message) {
        const msgEl = document.createElement('span');
        msgEl.style.cssText = 'opacity:0.7;font-size:12px;';
        msgEl.textContent = `"${donation.message}"`;
        lines.push(msgEl);
    }

    const title = window.translations?.donation_toast_title || 'Lightning Donation';
    _buildLiveToast(title, lines, _getLiveToastColor('color_donation'), 8000);
}

// title    — short section label shown in the configured color (e.g. "Wallet", "Bitaxe")
// message  — detail text (user data — rendered as text, never as markup)
// colorKey — config key base (e.g. 'color_wallets', 'color_bitaxe_stats')
function showLiveToast(title, message, colorKey) {
    _buildLiveToast(title, [message], _getLiveToastColor(colorKey));
}

async function uploadOpsecFiles(files) {
    const progressDiv = document.getElementById('opsec-upload-progress');
    const progressBar = document.getElementById('opsec-progress-bar');
    const statusText = document.getElementById('opsec-upload-status');

    if (!files || files.length === 0) return;

    const imageFiles = files.filter(f => f.type.startsWith('image/'));
    if (imageFiles.length === 0) {
        showNotification(window.translations?.upload_images_only || 'Please select image files only', 'error');
        return;
    }

    const t = window.translations;

    // Show progress
    if (progressDiv && progressBar && statusText) {
        progressDiv.style.display = 'block';
        progressBar.style.transform = 'scaleX(0)';
        statusText.textContent = t?.upload_checking_duplicates || 'Checking for duplicates...';
        statusText.style.color = '#F7931A';
    }

    // Fetch existing hashes for duplicate detection
    const existingHashes = await getExistingOpsecHashes();

    // Build a working set of filenames (server state + files queued this batch)
    const existingFilenames = new Set(Object.values(existingHashes));

    // Process files: check for duplicates, offer rename
    const filesToUpload = [];
    const duplicates = [];

    for (let i = 0; i < imageFiles.length; i++) {
        const file = imageFiles[i];

        if (statusText) {
            statusText.textContent = (t?.upload_processing || 'Processing {current}/{total}: {filename}...')
                .replace('{current}', i + 1).replace('{total}', imageFiles.length).replace('{filename}', file.name);
        }

        // Calculate SHA-256 hash
        const hash = await calculateFileHash(file);

        // Skip duplicates
        if (hash && existingHashes[hash]) {
            duplicates.push({ name: file.name, duplicate: existingHashes[hash] });
            continue;
        }

        let targetName = file.name;

        // Check for filename conflict (same name, different content)
        if (existingFilenames.has(file.name)) {
            const ext = file.name.substring(file.name.lastIndexOf('.'));
            const base = file.name.substring(0, file.name.lastIndexOf('.'));

            // Auto-generate a non-conflicting name: base_1.ext, base_2.ext, …
            let counter = 1;
            while (existingFilenames.has(base + '_' + counter + ext)) {
                counter++;
            }
            const suggestedName = base + '_' + counter + ext;

            // Show dialog with the pre-corrected name so user can adjust if desired
            targetName = await showRenameDialog(file.name, file, suggestedName, existingFilenames);
        }

        const uploadFile = targetName === file.name
            ? file
            : new File([file], targetName, { type: file.type });

        filesToUpload.push({ file: uploadFile, name: targetName, hash });
        // Track name within this batch to avoid intra-batch conflicts
        existingFilenames.add(targetName);
    }

    // Show pre-upload summary
    let summaryMessage = '';
    if (duplicates.length > 0) {
        summaryMessage += (t?.upload_skipped_duplicates_msg || 'Skipped {count} duplicate(s).').replace('{count}', duplicates.length) + ' ';
    }
    if (filesToUpload.length > 0) {
        summaryMessage += (t?.upload_uploading_count || 'Uploading {count} file(s)...').replace('{count}', filesToUpload.length);
    } else {
        summaryMessage = t?.upload_no_files || 'No files to upload.';
    }

    if (statusText) {
        statusText.textContent = summaryMessage;
        statusText.style.color = duplicates.length > 0 ? '#ff9800' : '#F7931A';
    }

    if (duplicates.length > 0) {
        const dupList = duplicates.map(d => `• ${d.name} (duplicate of ${d.duplicate})`).join('\n');
        showNotification((t?.upload_duplicates_skipped_notification || '{count} duplicate file(s) skipped').replace('{count}', duplicates.length), 'warning');
    }

    // Upload non-duplicate files
    if (filesToUpload.length > 0) {
        let uploadedCount = 0;
        let failedCount = 0;

        for (let i = 0; i < filesToUpload.length; i++) {
            const { file, name } = filesToUpload[i];

            if (statusText) {
                statusText.textContent = (t?.upload_uploading_progress || 'Uploading {current}/{total}: {filename}...')
                    .replace('{current}', i + 1).replace('{total}', filesToUpload.length).replace('{filename}', name);
            }
            if (progressBar) {
                progressBar.style.transform = `scaleX(${i / filesToUpload.length})`;
            }

            const formData = new FormData();
            formData.append('file', file);

            try {
                const response = await fetch('/api/upload-opsec', { method: 'POST', body: formData });
                const result = await response.json();
                if (result.success) uploadedCount++;
                else { failedCount++; console.error(`Failed to upload ${name}:`, result.message); }
            } catch (error) {
                failedCount++;
                console.error(`Error uploading ${name}:`, error);
            }
        }

        if (progressBar) progressBar.style.transform = 'scaleX(1)';

        // Final status summary
        if (statusText) {
            const parts = [];
            if (uploadedCount > 0) parts.push((t?.upload_count_uploaded || '✓ {count} uploaded').replace('{count}', uploadedCount));
            if (failedCount > 0) parts.push((t?.upload_count_failed || '✗ {count} failed').replace('{count}', failedCount));
            if (duplicates.length > 0) parts.push((t?.upload_count_skipped || '⊝ {count} skipped (duplicates)').replace('{count}', duplicates.length));
            statusText.textContent = parts.join(' | ');
            statusText.style.color = failedCount > 0 ? '#e53e3e' : '#38a169';
        }

        if (uploadedCount > 0) loadOpsecImages();

        setTimeout(() => { if (progressDiv) progressDiv.style.display = 'none'; }, 4000);

        if (uploadedCount > 0) {
            showNotification((t?.upload_success_notification || 'Successfully uploaded {count} file(s)').replace('{count}', uploadedCount), 'success');
        }
        if (failedCount > 0) {
            showNotification((t?.upload_fail_notification || 'Failed to upload {count} file(s)').replace('{count}', failedCount), 'error');
        }
    } else {
        setTimeout(() => { if (progressDiv) progressDiv.style.display = 'none'; }, 3000);
    }
}


// ── Unsaved-changes tracking ─────────────────────────────────────────────────
let _savedSnapshot = '';

// Controls that drive a preview rather than a setting - the fee slider in the
// block-height panel is the only one so far. They carry no config key, so they
// never reach the snapshot; this marks them so their events do not run the
// check either. Moving one cannot change what would be saved, and a check it
// triggers can only report a difference it had nothing to do with.
function _isPreviewOnly(el) {
    return !!(el && el.closest && el.closest('[data-preview-only]'));
}

function _collectFormSnapshot() {
    const vals = {};
    document.querySelectorAll('[data-config-key]').forEach(el => {
        const key = el.dataset.configKey;
        if (el.getValue) vals[key] = el.getValue();
        else if (el.type === 'checkbox') vals[key] = el.checked;
        else vals[key] = el.value;
    });
    return JSON.stringify(vals);
}

function _checkDirty() {
    const sshDirty = typeof window._sshIsDirty === 'function' && window._sshIsDirty();
    const dirty = _collectFormSnapshot() !== _savedSnapshot || sshDirty;
    document.querySelectorAll('#desktop-save-button, #mobile-save-button').forEach(btn => {
        btn.classList.toggle('unsaved-changes', dirty);
    });
}

function _markClean() {
    _savedSnapshot = _collectFormSnapshot();
    _checkDirty();
}

function _initDirtyTracking() {
    _savedSnapshot = _collectFormSnapshot();
    const form = document.getElementById('config-form') || document.getElementById('config-container');
    const onActivity = (e) => { if (!_isPreviewOnly(e.target)) _checkDirty(); };
    if (form) {
        form.addEventListener('input', onActivity);
        form.addEventListener('change', onActivity);
    }
    // Also listen for custom toggle clicks (boolean switches fire click, not change)
    document.addEventListener('click', (e) => {
        if (_isPreviewOnly(e.target)) return;
        if (e.target.closest('.boolean-switch, .toggle-switch, [data-config-key]')) {
            setTimeout(_checkDirty, 50);
        }
    });
}

// Silent configuration save (no user feedback)
async function saveConfigurationSilent(configToSave) {
    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(configToSave)
        });
        
        const result = await response.json();
        return result.success;
    } catch (error) {
        console.error('Failed to save configuration:', error);
        return false;
    }
}

// Navigation button save handler
async function handleSaveButtonClick(buttonElement) {
    if (!buttonElement) return;
    
    buttonElement.disabled = true;
    const originalHTML = buttonElement.innerHTML;
    
    // Show saving state
    if (buttonElement.id.includes('mobile')) {
        buttonElement.innerHTML = '<span style="font-size: 12px;">•••</span>';
    } else {
        buttonElement.innerHTML = '<span>Savin3...</span>';
    }
    
    try {
        const success = await saveConfiguration();
        // Success notification is already shown in saveConfiguration
    } catch (error) {
        console.error('Save button error:', error);
        showNotification('Failed to save configuration', 'error');
    } finally {
        buttonElement.disabled = false;
        buttonElement.innerHTML = originalHTML;
    }
}

// Global function that can be called from onclick
window.saveConfigFromButton = async function(buttonId) {
    const button = document.getElementById(buttonId);
    await handleSaveButtonClick(button);
};

// Save configuration function that can be called from buttons
async function saveConfiguration() {
    try {
        const formConfig = {}; 
        // Collect all form values
        document.querySelectorAll('[data-config-key]').forEach(element => {
            const key = element.dataset.configKey;
            
            if (element.getValue) {
                const value = element.getValue();
                formConfig[key] = value;
            } else if (element.type === 'checkbox') {
                formConfig[key] = element.checked;
            } else if (element.type === 'number') {
                const n = _numFieldValue(element);
                if (n !== undefined) formConfig[key] = n;
            } else {
                formConfig[key] = element.value;
            }
        });
        
        // Fallback: ensure all boolean fields are properly collected if missed above
        const expectedBooleanFields = ['prioritize_large_scaled_meme', 'color_mode_dark', 'show_btc_price_block', 'show_bitaxe_block', 'show_wallet_balances_block', 'show_donation_block', 'e-ink-display-connected', 'mempool_is_private'];
        expectedBooleanFields.forEach(fieldName => {
            if (!(fieldName in formConfig)) {
                const element = document.querySelector(`[data-config-key="${fieldName}"]`);
                if (element && element.getValue) {
                    formConfig[fieldName] = element.getValue();
                } else if (element && element.classList && element.classList.contains('boolean-switch')) {
                    const switchEl = element.querySelector('.switch');
                    if (switchEl) formConfig[fieldName] = switchEl.classList.contains('active');
                }
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
            if (!accepted) return false;
        }

        // Merge form values with current config to preserve non-form fields
        const newConfig = { ...currentConfig, ...formConfig };

        // Capture old display state before save for driver install detection
        const oldDeviceName = currentConfig.omni_device_name;
        const oldDisplayEnabled = currentConfig['e-ink-display-connected'];

        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(newConfig)
        });
        
        if (response.status === 401) {
            // Session expired - try to handle gracefully
            showNotification(window.translations?.session_expired || 'Session expired. Redirecting to login...', 'error');
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
            return false;
        }
        
        if (response.status === 429) {
            const errorData = await response.json();
            const retryAfter = errorData.retry_after || 60;
            const rateLimitMessage = window.translations?.rate_limit_exceeded || 'Rate limit exceeded. Please wait {seconds} seconds before trying again.';
            showNotification(rateLimitMessage.replace('{seconds}', retryAfter), 'error');
            return false;
        }
        
        const result = await response.json();
        
        if (result.success) {
            // Check if language was changed using pendingLanguageChange
            const oldLanguage = currentConfig.language;
            const newLanguage = pendingLanguageChange || formConfig.language;
            const languageChanged = pendingLanguageChange !== null || (newLanguage && newLanguage !== oldLanguage);

            // Update current config
            currentConfig = newConfig;
            window.currentConfig = newConfig; // Make available globally

            // Language already applied live via setLanguage() on dropdown change — just clear pending flag
            if (languageChanged) {
                pendingLanguageChange = null;
            }

            // Save SSH keys if the section added/removed any
            if (typeof window._sshSaveHook === 'function') {
                try { await window._sshSaveHook(); } catch (_) { /* error shown in SSH section */ }
            }

            // Block notifications are always enabled - no need to update subscription
            return true;
        } else {
            showNotification(result.message || 'Failed to save configuration', 'error');
            return false;
        }
    } catch (error) {
        console.error('Save configuration error:', error);
        showNotification('Failed to save configuration', 'error');
        return false;
    }
}

// Save configuration
const saveButton = document.getElementById('save-button');
if (saveButton) {
    saveButton.addEventListener('click', async () => {
        document.querySelectorAll('#desktop-save-button, #mobile-save-button').forEach(btn => {
            btn.classList.remove('unsaved-changes');
        });
        saveButton.disabled = true;
        saveButton.textContent = '';
        try {
            // Only show toast after save result, not before
            const formConfig = {};
            document.querySelectorAll('[data-config-key]').forEach(element => {
                const key = element.dataset.configKey;
                if (element.getValue) {
                    const value = element.getValue();
                    formConfig[key] = value;
                } else if (element.type === 'checkbox') {
                    formConfig[key] = element.checked;
                } else if (element.type === 'number') {
                    const n = _numFieldValue(element);
                    if (n !== undefined) formConfig[key] = n;
                } else {
                    formConfig[key] = element.value;
                }
            });
            if (pendingLanguageChange) {
                formConfig.language = pendingLanguageChange;
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
                const oldLanguage = currentConfig.language;
                const newLanguage = pendingLanguageChange || formConfig.language;
                const languageChanged = pendingLanguageChange !== null || (newLanguage && newLanguage !== oldLanguage);
                currentConfig = { ...currentConfig, ...formConfig };
                if (languageChanged) {
                    pendingLanguageChange = null;
                }
                if (result.partial && Array.isArray(result.skipped_sensitive) && result.skipped_sensitive.length) {
                    // The public settings were written but the encrypted ones
                    // could not be. A success toast here would let the operator
                    // believe an edit took effect when it did not, so this is a
                    // modal: it names what was left unchanged and has to be
                    // acknowledged rather than fading away unread.
                    const t = window.translations || {};
                    const body =
                        (t.configuration_saved_partial
                         || 'General settings were saved. Encrypted storage is currently unavailable, so these were left unchanged:')
                        + '\n\n• ' + result.skipped_sensitive.join('\n• ')
                        + '\n\n' + (t.tang_retry_hint
                                    || 'Their existing values on the device are untouched. Restore the Tang server and save again to apply your changes.');
                    if (typeof window.showAlertModal === 'function') {
                        window.showAlertModal({
                            title: t.configuration_saved_partial_title || 'Partially saved',
                            message: body,
                        });
                    } else {
                        showNotification(body, 'warning', 20000);
                    }
                } else {
                    showNotification(window.translations?.configuration_saved || 'Configuration saved successfully!', 'success');
                }
                _markClean();
            } else {
                showNotification(result.message || window.translations?.failed_to_save_configuration || 'Failed to save configuration', 'error');
            }
        } catch (error) {
            console.error('Error saving configuration:', error);
            showNotification(window.translations?.failed_to_save_configuration || 'Failed to save configuration', 'error');
        } finally {
            saveButton.disabled = false;
            saveButton.textContent = 'Save Configuration';
        }
    });
}

// Listen for config changes from header toggles
document.addEventListener('configChange', async (event) => {
    const { key, value } = event.detail;
    
    // Update the configuration immediately
    const formElement = document.querySelector(`[data-config-key="${key}"]`);
    if (formElement) {
        if (formElement.type === 'checkbox') {
            formElement.checked = value;
        } else {
            formElement.value = value;
        }
    }
    
    // Save the configuration automatically
    try {
        const result = await saveConfigurationSilent({ ...currentConfig, [key]: value });
        if (result.success) {
        }
    } catch (error) {
        console.error('Error saving section toggle:', error);
    }
});

// Meme Modal Functions
let currentModalMeme = null;

function openMemeModal(filename, url, tags, apiTags) {
    currentModalMeme = { filename, url, tags: tags || [], apiTags: apiTags || [] };
    
    // Set basic info with null checks
    const modalTitle = document.getElementById('meme-modal-title');
    const modalImage = document.getElementById('meme-modal-image');
    const modalDimensions = document.getElementById('meme-modal-dimensions');
    const modalFilesize = document.getElementById('meme-modal-filesize');
    const memeModal = document.getElementById('meme-modal');
    
    if (modalTitle) {
        const previewText = window.translations?.meme_preview || 'Meme Preview';
        modalTitle.textContent = `${previewText} - ${filename}`;
    }
    
    // Set filename in display span (not the input)
    const modalFilenameDisplay = document.getElementById('meme-modal-filename-display');
    if (modalFilenameDisplay) {
        modalFilenameDisplay.textContent = filename;
    }
    
    // Reset rename UI to display mode
    const filenameInput = document.getElementById('meme-modal-filename-input');
    const editBtn = document.getElementById('meme-modal-edit-btn');
    const saveBtn = document.getElementById('meme-modal-save-btn');
    const cancelBtn = document.getElementById('meme-modal-cancel-rename-btn');
    const renameActionsReset = document.getElementById('meme-rename-actions');

    if (modalFilenameDisplay) modalFilenameDisplay.style.display = 'inline';
    if (editBtn) editBtn.style.display = 'inline-block';
    if (filenameInput) filenameInput.style.display = 'none';
    if (renameActionsReset) renameActionsReset.style.display = 'none';
    // Clear any stale inline display so buttons are visible when wrapper is shown
    if (saveBtn) { saveBtn.style.display = ''; saveBtn.disabled = false; saveBtn.classList.remove('rename-dirty', 'rename-clean'); }
    if (cancelBtn) cancelBtn.style.display = '';
    
    // Render tags: API tags (read-only) + user tags (editable)
    const tagsContainer = document.getElementById('meme-modal-tags-container');
    const saveTagsBtn = document.getElementById('meme-modal-save-tags-btn');
    if (tagsContainer) {
        tagsContainer.innerHTML = '';
        const apiTagsLower = new Set((currentModalMeme.apiTags || []).map(t => t.toLowerCase()));
        // User tags = tags that are NOT in the API set
        const userTags = (currentModalMeme.tags || []).filter(t => !apiTagsLower.has(t.toLowerCase()));

        // Wrapper div for the combined display
        const wrapper = document.createElement('div');
        wrapper.style.display = 'flex';
        wrapper.style.flexWrap = 'wrap';
        wrapper.style.gap = '6px';
        wrapper.style.alignItems = 'center';
        wrapper.style.flex = '1';

        // Render API tags as read-only pills
        (currentModalMeme.apiTags || []).forEach(tagText => {
            const pill = document.createElement('div');
            pill.className = 'tag';
            pill.style.opacity = '0.7';
            pill.style.cursor = 'default';
            pill.textContent = tagText;
            pill.title = 'API tag (read-only)';
            wrapper.appendChild(pill);
        });

        // Editable tags input for user-added tags
        const placeholder = window.translations?.tags_placeholder || 'Add tag...';
        const tagsInput = createTagsInput(userTags, placeholder);
        tagsInput.style.flex = '1';
        tagsInput.style.minWidth = '120px';
        // Store api tags as data attribute so duplicate check includes them
        tagsInput.dataset.apiTags = JSON.stringify(currentModalMeme.apiTags || []);
        wrapper.appendChild(tagsInput);

        tagsContainer.appendChild(wrapper);
        // Tags save button: grey until tags differ from original, dot when changed
        if (saveTagsBtn) {
            saveTagsBtn.style.display = 'inline-block';
            saveTagsBtn.classList.add('rename-clean');
            saveTagsBtn.classList.remove('rename-dirty');
            saveTagsBtn.disabled = true;
            const originalTagsKey = [...userTags].map(t => t.trim().toLowerCase()).sort().join('\0');
            HTMLElement.prototype.addEventListener.call(tagsInput, 'change', () => {
                const currentKey = tagsInput.getValue().map(t => t.trim().toLowerCase()).sort().join('\0');
                if (currentKey === originalTagsKey) {
                    saveTagsBtn.classList.remove('rename-dirty');
                    saveTagsBtn.classList.add('rename-clean');
                    saveTagsBtn.disabled = true;
                } else {
                    saveTagsBtn.classList.remove('rename-clean');
                    saveTagsBtn.classList.add('rename-dirty');
                    saveTagsBtn.disabled = false;
                }
            });
        }
    }

    // Set loading state for dimensions
    if (modalDimensions) {
        const loadingText = window.translations?.loading || 'Loading...';
        modalDimensions.textContent = loadingText;
    }
    
    // Set loading state for filesize
    if (modalFilesize) {
        const loadingText = window.translations?.loading || 'Loading...';
        modalFilesize.textContent = loadingText;
    }
    
    if (modalImage) {
        // Set up image load handler to get dimensions
        modalImage.onload = function() {
            if (modalDimensions) {
                modalDimensions.textContent = `${this.naturalWidth} × ${this.naturalHeight} px`;
            }
        };
        
        // Set up error handler
        modalImage.onerror = function() {
            if (modalDimensions) {
                modalDimensions.textContent = 'Error loading image';
            }
        };
        
        modalImage.src = url;
    }
    
    if (memeModal) {
        memeModal.style.display = 'flex';
        // Remove conflicting positioning - let CSS flexbox handle centering
    }
    
    // Try to get file size via HEAD request first, then fall back to GET
    fetch(url, { method: 'HEAD' })
        .then(response => {
            const contentLength = response.headers.get('content-length');
            const modalFilesize = document.getElementById('meme-modal-filesize');
            if (!modalFilesize) return;
            
            if (contentLength) {
                const bytes = parseInt(contentLength);
                const size = formatFileSize(bytes);
                modalFilesize.textContent = size;
            } else {
                // Fallback: try to estimate size from a partial fetch
                return fetch(url, { method: 'GET', headers: { 'Range': 'bytes=0-1' } })
                    .then(response => {
                        const contentRange = response.headers.get('content-range');
                        if (contentRange) {
                            const match = contentRange.match(/\/(\d+)$/);
                            if (match) {
                                const bytes = parseInt(match[1]);
                                const size = formatFileSize(bytes);
                                modalFilesize.textContent = size;
                                return;
                            }
                        }
                        modalFilesize.textContent = 'Unknown';
                    })
                    .catch(() => {
                        modalFilesize.textContent = 'Unknown';
                    });
            }
        })
        .catch(() => {
            const modalFilesize = document.getElementById('meme-modal-filesize');
            if (modalFilesize) {
                modalFilesize.textContent = 'Unknown';
            }
        });
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function downloadMemeFromModal() {
    if (currentModalMeme) {
        downloadMeme(currentModalMeme.filename);
    }
}

function deleteMemeFromModal() {
    if (currentModalMeme) {
        closeMemeModal();
        showDeleteModal(currentModalMeme.filename);
    }
}

async function saveMemeTags() {
    if (!currentModalMeme) return;
    const tagsContainer = document.getElementById('meme-modal-tags-container');
    const tagsInput = tagsContainer?.querySelector('.tags-input');
    if (!tagsInput) return;
    const tags = tagsInput.getValue();
    try {
        const response = await fetch('/api/meme-tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: currentModalMeme.filename, tags })
        });
        const result = await response.json();
        if (result.success) {
            // Merge API tags + user tags for the full list
            const apiTags = currentModalMeme.apiTags || [];
            const apiLower = new Set(apiTags.map(t => t.toLowerCase()));
            const uniqueUserTags = tags.filter(t => !apiLower.has(t.toLowerCase()));
            currentModalMeme.tags = [...apiTags, ...uniqueUserTags];
            const saveBtn = document.getElementById('meme-modal-save-tags-btn');
            if (saveBtn) { saveBtn.classList.remove('rename-dirty'); saveBtn.classList.add('rename-clean'); }
            showNotification(window.translations?.tags_saved || 'Tags saved', 'success');
        } else {
            showNotification(result.message || window.translations?.tags_save_failed || 'Failed to save tags', 'error');
        }
    } catch (error) {
        showNotification((window.translations?.tags_save_failed || 'Failed to save tags') + ': ' + error.message, 'error');
    }
}

// Close modal when clicking outside of it
const memeModal = document.getElementById('meme-modal');
if (memeModal) {
    memeModal.addEventListener('click', function(event) {
        if (event.target === this) {
            closeMemeModal();
        }
    });
} else if (isConfigPage) {
    console.warn('Meme modal not found in DOM');
}
