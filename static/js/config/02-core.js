// Shared page state, the meme cache and loader, and initial page wiring.
// Part 2 of 8, split from config.js. Load order matters:
// these run as classic scripts sharing one global scope.

let currentConfig = {};
let configSchema = {};
let categories = [];
let colorOptions = [];
let configCurrentUser = '';
let pendingLanguageChange = null;
let memeToDelete = null;

// Dark mode management functions
function applyDarkMode(isDarkMode) {
    if (isDarkMode) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
}

function applyDarkModeFromStorage() {
    // Theme is applied server-side via body class — no client-side action needed
}

// Check if we're on the config page
const isConfigPage = window.location.pathname.includes('/config');

// Privacy: detect whether the configured mempool is a public (non-local) instance
// Returns false (safe) if the user has explicitly marked the instance as private.
function _isPublicMempool() {
    const cfg = window.currentConfig || {};
    // User has explicitly confirmed this instance is private/self-hosted
    if (cfg.mempool_is_private) return false;
    const host = (cfg.mempool_host || '127.0.0.1').trim().toLowerCase();
    if (!host || host === 'localhost') return false;
    // Private IPv4 ranges
    if (host.startsWith('127.') || host.startsWith('10.') || host.startsWith('192.168.')) return false;
    if (/^172\.(1[6-9]|2\d|3[01])\./.test(host)) return false;
    // IPv6 loopback
    if (host === '::1') return false;
    // Anything with a dot that isn't a private IP is public
    return true;
}

// Privacy: show warning when wallet monitoring uses a public mempool instance
// Returns a promise: true = user accepted, false = user declined
async function _showPrivacyWarning() {
    const t = window.translations || {};
    return showConfirmModal({
        title: t.privacy_warning_title || 'Privacy Warning',
        message: (t.privacy_warning_public_mempool || 'You are connected to a public Mempool instance. Querying wallet addresses or extended public keys (XPUB/ZPUB) exposes your entire wallet \u2014 all derived addresses, balances, and transaction history \u2014 to the server operator.')
            + '\n\n' + (t.privacy_warning_recommendation || 'For maximum privacy, use a self-hosted Mempool instance on your local network.'),
        confirmText: t.privacy_warning_accept || 'I understand the risks',
        cancelText: t.privacy_warning_decline || 'Cancel',
        danger: true
    });
}

// Privacy: host-change listener is now inline in the mempool_host field creation.
// This function is kept as a no-op for the setTimeout call in loadConfiguration.
function _initMempoolPrivacyWatch() {}

// Helper function to get the toggle key for a category
function getSectionToggleKey(categoryId) {
    const toggleMapping = {
        'price_stats': 'show_btc_price_block',
        'countdown': 'show_countdown_block',
        'halving': 'show_halving_block',
        'network_stats': 'show_network_block',
        'bitaxe_stats': 'show_bitaxe_block',
        'wallet_monitoring': 'show_wallet_balances_block',
        'eink_display': 'e-ink-display-connected',
        'donation': 'show_donation_block',
    };
    return toggleMapping[categoryId] || null;
}

// Create custom select dropdown for HTML content (like flag icons)
function createCustomSelect(field, value) {
    const container = document.createElement('div');
    container.className = 'custom-select-container';
    
    // Create the select button
    const selectButton = document.createElement('div');
    selectButton.className = 'form-select custom-select-trigger';
    selectButton.style.cursor = 'pointer';
    selectButton.style.userSelect = 'none';
    
    // Create dropdown list
    const dropdownList = document.createElement('div');
    dropdownList.className = 'custom-select-options';
    dropdownList.style.display = 'none';
    
    // Find the currently selected option
    let currentOption = field.options.find(opt => opt.value === value) || field.options[0];
    
    // Set initial button content
    function updateButtonDisplay(option) {
        if (option.flag && option.flag.includes('<img')) {
            selectButton.innerHTML = `${option.flag} <span style="margin-left: 8px;">${option.label}</span>`;
        } else if (option.flag) {
            selectButton.innerHTML = `<span style="margin-right: 8px;">${option.flag}</span>${option.label}`;
        } else {
            selectButton.textContent = option.label;
        }
    }
    
    updateButtonDisplay(currentOption);
    
    // Create options
    field.options.forEach(option => {
        const optionDiv = document.createElement('div');
        optionDiv.className = 'custom-select-option';
        optionDiv.style.cursor = 'pointer';
        optionDiv.setAttribute('data-value', option.value);
        
        if (option.flag && option.flag.includes('<img')) {
            optionDiv.innerHTML = `${option.flag} <span style="margin-left: 8px;">${option.label}</span>`;
        } else if (option.flag) {
            optionDiv.innerHTML = `<span style="margin-right: 8px;">${option.flag}</span>${option.label}`;
        } else {
            optionDiv.textContent = option.label;
        }
        
        // Mark current selection
        if (option.value === value) {
            optionDiv.classList.add('selected');
        }
        
        // Add click handler
        optionDiv.addEventListener('click', function(e) {
            e.stopPropagation();
            
            // Remove selected class from all options
            dropdownList.querySelectorAll('.custom-select-option').forEach(opt => {
                opt.classList.remove('selected');
            });
            
            // Add selected class to clicked option
            optionDiv.classList.add('selected');
            
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
    
    // Create hidden input for form compatibility
    const hiddenInput = document.createElement('input');
    hiddenInput.type = 'hidden';
    hiddenInput.value = value;
    
    // Toggle dropdown on button click
    selectButton.addEventListener('click', function(e) {
        e.stopPropagation();
        
        const isOpen = dropdownList.style.display === 'block';
        
        // Close all other custom selects
        document.querySelectorAll('.custom-select-container').forEach(container => {
            const options = container.querySelector('.custom-select-options');
            if (options && options !== dropdownList) {
                options.style.display = 'none';
                container.classList.remove('open');
            }
        });
        
        // Toggle this dropdown
        if (isOpen) {
            dropdownList.style.display = 'none';
            container.classList.remove('open');
        } else {
            dropdownList.style.display = 'block';
            container.classList.add('open');
        }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!container.contains(e.target)) {
            dropdownList.style.display = 'none';
            container.classList.remove('open');
        }
    });
    
    // Assemble the component
    container.appendChild(selectButton);
    container.appendChild(dropdownList);
    container.appendChild(hiddenInput);
    
    // Add value property for compatibility
    Object.defineProperty(container, 'value', {
        get: () => hiddenInput.value,
        set: (newValue) => {
            const option = field.options.find(opt => opt.value === newValue);
            if (option) {
                hiddenInput.value = newValue;
                updateButtonDisplay(option);
                currentOption = option;
                
                // Update selected state in options
                dropdownList.querySelectorAll('.custom-select-option').forEach(opt => {
                    opt.classList.toggle('selected', opt.getAttribute('data-value') === newValue);
                });
            }
        }
    });
    
    // Add addEventListener method for compatibility
    container.addEventListener = function(event, handler) {
        hiddenInput.addEventListener(event, handler);
    };
    
    // Add getValue method for form collection
    container.getValue = () => hiddenInput.value;
    
    return container;
}

// Create password change interface for password fields managed via button/form flow.
function createPasswordChangeInterface(key, field) {
    const container = document.createElement('div');
    container.className = 'password-change-container';
    
    // Create styled wrapper for the "Change Password" button (matches password form styling)
    const buttonWrapper = document.createElement('div');
    buttonWrapper.className = 'password-button-wrapper';
    buttonWrapper.style.padding = '15px';
    buttonWrapper.style.border = '1px solid #ddd';
    buttonWrapper.style.borderRadius = '4px';
    buttonWrapper.style.backgroundColor = 'var(--bg-color)';
    buttonWrapper.style.textAlign = 'center';
    
    // Create "Change Password" button
    const changeButton = document.createElement('button');
    changeButton.type = 'button';
    changeButton.className = 'form-button';
    changeButton.style.backgroundColor = '#F7931A';
    changeButton.style.color = 'white';
    changeButton.style.border = 'none';
    changeButton.style.padding = '8px 16px';
    changeButton.style.borderRadius = '4px';
    changeButton.style.cursor = 'pointer';
    changeButton.textContent = window.translations?.change_password || 'Change Password';
    
    // Create password change form (initially hidden)
    const passwordForm = document.createElement('form');
    passwordForm.className = 'password-change-form';
    passwordForm.style.display = 'none';
    passwordForm.style.marginTop = '10px';
    passwordForm.style.padding = '15px';
    passwordForm.style.border = '1px solid #ddd';
    passwordForm.style.borderRadius = '4px';
    passwordForm.style.backgroundColor = 'var(--bg-color)';
    passwordForm.onsubmit = e => e.preventDefault();
    // Hidden username field required by password managers / browser accessibility
    const _hiddenUser = document.createElement('input');
    _hiddenUser.type = 'text'; _hiddenUser.autocomplete = 'username';
    _hiddenUser.setAttribute('aria-hidden', 'true'); _hiddenUser.style.display = 'none';
    passwordForm.appendChild(_hiddenUser);

    // New password field
    const newPasswordLabel = document.createElement('label');
    newPasswordLabel.textContent = window.translations?.new_password || 'New Password';
    newPasswordLabel.style.display = 'block';
    newPasswordLabel.style.marginBottom = '5px';
    
    const newPasswordInput = document.createElement('input');
    newPasswordInput.type = 'password';
    newPasswordInput.className = 'form-input';
    newPasswordInput.placeholder = window.translations?.new_password || 'New Password';
    newPasswordInput.maxLength = 128;
    newPasswordInput.autocomplete = 'new-password';
    newPasswordInput.style.marginBottom = '6px';

    // Password strength checklist (admin_password only) or advisory (mempool_password)
    const pwFeedback = document.createElement('div');
    pwFeedback.style.marginBottom = '10px';
    let updateSaveState = () => {};
    if (key === 'admin_password') {
        pwFeedback.className = 'pw-strength';
        const tr = window.translations || {};
        const pwRules = [
            { re: null,              min: 16, label: tr.pw_rule_min_length || 'At least 16 characters' },
            { re: /[A-Z]/,           min: 0,  label: tr.pw_rule_uppercase  || 'Uppercase letter (A–Z)' },
            { re: /[a-z]/,           min: 0,  label: tr.pw_rule_lowercase  || 'Lowercase letter (a–z)' },
            { re: /[0-9]/,           min: 0,  label: tr.pw_rule_number     || 'Number (0–9)' },
            { re: /[^A-Za-z0-9]/,   min: 0,  label: tr.pw_rule_special    || 'Special character (!@#…)' },
        ];
        function renderPwStrength(pw) {
            pwFeedback.innerHTML = '';
            if (!pw) { pwFeedback.style.display = 'none'; return; }
            pwRules.forEach(r => {
                const ok = r.re ? r.re.test(pw) : pw.length >= r.min;
                const el = document.createElement('div');
                el.className = 'pw-rule' + (ok ? ' ok' : '');
                el.textContent = r.label;
                pwFeedback.appendChild(el);
            });
            pwFeedback.style.display = 'flex';
        }
        updateSaveState = () => {
            const pw = newPasswordInput.value;
            const conf = confirmPasswordInput.value;
            const allPass = pwRules.every(r => r.re ? r.re.test(pw) : pw.length >= r.min);
            saveButton.disabled = !(allPass && conf.length > 0 && pw === conf);
        };
        newPasswordInput.addEventListener('input', () => {
            renderPwStrength(newPasswordInput.value);
            errorMessage.style.display = 'none';
            updateSaveState();
        });
        newPasswordInput.addEventListener('blur', () => {
            if (newPasswordInput.value) renderPwStrength(newPasswordInput.value);
        });
    }

    // Confirm password field
    const confirmPasswordLabel = document.createElement('label');
    confirmPasswordLabel.textContent = window.translations?.confirm_password || 'Confirm Password';
    confirmPasswordLabel.style.display = 'block';
    confirmPasswordLabel.style.marginBottom = '5px';

    const confirmPasswordInput = document.createElement('input');
    confirmPasswordInput.type = 'password';
    confirmPasswordInput.className = 'form-input';
    confirmPasswordInput.placeholder = window.translations?.confirm_password || 'Confirm Password';
    confirmPasswordInput.maxLength = 128;
    confirmPasswordInput.autocomplete = 'new-password';
    confirmPasswordInput.style.marginBottom = '6px';

    // Live match indicator below confirm field
    const matchHint = document.createElement('div');
    matchHint.style.cssText = 'font-size:0.82rem; margin-bottom:10px; display:none;';
    function updateMatchHint() {
        const a = newPasswordInput.value;
        const b = confirmPasswordInput.value;
        if (!b) { matchHint.style.display = 'none'; return; }
        const match = a === b;
        matchHint.style.display = 'flex';
        matchHint.style.alignItems = 'center';
        matchHint.style.gap = '7px';
        matchHint.style.color = match ? 'var(--success)' : 'var(--danger)';
        matchHint.textContent = match
            ? (window.translations?.passwords_match || 'Passwords match')
            : (window.translations?.passwords_do_not_match || 'Passwords do not match');
    }
    confirmPasswordInput.addEventListener('input', () => { updateMatchHint(); updateSaveState(); });
    newPasswordInput.addEventListener('input', updateMatchHint);

    // Error message div
    const errorMessage = document.createElement('div');
    errorMessage.className = 'password-error';
    errorMessage.style.color = 'red';
    errorMessage.style.marginBottom = '10px';
    errorMessage.style.display = 'none';
    
    // Action buttons container
    const buttonContainer = document.createElement('div');
    buttonContainer.style.display = 'flex';
    buttonContainer.style.gap = '10px';
    
    // Save button
    const saveButton = document.createElement('button');
    saveButton.type = 'button';
    saveButton.className = 'form-button pw-save-btn';
    saveButton.textContent = window.translations?.save || 'Save';
    if (key === 'admin_password') saveButton.disabled = true;

    // Cancel button
    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'form-button';
    cancelButton.style.backgroundColor = '#666';
    cancelButton.style.color = 'white';
    cancelButton.style.border = 'none';
    cancelButton.style.padding = '8px 16px';
    cancelButton.style.borderRadius = '4px';
    cancelButton.style.cursor = 'pointer';
    cancelButton.textContent = window.translations?.cancel || 'Cancel';
    
    // Event handlers
    changeButton.addEventListener('click', () => {
        passwordForm.style.display = 'block';
        buttonWrapper.style.display = 'none';
        if (key === 'admin_password') saveButton.disabled = true;
        newPasswordInput.focus();
        // Pre-size button once to the saving-state width so it never shifts during save
        if (key === 'admin_password' && !saveButton._widthSet) {
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
        buttonWrapper.style.display = 'block';
        newPasswordInput.value = '';
        confirmPasswordInput.value = '';
        errorMessage.style.display = 'none';
        if (key === 'admin_password') { pwFeedback.innerHTML = ''; pwFeedback.style.display = 'none'; saveButton.disabled = true; }
        matchHint.style.display = 'none';
    });

    saveButton.addEventListener('click', async () => {
        const newPassword = newPasswordInput.value;
        const confirmPassword = confirmPasswordInput.value;

        // Validate passwords
        if (!newPassword || !confirmPassword) {
            errorMessage.textContent = 'Please fill in both password fields';
            errorMessage.style.display = 'block';
            return;
        }
        
        if (newPassword !== confirmPassword) {
            errorMessage.textContent = window.translations?.passwords_do_not_match || 'Passwords do not match';
            errorMessage.style.display = 'block';
            return;
        }

        const failedRules = key === 'admin_password'
            ? pwRules.filter(r => !(r.re ? r.re.test(newPassword) : newPassword.length >= r.min))
            : [];
        if (failedRules.length > 0) {
            // Force checklist visible so user sees exactly what's missing
            renderPwStrength(newPassword);
            errorMessage.textContent = window.translations?.password_too_short || 'Password does not meet requirements';
            errorMessage.style.display = 'block';
            return;
        }
        if (newPassword.length > 128) {
            errorMessage.textContent = window.translations?.password_too_long || 'Password too long (max 128 characters)';
            errorMessage.style.display = 'block';
            return;
        }

        // Save the password
        try {
            saveButton.disabled = true;
            saveButton.innerHTML = `${window.translations?.saving || 'Saving'}<span class="mpa-dots"></span>`;

            // Update the config with new password
            currentConfig[key] = newPassword;
            await saveConfiguration();

            // Hide form and show success
            passwordForm.style.display = 'none';
            buttonWrapper.style.display = 'block';
            newPasswordInput.value = '';
            confirmPasswordInput.value = '';
            errorMessage.style.display = 'none';

            // Show success message
            showNotification(window.translations?.password_changed_successfully || 'Password changed successfully', 'success');

        } catch (error) {
            console.error('Error changing password:', error);
            errorMessage.textContent = window.translations?.password_change_failed || 'Failed to change password';
            errorMessage.style.display = 'block';
        } finally {
            saveButton.textContent = window.translations?.save || 'Save';
            updateSaveState();
        }
    });

    // Assemble the form
    passwordForm.appendChild(newPasswordLabel);
    passwordForm.appendChild(newPasswordInput);
    passwordForm.appendChild(pwFeedback);
    passwordForm.appendChild(confirmPasswordLabel);
    passwordForm.appendChild(confirmPasswordInput);
    passwordForm.appendChild(matchHint);
    passwordForm.appendChild(errorMessage);
    buttonContainer.appendChild(saveButton);
    buttonContainer.appendChild(cancelButton);
    passwordForm.appendChild(buttonContainer);
    
    // Assemble the button wrapper
    buttonWrapper.appendChild(changeButton);
    
    // Assemble the container
    container.appendChild(buttonWrapper);
    container.appendChild(passwordForm);
    
    // Set data-config-key for form collection
    container.dataset.configKey = key;
    
    // Add getValue method for form collection compatibility
    container.getValue = () => {
        // For password change interface, we don't want to return the current value
        // The password change will be handled separately
        return undefined;
    };
    
    // Add value property for compatibility (but it won't be used for saving)
    Object.defineProperty(container, 'value', {
        get: () => undefined,
        set: () => {} // Do nothing - password changes are handled separately
    });
    
    return container;
}

// Load configuration on page load
document.addEventListener('DOMContentLoaded', () => {
    loadConfiguration();
    loadMemes();
    // Reverted: No injected viewport meta, no centering or max-width styles

    setupUpload();
    setupModals();
    // Always register and subscribe for block notifications if authenticated
    registerPageForNotifications('config');
    subscribeToBlockNotifications();
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
    
    // Apply dark mode from localStorage if available
    applyDarkModeFromStorage();
});

// Setup modal functionality
function setupModals() {
    // Delete confirmation modal
    const confirmDeleteBtn = document.getElementById('confirm-delete');
    const cancelDeleteBtn = document.getElementById('cancel-delete');
    
    if (confirmDeleteBtn) {
        confirmDeleteBtn.onclick = async () => {
            if (memeToDelete) {
                await deleteMeme(memeToDelete);
                hideDeleteModal();
            }
        };
    }
    
    if (cancelDeleteBtn) {
        cancelDeleteBtn.onclick = () => {
            hideDeleteModal();
        };
    }
}

// Modal helper functions
function showDeleteModal(filename) {
    memeToDelete = filename;
    const deleteModal = document.getElementById('delete-modal');
    if (deleteModal) {
        deleteModal.style.display = 'flex';
    } else if (isConfigPage) {
        console.warn('Delete modal not found in DOM');
    }
}

function hideDeleteModal() {
    memeToDelete = null;
    const deleteModal = document.getElementById('delete-modal');
    if (deleteModal) {
        deleteModal.style.display = 'none';
    } else if (isConfigPage) {
        console.warn('Delete modal not found');
    }
}

// Setup upload functionality
function setupUpload() {
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    
    if (!uploadArea || !fileInput) {
        return;
    }
    
    uploadArea.addEventListener('click', () => fileInput.click());
    
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const files = Array.from(e.dataTransfer.files);
        if (files.length > 0) {
            uploadFiles(files).catch(err => reportUploadFailure('upload-status', err));
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            uploadFiles(Array.from(e.target.files)).catch(err => reportUploadFailure('upload-status', err));
        }
        // Reset input to allow re-uploading the same file
        e.target.value = '';
    });
}

// Global set of existing meme filenames for client-side duplicate name checking
window.memeFilenameSet = new Set();

// Calculate SHA-256 hash of file content for duplicate detection
async function calculateFileHash(file) {
    try {
        const arrayBuffer = await file.arrayBuffer();
        const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        return hashHex;
    } catch (error) {
        console.error('Failed to calculate file hash:', error);
        return null;
    }
}

// Surface an upload failure in the UI. Without this, an exception thrown inside
// an async upload becomes an unhandled rejection: the progress bar stays visible
// and frozen on whatever status line was last written, which is indistinguishable
// from an upload that is still working.
function reportUploadFailure(statusElementId, error) {
    console.error('Upload failed:', error);

    const statusText = document.getElementById(statusElementId);
    if (statusText) {
        const label = window.translations?.upload_failed || 'Upload failed';
        statusText.textContent = `${label}: ${error?.message || error}`;
        statusText.style.color = '#e53e3e';
    }
    showNotification(window.translations?.upload_failed || 'Upload failed', 'error');
}

// Build a URL by appending a filename as a single path segment.
// Filenames are server-supplied (and for synced memes ultimately external), and
// land in src/href attributes; encoding the segment stops a name containing
// '../', '?' or '#' from changing which resource the browser actually requests.
function assetUrl(prefix, filename) {
    return prefix + encodeURIComponent(filename);
}

// Reduce a configured host to the characters legal in host[:port] (including
// brackets for IPv6) before it is interpolated into a URL, so a config value
// cannot smuggle in a path, a query or a different scheme.
function sanitizeHost(host) {
    return String(host == null ? '' : host).replace(/[^A-Za-z0-9.\-:[\]]/g, '');
}

// Build a meme/OPSec action button (download, delete, ...).
//
// The handler is attached as a function rather than written into an inline
// onclick attribute with the filename interpolated into it. escapeHtml() does
// not escape single quotes, so a filename like  x');alert(1);//  would leave the
// HTML attribute intact while breaking out of the handler's JS string.
function buildActionButton(iconName, label, extraClass, onClick) {
    const btn = document.createElement('button');
    btn.className = extraClass ? `action-button ${extraClass}` : 'action-button';
    btn.title = label;

    const icon = document.createElement('img');
    icon.src = `/static/icons/${iconName}.svg`;
    icon.alt = label;
    icon.style.cssText = 'width:16px; height:16px; filter:brightness(0) invert(1);';

    btn.appendChild(icon);
    btn.addEventListener('click', onClick);
    return btn;
}

// Populate a meme thumbnail's action row and filename label.
// Built as elements rather than markup: the filename comes from the server (and
// for synced memes, ultimately from an external source), and was previously
// interpolated both into an inline onclick and into the label's HTML.
function renderMemeThumbBody(memeDiv, meme) {
    const actions = document.createElement('div');
    actions.className = 'meme-actions';
    actions.append(
        buildActionButton('download', window.translations?.download_meme || 'Download', '',
            () => downloadMeme(meme.filename)),
        buildActionButton('delete', window.translations?.delete_meme || 'Delete', 'delete',
            () => showDeleteModal(meme.filename))
    );

    const name = document.createElement('div');
    name.className = 'meme-filename';
    name.textContent = meme.filename;

    memeDiv.replaceChildren(actions, name);
}

// Get all existing OPSec image hashes from server
async function getExistingOpsecHashes() {
    try {
        const response = await fetch('/api/opsec-hashes');
        if (response.ok) {
            const data = await response.json();
            return data.hashes || {}; // Returns {hash: filename, ...}
        }
    } catch (error) {
        console.warn('Failed to fetch existing OPSec hashes:', error);
    }
    return {};
}

// Get all existing meme hashes from server
async function getExistingMemeHashes() {
    try {
        const response = await fetch('/api/meme-hashes');
        if (response.ok) {
            const data = await response.json();
            return data.hashes || {}; // Returns {hash: filename, ...}
        }
    } catch (error) {
        console.warn('Failed to fetch existing meme hashes:', error);
    }
    return {};
}

// Show rename dialog for a file when a filename conflict is detected.
// suggestedFilename: pre-corrected full filename (e.g. "my_pic_1.png")
// existingFilenames: Set of filenames already present on the server
async function showRenameDialog(originalFilename, file, suggestedFilename, existingFilenames) {
    const extension = suggestedFilename.substring(suggestedFilename.lastIndexOf('.'));
    const suggestedNameWithoutExt = suggestedFilename.substring(0, suggestedFilename.lastIndexOf('.'));
    const t = window.translations;

    const previewUrl = file ? URL.createObjectURL(file) : null;

    return new Promise((resolve) => {
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.style.display = 'flex';

        // Built as elements rather than markup: the filename comes from the
        // user's own file picker and previously reached an alt attribute, a
        // <strong> body and an input value through innerHTML.
        const content = document.createElement('div');
        content.className = 'modal-content';
        content.style.maxWidth = '400px';

        const heading = document.createElement('h3');
        heading.textContent = t?.rename_image || 'Rename Image';
        content.appendChild(heading);

        if (previewUrl) {
            const previewWrap = document.createElement('div');
            previewWrap.style.cssText = 'text-align: center; margin-bottom: 15px;';
            const previewImg = document.createElement('img');
            // createObjectURL only ever mints blob:<origin>/<uuid> - nothing from
            // the file or its name reaches the URL - and img.src does not execute
            // javascript: URLs. CodeQL taints the result through createObjectURL.
            // codeql[js/xss-through-dom]
            previewImg.src = previewUrl;
            previewImg.alt = originalFilename;
            previewImg.style.cssText = 'max-width: 150px; max-height: 150px; object-fit: contain; border-radius: 6px; border: 1px solid #ddd;';
            previewWrap.appendChild(previewImg);
            content.appendChild(previewWrap);
        }

        const info = document.createElement('p');
        info.style.cssText = 'margin-bottom: 8px; color: #6a6a78;';
        const nameEl = document.createElement('strong');
        nameEl.textContent = originalFilename;
        info.append(
            (t?.rename_conflict_info || 'A file named') + ' ',
            nameEl,
            ' ' + (t?.rename_conflict_exists || 'already exists.')
        );
        content.appendChild(info);

        const label = document.createElement('label');
        label.style.cssText = 'display: block; margin-bottom: 5px; font-weight: 600;';
        label.textContent = t?.rename_new_name || 'New name (without extension):';
        content.appendChild(label);

        const input = document.createElement('input');
        input.type = 'text';
        input.id = 'rename-input';
        input.className = 'form-input';
        input.value = suggestedNameWithoutExt;
        input.style.marginBottom = '5px';
        content.appendChild(input);

        const warning = document.createElement('p');
        warning.id = 'rename-name-warning';
        warning.style.cssText = 'font-size: 0.85rem; color: #e53e3e; margin-bottom: 5px; display: none;';
        warning.textContent = t?.rename_name_in_use || 'This name is already in use. Please choose a different name.';
        content.appendChild(warning);

        const extNote = document.createElement('p');
        extNote.style.cssText = 'font-size: 0.85rem; color: #F7931A; margin-bottom: 15px;';
        extNote.textContent = (t?.rename_extension_preserved || 'Extension {ext} will be preserved')
            .replace('{ext}', extension);
        content.appendChild(extNote);

        const buttons = document.createElement('div');
        buttons.className = 'modal-buttons';
        buttons.style.cssText = 'display: flex; gap: 10px;';
        const confirmBtn = document.createElement('button');
        confirmBtn.id = 'rename-confirm';
        confirmBtn.className = 'save-button';
        confirmBtn.style.flex = '1';
        confirmBtn.textContent = t?.rename_confirm || 'Rename';
        const skipBtn = document.createElement('button');
        skipBtn.id = 'rename-skip';
        skipBtn.className = 'cancel-button';
        skipBtn.style.flex = '1';
        skipBtn.textContent = t?.rename_keep_original || 'Keep Original';
        buttons.append(confirmBtn, skipBtn);
        content.appendChild(buttons);

        modal.appendChild(content);
        document.body.appendChild(modal);

        const validateInput = () => {
            const candidate = input.value.trim() + extension;
            const conflict = existingFilenames && existingFilenames.has(candidate);
            warning.style.display = conflict ? 'block' : 'none';
            confirmBtn.disabled = conflict || !input.value.trim();
            confirmBtn.style.opacity = confirmBtn.disabled ? '0.5' : '';
            confirmBtn.style.cursor = confirmBtn.disabled ? 'not-allowed' : '';
        };

        input.addEventListener('input', validateInput);
        validateInput();
        input.focus();
        input.select();

        const cleanup = () => {
            modal.remove();
            if (previewUrl) URL.revokeObjectURL(previewUrl);
        };

        confirmBtn.onclick = () => {
            if (confirmBtn.disabled) return;
            const newName = input.value.trim();
            cleanup();
            resolve(newName + extension);
        };

        skipBtn.onclick = () => {
            cleanup();
            resolve(suggestedFilename);
        };

        input.onkeydown = (e) => {
            if (e.key === 'Enter') {
                confirmBtn.click();
            } else if (e.key === 'Escape') {
                skipBtn.click();
            }
        };
    });
}

// Upload multiple files with duplicate detection and rename capability
async function uploadFiles(files) {
    const progressDiv = document.getElementById('upload-progress');
    const progressBar = document.getElementById('progress-bar');
    const statusText = document.getElementById('upload-status');
    
    if (!files || files.length === 0) return;
    
    const t = window.translations;

    // Show progress
    if (progressDiv && progressBar && statusText) {
        progressDiv.style.display = 'block';
        progressBar.style.transform = 'scaleX(0)';
        statusText.textContent = t?.upload_checking_duplicates || 'Checking for duplicates...';
        statusText.style.color = '#F7931A';
    }

    // Get existing hashes
    const existingHashes = await getExistingMemeHashes();

    // Build a working set of filenames (server state + files queued this batch)
    const existingFilenames = new Set(Object.values(existingHashes));

    // Process files: check duplicates and handle name conflicts
    const filesToUpload = [];
    const duplicates = [];

    for (let i = 0; i < files.length; i++) {
        const file = files[i];

        if (statusText) {
            statusText.textContent = (t?.upload_processing || 'Processing {current}/{total}: {filename}...')
                .replace('{current}', i + 1).replace('{total}', files.length).replace('{filename}', file.name);
        }

        // Calculate hash for content-duplicate detection
        const hash = await calculateFileHash(file);

        // Skip content-identical files
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
    
    // Show summary
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
    
    // Show duplicate details if any
    if (duplicates.length > 0) {
        const dupList = duplicates.map(d => `• ${d.name} (duplicate of ${d.duplicate})`).join('\n');
        showNotification((t?.upload_duplicates_skipped_notification || '{count} duplicate file(s) skipped').replace('{count}', duplicates.length), 'warning');
    }
    
    // Upload files one by one
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
                const response = await fetch('/api/upload-meme', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if (result.success) {
                    uploadedCount++;
                    window.memeFilenameSet.add(name);
                } else {
                    failedCount++;
                    console.error(`Failed to upload ${name}:`, result.message);
                }
            } catch (error) {
                failedCount++;
                console.error(`Error uploading ${name}:`, error);
            }
        }
        
        if (progressBar) {
            progressBar.style.transform = 'scaleX(1)';
        }

        // Show final status
        if (statusText) {
            const parts = [];
            if (uploadedCount > 0) {
                parts.push((t?.upload_count_uploaded || '✓ {count} uploaded').replace('{count}', uploadedCount));
            }
            if (failedCount > 0) {
                parts.push((t?.upload_count_failed || '✗ {count} failed').replace('{count}', failedCount));
            }
            if (duplicates.length > 0) {
                parts.push((t?.upload_count_skipped || '⊝ {count} skipped (duplicates)').replace('{count}', duplicates.length));
            }

            statusText.textContent = parts.join(' | ');
            statusText.style.color = failedCount > 0 ? '#e53e3e' : '#38a169';
        }
        
        // Clear cache and reload memes
        if (uploadedCount > 0) {
            clearMemeCache();
            // Add new memes to the list without reloading entire page
            loadMemes();
        }
        
        // Hide progress after delay
        setTimeout(() => {
            if (progressDiv) {
                progressDiv.style.display = 'none';
            }
        }, 4000);
        
        // Show summary notification
        if (uploadedCount > 0) {
            showNotification((t?.upload_success_notification || 'Successfully uploaded {count} file(s)').replace('{count}', uploadedCount), 'success');
        }
        if (failedCount > 0) {
            showNotification((t?.upload_fail_notification || 'Failed to upload {count} file(s)').replace('{count}', failedCount), 'error');
        }
    } else {
        // No files to upload
        setTimeout(() => {
            if (progressDiv) {
                progressDiv.style.display = 'none';
            }
        }, 3000);
    }
}

// Legacy single file upload (kept for backwards compatibility)
async function uploadFile(file) {
    await uploadFiles([file]);
}

// Download meme function
async function downloadMeme(filename) {
    try {
        const response = await fetch(`/api/download-meme/${filename}`);
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } else {
            showNotification(window.translations.download_failed, 'error');
        }
    } catch (error) {
        showNotification(window.translations.download_failed + ': ' + error.message, 'error');
    }
}

// Delete meme function
async function deleteMeme(filename) {
    try {
        const response = await fetch(`/api/delete-meme/${filename}`, {
            method: 'DELETE'
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(window.translations.meme_deleted_successfully, 'success');
            clearMemeCache(); // Clear cache
            window.memeFilenameSet.delete(filename);

            // Find and remove the meme element from the DOM without reloading the page
            const memesList = document.getElementById('memes-list');
            if (memesList) {
                // Find the image element with matching filename
                const imgElement = memesList.querySelector(`img[data-filename="${filename}"]`);
                if (imgElement) {
                    // Find the parent meme-thumbnail div and remove it
                    const memeDiv = imgElement.closest('.meme-thumbnail');
                    if (memeDiv) {
                        memeDiv.remove();
                        
                        // Update total count
                        if (memeLoader && memeLoader.totalMemes > 0) {
                            memeLoader.totalMemes--;
                        }
                        
                        // Check if list is now empty
                        const remainingMemes = memesList.querySelectorAll('.meme-thumbnail');
                        if (remainingMemes.length === 0) {
                            const loadMoreBtn = memesList.querySelector('.load-more-btn');
                            if (!loadMoreBtn) {
                                // No more memes and no load more button
                                memesList.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">${window.translations.no_memes_uploaded}</p>`;
                            }
                        }
                    }
                }
            }
        } else {
            showNotification(result.message || window.translations.meme_delete_failed, 'error');
        }
    } catch (error) {
        showNotification(window.translations.meme_delete_failed + ': ' + error.message, 'error');
    }
}

// Rename meme function
async function renameMeme(oldFilename, newFilename) {
    try {
        const response = await fetch('/api/rename-meme', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                old_filename: oldFilename,
                new_filename: newFilename
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(window.translations.meme_renamed_successfully || 'Meme renamed successfully', 'success');
            clearMemeCache();
            window.memeFilenameSet.delete(oldFilename);
            window.memeFilenameSet.add(newFilename);
            
            // Update the meme element in the DOM without reloading
            const memesList = document.getElementById('memes-list');
            if (memesList) {
                const imgElement = memesList.querySelector(`img[data-filename="${oldFilename}"]`);
                if (imgElement) {
                    const memeDiv = imgElement.closest('.meme-thumbnail');
                    if (memeDiv) {
                        // Update the filename in data attribute
                        imgElement.dataset.filename = newFilename;
                        
                        // Update URL if needed
                        const newUrl = assetUrl('/static/memes/', newFilename);
                        imgElement.dataset.url = newUrl;
                        if (imgElement.src && !imgElement.src.includes('data:image/svg')) {
                            imgElement.src = newUrl;
                        }
                        
                        // Update the filename display
                        const filenameDiv = memeDiv.querySelector('.meme-filename');
                        if (filenameDiv) {
                            filenameDiv.textContent = newFilename;
                        }
                        
                        // Update action buttons to use new filename
                        const actionsDiv = memeDiv.querySelector('.meme-actions');
                        if (actionsDiv) {
                            actionsDiv.replaceChildren(
                                buildActionButton('download', window.translations?.download_meme || 'Download', '',
                                    () => downloadMeme(newFilename)),
                                buildActionButton('delete', window.translations?.delete_meme || 'Delete', 'delete',
                                    () => showDeleteModal(newFilename))
                            );
                        }
                        
                        // Update onclick for the image (preserve tags from current modal)
                        const currentTags = currentModalMeme?.tags || [];
                        const currentApiTags = currentModalMeme?.apiTags || [];
                        imgElement.onclick = () => openMemeModal(newFilename, newUrl, currentTags, currentApiTags);
                    }
                }
            }
        } else {
            showNotification(result.message || window.translations.meme_rename_failed || 'Failed to rename meme', 'error');
        }
    } catch (error) {
        showNotification((window.translations.meme_rename_failed || 'Failed to rename meme') + ': ' + error.message, 'error');
    }
}

// Inline rename functions for preview modal
function startRenameInModal() {
    if (!currentModalMeme) return;

    const filenameDisplay = document.getElementById('meme-modal-filename-display');
    const filenameInput = document.getElementById('meme-modal-filename-input');
    const editBtn = document.getElementById('meme-modal-edit-btn');
    const saveBtn = document.getElementById('meme-modal-save-btn');
    const cancelBtn = document.getElementById('meme-modal-cancel-rename-btn');
    const renameActions = document.getElementById('meme-rename-actions');
    const warning = document.getElementById('meme-modal-rename-warning');

    if (!filenameDisplay || !filenameInput || !editBtn || !saveBtn || !cancelBtn) return;

    const filename = currentModalMeme.filename;
    const extension = filename.substring(filename.lastIndexOf('.'));
    const nameWithoutExt = filename.substring(0, filename.lastIndexOf('.'));

    // Switch to edit mode
    filenameDisplay.style.display = 'none';
    editBtn.style.display = 'none';
    filenameInput.style.display = 'inline-block';
    if (renameActions) renameActions.style.display = 'flex';

    filenameInput.value = nameWithoutExt;
    filenameInput.focus();
    filenameInput.select();

    // Live validation: block saving if the chosen name is already in use by another file
    const validateModalInput = () => {
        const val = filenameInput.value.trim();
        const candidate = val + extension;
        const conflict = candidate !== filename && window.memeFilenameSet.has(candidate);
        const unchanged = val === nameWithoutExt.trim();
        if (warning) {
            warning.textContent = conflict
                ? (window.translations?.rename_name_in_use || 'This name is already in use. Please choose a different name.')
                : '';
            warning.style.display = conflict ? 'block' : 'none';
        }
        if (!val || conflict || unchanged) {
            saveBtn.disabled = true;
            saveBtn.classList.remove('rename-dirty');
            saveBtn.classList.add('rename-clean');
        } else {
            saveBtn.disabled = false;
            saveBtn.classList.remove('rename-clean');
            saveBtn.classList.add('rename-dirty');
        }
    };

    // Remove any previous listener before adding a new one
    filenameInput._modalValidate && filenameInput.removeEventListener('input', filenameInput._modalValidate);
    filenameInput._modalValidate = validateModalInput;
    filenameInput.addEventListener('input', validateModalInput);
    validateModalInput();

    filenameInput.onkeydown = (e) => {
        if (e.key === 'Enter') {
            saveRenameInModal();
        } else if (e.key === 'Escape') {
            cancelRenameInModal();
        }
    };
}

async function saveRenameInModal() {
    if (!currentModalMeme) return;

    const filenameInput = document.getElementById('meme-modal-filename-input');
    const saveBtn = document.getElementById('meme-modal-save-btn');
    if (!filenameInput) return;

    // Guard: respect disabled state set by live validation
    if (saveBtn && saveBtn.disabled) return;

    const oldFilename = currentModalMeme.filename;
    const extension = oldFilename.substring(oldFilename.lastIndexOf('.'));
    const nameWithoutExt = oldFilename.substring(0, oldFilename.lastIndexOf('.'));
    const newName = filenameInput.value.trim();

    if (!newName) {
        showNotification(window.translations?.please_enter_valid_name || 'Please enter a valid name', 'error');
        return;
    }

    if (newName === nameWithoutExt) {
        // No change, just cancel
        cancelRenameInModal();
        return;
    }

    const newFilename = newName + extension;

    // Final guard: check the set once more before the API call
    if (window.memeFilenameSet.has(newFilename)) {
        showNotification(window.translations?.rename_name_in_use || 'This name is already in use. Please choose a different name.', 'error');
        return;
    }

    // Perform the rename
    await renameMeme(oldFilename, newFilename);

    // Update modal with new filename
    currentModalMeme.filename = newFilename;
    currentModalMeme.url = assetUrl('/static/memes/', newFilename);

    // Update display
    const filenameDisplay = document.getElementById('meme-modal-filename-display');
    const modalTitle = document.getElementById('meme-modal-title');
    if (filenameDisplay) {
        filenameDisplay.textContent = newFilename;
    }
    if (modalTitle) {
        const previewText = window.translations?.meme_preview || 'Meme Preview';
        modalTitle.textContent = `${previewText} - ${newFilename}`;
    }

    // Exit edit mode
    cancelRenameInModal();
}

function cancelRenameInModal() {
    const filenameDisplay = document.getElementById('meme-modal-filename-display');
    const filenameInput = document.getElementById('meme-modal-filename-input');
    const editBtn = document.getElementById('meme-modal-edit-btn');
    const saveBtn = document.getElementById('meme-modal-save-btn');
    const cancelBtn = document.getElementById('meme-modal-cancel-rename-btn');
    const renameActions = document.getElementById('meme-rename-actions');
    const warning = document.getElementById('meme-modal-rename-warning');

    if (!filenameDisplay || !filenameInput || !editBtn || !saveBtn || !cancelBtn) return;

    // Switch back to display mode
    filenameDisplay.style.display = 'inline';
    editBtn.style.display = 'inline-block';
    filenameInput.style.display = 'none';
    if (renameActions) renameActions.style.display = 'none';
    saveBtn.disabled = false;
    saveBtn.classList.remove('rename-dirty', 'rename-clean');
    if (warning) { warning.style.display = 'none'; warning.textContent = ''; }
}

// Load memes function
// Meme cache management
class MemeCache {
    constructor() {
        this.cache = new Map();
        this.loadFromStorage();
    }
    
    loadFromStorage() {
        try {
            const stored = localStorage.getItem('meme_cache');
            if (stored) {
                const data = JSON.parse(stored);
                // Only use cache if it's less than 1 hour old
                if (Date.now() - data.timestamp < 3600000) {
                    this.cache = new Map(data.memes);
                }
            }
        } catch (e) {
            console.warn('Failed to load meme cache:', e);
        }
    }
    
    saveToStorage() {
        try {
            const data = {
                timestamp: Date.now(),
                memes: Array.from(this.cache.entries())
            };
            localStorage.setItem('meme_cache', JSON.stringify(data));
        } catch (e) {
            console.warn('Failed to save meme cache:', e);
        }
    }
    
    get(filename) {
        return this.cache.get(filename);
    }
    
    set(filename, data) {
        this.cache.set(filename, data);
        this.saveToStorage();
    }
    
    clear() {
        this.cache.clear();
        localStorage.removeItem('meme_cache');
    }
}

// Global meme cache instance
const memeCache = new MemeCache();

// Lazy loading implementation
class MemeLoader {
    constructor() {
        this.loadedPages = new Set();
        this.isLoading = false;
        this.totalMemes = 0;
        this.perPage = 50;
        this.observer = null;
        this.setupIntersectionObserver();
    }
    
    setupIntersectionObserver() {
        // Set up intersection observer for lazy loading
        this.observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    this.loadImageForElement(entry.target);
                }
            });
        }, {
            rootMargin: '400px'
        });
    }
    
    async loadImageForElement(imgElement) {
        if (imgElement.classList.contains('loaded')) {
            return; // Already loaded
        }

        const filename = imgElement.dataset.filename;
        const url = imgElement.dataset.url;

        if (!filename || !url) return;

        this.observer.unobserve(imgElement);

        const cached = memeCache.get(filename);
        const actualUrl = (cached && cached.url) ? cached.url : url;

        imgElement.onload = () => {
            imgElement.style.transition = 'none';
            imgElement.classList.add('loaded');
            imgElement.onload = null;
            imgElement.onerror = null;
            if (!cached) memeCache.set(filename, { url: actualUrl, loaded: Date.now() });
            requestAnimationFrame(() => requestAnimationFrame(() => {
                imgElement.style.transition = '';
            }));
        };
        imgElement.onerror = () => {
            imgElement.classList.add('error');
            imgElement.onload = null;
            imgElement.onerror = null;
        };
        imgElement.src = actualUrl;
    }
    
    async loadMemePage(page = 1, search = '') {
        // Only block if currently loading this page
        if (this.isLoading) {
            return null;
        }
        this.isLoading = true;
        try {
            let url = `/api/memes?page=${page}&per_page=${this.perPage}`;
            if (search) url += `&search=${encodeURIComponent(search)}`;
            const response = await fetch(url);
            const data = await response.json();
            this.totalMemes = data.total;
            // Only mark page as loaded if fetch succeeded and no search filter
            if (!search && data && data.memes && data.memes.length > 0) {
                this.loadedPages.add(page);
            }
            return data;
        } catch (error) {
            console.error('Failed to load memes page:', page, error);
            return null;
        } finally {
            this.isLoading = false;
        }
    }
}

// Global meme loader instance
const memeLoader = new MemeLoader();

// Current meme search term
let currentMemeSearch = '';
let memeLoadGeneration = 0;

async function loadMemes(search = '') {
    currentMemeSearch = search;
    const thisGen = ++memeLoadGeneration;
    // Cancel any in-flight scroll load so it doesn't block or corrupt the new search
    memeLoader.isLoading = false;
    memeScrollLoading = false;
    if (memeScrollObserver) { memeScrollObserver.disconnect(); memeScrollObserver = null; }
    try {
        const memesList = document.getElementById('memes-list');
        if (!memesList) {
            return;
        }
        // Show loading indicator
        memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">Loading memes...</div>';
        // Load first page
        const data = await memeLoader.loadMemePage(1, search);
        // Bail out if a newer search superseded this one while we were waiting
        if (thisGen !== memeLoadGeneration) return;
        if (!data) {
            memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--danger);">Failed to load memes</div>';
            return;
        }
        memesList.innerHTML = '';

        // Update count label
        const memeCountLabel = document.getElementById('meme-image-count');
        if (memeCountLabel) memeCountLabel.textContent = `(${data.total || 0})`;

        // Rebuild filename set from loaded page
        window.memeFilenameSet = new Set();
        if (data.memes && data.memes.length > 0) {
            data.memes.forEach(meme => {
                window.memeFilenameSet.add(meme.filename);
                const memeDiv = document.createElement('div');
                memeDiv.className = 'meme-thumbnail';
                // Create placeholder image with lazy loading
                const img = document.createElement('img');
                img.dataset.filename = meme.filename;
                img.dataset.url = meme.thumb_url || meme.url;
                img.alt = meme.filename;
                img.style.cursor = 'pointer';
                img.title = 'Click to inspect';
                img.onclick = () => openMemeModal(meme.filename, meme.url, meme.tags || [], meme.api_tags || []);
                // Add placeholder until loaded
                img.src = '/static/icons/image.svg';
                img.classList.add('meme-lazy');
                // Set up lazy loading observer
                memeLoader.observer.observe(img);
                renderMemeThumbBody(memeDiv, meme);
                // Insert the image at the beginning
                memeDiv.insertBefore(img, memeDiv.firstChild);
                memesList.appendChild(memeDiv);
            });
            // Add infinite scroll sentinel if there are more pages
            if (data.has_next) {
                const sentinel = document.createElement('div');
                sentinel.className = 'meme-scroll-sentinel';
                sentinel.dataset.nextPage = data.page + 1;
                memesList.appendChild(sentinel);
                setupMemeInfiniteScroll(sentinel);
            }
            
        } else {
            memesList.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">${window.translations.no_memes_uploaded}</p>`;
        }
        
        
    } catch (error) {
        if (thisGen !== memeLoadGeneration) return;
        console.error('Failed to load memes:', error);
        const memesList = document.getElementById('memes-list');
        memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--danger);">Failed to load memes</div>';
    }
}

// Infinite scroll observer for meme grid
let memeScrollObserver = null;
let memeScrollLoading = false;

function setupMemeInfiniteScroll(sentinel) {
    // Clean up previous observer if any
    if (memeScrollObserver) {
        memeScrollObserver.disconnect();
    }
    const scrollContainer = document.querySelector('.memes-scroll-container');
    memeScrollObserver = new IntersectionObserver((entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && !memeScrollLoading) {
            const nextPage = parseInt(sentinel.dataset.nextPage, 10);
            if (nextPage) {
                loadMoreMemes(nextPage, sentinel);
            }
        }
    }, { root: scrollContainer, rootMargin: '600px' });
    memeScrollObserver.observe(sentinel);
}

async function loadMoreMemes(page, sentinel) {
    if (memeScrollLoading) return;
    memeScrollLoading = true;
    try {
        const data = await memeLoader.loadMemePage(page, currentMemeSearch);
        if (!data || !data.memes.length) {
            sentinel.remove();
            memeScrollLoading = false;
            return;
        }
        
        const memesList = document.getElementById('memes-list');
        
        // Add new memes before the sentinel
        data.memes.forEach(meme => {
            const memeDiv = document.createElement('div');
            memeDiv.className = 'meme-thumbnail';
            
            const img = document.createElement('img');
            img.dataset.filename = meme.filename;
            img.dataset.url = meme.thumb_url || meme.url;
            img.alt = meme.filename;
            img.style.cursor = 'pointer';
            img.title = 'Click to inspect';
            img.onclick = () => openMemeModal(meme.filename, meme.url, meme.tags || [], meme.api_tags || []);
            img.src = '/static/icons/image.svg';
            img.classList.add('meme-lazy');

            memeLoader.observer.observe(img);
            
            renderMemeThumbBody(memeDiv, meme);
            
            memeDiv.insertBefore(img, memeDiv.firstChild);
            memesList.insertBefore(memeDiv, sentinel);
        });
        
        // Update sentinel for next page or remove it
        if (data.has_next) {
            sentinel.dataset.nextPage = page + 1;
        } else {
            if (memeScrollObserver) memeScrollObserver.disconnect();
            sentinel.remove();
        }
        
    } catch (error) {
        console.error('Failed to load more memes:', error);
    }
    memeScrollLoading = false;
}

// Clear cache when memes are uploaded or deleted
function clearMemeCache() {
    memeCache.clear();
}

// Logout functionality
const logoutButton = document.getElementById('logout-button');
if (logoutButton) {
    logoutButton.addEventListener('click', () => {
        window.location.href = '/logout';
    });
}

async function loadConfiguration() {
    try {
        const response = await fetch('/api/config');
        
        if (response.status === 429) {
            const errorData = await response.json();
            const retryAfter = errorData.retry_after || 60;
            throw new Error(`Rate limit exceeded. Please wait ${retryAfter} seconds.`);
        }
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(`Server error: ${data.error}`);
        }
        
        currentConfig = data.config;
        window.currentConfig = data.config; // Make available globally for wallet loading
        configSchema = data.schema;
        categories = data.categories;
        colorOptions = data.color_options || [];
        window.btcHolidays = data.btc_holidays || {};
        window.mempoolOnionPresets = data.mempool_onion_presets || [];
        window._rebootWindow = data.reboot_window || null;
        configCurrentUser = data.current_user || '';
        
        // Check wallet configuration data
        colorOptions = data.color_options || [];
        
        // Apply dark mode based on config
        if (currentConfig.color_mode_dark !== undefined) {
            applyDarkMode(currentConfig.color_mode_dark);
        }
        
        // console.log('Config loaded:', currentConfig);
        // console.log('Schema loaded:', configSchema);
        // console.log('Categories loaded:', categories);
        
        renderConfigurationForm();
        // Start tracking unsaved changes after a short delay (let form render settle)
        setTimeout(_initDirtyTracking, 300);
        // Privacy: monitor mempool_host changes and reset mempool_is_private when host changes
        setTimeout(_initMempoolPrivacyWatch, 400);
        // Enhance display select with availability badges from API
        setTimeout(_enhanceDisplaySelect, 150);
    setTimeout(_initTorToggleWatch, 160);
    setTimeout(_initTangToggleWatch, 160);
    } catch (error) {
        // console.error('Configuration load error:', error);
        const failedMessage = window.translations?.failed_to_load_configuration || 'Failed to load configuration';
        showNotification(`${failedMessage}: ${error.message}`, 'error');
    }
}
