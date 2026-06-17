// Fix: Define closeOpsecModal globally for HTML onclick handlers
function closeOpsecModal() {
    const opsecModal = document.getElementById('opsec-modal');
    if (opsecModal) {
        opsecModal.style.display = 'none';
        opsecModal.style.position = '';
        opsecModal.style.top = '';
        opsecModal.style.left = '';
        opsecModal.style.transform = '';
        opsecModal.style.margin = '';
    }
    window.currentModalOpsec = null;
}

// Fix: Define closeMemeModal globally for HTML onclick handlers
function closeMemeModal() {
    const memeModal = document.getElementById('meme-modal');
    if (memeModal) {
        memeModal.style.display = 'none';
        // Clear any inline styles that might interfere with centering
        memeModal.style.position = '';
        memeModal.style.top = '';
        memeModal.style.left = '';
        memeModal.style.transform = '';
        memeModal.style.margin = '';
    }
    window.currentModalMeme = null;
}
    function initializeWebSocket() {
        // Connect to backend using Socket.IO
        if (window.io) {
            const socket = window.io();
            window.configSocket = socket;

            socket.on('connect', function() {
                console.log('🔌 Config WebSocket connected');
            });

            socket.on('disconnect', function(reason) {
                console.warn('Config WebSocket disconnected:', reason);
            });

            socket.on('connect_error', function(error) {
                console.error('Config WebSocket connection error:', error);
            });

            socket.on('block_notification', function(data) {
                console.log('🔔 [CONFIG] Block notification:', data);
            });

            // Live wallet balance updates from backend
            socket.on('wallet_balance_updated', function(data) {
                console.log('💰 [CONFIG] Wallet balance updated via WebSocket');
                const tbody = document.querySelector('.wallet-table tbody');
                if (!tbody) return;
                const allEntries = [].concat(data.addresses || [], data.xpubs || []);
                const prevAddrs = data.prev_addresses || [];
                const prevXpubs = data.prev_xpubs || [];
                const allPrev = [].concat(prevAddrs, prevXpubs);
                const isInit = data.after_config_save || false;

                // Update table cells
                if (data.addresses) {
                    const rows = tbody.querySelectorAll('tr');
                    data.addresses.forEach((addrInfo, i) => {
                        if (i >= rows.length) return;
                        const display = rows[i].querySelector('.wallet-balance-display');
                        if (display) {
                            const bal = addrInfo.balance_btc || addrInfo.balance || addrInfo.cached_balance || 0;
                            display.textContent = bal.toFixed(8);
                            display.style.color = 'var(--accent)';
                            display.style.opacity = '1';
                            display.title = 'Live balance data';
                        }
                    });
                }

                // Toast notifications per entry
                allEntries.forEach(entry => {
                    const label = entry.comment || entry.xpub_short || 'Wallet';
                    const bal = entry.balance_btc || 0;
                    const addr = entry.address || entry.xpub || '';
                    // Find previous balance
                    const prev = allPrev.find(p => (p.address || p.xpub) === addr);
                    const prevBal = prev ? (prev.balance_btc || 0) : -1;

                    if (prevBal < 0) {
                        // Newly initialized — no previous balance known, wallet was unavailable
                        if (bal > 0) showLiveToast(window.translations?.toast_wallet_title || 'Wallet', `'${label}' initialized: ${bal.toFixed(8)} BTC`, 'color_wallets');
                    } else if (bal !== prevBal) {
                        showLiveToast(window.translations?.toast_wallet_title || 'Wallet', `'${label}' balance: ${prevBal.toFixed(8)} → ${bal.toFixed(8)} BTC`, 'color_wallets');
                    }
                });
            });

            // Live bitaxe stats updates from backend
            socket.on('bitaxe_stats_updated', function(data) {
                console.log('⛏️ [CONFIG] Bitaxe stats updated via WebSocket');
                if (!data || !data.miners) return;
                const rows = document.querySelectorAll('.bitaxe-table-container tbody tr');
                rows.forEach(row => {
                    const ipInput = row.querySelector('.bitaxe-address-input');
                    const diffDisplay = row.querySelector('.bitaxe-best-diff-display');
                    if (!ipInput || !diffDisplay) return;
                    const ip = ipInput.value.trim();
                    const minerData = data.miners[ip];
                    if (!minerData) return;
                    if (minerData.online) {
                        diffDisplay.textContent = formatBitaxeDifficulty(minerData.best_diff);
                        diffDisplay.style.color = 'var(--accent)';
                    } else {
                        diffDisplay.textContent = 'Offline';
                        diffDisplay.style.color = '#ff6b6b';
                    }
                    // Toast for best diff changes — only when a real previous value exists
                    const label = minerData.label || ip;
                    if (minerData.best_diff > 0 && minerData.prev_best_diff > 0 && minerData.best_diff !== minerData.prev_best_diff) {
                        showLiveToast(window.translations?.toast_bitaxe_title || 'Bitaxe', `New best diff for ${label}: ${formatBitaxeDifficulty(minerData.best_diff)}`, 'color_bitaxe_stats');
                    }

                });
            });

            // Live found-blocks updates from backend
            socket.on('found_blocks_updated', function(data) {
                console.log('🏆 [CONFIG] Found blocks updated via WebSocket');
                if (!data || !data.blocks) return;
                const rows = document.querySelectorAll('.block-reward-table-container tbody tr');
                rows.forEach(row => {
                    const addrInput = row.querySelector('.block-reward-address-input');
                    if (!addrInput) return;
                    const address = addrInput.value.trim();
                    const blockData = data.blocks[address];
                    if (!blockData) return;
                    let cell = row.querySelector('td[data-address]');
                    if (!cell) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 3) cell = cells[2];
                    }
                    if (cell) {
                        cell.textContent = blockData.count || '0';
                        cell.style.color = 'var(--accent)';
                    }
                    // Toast for new blocks found
                    if (blockData.count > blockData.prev_count) {
                        const diff = blockData.count - blockData.prev_count;
                        showLiveToast(window.translations?.toast_block_found_title || 'Block Found', `${blockData.label}: ${diff} new block${diff > 1 ? 's' : ''} found! (total: ${blockData.count})`, 'color_bitaxe_stats');
                    }
                })
            });

            socket.on('donation_received', function(donation) {
                console.log('⚡ Donation received:', donation);
                // Prepend new row to table if it is currently visible
                const tbody = document.getElementById('donation-history-tbody');
                if (tbody) {
                    // Remove the "No donations yet" placeholder row if present
                    if (tbody.rows.length === 1 && tbody.rows[0].cells.length === 1) {
                        tbody.innerHTML = '';
                    }
                    const ts = donation.timestamp
                        ? new Date(donation.timestamp + 'Z').toLocaleString() : '—';
                    const sats = (donation.amount_sats || 0).toLocaleString();
                    const msg = donation.message
                        ? escapeHtml(donation.message) : '<em style="color:#888">—</em>';
                    const tr = document.createElement('tr');
                    tr.style.cssText = 'border-bottom:1px solid var(--border-color);';
                    tr.innerHTML = `
                        <td style="padding:5px 8px; white-space:nowrap;">${ts}</td>
                        <td style="padding:5px 8px; text-align:right; font-weight:bold; color:var(--accent); font-family:var(--font-mono);">${sats}</td>
                        <td style="padding:5px 8px;">${msg}</td>`;
                    tbody.insertBefore(tr, tbody.firstChild);
                    // Update total
                    const totalEl = document.getElementById('donation-total-sats');
                    if (totalEl) {
                        const prev = parseInt(totalEl.dataset.total || '0', 10);
                        const next = prev + (donation.amount_sats || 0);
                        totalEl.dataset.total = next;
                        totalEl.textContent = next.toLocaleString() + ' sats';
                    }
                }
                // Toast notification
                showDonationToast(donation);
            });
        } else {
            console.error('Socket.IO client (window.io) not found. Make sure socket.io.min.js is loaded.');
        }
    }
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
    const passwordForm = document.createElement('div');
    passwordForm.className = 'password-change-form';
    passwordForm.style.display = 'none';
    passwordForm.style.marginTop = '10px';
    passwordForm.style.padding = '15px';
    passwordForm.style.border = '1px solid #ddd';
    passwordForm.style.borderRadius = '4px';
    passwordForm.style.backgroundColor = 'var(--bg-color)';
    
    // New password field
    const newPasswordLabel = document.createElement('label');
    newPasswordLabel.textContent = window.translations?.new_password || 'New Password';
    newPasswordLabel.style.display = 'block';
    newPasswordLabel.style.marginBottom = '5px';
    
    const newPasswordInput = document.createElement('input');
    newPasswordInput.type = 'password';
    newPasswordInput.className = 'form-input';
    newPasswordInput.placeholder = window.translations?.new_password || 'New Password';
    newPasswordInput.style.marginBottom = '10px';
    
    // Confirm password field
    const confirmPasswordLabel = document.createElement('label');
    confirmPasswordLabel.textContent = window.translations?.confirm_password || 'Confirm Password';
    confirmPasswordLabel.style.display = 'block';
    confirmPasswordLabel.style.marginBottom = '5px';
    
    const confirmPasswordInput = document.createElement('input');
    confirmPasswordInput.type = 'password';
    confirmPasswordInput.className = 'form-input';
    confirmPasswordInput.placeholder = window.translations?.confirm_password || 'Confirm Password';
    confirmPasswordInput.style.marginBottom = '15px';
    
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
    saveButton.className = 'form-button';
    saveButton.style.backgroundColor = '#F7931A';
    saveButton.style.color = 'white';
    saveButton.style.border = 'none';
    saveButton.style.padding = '8px 16px';
    saveButton.style.borderRadius = '4px';
    saveButton.style.cursor = 'pointer';
    saveButton.textContent = window.translations?.save || 'Save';
    
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
        newPasswordInput.focus();
    });
    
    cancelButton.addEventListener('click', () => {
        passwordForm.style.display = 'none';
        buttonWrapper.style.display = 'block';
        newPasswordInput.value = '';
        confirmPasswordInput.value = '';
        errorMessage.style.display = 'none';
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
        
        if (newPassword.length < 6) {
            errorMessage.textContent = 'Password must be at least 6 characters long';
            errorMessage.style.display = 'block';
            return;
        }
        
        // Save the password
        try {
            saveButton.disabled = true;
            saveButton.textContent = '';
            
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
            saveButton.disabled = false;
            saveButton.textContent = window.translations?.save || 'Save';
        }
    });
    
    // Assemble the form
    passwordForm.appendChild(newPasswordLabel);
    passwordForm.appendChild(newPasswordInput);
    passwordForm.appendChild(confirmPasswordLabel);
    passwordForm.appendChild(confirmPasswordInput);
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
                    // Show notification if it's recent (within 5 seconds)
                    console.log('⚙️ Received cross-page block notification');
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
            console.log('Confirm delete clicked, memeToDelete:', memeToDelete);
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
        if (isConfigPage) {
            console.warn('Upload elements not found - upload functionality disabled');
        }
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
            uploadFiles(files);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            uploadFiles(Array.from(e.target.files));
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

        const previewHtml = previewUrl
            ? `<div style="text-align: center; margin-bottom: 15px;">
                   <img src="${previewUrl}" alt="${originalFilename}" style="max-width: 150px; max-height: 150px; object-fit: contain; border-radius: 6px; border: 1px solid #ddd;">
               </div>`
            : '';

        modal.innerHTML = `
            <div class="modal-content" style="max-width: 400px;">
                <h3>${t?.rename_image || 'Rename Image'}</h3>
                ${previewHtml}
                <p style="margin-bottom: 8px; color: #6a6a78;">${t?.rename_conflict_info || 'A file named'} <strong>${originalFilename}</strong> ${t?.rename_conflict_exists || 'already exists.'}</p>
                <label style="display: block; margin-bottom: 5px; font-weight: 600;">${t?.rename_new_name || 'New name (without extension):'}</label>
                <input type="text" id="rename-input" class="form-input" value="${suggestedNameWithoutExt}" style="margin-bottom: 5px;">
                <p id="rename-name-warning" style="font-size: 0.85rem; color: #e53e3e; margin-bottom: 5px; display: none;">${t?.rename_name_in_use || 'This name is already in use. Please choose a different name.'}</p>
                <p style="font-size: 0.85rem; color: #F7931A; margin-bottom: 15px;">${(t?.rename_extension_preserved || 'Extension {ext} will be preserved').replace('{ext}', extension)}</p>
                <div class="modal-buttons" style="display: flex; gap: 10px;">
                    <button id="rename-confirm" class="save-button" style="flex: 1;">${t?.rename_confirm || 'Rename'}</button>
                    <button id="rename-skip" class="cancel-button" style="flex: 1;">${t?.rename_keep_original || 'Keep Original'}</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        const input = modal.querySelector('#rename-input');
        const confirmBtn = modal.querySelector('#rename-confirm');
        const skipBtn = modal.querySelector('#rename-skip');
        const warning = modal.querySelector('#rename-name-warning');

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
        progressBar.style.width = '0%';
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
        console.log('Duplicates detected:\n' + dupList);
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
                progressBar.style.width = `${((i) / filesToUpload.length) * 100}%`;
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
            progressBar.style.width = '100%';
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
                        const newUrl = `/static/memes/${newFilename}`;
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
                            actionsDiv.innerHTML = `
                                <button class="action-button" onclick="downloadMeme('${newFilename}')" title="${window.translations?.download_meme || 'Download'}">
                                    <img src="/static/icons/download.svg" alt="Download" style="width: 16px; height: 16px; filter: brightness(0) invert(1);" />
                                </button>
                                <button class="action-button delete" onclick="showDeleteModal('${newFilename}')" title="${window.translations?.delete_meme || 'Delete'}">
                                    <img src="/static/icons/delete.svg" alt="Delete" style="width: 16px; height: 16px; filter: brightness(0) invert(1);" />
                                </button>
                            `;
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
    const warning = document.getElementById('meme-modal-rename-warning');

    if (!filenameDisplay || !filenameInput || !editBtn || !saveBtn || !cancelBtn) return;

    const filename = currentModalMeme.filename;
    const extension = filename.substring(filename.lastIndexOf('.'));
    const nameWithoutExt = filename.substring(0, filename.lastIndexOf('.'));

    // Switch to edit mode
    filenameDisplay.style.display = 'none';
    editBtn.style.display = 'none';
    filenameInput.style.display = 'inline-block';
    saveBtn.style.display = 'inline-block';
    cancelBtn.style.display = 'inline-block';

    filenameInput.value = nameWithoutExt;
    filenameInput.focus();
    filenameInput.select();

    // Live validation: block saving if the chosen name is already in use by another file
    const validateModalInput = () => {
        const candidate = filenameInput.value.trim() + extension;
        // Allow the current filename itself (no-op rename)
        const conflict = candidate !== filename && window.memeFilenameSet.has(candidate);
        if (warning) {
            warning.textContent = conflict
                ? (window.translations?.rename_name_in_use || 'This name is already in use. Please choose a different name.')
                : '';
            warning.style.display = conflict ? 'block' : 'none';
        }
        saveBtn.disabled = conflict || !filenameInput.value.trim();
        saveBtn.style.opacity = saveBtn.disabled ? '0.5' : '';
        saveBtn.style.cursor = saveBtn.disabled ? 'not-allowed' : '';
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
    currentModalMeme.url = `/static/memes/${newFilename}`;

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
    const warning = document.getElementById('meme-modal-rename-warning');

    if (!filenameDisplay || !filenameInput || !editBtn || !saveBtn || !cancelBtn) return;

    // Switch back to display mode
    filenameDisplay.style.display = 'inline';
    editBtn.style.display = 'inline-block';
    filenameInput.style.display = 'none';
    saveBtn.style.display = 'none';
    saveBtn.disabled = false;
    saveBtn.style.opacity = '';
    saveBtn.style.cursor = '';
    cancelBtn.style.display = 'none';
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
            rootMargin: '50px' // Start loading 50px before the image comes into view
        });
    }
    
    async loadImageForElement(imgElement) {
        if (imgElement.src && !imgElement.src.includes('data:image')) {
            return; // Already loaded
        }
        
        const filename = imgElement.dataset.filename;
        const url = imgElement.dataset.url;
        
        if (!filename || !url) return;
        
        try {
            // Check cache first
            const cached = memeCache.get(filename);
            if (cached && cached.url) {
                imgElement.src = cached.url;
                imgElement.classList.add('loaded');
                this.observer.unobserve(imgElement);
                return;
            }
            
            // Load the image
            imgElement.src = url;
            imgElement.classList.add('loaded');
            
            // Cache the successful load
            memeCache.set(filename, { url, loaded: Date.now() });
            
            this.observer.unobserve(imgElement);
        } catch (error) {
            console.warn('Failed to load meme image:', filename, error);
            imgElement.classList.add('error');
        }
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

async function loadMemes(search = '') {
    currentMemeSearch = search;
    try {
        const memesList = document.getElementById('memes-list');
        if (!memesList) {
            console.warn('memes-list element not found, skipping meme load');
            return;
        }
        // Show loading indicator
        memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">Loading memes...</div>';
        // Load first page
        const data = await memeLoader.loadMemePage(1, search);
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
                img.loading = 'lazy'; // Native lazy loading as fallback
                img.style.cursor = 'pointer';
                img.title = 'Click to inspect';
                img.onclick = () => openMemeModal(meme.filename, meme.url, meme.tags || [], meme.api_tags || []);
                // Add placeholder until loaded
                img.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100%" height="100%" fill="%23222228"/><text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="%23999">📷</text></svg>';
                img.classList.add('meme-lazy');
                // Set up lazy loading observer
                memeLoader.observer.observe(img);
                memeDiv.innerHTML = `
                    <div class="meme-actions">
                        <button class="action-button" onclick="downloadMeme('${meme.filename}')" title="${window.translations?.download_meme || 'Download'}">
                            <img src="/static/icons/download.svg" alt="Download" style="width: 16px; height: 16px; filter: brightness(0) invert(1);" />
                        </button>
                        <button class="action-button delete" onclick="showDeleteModal('${meme.filename}')" title="${window.translations?.delete_meme || 'Delete'}">
                            <img src="/static/icons/delete.svg" alt="Delete" style="width: 16px; height: 16px; filter: brightness(0) invert(1);" />
                        </button>
                    </div>
                    <div class="meme-filename">${meme.filename}</div>
                `;
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
    }, { root: scrollContainer, rootMargin: '200px' });
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
            img.loading = 'lazy';
            img.style.cursor = 'pointer';
            img.title = 'Click to inspect';
            img.onclick = () => openMemeModal(meme.filename, meme.url, meme.tags || [], meme.api_tags || []);
            img.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100%" height="100%" fill="%23222228"/><text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="%23999">📷</text></svg>';
            img.classList.add('meme-lazy');

            memeLoader.observer.observe(img);
            
            memeDiv.innerHTML = `
                <div class="meme-actions">
                    <button class="action-button" onclick="downloadMeme('${meme.filename}')" title="${window.translations?.download_meme || 'Download'}">
                        <img src="/static/icons/download.svg" alt="Download" style="width: 16px; height: 16px; filter: brightness(0) invert(1);" />
                    </button>
                    <button class="action-button delete" onclick="showDeleteModal('${meme.filename}')" title="${window.translations?.delete_meme || 'Delete'}">
                        <img src="/static/icons/delete.svg" alt="Delete" style="width: 16px; height: 16px; filter: brightness(0) invert(1);" />
                    </button>
                </div>
                <div class="meme-filename">${meme.filename}</div>
            `;
            
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
    logoutButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/api/logout', { method: 'POST' });
            const result = await response.json();
            window.location.href = result.public_dashboard ? '/' : '/login';
        } catch (error) {
            console.error('Logout failed:', error);
            window.location.href = '/login';
        }
    });
} else if (isConfigPage) {
    console.warn('Logout button not found in DOM - expected on config page');
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
    } catch (error) {
        // console.error('Configuration load error:', error);
        const failedMessage = window.translations?.failed_to_load_configuration || 'Failed to load configuration';
        showNotification(`${failedMessage}: ${error.message}`, 'error');
    }
}

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
    input.setAttribute('autocomplete', 'off');
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

    const passwordForm = document.createElement('div');
    passwordForm.className = 'password-change-form';
    passwordForm.style.cssText = 'display:none;margin-top:10px;padding:15px;border:1px solid #ddd;border-radius:4px;background:var(--bg-color);';

    const newPasswordInput = document.createElement('input');
    newPasswordInput.type = 'password';
    newPasswordInput.className = 'form-input';
    newPasswordInput.placeholder = window.translations?.new_password || 'New Password';
    newPasswordInput.style.marginBottom = '10px';

    const confirmPasswordInput = document.createElement('input');
    confirmPasswordInput.type = 'password';
    confirmPasswordInput.className = 'form-input';
    confirmPasswordInput.placeholder = window.translations?.confirm_password || 'Confirm Password';
    confirmPasswordInput.style.marginBottom = '15px';

    const errorMessage = document.createElement('div');
    errorMessage.className = 'password-error';
    errorMessage.style.cssText = 'color:red;margin-bottom:10px;display:none;';

    const buttonContainer = document.createElement('div');
    buttonContainer.style.cssText = 'display:flex;gap:10px;';

    const saveButton = document.createElement('button');
    saveButton.type = 'button';
    saveButton.className = 'form-button';
    saveButton.style.cssText = 'background:#F7931A;color:white;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;';
    saveButton.textContent = window.translations?.save || 'Save';

    const cancelButton = document.createElement('button');
    cancelButton.type = 'button';
    cancelButton.className = 'form-button';
    cancelButton.style.cssText = 'background:#666;color:white;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;';
    cancelButton.textContent = window.translations?.cancel || 'Cancel';

    changeButton.addEventListener('click', () => {
        passwordForm.style.display = 'block';
        buttonWrapper.style.display = 'none';
        newPasswordInput.focus();
    });
    cancelButton.addEventListener('click', () => {
        passwordForm.style.display = 'none';
        buttonWrapper.style.display = '';
        newPasswordInput.value = '';
        confirmPasswordInput.value = '';
        errorMessage.style.display = 'none';
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
        if (newPassword.length < 8) {
            errorMessage.textContent = 'Password must be at least 8 characters';
            errorMessage.style.display = '';
            return;
        }
        errorMessage.style.display = 'none';
        saveButton.disabled = true;
        saveButton.textContent = '...';
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
            saveButton.disabled = false;
            saveButton.textContent = window.translations?.save || 'Save';
        }
    });

    buttonContainer.appendChild(saveButton);
    buttonContainer.appendChild(cancelButton);
    passwordForm.appendChild(newPasswordInput);
    passwordForm.appendChild(confirmPasswordInput);
    passwordForm.appendChild(errorMessage);
    passwordForm.appendChild(buttonContainer);
    buttonWrapper.appendChild(changeButton);
    container.appendChild(buttonWrapper);
    container.appendChild(passwordForm);
    return container;
}

// (removed — user management is now inline in the General section)
function renderUserManagementSection(grid) { /* no-op */ }

function renderConfigurationForm() {
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
    
    categories.forEach(category => {
        //console.log(`Processing category: ${category.id} - ${category.label}`);
        
        const section = document.createElement('div');
        section.className = 'config-section';
        
        // Add special class for meme/opsec management sections (spans 2 columns on desktop)
        if (category.id === 'meme_management' || category.id === 'opsec') {
            section.classList.add('meme-management-section');
        }
        
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
            toggleSwitch.addEventListener('click', function() {
                const newValue = !toggleSwitch.classList.contains('enabled');
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

        // Append advanced container after all regular fields so it appears at the bottom
        if (advancedContainer && !advancedContainer.parentElement) {
            section.appendChild(advancedContainer);
        }

        // Append user credential fields (username + password) to the General advanced section
        if (category.id === 'general' && configCurrentUser) {
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
            advancedContainer.querySelector('.advanced-section-content').appendChild(createCurrentUserUsernameField());
            advancedContainer.querySelector('.advanced-section-content').appendChild(createCurrentUserPasswordField());
            fieldsAdded += 2;
        }

        //console.log(`Category ${category.id} has ${fieldsAdded} fields`);

        // Add section if it has fields OR if it has a toggle (like sections that only contain a toggle)
        if (fieldsAdded > 0 || enableToggleKey) {
            grid.appendChild(section);
        } else {
            //console.warn(`Category ${category.id} has no fields!`);
        }
    });

    container.appendChild(grid);
    // Render the configuration form

    // Load cached balances for any existing wallet entries after form is rendered
    setTimeout(() => {
        const walletTable = document.querySelector('.wallet-table tbody');
        if (walletTable && walletTable.children.length > 0) {
            console.log('Loading cached balances for existing wallet entries');
            loadCachedWalletBalances(walletTable);
        }
    }, 100); // Small delay to ensure DOM is fully updated
    
    // Diagnostic call to check boolean elements after form is rendered
    setTimeout(() => {
        diagnoseBooleanElements();
    }, 200); // Ensure everything is fully loaded
}

function createFormField(key, field, value) {
    const formGroup = document.createElement('div');
    formGroup.className = 'form-group';
    
    // Add special class for color fields to allow side-by-side layout
    if (field.type === 'color' || field.type === 'color_select') {
        formGroup.classList.add('form-group-color');
    }
    
    // Skip adding label for self-managed interfaces and pure info boxes
    if (field.type !== 'meme_management' && field.type !== 'donation_history' && field.type !== 'info_text') {
        const label = document.createElement('label');
        label.className = 'form-label';
        label.textContent = field.label;
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
            
            // Disable autocomplete for admin_username field
            if (key === 'admin_username') {
                input.setAttribute('autocomplete', 'off');
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
            }
            break;
            
        case 'number':
            input = document.createElement('input');
            input.type = 'number';
            input.className = 'form-input';
            input.value = value !== undefined && value !== null ? value : '';
            input.min = field.min || '';
            input.max = field.max || '';
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
            
            // Special handling for language changes - remove immediate modal, save for later
            if (key === 'language') {
                input.addEventListener('change', (e) => {
                    const newLanguage = e.target.value;
                    
                    if (newLanguage !== currentConfig.language) {
                        // Store the language change but don't update currentConfig yet
                        pendingLanguageChange = newLanguage;
                    } else {
                        // Reset if user changes back to original
                        pendingLanguageChange = null;
                    }
                });
            }
            break;
            
        case 'color_select':
            input = createColorSelect(value);
            break;
            
        case 'color':
            input = createColorInput(value);
            break;

        case 'holiday_color_group':
            input = createHolidayColorGroup();
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
            break;
            
        case 'tags':
            input = createTagsInput(value || [], field.placeholder);
            break;
            
        case 'wallet_table':
            console.log(`Creating wallet table for key ${key} (${(value || []).length} entries)`);
            input = createWalletTableInput(value || [], field);
            break;
            
        case 'bitaxe_table':
            console.log(`Creating bitaxe table for key ${key} (${(value || []).length} entries)`);
            input = createBitaxeTableInput(value || [], field);
            break;
            
        case 'block_reward_table':
            console.log(`Creating block reward table for key ${key} (${(value || []).length} entries)`);
            input = createBlockRewardTableInput(value || [], field);
            break;
            
        case 'meme_management':
            console.log(`Creating meme management interface for key ${key}`);
            input = createMemeManagementInterface(field);
            break;

        case 'opsec_management':
            console.log(`Creating OPSec management interface for key ${key}`);
            input = createOpsecManagementInterface(field);
            break;

        case 'donation_history':
            input = createDonationHistoryInterface();
            break;

        case 'info_text': {
            const infoBox = document.createElement('div');
            infoBox.className = 'form-info-box';
            const rawHtml = (field.html || field.text || '');
            infoBox.innerHTML = rawHtml.replace(/\{BASE_URL\}/g, window.location.origin);
            // Not a config value — excluded from saves
            infoBox.getValue = () => null;
            input = infoBox;
            break;
        }

        case 'hidden':
            // Create hidden input that won't be displayed
            input = document.createElement('input');
            input.type = 'hidden';
            input.value = value !== undefined && value !== null ? value : '';
            input.style.display = 'none';
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
        // (skip for composite widgets that manage their own child config keys)
        if (field.type !== 'holiday_color_group') {
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
    
    formGroup.appendChild(input);
    
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
    });

    textInput.addEventListener('input', () => {
        const val = textInput.value;
        if (/^#[0-9A-F]{6}$/i.test(val)) {
            colorInput.value = val;
        }
    });

    container.appendChild(colorInput);
    container.appendChild(textInput);
    
    // Config collector uses getValue() if available
    container.getValue = function() {
        return textInput.value;
    };

    return container;
}


function createHolidayColorGroup() {
    const t = window.translations || {};
    const wrapper = document.createElement('div');
    wrapper.style.width = '100%';

    // Read current values from the already-loaded config
    const cfg = window.currentConfig || {};
    const lightStart = cfg['color_holiday_light'] || '#F7931A';
    const lightEnd   = cfg['color_holiday_end_light'] || '#C62828';
    const darkStart  = cfg['color_holiday_dark'] || '#F7931A';
    const darkEnd    = cfg['color_holiday_end_dark'] || '#FF6F6F';

    const previewText = 'Bitcoin Pizza Day';

    function buildRow(themeLabel, startKey, endKey, startVal, endVal, bgColor, previewBg) {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex; flex-wrap:wrap; align-items:flex-start; gap:12px; margin-bottom:14px; padding:12px; border-radius:8px; background:' + bgColor;

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

        // Gradient preview
        const preview = document.createElement('div');
        preview.style.cssText = 'flex:1; min-width:160px; display:flex; align-items:center; justify-content:center; padding:10px 16px; border-radius:6px; background:' + previewBg;
        const previewSpan = document.createElement('span');
        previewSpan.style.cssText = 'font-size:1.1em; font-weight:700; background:linear-gradient(90deg,' + startVal + ',' + endVal + '); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;';
        previewSpan.textContent = previewText;
        preview.appendChild(previewSpan);
        row.appendChild(preview);

        // Live-update the gradient preview when colors change
        function updatePreview() {
            const s = startInput.getValue ? startInput.getValue() : startVal;
            const e = endInput.getValue ? endInput.getValue() : endVal;
            previewSpan.style.background = 'linear-gradient(90deg,' + s + ',' + e + ')';
            previewSpan.style.webkitBackgroundClip = 'text';
            previewSpan.style.backgroundClip = 'text';
        }
        startInput.addEventListener('input', updatePreview);
        endInput.addEventListener('input', updatePreview);

        return row;
    }

    // Light theme row (first)
    wrapper.appendChild(buildRow(
        t.holiday_color_light_theme || 'Light Theme',
        'color_holiday_light', 'color_holiday_end_light',
        lightStart, lightEnd,
        'rgba(255,255,255,0.06)', '#ffffff'
    ));

    // Dark theme row (second)
    wrapper.appendChild(buildRow(
        t.holiday_color_dark_theme || 'Dark Theme',
        'color_holiday_dark', 'color_holiday_end_dark',
        darkStart, darkEnd,
        'rgba(255,255,255,0.06)', '#1a1a2e'
    ));

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

// Diagnostic function to test boolean elements
function diagnoseBooleanElements() {
    console.log('👁️ [DIAGNOSTIC] Checking all boolean elements:');
    const booleanFields = ['prioritize_large_scaled_meme', 'color_mode_dark', 'show_btc_price_block', 'show_bitaxe_block', 'show_wallet_balances_block', 'show_donation_block', 'e-ink-display-connected'];
    
    booleanFields.forEach(fieldName => {
        const element = document.querySelector(`[data-config-key="${fieldName}"]`);
        if (element) {
            // console.log(`✅ Found ${fieldName}:`, {
            //     tagName: element.tagName,
            //     className: element.className,
            //     hasGetValue: typeof element.getValue === 'function',
            //     dataConfigKey: element.dataset.configKey,
            //     currentValue: element.getValue ? element.getValue() : 'N/A'
            // });
        } else {
            console.log(`❌ Missing ${fieldName}`);
        }
    });
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
        const active = switchEl.classList.contains('active');
        return active;
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
        
        // Create proper icon HTML if icon is provided
        if (option.icon) {
            const iconImg = document.createElement('img');
            iconImg.src = option.icon;
            iconImg.alt = option.label;
            iconImg.style.width = '16px';
            iconImg.style.height = '16px';
            iconImg.style.marginRight = '8px';
            iconImg.style.filter = 'brightness(0) invert(1)'; // Make icons white for dark theme
            
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
        const value = input.value;
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
    addButton.innerHTML = '➕';
    addButton.title = 'Tag hinzufügen';
    addButton.style.marginLeft = '8px';
    addButton.style.padding = '8px 12px';
    addButton.style.border = '1px solid #ced4da';
    addButton.style.borderRadius = '4px';
    addButton.style.backgroundColor = '#f8f9fa';
    addButton.style.cursor = 'pointer';
    addButton.style.fontSize = '14px';
    
    // Add button click handler
    addButton.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        const value = input.value.trim();
        if (value) {
            addTag(container, value);
            input.value = '';
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
    tag.innerHTML = `${value} <button type="button" class="tag-remove">×</button>`;
    
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
    balanceHeader.textContent = window.translations?.wallet_table_balance || 'Balance (BTC)';
    balanceHeader.style.padding = '10px';
    balanceHeader.style.border = '1px solid var(--border-subtle)';
    balanceHeader.style.backgroundColor = '#2a2d3e';
    balanceHeader.style.color = '#ffffff';
    balanceHeader.style.width = '20%';
    balanceHeader.style.textAlign = 'center';
    
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
    
    addButton.addEventListener('click', (e) => {
        e.preventDefault();
        addWalletTableRow(tbody, { address: '', comment: '', balance: 0 });
        updateTableVisibility();
        container.dispatchEvent(new Event('change', { bubbles: true }));
    });
    
    const buttonContainer = document.createElement('div');
    buttonContainer.appendChild(addButton);
    container.appendChild(buttonContainer);
    
    // Add getter for value (used by form system)
    container.getValue = () => {
        const rows = tbody.querySelectorAll('tr');
        const result = Array.from(rows).map(row => {
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
        
        console.log('Wallet table getValue called, returning:', result.length + ' entries (addresses masked)');
        return result;
    };
    
    // Add value property for compatibility
    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (newValues) => {
            console.log('Wallet table setValue called with:', (newValues || []).length + ' entries (addresses masked)');
            // Clear existing rows
            tbody.innerHTML = '';
            // Add new rows
            if (Array.isArray(newValues)) {
                newValues.forEach(entry => addWalletTableRow(tbody, entry));
                console.log(`Added ${newValues.length} wallet entries to table`);
                
                // Load cached balances for the newly added entries
                loadCachedWalletBalances(tbody);
            } else {
                console.log('Invalid newValues for wallet table:', typeof newValues + ' (content masked)');
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
        tbody.parentElement.parentElement.dispatchEvent(new Event('change', { bubbles: true }));
    });
    
    addressCell.appendChild(addressInput);
    
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
    balanceDisplay.textContent = entry.cached_balance ? `${entry.cached_balance.toFixed(8)}` : '0.00000000';
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
        // Update table visibility after removing row
        const container = tbody.closest('.wallet-table-container');
        if (container && container._updateTableVisibility) {
            container._updateTableVisibility();
        }
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
    addressHeader.style.width = '35%';

    const commentHeader = document.createElement('th');
    commentHeader.innerHTML = (window.translations?.bitaxe_table_comment || 'Comment/Label').replace('/', '/<br>');
    commentHeader.style.padding = '10px';
    commentHeader.style.border = '1px solid var(--border-subtle)';
    commentHeader.style.backgroundColor = '#2a2d3e';
    commentHeader.style.color = '#ffffff';
    commentHeader.style.width = '30%';

    const bestDiffHeader = document.createElement('th');
    bestDiffHeader.textContent = window.translations?.bitaxe_table_best_diff || 'Best Difficulty';
    bestDiffHeader.style.padding = '10px';
    bestDiffHeader.style.border = '1px solid var(--border-subtle)';
    bestDiffHeader.style.backgroundColor = '#2a2d3e';
    bestDiffHeader.style.color = '#ffffff';
    bestDiffHeader.style.width = '25%';
    bestDiffHeader.style.textAlign = 'center';

    const actionsHeader = document.createElement('th');
    actionsHeader.textContent = '';
    actionsHeader.style.padding = '10px';
    actionsHeader.style.border = '1px solid var(--border-subtle)';
    actionsHeader.style.backgroundColor = '#2a2d3e';
    actionsHeader.style.color = '#ffffff';
    actionsHeader.style.width = '10%';

    headerRow.appendChild(addressHeader);
    headerRow.appendChild(commentHeader);
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
        const result = Array.from(rows).map(row => {
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
        
        console.log('Bitaxe table getValue called, returning:', result.length + ' entries (IPs masked for privacy)');
        return result;
    };
    
    // Add value property for compatibility
    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (newValues) => {
            console.log('Bitaxe table setValue called with:', Array.isArray(newValues) ? newValues.length + ' entries (IPs masked for privacy)' : 'invalid data');
            // Clear existing rows
            tbody.innerHTML = '';
            // Add new rows
            if (Array.isArray(newValues)) {
                newValues.forEach(entry => addBitaxeTableRow(tbody, entry));
                console.log(`Added ${newValues.length} bitaxe entries to table`);
            } else {
                console.log('Invalid newValues for bitaxe table: type =', typeof newValues, '(data masked for privacy)');
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

    // Update best diff when IP changes — debounced so we only fetch once typing stops
    let _bitaxeIpDebounce = null;
    addressInput.addEventListener('input', () => {
        clearTimeout(_bitaxeIpDebounce);
        const newIp = addressInput.value.trim();
        if (!newIp) {
            bestDiffDisplay.textContent = '-';
            bestDiffDisplay.style.color = 'var(--text-muted)';
            return;
        }
        // Wait until the field looks like a complete IPv4 address before fetching
        _bitaxeIpDebounce = setTimeout(() => {
            const ip = addressInput.value.trim();
            if (/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) {
                bestDiffDisplay.textContent = '...';
                bestDiffDisplay.style.color = 'var(--text-muted)';
                fetchBitaxeBestDiff(ip, bestDiffDisplay);
            }
        }, 1000);
    });

    // Load initial best diff if IP is set
    if (entry.address) {
        bestDiffDisplay.textContent = '...';
        bestDiffDisplay.style.color = 'var(--text-muted)';
        fetchBitaxeBestDiff(entry.address, bestDiffDisplay);
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
        // Update table visibility after removing row
        const container = tbody.closest('.bitaxe-table-container');
        if (container && container._updateTableVisibility) {
            container._updateTableVisibility();
        }
        container.dispatchEvent(new Event('change', { bubbles: true }));
    });

    actionsCell.appendChild(removeButton);

    // Assemble row
    row.appendChild(addressCell);
    row.appendChild(commentCell);
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
    
    addButton.addEventListener('click', () => {
        addBlockRewardTableRow(tbody, { address: '', comment: '' });
        updateTableVisibility();
    });
    
    container.appendChild(table);
    container.appendChild(addButton);
    
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
            console.log('Setting block reward table values:', Array.isArray(newValues) ? newValues.length + ' entries (addresses masked for privacy)' : 'invalid data');
            if (Array.isArray(newValues)) {
                // Clear existing rows
                tbody.innerHTML = '';
                
                // Add new rows
                newValues.forEach(entry => {
                    if (entry && typeof entry === 'object') {
                        addBlockRewardTableRow(tbody, entry);
                    }
                });
            } else {
                console.log('Invalid newValues for block reward table: type =', typeof newValues, '(data masked for privacy)');
            }
        }
    });
    
    // Add getValue method for form collection
    container.getValue = () => {
        const entries = [];
        const rows = tbody.querySelectorAll('tr');
        console.log('Block reward table getValue called, found rows:', rows.length);
        
        rows.forEach((row, index) => {
            const addressInput = row.querySelector('.block-reward-address-input');
            const commentInput = row.querySelector('.block-reward-comment-input');
            
            if (addressInput && commentInput) {
                const address = addressInput.value.trim();
                const comment = commentInput.value.trim();
                
                console.log(`Row ${index}: address="${address ? '[MASKED]' : ''}", comment="${comment}"`);
                
                if (address) {
                    entries.push({
                        address: address,
                        comment: comment || 'Block Reward Address'
                    });
                }
            }
        });
        
        console.log('Block reward table getValue returning:', entries.length, 'entries (addresses masked for privacy)');
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
    
    addressCell.appendChild(addressInput);
    
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

async function fetchBitaxeBestDiff(ip, cell) {
    try {
        const response = await fetch(`/api/bitaxe/${encodeURIComponent(ip)}/best-diff`);
        if (response.ok) {
            const data = await response.json();
            if (data.online) {
                cell.textContent = formatBitaxeDifficulty(data.best_diff);
                cell.style.color = 'var(--accent)';
            } else {
                cell.textContent = 'Offline';
                cell.style.color = '#ff6b6b';
            }
        } else {
            cell.textContent = 'Error';
            cell.style.color = '#ff6b6b';
        }
    } catch (error) {
        console.error('Error fetching Bitaxe best difficulty:', error);
        cell.textContent = 'Error';
        cell.style.color = '#ff6b6b';
    }
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
            <div id="progress-bar" style="height: 8px; background: #F7931A; width: 0%; transition: width 0.3s;"></div>
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
    memesLabel.innerHTML = `${window.translations?.current_memes || 'Current Memes'} <span id="meme-image-count" style="color: var(--text-muted); font-weight: 400;"></span>`;
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




// --- OPSec Image Management ---

function createOpsecThumb(img) {
    const thumb = document.createElement('div');
    thumb.className = 'meme-thumbnail';
    thumb.style.position = 'relative';

    const imgEl = document.createElement('img');
    imgEl.src = img.thumb_url || img.url;
    imgEl.alt = img.filename;
    imgEl.dataset.filename = img.filename;
    imgEl.loading = 'lazy';
    imgEl.style.cssText = 'width:100%; aspect-ratio:1; object-fit:cover; border-radius:8px; cursor:pointer;';
    imgEl.title = img.filename;
    imgEl.onclick = () => openOpsecModal(img.filename, img.url);

    const nameEl = document.createElement('div');
    nameEl.className = 'meme-filename';
    nameEl.style.cssText = 'font-size:0.7rem; text-align:center; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding: 2px 4px;';
    nameEl.textContent = img.filename;

    const actionsEl = document.createElement('div');
    actionsEl.className = 'meme-actions';
    actionsEl.style.cssText = 'display:flex; justify-content:center; gap:4px; margin-top:4px;';
    actionsEl.innerHTML = `
        <button class="action-button" title="${window.translations?.download_meme || 'Download'}"
                onclick="downloadOpsecImage('${img.filename}')">
            <img src="/static/icons/download.svg" alt="Download" style="width:16px; height:16px; filter:brightness(0) invert(1);" />
        </button>
        <button class="action-button delete" title="${window.translations?.delete_meme || 'Delete'}"
                onclick="showOpsecDeleteModal('${img.filename}')">
            <img src="/static/icons/delete.svg" alt="Delete" style="width:16px; height:16px; filter:brightness(0) invert(1);" />
        </button>
    `;

    thumb.appendChild(imgEl);
    thumb.appendChild(nameEl);
    thumb.appendChild(actionsEl);
    return thumb;
}

// Opsec infinite scroll
let opsecScrollObserver = null;
let opsecScrollLoading = false;

function setupOpsecInfiniteScroll(sentinel) {
    if (opsecScrollObserver) {
        opsecScrollObserver.disconnect();
    }
    const scrollContainer = document.querySelector('.opsec-scroll-container');
    opsecScrollObserver = new IntersectionObserver((entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && !opsecScrollLoading) {
            const nextPage = parseInt(sentinel.dataset.nextPage, 10);
            if (nextPage) {
                loadMoreOpsecImages(nextPage, sentinel);
            }
        }
    }, { root: scrollContainer, rootMargin: '200px' });
    opsecScrollObserver.observe(sentinel);
}

async function loadOpsecImages() {
    const list = document.getElementById('opsec-images-list');
    if (!list) return;

    list.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">${window.translations?.loading || 'Loading...'}</div>`;

    try {
        const response = await fetch('/api/opsec-images?page=1&per_page=50');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const images = data.images || [];

        list.innerHTML = '';

        // Update count label
        const countLabel = document.getElementById('opsec-image-count');
        if (countLabel) countLabel.textContent = `(${data.total || images.length})`;

        if (images.length === 0) {
            list.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">${window.translations?.no_opsec_images || 'No OPSec images uploaded yet'}</p>`;
            return;
        }

        images.forEach(img => list.appendChild(createOpsecThumb(img)));

        if (data.has_next) {
            const sentinel = document.createElement('div');
            sentinel.className = 'meme-scroll-sentinel';
            sentinel.dataset.nextPage = data.page + 1;
            list.appendChild(sentinel);
            setupOpsecInfiniteScroll(sentinel);
        }
    } catch (error) {
        console.error('Error loading OPSec images:', error);
        list.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: var(--danger);">Error loading OPSec images</p>`;
    }
}

async function loadMoreOpsecImages(page, sentinel) {
    if (opsecScrollLoading) return;
    opsecScrollLoading = true;
    try {
        const response = await fetch(`/api/opsec-images?page=${page}&per_page=50`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        const images = data.images || [];

        if (!images.length) {
            sentinel.remove();
            opsecScrollLoading = false;
            return;
        }

        const list = document.getElementById('opsec-images-list');
        images.forEach(img => list.insertBefore(createOpsecThumb(img), sentinel));

        if (data.has_next) {
            sentinel.dataset.nextPage = page + 1;
        } else {
            if (opsecScrollObserver) opsecScrollObserver.disconnect();
            sentinel.remove();
        }
    } catch (error) {
        console.error('Failed to load more OPSec images:', error);
    }
    opsecScrollLoading = false;
}

function downloadOpsecImage(filename) {
    const a = document.createElement('a');
    a.href = `/api/download-opsec/${encodeURIComponent(filename)}`;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

async function deleteOpsecImage(filename) {
    try {
        const response = await fetch(`/api/delete-opsec/${encodeURIComponent(filename)}`, { method: 'DELETE' });
        const result = await response.json();
        if (result.success) {
            showNotification(window.translations?.opsec_image_deleted_successfully || 'OPSec image deleted successfully!', 'success');
            // Remove from DOM directly to preserve pagination state
            const list = document.getElementById('opsec-images-list');
            if (list) {
                const imgEl = list.querySelector(`img[data-filename="${filename}"]`);
                if (imgEl) {
                    const thumb = imgEl.closest('.meme-thumbnail');
                    if (thumb) thumb.remove();
                    // If grid is now empty (only the load-more btn or nothing left), show empty message
                    const remaining = list.querySelectorAll('.meme-thumbnail');
                    if (remaining.length === 0) {
                        const loadMoreBtn = list.querySelector('.load-more-btn');
                        if (!loadMoreBtn) {
                            list.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: var(--text-secondary);">${window.translations?.no_opsec_images || 'No OPSec images uploaded yet'}</p>`;
                        }
                    }
                }
            }
        } else {
            showNotification(result.message || window.translations?.opsec_image_delete_failed || 'Failed to delete OPSec image', 'error');
        }
    } catch (error) {
        showNotification((window.translations?.opsec_image_delete_failed || 'Failed to delete OPSec image') + ': ' + error.message, 'error');
    }
}

function createOpsecManagementInterface(field) {
    const container = document.createElement('div');
    container.className = 'meme-management-container';

    // Upload section
    const uploadSection = document.createElement('div');
    uploadSection.className = 'form-group';
    uploadSection.style.marginBottom = '30px';

    const uploadLabel = document.createElement('label');
    uploadLabel.className = 'form-label';
    uploadLabel.textContent = window.translations?.upload_opsec_image || 'Upload OPSec Cover Image';
    uploadSection.appendChild(uploadLabel);

    const uploadArea = document.createElement('div');
    uploadArea.className = 'upload-area';
    uploadArea.id = 'opsec-upload-area';
    uploadArea.innerHTML = `
        <input type="file" id="opsec-file-input" accept="image/*" multiple style="display: none;">
        <div class="upload-placeholder">
            <img src="/static/icons/add_meme.svg" alt="Add Image" class="upload-icon" style="width: 2rem; height: 2rem; margin-bottom: 10px;" />
            <p>${window.translations?.upload_placeholder || 'Click to select image(s) or drag & drop'}</p>
            <p style="font-size: 0.8rem; color: var(--accent);">${window.translations?.upload_formats || 'Supported: PNG, JPG, JPEG, GIF, WebP (Multiple files allowed)'}</p>
        </div>
    `;

    const uploadProgress = document.createElement('div');
    uploadProgress.id = 'opsec-upload-progress';
    uploadProgress.style.display = 'none';
    uploadProgress.style.marginTop = '10px';
    uploadProgress.innerHTML = `
        <div style="background: var(--bg-input); border-radius: 10px; overflow: hidden;">
            <div id="opsec-progress-bar" style="height: 8px; background: #F7931A; width: 0%; transition: width 0.3s;"></div>
        </div>
        <p id="opsec-upload-status" style="margin-top: 5px; font-size: 0.9rem;"></p>
    `;

    uploadSection.appendChild(uploadArea);
    uploadSection.appendChild(uploadProgress);

    // Current images section
    const imagesSection = document.createElement('div');
    imagesSection.className = 'form-group';

    const imagesLabel = document.createElement('label');
    imagesLabel.className = 'form-label';
    imagesLabel.innerHTML = `${window.translations?.current_opsec_images || 'Current OPSec Images'} <span id="opsec-image-count" style="color: var(--text-muted); font-weight: 400;"></span>`;
    imagesSection.appendChild(imagesLabel);

    const imagesList = document.createElement('div');
    imagesList.id = 'opsec-images-list';
    imagesList.style.display = 'grid';
    imagesList.style.gridTemplateColumns = 'repeat(auto-fill, minmax(100px, 1fr))';
    imagesList.style.gap = '10px';
    imagesList.style.marginTop = '10px';

    // Wrap in scrollable container so user can scroll past the section
    const opsecScrollContainer = document.createElement('div');
    opsecScrollContainer.className = 'opsec-scroll-container';
    opsecScrollContainer.appendChild(imagesList);
    imagesSection.appendChild(opsecScrollContainer);

    container.appendChild(uploadSection);
    container.appendChild(imagesSection);

    // Wire up upload area
    setTimeout(() => {
        const area = document.getElementById('opsec-upload-area');
        const fileInput = document.getElementById('opsec-file-input');
        if (!area || !fileInput) return;

        area.addEventListener('click', () => fileInput.click());
        area.addEventListener('dragover', (e) => { e.preventDefault(); area.classList.add('dragover'); });
        area.addEventListener('dragleave', () => area.classList.remove('dragover'));
        area.addEventListener('drop', (e) => {
            e.preventDefault();
            area.classList.remove('dragover');
            uploadOpsecFiles(Array.from(e.dataTransfer.files));
        });
        fileInput.addEventListener('change', () => {
            uploadOpsecFiles(Array.from(fileInput.files));
            fileInput.value = '';
        });

        loadOpsecImages();
    }, 100);

    container.getValue = () => null;
    return container;
}

function createDonationHistoryInterface() {
    const container = document.createElement('div');
    container.className = 'donation-history-container';
    container.style.cssText = 'margin-top: 12px;';

    const t = window.translations || {};
    const title = document.createElement('h4');
    title.textContent = t.recent_donations || 'Recent Donations';
    title.style.cssText = 'margin: 0 0 10px 0; font-size: 15px;';
    container.appendChild(title);

    const tableWrapper = document.createElement('div');
    tableWrapper.style.cssText = 'overflow-x: auto; overflow-y: auto; max-height: 210px; border: 1px solid var(--border-color); border-radius: 6px;';

    const table = document.createElement('table');
    table.style.cssText = 'width: 100%; border-collapse: collapse; font-size: 13px;';
    table.innerHTML = `
        <thead>
            <tr style="border-bottom: 1px solid var(--border-color);">
                <th style="text-align:left; padding: 6px 8px; position: sticky; top: 0; background: var(--bg-card); z-index: 1; color: var(--text-secondary);">${t.donation_col_time || 'Time'}</th>
                <th style="text-align:right; padding: 6px 8px; position: sticky; top: 0; background: var(--bg-card); z-index: 1; color: var(--text-secondary);">Sats</th>
                <th style="text-align:left; padding: 6px 8px; position: sticky; top: 0; background: var(--bg-card); z-index: 1; color: var(--text-secondary);">${t.donation_col_message || 'Message'}</th>
            </tr>
        </thead>
        <tbody id="donation-history-tbody"><tr><td colspan="3" style="padding:8px; color: var(--text-muted);">${t.loading || 'Loading…'}</td></tr></tbody>
    `;
    tableWrapper.appendChild(table);
    container.appendChild(tableWrapper);

    // Fixed total row (outside the scrollable wrapper)
    const totalRow = document.createElement('div');
    totalRow.id = 'donation-total-row';
    totalRow.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding: 6px 10px; border: 1px solid var(--border-color); border-top: none; border-radius: 0 0 6px 6px; font-size:13px; background: var(--bg-card);';
    totalRow.innerHTML = `<span style="color:var(--text-muted);">${t.donation_total || 'Total received'}</span><span id="donation-total-sats" style="font-weight:bold; color:var(--accent); font-family:var(--font-mono);">—</span>`;
    container.appendChild(totalRow);

    // Load donations from API
    fetch('/api/donations')
        .then(r => r.json())
        .then(data => {
            const tbody = table.querySelector('#donation-history-tbody');
            const donations = data.donations || [];
            if (donations.length === 0) {
                tbody.innerHTML = `<tr><td colspan="3" style="padding:8px; color: var(--text-muted);">${t.no_donations_yet || 'No donations yet.'}</td></tr>`;
                return;
            }
            tbody.innerHTML = donations.map(d => {
                const ts = d.timestamp ? new Date(d.timestamp + 'Z').toLocaleString() : '—';
                const sats = (d.amount_sats || 0).toLocaleString();
                const msg = d.message ? escapeHtml(d.message) : '<em style="color: var(--text-muted);">—</em>';
                return `<tr style="border-bottom:1px solid var(--border-color);">
                    <td style="padding:5px 8px; white-space:nowrap;">${ts}</td>
                    <td style="padding:5px 8px; text-align:right; font-weight:bold; color:var(--accent); font-family:var(--font-mono);">${sats}</td>
                    <td style="padding:5px 8px;">${msg}</td>
                </tr>`;
            }).join('');
            const total = donations.reduce((sum, d) => sum + (d.amount_sats || 0), 0);
            const totalEl = container.querySelector('#donation-total-sats');
            if (totalEl) {
                totalEl.dataset.total = total;
                totalEl.textContent = total.toLocaleString() + ' sats';
            }
        })
        .catch(() => {
            const tbody = table.querySelector('#donation-history-tbody');
            tbody.innerHTML = `<tr><td colspan="3" style="padding:8px; color: var(--text-muted);">${t.could_not_load_donations || 'Could not load donations.'}</td></tr>`;
        });

    container.getValue = () => null;
    return container;
}

function escapeHtml(text) {
    return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Live toast helpers ────────────────────────────────────────────────────────

// Resolve the configured section colour for the current theme
function _getLiveToastColor(keyBase) {
    const isDark = document.body.classList.contains('dark-mode');
    const cfg = window.currentConfig || {};
    return cfg[isDark ? keyBase + '_dark' : keyBase + '_light'] || '#F7931A';
}

// Return (or create) the shared upper-right toast stack container
function _getLiveToastContainer() {
    let el = document.getElementById('block-toast-container');
    if (!el) {
        el = document.createElement('div');
        el.id = 'block-toast-container';
        el.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
            font-family: 'Roboto', Arial, sans-serif;
        `;
        document.body.appendChild(el);
    }
    return el;
}

// Build and display a glass-card toast in the shared upper-right container
function _buildLiveToast(titleText, bodyHtml, titleColor, autoDismissMs = 6000) {
    const isDark      = document.body.classList.contains('dark-mode');
    const toastBg     = isDark ? 'rgba(30, 30, 36, 0.92)'  : 'rgba(255, 255, 255, 0.95)';
    const toastColor  = isDark ? '#e8e8ec'                  : '#1a1a2e';
    const toastBorder = isDark ? 'rgba(255, 255, 255, 0.08)': 'rgba(0, 0, 0, 0.1)';
    const toastShadow = isDark
        ? '0 8px 32px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(255,255,255,0.06)'
        : '0 8px 32px rgba(0, 0, 0, 0.12), 0 0 0 1px rgba(0,0,0,0.04)';
    const closeBtnBg      = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
    const closeBtnColor   = isDark ? '#9a9aaa'                   : '#555';
    const closeBtnHoverBg = isDark ? 'rgba(255, 255, 255, 0.15)' : 'rgba(0, 0, 0, 0.12)';

    const toast = document.createElement('div');
    toast.style.cssText = `
        background: ${toastBg};
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        color: ${toastColor};
        padding: 14px 18px;
        border-radius: 14px;
        box-shadow: ${toastShadow};
        border: 1px solid ${toastBorder};
        margin-bottom: 10px;
        min-width: 280px;
        max-width: 360px;
        opacity: 0;
        transform: translateX(100%);
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        font-size: 13px;
        line-height: 1.4;
        cursor: pointer;
    `;

    const closeBtn = document.createElement('button');
    closeBtn.innerHTML = '&times;';
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
        width: 26px;
        height: 26px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
        transition: background-color 0.2s;
        font-weight: bold;
        line-height: 1;
    `;

    const closeToast = () => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 400);
    };

    closeBtn.addEventListener('click', e => { e.stopPropagation(); closeToast(); });
    closeBtn.addEventListener('mouseenter', () => { closeBtn.style.backgroundColor = closeBtnHoverBg; });
    closeBtn.addEventListener('mouseleave', () => { closeBtn.style.backgroundColor = closeBtnBg; });
    toast.addEventListener('click', closeToast);

    const content = document.createElement('div');
    content.style.cssText = 'margin-right: 28px;';
    content.innerHTML =
        `<div style="font-weight:600;font-size:14px;margin-bottom:5px;color:${titleColor};">${titleText}</div>` +
        `<div style="opacity:0.85;font-size:13px;">${bodyHtml}</div>`;

    toast.appendChild(closeBtn);
    toast.appendChild(content);
    _getLiveToastContainer().appendChild(toast);

    requestAnimationFrame(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(0)';
    });

    const timer = setTimeout(closeToast, autoDismissMs);
    toast.closeToast = () => { clearTimeout(timer); closeToast(); };
}

function showDonationToast(donation) {
    const sats     = (donation.amount_sats || 0).toLocaleString();
    const satLabel = donation.amount_sats === 1 ? 'sat' : 'sats';
    const bodyHtml = `<strong>${sats} ${satLabel}</strong>` +
        (donation.message
            ? `<br><span style="opacity:0.7;font-size:12px;">"${escapeHtml(donation.message)}"</span>`
            : '');
    const title = window.translations?.donation_toast_title || 'Lightning Donation';
    _buildLiveToast(title, bodyHtml, _getLiveToastColor('color_donation'), 8000);
}

// title    — short section label shown in the configured colour (e.g. "Wallet", "Bitaxe")
// message  — detail text (user data — will be HTML-escaped)
// colorKey — config key base (e.g. 'color_wallets', 'color_bitaxe_stats')
function showLiveToast(title, message, colorKey) {
    _buildLiveToast(title, escapeHtml(message), _getLiveToastColor(colorKey));
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
        progressBar.style.width = '0%';
        statusText.textContent = t?.upload_checking_duplicates || 'Checking for duplicates...';
        statusText.style.color = '#F7931A';
    }

    // Fetch existing hashes for duplicate detection
    const existingHashes = await getExistingOpsecHashes();

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

        // Offer rename dialog (same as meme upload)
        const newName = await showRenameDialog(file.name, file);

        if (newName === file.name) {
            filesToUpload.push({ file, name: file.name, hash });
        } else {
            const renamedFile = new File([file], newName, { type: file.type });
            filesToUpload.push({ file: renamedFile, name: newName, hash });
        }
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
        console.log('OPSec duplicates detected:\n' + dupList);
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
                progressBar.style.width = `${(i / filesToUpload.length) * 100}%`;
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

        if (progressBar) progressBar.style.width = '100%';

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
                formConfig[key] = parseInt(element.value) || 0;
            } else {
                formConfig[key] = element.value;
            }
        });
        
        // Additional safety check: ensure all boolean fields are properly collected
        // This is a fallback in case boolean switches weren't collected above
        const expectedBooleanFields = ['prioritize_large_scaled_meme', 'color_mode_dark', 'show_btc_price_block', 'show_bitaxe_block', 'show_wallet_balances_block', 'show_donation_block', 'e-ink-display-connected'];
        expectedBooleanFields.forEach(fieldName => {
            if (!(fieldName in formConfig)) {
                console.log(`🚨 [FALLBACK] Missing boolean field ${fieldName} in form collection, attempting to recover...`);
                const element = document.querySelector(`[data-config-key="${fieldName}"]`);
                if (element && element.getValue) {
                    const value = element.getValue();
                    formConfig[fieldName] = value;
                    console.log(`🔧 [FALLBACK] Recovered boolean field ${fieldName}: ${value}`);
                } else if (element && element.classList && element.classList.contains('boolean-switch')) {
                    // Direct fallback for boolean switches
                    const switchEl = element.querySelector('.switch');
                    if (switchEl) {
                        const isActive = switchEl.classList.contains('active');
                        formConfig[fieldName] = isActive;
                        console.log(`🔧 [FALLBACK] Direct boolean recovery for ${fieldName}: ${isActive}`);
                    }
                } else {
                    console.log(`❌ [FALLBACK] Could not recover boolean field ${fieldName}, element not found or invalid`);
                }
            }
        });
        
        // If we have a pending language change, make sure it's included in formConfig
        if (pendingLanguageChange) {
            formConfig.language = pendingLanguageChange;
        }
        
        // Merge form values with current config to preserve non-form fields
        const newConfig = { ...currentConfig, ...formConfig };

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
            
            console.log('👁️ Language change detection (saveConfiguration):', {
                oldLanguage,
                newLanguage,
                pendingLanguageChange,
                languageChanged,
                'pendingLanguageChange !== null': pendingLanguageChange !== null,
                'formConfig has language': !!formConfig.language
            });
            
            // Update current config
            currentConfig = newConfig;
            window.currentConfig = newConfig; // Make available globally
            
            // Handle language change with page reload
            if (languageChanged) {
                console.log('⚙️ LANGUAGE CHANGE DETECTED! (saveConfiguration) Processing language change from', oldLanguage, 'to', newLanguage);
                
                // Clear the pending change and reload page immediately
                pendingLanguageChange = null;
                setTimeout(() => {
                    console.log('⚙️ FORCING PAGE RELOAD for language change (saveConfiguration)');
                    window.location.reload(true); // Force reload from server
                }, 500); // Very short timeout for immediate reload
                
                return true; // Return success before reload
            } else {
                // Fallback check: if language in formConfig is different from what was in currentConfig
                if (formConfig.language && formConfig.language !== oldLanguage) {
                    console.log('⚙️ FALLBACK (saveConfiguration): Language difference detected via form config!', oldLanguage, '->', formConfig.language);
                    setTimeout(() => {
                        console.log('⚙️ FALLBACK PAGE RELOAD for language change (saveConfiguration)');
                        window.location.reload(true);
                    }, 500);
                    return true;
                }
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
                    formConfig[key] = parseInt(element.value) || 0;
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
                    showNotification('Language changed! Reloading page...', 'success');
                    pendingLanguageChange = null;
                    setTimeout(() => {
                        window.location.reload(true);
                    }, 1000);
                } else if (formConfig.language && formConfig.language !== oldLanguage) {
                    showNotification('Language changed! Reloading page...', 'success');
                    setTimeout(() => {
                        window.location.reload(true);
                    }, 1000);
                } else {
                    showNotification(window.translations?.configuration_saved || 'Configuration saved successfully!', 'success');
                }
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
} else if (isConfigPage) {
    console.warn('Save button not found in DOM - expected on config page');
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
            console.log(`Section toggle for ${key} saved successfully`);
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
    
    if (modalFilenameDisplay && filenameInput && editBtn && saveBtn && cancelBtn) {
        modalFilenameDisplay.style.display = 'inline';
        editBtn.style.display = 'inline-block';
        filenameInput.style.display = 'none';
        saveBtn.style.display = 'none';
        cancelBtn.style.display = 'none';
    }
    
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
        // Show save button when user tags change
        if (saveTagsBtn) {
            saveTagsBtn.style.display = 'none';
            HTMLElement.prototype.addEventListener.call(tagsInput, 'change', () => {
                saveTagsBtn.style.display = 'inline-block';
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
            if (saveBtn) saveBtn.style.display = 'none';
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

    if (modalFilenameDisplay && filenameInput && editBtn && saveBtn && cancelBtn) {
        modalFilenameDisplay.style.display = 'inline';
        editBtn.style.display = 'inline-block';
        filenameInput.style.display = 'none';
        saveBtn.style.display = 'none';
        cancelBtn.style.display = 'none';
    }

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

    if (!filenameDisplay || !filenameInput || !editBtn || !saveBtn || !cancelBtn) return;

    const filename = currentModalOpsec.filename;
    const nameWithoutExt = filename.substring(0, filename.lastIndexOf('.'));

    filenameDisplay.style.display = 'none';
    editBtn.style.display = 'none';
    filenameInput.style.display = 'inline-block';
    saveBtn.style.display = 'inline-block';
    cancelBtn.style.display = 'inline-block';

    filenameInput.value = nameWithoutExt;
    filenameInput.focus();
    filenameInput.select();

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
    currentModalOpsec.url = `/static/opsec/${newFilename}`;

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

    if (!filenameDisplay || !filenameInput || !editBtn || !saveBtn || !cancelBtn) return;

    filenameDisplay.style.display = 'inline';
    editBtn.style.display = 'inline-block';
    filenameInput.style.display = 'none';
    saveBtn.style.display = 'none';
    cancelBtn.style.display = 'none';
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
                img.src = `/static/opsec/${newFilename}`;
                img.title = newFilename;
                const thumb = img.closest('.meme-thumbnail');
                if (thumb) {
                    const nameEl = thumb.querySelector('.meme-filename');
                    if (nameEl) nameEl.textContent = newFilename;
                    // Update action buttons to use new filename
                    const actionsDiv = thumb.querySelector('.meme-actions');
                    if (actionsDiv) {
                        actionsDiv.innerHTML = `
                            <button class="action-button" onclick="downloadOpsecImage('${newFilename}')" title="${window.translations?.download_meme || 'Download'}">
                                <img src="/static/icons/download.svg" alt="Download" style="width:16px; height:16px; filter:brightness(0) invert(1);" />
                            </button>
                            <button class="action-button delete" onclick="showOpsecDeleteModal('${newFilename}')" title="${window.translations?.delete_meme || 'Delete'}">
                                <img src="/static/icons/delete.svg" alt="Delete" style="width:16px; height:16px; filter:brightness(0) invert(1);" />
                            </button>
                        `;
                    }
                    // Update onclick to use new filename
                    img.onclick = () => openOpsecModal(newFilename, `/static/opsec/${newFilename}`);
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
        a.href = `/api/download-opsec/${currentModalOpsec.filename}`;
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
                console.log('Test API error:', apiError);
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
                            }
            if (commentInput && !commentInput.value) {
                commentInput.value = entry.comment;
                            }
            
            // Update the balance display
            const balanceDisplay = row.querySelector('.wallet-balance-display');
            if (balanceDisplay) {
                const balance = entry.cached_balance || 0.0;
                balanceDisplay.textContent = `${balance.toFixed(8)}`;
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

// Show notification message
function showNotification(message, type = 'info', duration = 5000) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    // Style the notification
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 6px;
        color: white;
        font-weight: 500;
        z-index: 9999;
        max-width: 400px;
        word-wrap: break-word;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        animation: slideIn 0.3s ease-out;
    `;
    
    // Set background color based on type
    switch (type) {
        case 'success':
            notification.style.backgroundColor = '#38a169';
            break;
        case 'warning':
            notification.style.backgroundColor = '#ffc107';
            notification.style.color = '#212529';
            break;
        case 'error':
            notification.style.backgroundColor = '#e53e3e';
            break;
        default:
            notification.style.backgroundColor = '#17a2b8';
    }
    
    // Add animation styles if not already present
    if (!document.querySelector('#notification-styles')) {
        const styles = document.createElement('style');
        styles.id = 'notification-styles';
        styles.textContent = `
            @keyframes slideIn {
                from { transform: translateX(100%); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            @keyframes slideOut {
                from { transform: translateX(0); opacity: 1; }
                to { transform: translateX(100%); opacity: 0; }
            }
        `;
        document.head.appendChild(styles);
    }
    
    // Add to page
    document.body.appendChild(notification);
    
    // Auto-remove after duration
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, duration);
    
    return notification;
}

// WebSocket connection for real-time updates
let configSocket = null;
let reconnectingConfig = false;
let reconnectTimeoutConfig = null;

function connectConfigSocket() {
    if (typeof io === 'undefined') {
        console.log('Socket.IO not available');
        return;
    }
    configSocket = io();
    setupConfigSocketHandlers();
}

function setupConfigSocketHandlers() {
    configSocket.on('connect', () => {
        console.log('🔌 Config WebSocket connected');
        reconnectingConfig = false;
        // Register this page for notifications
        registerPageForNotifications('config');
        // Subscribe to block notifications (always enabled)
        subscribeToBlockNotifications();
    });

    configSocket.on('disconnect', () => {
        console.log('🔌 Config WebSocket disconnected');
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
        console.log('💾 Received wallet balance update:', data ? Object.keys(data).length + ' addresses (data masked for privacy)' : 'no data');
        updateWalletBalancesFromWebSocket(data);
        showNotification(window.translations?.wallet_balances_updated || 'Wallet balances updated automatically!', 'success');
    });

    // Listen for block notifications
    configSocket.on('new_block_notification', (data) => {
        console.log("👁️ New block notification received:", data && data.height ? 'block ' + data.height + ' (details masked for privacy)' : 'notification data');
        
        const state = getNotificationState();
        const now = Date.now();
        
        // Allow updates for the same block (enriched data) but prevent duplicate new blocks
        const isEnrichment = data.enriched === true;
        const isDifferentBlock = !state.lastBlockHeight || state.lastBlockHeight !== data.block_height;
        
        if (!isEnrichment && !isDifferentBlock && (now - state.lastNotification) < 10000) {
            console.log("⚠️ Duplicate block notification detected, skipping");
            return;
        }
        
        // Update state for new blocks (not enrichments)
        if (!isEnrichment || isDifferentBlock) {
            state.lastNotification = now;
            state.lastBlockHeight = data.block_height;
            setNotificationState(state);
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

    configSocket.on('block_notification_status', (data) => {
        if (data.status === 'subscribed') {
            console.log('⚙️ [CONFIG] ' + (data.message || 'Subscribed to live block notifications'));
        } else if (data.status === 'unsubscribed') {
            console.log('⚙️ [CONFIG] Unsubscribed from live block notifications');
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
                    console.log('⚙️ Received cross-page block notification');
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
    if (reconnectingConfig) return;
    reconnectingConfig = true;
    if (reconnectTimeoutConfig) clearTimeout(reconnectTimeoutConfig);
    reconnectTimeoutConfig = setTimeout(() => {
        console.log("⚙️ Attempting Config WebSocket reconnect...");
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
                        balanceDisplay.textContent = `${newBalance.toFixed(8)}`;
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
                button.disabled = true;
                // Keep original content, just disable the button
                
                try {
                    const formConfig = {};
                    
                    console.log('👁️ [SAVE DEBUG] Starting form collection...');
                    
                    // Collect all form values using the proper method that handles custom getValue() functions
                    document.querySelectorAll('[data-config-key]').forEach(element => {
                        const key = element.dataset.configKey;
                        
                        if (element.getValue) {
                            // Use custom getValue method for boolean switches and other custom elements
                            const value = element.getValue();
                            formConfig[key] = value;
                            console.log(`👁️ [SAVE DEBUG] Collected ${key} via getValue(): ${value} (type: ${typeof value})`);
                        } else if (element.type === 'checkbox') {
                            formConfig[key] = element.checked;
                            console.log(`👁️ [SAVE DEBUG] Collected ${key} via checkbox: ${element.checked}`);
                        } else if (element.type === 'number') {
                            formConfig[key] = parseFloat(element.value) || 0;
                            console.log(`👁️ [SAVE DEBUG] Collected ${key} via number: ${formConfig[key]}`);
                        } else {
                            formConfig[key] = element.value;
                            console.log(`👁️ [SAVE DEBUG] Collected ${key} via value: ${element.value}`);
                        }
                    });
                    
                    console.log('👁️ [SAVE DEBUG] Final formConfig:', formConfig);
                    
                    // Temporary: Show what we collected for boolean fields
                    const booleanFields = ['prioritize_large_scaled_meme', 'color_mode_dark', 'show_btc_price_block', 'show_bitaxe_block', 'show_wallet_balances_block', 'show_donation_block', 'e-ink-display-connected'];
                    const booleanData = {};
                    booleanFields.forEach(field => {
                        if (formConfig.hasOwnProperty(field)) {
                            booleanData[field] = formConfig[field];
                        }
                    });
                    console.log('👁️ [SAVE DEBUG] Boolean fields being saved:', booleanData);
                    
                    
                    // If we have a pending language change, make sure it's included in formConfig
                    if (pendingLanguageChange) {
                        formConfig.language = pendingLanguageChange;
                        console.log('Including pending language change in form config:', pendingLanguageChange);
                    }
                    
                    console.log('Form config collected: object with', Object.keys(formConfig).length, 'fields (sensitive data masked)');
                    console.log('Current config language:', currentConfig.language);
                    console.log('Form config language:', formConfig.language);
                    console.log('Pending language change:', pendingLanguageChange);
                    
                    console.log('Saving configuration: object with', Object.keys(formConfig).length, 'fields (sensitive data masked)');
                    
                    const response = await fetch('/api/config', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(formConfig)
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        // Check if language was changed using pendingLanguageChange
                        const oldLanguage = currentConfig.language;
                        const newLanguage = pendingLanguageChange || formConfig.language;
                        const languageChanged = pendingLanguageChange !== null || (newLanguage && newLanguage !== oldLanguage);
                        
                        console.log('👁️ Language change detection (nav buttons):', {
                            oldLanguage,
                            newLanguage,
                            pendingLanguageChange,
                            languageChanged,
                            'pendingLanguageChange !== null': pendingLanguageChange !== null,
                            'formConfig has language': !!formConfig.language
                        });
                        
                        // Update current config
                        currentConfig = { ...currentConfig, ...formConfig };
                        
                        // Handle language change with new language success message
                        if (languageChanged) {
                            console.log('⚙️ LANGUAGE CHANGE DETECTED! (nav buttons) Processing language change from', oldLanguage, 'to', newLanguage);
                            
                            // Show notification and force page reload
                            showNotification('Language changed! Reloading page...', 'success');
                            
                            // Clear the pending change and reload page immediately
                            pendingLanguageChange = null;
                            setTimeout(() => {
                                console.log('⚙️ FORCING PAGE RELOAD for language change (nav buttons)');
                                window.location.reload(true); // Force reload from server
                            }, 1000); // Shorter timeout
                        } else {
                            // Fallback check: if language in formConfig is different from what was in currentConfig
                            if (formConfig.language && formConfig.language !== oldLanguage) {
                                console.log('⚙️ FALLBACK (nav): Language difference detected via form config!', oldLanguage, '->', formConfig.language);
                                showNotification('Language changed! Reloading page...', 'success');
                                setTimeout(() => {
                                    console.log('⚙️ FALLBACK PAGE RELOAD for language change (nav)');
                                    window.location.reload(true);
                                }, 1000);
                            } else {
                                showNotification(window.translations?.configuration_saved || 'Configuration saved successfully!', 'success');
                            }
                        }
                    } else {
                        showNotification(result.message || window.translations?.failed_to_save_configuration || 'Failed to save configuration', 'error');
                    }
                } catch (error) {
                    console.error('Error saving configuration:', error);
                    showNotification(window.translations?.failed_to_save_configuration || 'Failed to save configuration', 'error');
                } finally {
                    button.disabled = false;
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
                    danger: true
                });
                if (confirmed) {
                    try {
                        const response = await fetch('/api/logout', { method: 'POST' });
                        const result = await response.json();
                        window.location.href = result.public_dashboard ? '/' : '/login';
                    } catch (error) {
                        console.error('Logout failed:', error);
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
    // Always subscribe for config page, even if other pages are subscribed
    if (configSocket) {
        console.log('⚙️ Config page subscribing to live block notifications...');
        configSocket.emit('subscribe_block_notifications', { page: 'config' });
    }
}

function unsubscribeFromBlockNotifications() {
    if (configSocket) {
        console.log('⚙️ Config page unsubscribing from live block notifications...');
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
            z-index: 10000;
            font-family: 'Roboto', Arial, sans-serif;
        `;
        document.body.appendChild(toastContainer);
    }
    
    const blockHeight = blockData.block_height;
    const toastId = `toast-${blockHeight}`;
    
    // Check if toast already exists for this block (for enrichment updates)
    let toast = document.getElementById(toastId);
    const isUpdate = toast !== null;
    
    if (!toast) {
        // Create new toast element
        toast = document.createElement('div');
        toast.id = toastId;
        const isDark = document.body.classList.contains('dark-mode');
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
    const heightFormatted = blockData.block_height.toLocaleString().replace(/,/g, '.');
    const rewardFormatted = blockData.total_reward_btc.toFixed(8);
    const feesFormatted = blockData.total_fees_btc.toFixed(4);
    const medianFeeFormatted = blockData.median_fee_sat_vb.toFixed(1);
    
    // Find the content div or create toast content
    let contentDiv = toast.querySelector('.toast-content');
    if (!contentDiv) {
        contentDiv = document.createElement('div');
        contentDiv.className = 'toast-content';
        contentDiv.style.cssText = 'margin-right: 30px;';
        toast.appendChild(contentDiv);
    }
    
    // Update content (works for both new and enriched data)
    contentDiv.innerHTML = `
        <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px; color: #FFD700;">
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
            <span style="opacity: 0.8;">Reward:</span> <span style="font-weight: 500; color: #90EE90;">${rewardFormatted} BTC</span>
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
    // Setup navigation buttons
    setupNavigationButtons();
    
    // Delay WebSocket initialization to ensure everything is loaded
    setTimeout(initializeWebSocket, 1000);
});

// Testing function that can be called from browser console
window.testConfigSave = function() {
    console.log('🧪 Starting config save test...');
    
    // Test current boolean values
    const booleanFields = ['prioritize_large_scaled_meme', 'color_mode_dark', 'show_btc_price_block', 'show_bitaxe_block', 'show_wallet_balances_block', 'show_donation_block', 'e-ink-display-connected'];
    
    console.log('💾 Current boolean values:');
    booleanFields.forEach(fieldName => {
        const element = document.querySelector(`[data-config-key="${fieldName}"]`);
        if (element && element.getValue) {
            console.log(`  ${fieldName}: ${element.getValue()}`);
        } else {
            console.log(`  ${fieldName}: NOT FOUND or no getValue method`);
        }
    });
    
    // Trigger save
    console.log('💾 Triggering save configuration...');
    saveConfiguration();
    
    return 'Test initiated - check console for results';
};


