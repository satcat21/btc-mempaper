// Fix: Define closeMemeModal globally for HTML onclick handlers
function closeMemeModal() {
    const memeModal = document.getElementById('meme-modal');
    if (memeModal) {
        memeModal.style.display = 'none';
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

            // Example: listen for block notifications
            socket.on('block_notification', function(data) {
                console.log('🔔 [CONFIG] Block notification:', data);
                // You can add custom notification handling here
            });
        } else {
            console.error('Socket.IO client (window.io) not found. Make sure socket.io.min.js is loaded.');
        }
    }
let currentConfig = {};
let configSchema = {};
let categories = [];
let colorOptions = [];
let pendingLanguageChange = null;
let memeToDelete = null;

// Check if we're on the config page
const isConfigPage = window.location.pathname.includes('/config');

// Helper function to get the toggle key for a category
function getSectionToggleKey(categoryId) {
    const toggleMapping = {
        'price_stats': 'show_btc_price_block',
        'bitaxe_stats': 'show_bitaxe_block',
        'wallet_monitoring': 'show_wallet_balances_block',
        'eink_display': 'e-ink-display-connected'
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

// Create password change interface for admin password
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
    changeButton.style.backgroundColor = '#667eea';
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
    saveButton.style.backgroundColor = '#667eea';
    saveButton.style.color = 'white';
    saveButton.style.border = 'none';
    saveButton.style.padding = '8px 16px';
    saveButton.style.borderRadius = '4px';
    saveButton.style.cursor = 'pointer';
    saveButton.textContent = 'Save';
    
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
    cancelButton.textContent = 'Cancel';
    
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
            saveButton.textContent = 'Save';
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
                    console.log('🔔 Received cross-page block notification');
                    showBlockToast(notificationData.data);
                }
            } catch (error) {
                console.warn('Error parsing cross-page notification:', error);
            }
        }
    });
});

// Setup modal functionality
function setupModals() {
    // Delete confirmation modal
    const confirmDeleteBtn = document.getElementById('confirm-delete');
    const cancelDeleteBtn = document.getElementById('cancel-delete');
    
    if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener('click', async () => {
            if (memeToDelete) {
                await deleteMeme(memeToDelete);
                hideDeleteModal();
            }
        });
    }
    
    if (cancelDeleteBtn) {
        cancelDeleteBtn.addEventListener('click', () => {
            hideDeleteModal();
        });
    }
}

// Modal helper functions
function showDeleteModal(filename) {
    memeToDelete = filename;
    const deleteModal = document.getElementById('delete-modal');
    if (deleteModal) {
        deleteModal.style.display = 'flex';
    } else if (isConfigPage) {
        console.warn('Delete modal not found');
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
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            uploadFile(files[0]);
        }
    });
    
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            uploadFile(e.target.files[0]);
        }
    });
}

// Upload file function
async function uploadFile(file) {
    const progressDiv = document.getElementById('upload-progress');
    const progressBar = document.getElementById('progress-bar');
    const statusText = document.getElementById('upload-status');
    
    if (!progressDiv || !progressBar || !statusText) {
        if (isConfigPage) {
            console.warn('Upload progress elements not found - uploading without progress indication');
        }
    } else {
        progressDiv.style.display = 'block';
        progressBar.style.width = '0%';
        statusText.textContent = 'Uploading...';
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/upload-meme', {
            method: 'POST',
            body: formData
        });
        
        if (progressBar) {
            progressBar.style.width = '100%';
        }
        
        const result = await response.json();
        
        if (result.success) {
            if (statusText) {
                statusText.textContent = window.translations.upload_successful;
                statusText.style.color = '#28a745';
            }
            clearMemeCache(); // Clear cache before reloading
            loadMemes(); // Refresh memes list
            
            setTimeout(() => {
                if (progressDiv) {
                    progressDiv.style.display = 'none';
                }
            }, 2000);
        } else {
            if (statusText) {
                statusText.textContent = result.message || window.translations.upload_failed;
                statusText.style.color = '#dc3545';
            }
        }
    } catch (error) {
        if (statusText) {
            statusText.textContent = window.translations.upload_failed + ': ' + error.message;
            statusText.style.color = '#dc3545';
        }
    }
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
            clearMemeCache(); // Clear cache before reloading
            loadMemes(); // Refresh memes list
        } else {
            showNotification(result.message || window.translations.meme_delete_failed, 'error');
        }
    } catch (error) {
        showNotification(window.translations.meme_delete_failed + ': ' + error.message, 'error');
    }
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
    
    async loadMemePage(page = 1) {
        // Only block if currently loading this page
        if (this.isLoading) {
            return null;
        }
        this.isLoading = true;
        try {
            const response = await fetch(`/api/memes?page=${page}&per_page=${this.perPage}`);
            const data = await response.json();
            this.totalMemes = data.total;
            // Only mark page as loaded if fetch succeeded
            if (data && data.memes && data.memes.length > 0) {
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

async function loadMemes() {
    try {
        const memesList = document.getElementById('memes-list');
        if (!memesList) {
            console.warn('memes-list element not found, skipping meme load');
            return;
        }
        // Show loading indicator
        memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #666;">Loading memes...</div>';
        // Load first page
        const data = await memeLoader.loadMemePage(1);
        if (!data) {
            memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f44;">Failed to load memes</div>';
            return;
        }
        memesList.innerHTML = '';
        if (data.memes && data.memes.length > 0) {
            data.memes.forEach(meme => {
                const memeDiv = document.createElement('div');
                memeDiv.className = 'meme-thumbnail';
                // Create placeholder image with lazy loading
                const img = document.createElement('img');
                img.dataset.filename = meme.filename;
                img.dataset.url = meme.url;
                img.alt = meme.filename;
                img.loading = 'lazy'; // Native lazy loading as fallback
                img.style.cursor = 'pointer';
                img.title = 'Click to inspect';
                img.onclick = () => openMemeModal(meme.filename, meme.url);
                // Add placeholder until loaded
                img.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100%" height="100%" fill="%23f0f0f0"/><text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="%23999">📷</text></svg>';
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
            // Add load more button if there are more pages
            if (data.has_next) {
                const loadMoreBtn = document.createElement('button');
                loadMoreBtn.className = 'load-more-btn';
                loadMoreBtn.style.cssText = 'grid-column: 1/-1; padding: 15px; margin: 10px; background: linear-gradient(45deg, #667eea, #764ba2); color: white; border: none; border-radius: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px; transition: all 0.3s ease; font-weight: 600; box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);';
                const remaining = data.total - data.memes.length;
                
                // Create icon element
                const iconImg = document.createElement('img');
                iconImg.src = '/static/icons/unfold_more.svg';
                iconImg.style.cssText = 'width: 20px; height: 20px; filter: brightness(0) invert(1);'; // Make icon white
                
                loadMoreBtn.appendChild(iconImg);
                const loadMoreText = window.translations?.load_more_remaining || 'Load More ({remaining} remaining)';
                loadMoreBtn.appendChild(document.createTextNode(loadMoreText.replace('{remaining}', remaining)));
                loadMoreBtn.onclick = () => loadMoreMemes(data.page + 1, loadMoreBtn);
                memesList.appendChild(loadMoreBtn);
            }
            
        } else {
            memesList.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: #666;">${window.translations.no_memes_uploaded}</p>`;
        }
        
        
    } catch (error) {
        console.error('Failed to load memes:', error);
        const memesList = document.getElementById('memes-list');
        memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f44;">Failed to load memes</div>';
    }
}

async function loadMoreMemes(page, buttonElement) {
    try {
        buttonElement.textContent = 'Loading...';
        buttonElement.disabled = true;
        
        const data = await memeLoader.loadMemePage(page);
        if (!data || !data.memes.length) {
            buttonElement.remove();
            return;
        }
        
        const memesList = document.getElementById('memes-list');
        
        // Add new memes before the load more button
        data.memes.forEach(meme => {
            const memeDiv = document.createElement('div');
            memeDiv.className = 'meme-thumbnail';
            
            const img = document.createElement('img');
            img.dataset.filename = meme.filename;
            img.dataset.url = meme.url;
            img.alt = meme.filename;
            img.loading = 'lazy';
            img.style.cursor = 'pointer';
            img.title = 'Click to inspect';
            img.onclick = () => openMemeModal(meme.filename, meme.url);
            img.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100%" height="100%" fill="%23f0f0f0"/><text x="50%" y="50%" text-anchor="middle" dy=".3em" fill="%23999">📷</text></svg>';
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
            memesList.insertBefore(memeDiv, buttonElement);
        });
        
        // Update or remove the load more button
        if (data.has_next) {
            const remaining = data.total - (page * memeLoader.perPage);
            
            // Clear existing content and rebuild with icon
            buttonElement.innerHTML = '';
            buttonElement.style.cssText = 'grid-column: 1/-1; padding: 15px; margin: 10px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 8px;';
            
            const iconImg = document.createElement('img');
            iconImg.src = '/static/icons/unfold_more.svg';
            iconImg.style.cssText = 'width: 20px; height: 20px; filter: brightness(0) invert(1);';
            
            buttonElement.appendChild(iconImg);
            const loadMoreText = window.translations?.load_more_remaining || 'Load More ({remaining} remaining)';
            buttonElement.appendChild(document.createTextNode(loadMoreText.replace('{remaining}', remaining)));
            buttonElement.onclick = () => loadMoreMemes(page + 1, buttonElement);
            buttonElement.disabled = false;
        } else {
            buttonElement.remove();
        }
        
    } catch (error) {
        console.error('Failed to load more memes:', error);
        buttonElement.textContent = 'Failed to load';
        buttonElement.disabled = false;
    }
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
            await fetch('/api/logout', { method: 'POST' });
            window.location.href = '/';
        } catch (error) {
            console.error('Logout failed:', error);
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
        
        // Check wallet configuration data
        colorOptions = data.color_options || [];
        
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
        
        // Add special class for meme management section
        if (category.id === 'meme_management') {
            section.classList.add('meme-management-section');
        }
        
        const title = document.createElement('div');
        title.className = 'section-title';
        
        // Handle icon: if it's a path (starts with /), create an img tag, otherwise use as text
        let iconHtml;
        if (category.icon && category.icon.startsWith('/')) {
            iconHtml = `<img src="${category.icon}" alt="${category.label}" style="width: 24px; height: 24px; margin-right: 10px; vertical-align: middle; transform: translateY(-2px); filter: brightness(0) invert(1);">`;
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
        
        // Add fields for this category (skip the enable/disable toggle as it's now in header)
        Object.entries(configSchema).forEach(([key, field]) => {
            if (field.category === category.id && key !== enableToggleKey) {
                //console.log(`Adding field: ${key} to category ${category.id}`);
                try {
                    const formGroup = createFormField(key, field, currentConfig[key]);
                    section.appendChild(formGroup);
                    fieldsAdded++;
                } catch (error) {
                    console.error(`Error creating field ${key}:`, error);
                }
            }
        });
        
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
    
    // Skip adding label for meme_management since it manages its own interface
    if (field.type !== 'meme_management') {
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
            break;
            
        case 'password':
            if (key === 'admin_password') {
                // Special handling for admin password - show Change Password button instead
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
            
        case 'boolean':
            input = createBooleanSwitch(value);
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
        if (input.dataset) {
            input.dataset.configKey = key;
        } else {
            // Fallback for elements that might not have dataset property
            input.setAttribute('data-config-key', key);
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
        description.textContent = field.description;
        formGroup.appendChild(description);
    }
    
    return formGroup;
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
            optionDiv.style.borderBottom = '1px solid #f0f0f0';
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
    console.log('🔍 [DIAGNOSTIC] Checking all boolean elements:');
    const booleanFields = ['prioritize_large_scaled_meme', 'color_mode_dark', 'live_block_notifications_enabled', 'show_btc_price_block', 'show_bitaxe_block', 'show_wallet_balances_block', 'e-ink-display-connected'];
    
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
    // Check if tag already exists to avoid duplicates
    const existingTags = Array.from(container.querySelectorAll('.tag'))
        .map(tag => tag.textContent.replace('×', '').trim());
    
    if (existingTags.includes(value)) {
        return; // Don't add duplicate tags
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
    addressHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    addressHeader.style.backgroundColor = '#2a2d3e';
    addressHeader.style.color = '#ffffff';
    addressHeader.style.width = '35%';
    
    const commentHeader = document.createElement('th');
    commentHeader.textContent = window.translations?.wallet_table_comment || 'Comment/Label';
    commentHeader.style.padding = '10px';
    commentHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    commentHeader.style.backgroundColor = '#2a2d3e';
    commentHeader.style.color = '#ffffff';
    commentHeader.style.width = '35%';
    
    const balanceHeader = document.createElement('th');
    balanceHeader.textContent = window.translations?.wallet_table_balance || 'Balance (BTC)';
    balanceHeader.style.padding = '10px';
    balanceHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    balanceHeader.style.backgroundColor = '#2a2d3e';
    balanceHeader.style.color = '#ffffff';
    balanceHeader.style.width = '20%';
    
    const actionsHeader = document.createElement('th');
    actionsHeader.textContent = '';
    actionsHeader.style.padding = '10px';
    actionsHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
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
    addressCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    
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
    commentCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    
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
    balanceCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    balanceCell.style.textAlign = 'right';
    
    const balanceDisplay = document.createElement('span');
    balanceDisplay.className = 'wallet-balance-display';
    balanceDisplay.textContent = entry.cached_balance ? `${entry.cached_balance.toFixed(8)}` : '0.00000000';
    balanceDisplay.style.fontFamily = 'monospace';
    balanceDisplay.style.fontSize = '0.9em';
    balanceDisplay.style.color = entry.cached_balance && entry.cached_balance > 0 ? '#4FC3F7' : '#666';
    
    balanceCell.appendChild(balanceDisplay);
    
    // Actions cell
    const actionsCell = document.createElement('td');
    actionsCell.style.padding = '8px';
    actionsCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    actionsCell.style.textAlign = 'center';
    
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'wallet-remove-icon';
    removeButton.innerHTML = '<img src="/static/icons/delete.svg" alt="Delete" style="width: 16px; height: 16px; filter: brightness(0) invert(1);" />';
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
    addressHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    addressHeader.style.backgroundColor = '#2a2d3e';
    addressHeader.style.color = '#ffffff';
    addressHeader.style.width = '50%';
    
    const commentHeader = document.createElement('th');
    commentHeader.textContent = window.translations?.bitaxe_table_comment || 'Comment/Label';
    commentHeader.style.padding = '10px';
    commentHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    commentHeader.style.backgroundColor = '#2a2d3e';
    commentHeader.style.color = '#ffffff';
    commentHeader.style.width = '40%';
    
    const actionsHeader = document.createElement('th');
    actionsHeader.textContent = '';
    actionsHeader.style.padding = '10px';
    actionsHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    actionsHeader.style.backgroundColor = '#2a2d3e';
    actionsHeader.style.color = '#ffffff';
    actionsHeader.style.width = '10%';
    
    headerRow.appendChild(addressHeader);
    headerRow.appendChild(commentHeader);
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
    addressCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    
    const addressInput = document.createElement('input');
    addressInput.type = 'text';
    addressInput.className = 'bitaxe-address-input';
    addressInput.value = entry.address || '';
    addressInput.placeholder = window.translations?.bitaxe_table_placeholder_address || 'Enter IP address (e.g., 192.168.1.100)';
    addressInput.style.width = '100%';
    addressInput.style.border = '1px solid rgba(255, 255, 255, 0.3) !important';
    addressInput.style.padding = '8px !important';
    addressInput.style.background = 'rgba(255, 255, 255, 0.1) !important';
    addressInput.style.color = '#ffffff !important';
    addressInput.style.fontSize = '0.9em';
    addressInput.style.borderRadius = '4px !important';
    
    addressCell.appendChild(addressInput);
    
    // Comment cell
    const commentCell = document.createElement('td');
    commentCell.style.padding = '8px';
    commentCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    
    const commentInput = document.createElement('input');
    commentInput.type = 'text';
    commentInput.className = 'bitaxe-comment-input';
    commentInput.value = entry.comment || '';
    commentInput.placeholder = 'Miner name/description';
    commentInput.style.width = '100%';
    commentInput.style.border = '1px solid rgba(255, 255, 255, 0.3) !important';
    commentInput.style.padding = '8px !important';
    commentInput.style.background = 'rgba(255, 255, 255, 0.1) !important';
    commentInput.style.color = '#ffffff !important';
    commentInput.style.fontSize = '0.9em';
    commentInput.style.borderRadius = '4px !important';
    
    commentCell.appendChild(commentInput);
    
    // Actions cell
    const actionsCell = document.createElement('td');
    actionsCell.style.padding = '8px';
    actionsCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    actionsCell.style.textAlign = 'center';
    
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'bitaxe-remove-icon';
    removeButton.innerHTML = '<img src="/static/icons/delete.svg" alt="Delete" style="width: 16px; height: 16px; filter: brightness(0) invert(1);" />';
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
    addressHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    addressHeader.style.backgroundColor = '#2a2d3e';
    addressHeader.style.color = '#ffffff';
    addressHeader.style.width = '40%';
    
    const commentHeader = document.createElement('th');
    commentHeader.textContent = window.translations?.block_reward_table_comment || 'Comment/Label';
    commentHeader.style.padding = '10px';
    commentHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    commentHeader.style.backgroundColor = '#2a2d3e';
    commentHeader.style.color = '#ffffff';
    commentHeader.style.width = '30%';
    
    const foundBlocksHeader = document.createElement('th');
    foundBlocksHeader.textContent = window.translations?.block_reward_table_found_blocks || 'Found Blocks';
    foundBlocksHeader.style.padding = '10px';
    foundBlocksHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
    foundBlocksHeader.style.backgroundColor = '#2a2d3e';
    foundBlocksHeader.style.color = '#ffffff';
    foundBlocksHeader.style.width = '20%';
    foundBlocksHeader.style.textAlign = 'center';
    
    const actionsHeader = document.createElement('th');
    actionsHeader.textContent = '';
    actionsHeader.style.padding = '10px';
    actionsHeader.style.border = '1px solid rgba(255, 255, 255, 0.2)';
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
    addressCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    
    const addressInput = document.createElement('input');
    addressInput.type = 'text';
    addressInput.className = 'block-reward-address-input';
    addressInput.value = entry.address || '';
    addressInput.placeholder = window.translations?.block_reward_table_placeholder_address || 'Enter BTC address (e.g., bc1q...)';
    addressInput.style.width = '100%';
    addressInput.style.padding = '6px';
    addressInput.style.border = '1px solid #ced4da';
    addressInput.style.borderRadius = '4px';
    addressInput.style.fontSize = '14px';
    
    addressCell.appendChild(addressInput);
    
    // Comment cell
    const commentCell = document.createElement('td');
    commentCell.style.padding = '8px';
    commentCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    
    const commentInput = document.createElement('input');
    commentInput.type = 'text';
    commentInput.className = 'block-reward-comment-input';
    commentInput.value = entry.comment || '';
    commentInput.placeholder = 'Optional comment';
    commentInput.style.width = '100%';
    commentInput.style.padding = '6px';
    commentInput.style.border = '1px solid #ced4da';
    commentInput.style.borderRadius = '4px';
    commentInput.style.fontSize = '14px';
    
    commentCell.appendChild(commentInput);
    
    // Found blocks cell
    const foundBlocksCell = document.createElement('td');
    foundBlocksCell.style.padding = '8px';
    foundBlocksCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    foundBlocksCell.style.textAlign = 'center';
    foundBlocksCell.style.color = '#4FC3F7';
    foundBlocksCell.style.fontWeight = 'bold';
    foundBlocksCell.textContent = '-';
    foundBlocksCell.setAttribute('data-address', entry.address || '');
    
    // Actions cell
    const actionsCell = document.createElement('td');
    actionsCell.style.padding = '8px';
    actionsCell.style.border = '1px solid rgba(255, 255, 255, 0.15)';
    actionsCell.style.textAlign = 'center';
    
    const removeButton = document.createElement('button');
    removeButton.type = 'button';
    removeButton.className = 'block-reward-remove-icon';
    removeButton.innerHTML = '<img src="/static/icons/delete.svg" alt="Delete" style="width: 16px; height: 16px; filter: brightness(0) invert(1);" />';
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
            cell.style.color = data.found_blocks > 0 ? '#4FC3F7' : '#4FC3F7';
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
        <input type="file" id="file-input" accept="image/*" style="display: none;">
        <div class="upload-placeholder">
            <img src="/static/icons/add_meme.svg" alt="Add Meme" style="width: 2rem; height: 2rem; margin-bottom: 10px; filter: brightness(0) invert(1);" />
            <p>${window.translations?.upload_placeholder || 'Click to select image or drag & drop'}</p>
            <p style="font-size: 0.8rem; color: #667eea;">${window.translations?.upload_formats || 'Supported: PNG, JPG, JPEG, GIF, WebP'}</p>
        </div>
    `;
    
    const uploadProgress = document.createElement('div');
    uploadProgress.id = 'upload-progress';
    uploadProgress.style.display = 'none';
    uploadProgress.style.marginTop = '10px';
    uploadProgress.innerHTML = `
        <div style="background: #f0f0f0; border-radius: 10px; overflow: hidden;">
            <div id="progress-bar" style="height: 8px; background: #667eea; width: 0%; transition: width 0.3s;"></div>
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
    memesLabel.textContent = window.translations?.current_memes || 'Current Memes';
    memesSection.appendChild(memesLabel);
    
    const memesList = document.createElement('div');
    memesList.id = 'memes-list';
    memesList.style.display = 'grid';
    memesList.style.gridTemplateColumns = 'repeat(auto-fill, minmax(100px, 1fr))';
    memesList.style.gap = '10px';
    memesList.style.marginTop = '10px';
    memesSection.appendChild(memesList);
    
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
        const expectedBooleanFields = ['prioritize_large_scaled_meme', 'color_mode_dark', 'live_block_notifications_enabled', 'show_btc_price_block', 'show_bitaxe_block', 'show_wallet_balances_block', 'e-ink-display-connected'];
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
            
            console.log('🔍 Language change detection (saveConfiguration):', {
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
                console.log('🔄 LANGUAGE CHANGE DETECTED! (saveConfiguration) Processing language change from', oldLanguage, 'to', newLanguage);
                
                // Clear the pending change and reload page immediately
                pendingLanguageChange = null;
                setTimeout(() => {
                    console.log('🔄 FORCING PAGE RELOAD for language change (saveConfiguration)');
                    window.location.reload(true); // Force reload from server
                }, 500); // Very short timeout for immediate reload
                
                return true; // Return success before reload
            } else {
                // Fallback check: if language in formConfig is different from what was in currentConfig
                if (formConfig.language && formConfig.language !== oldLanguage) {
                    console.log('🔄 FALLBACK (saveConfiguration): Language difference detected via form config!', oldLanguage, '->', formConfig.language);
                    setTimeout(() => {
                        console.log('🔄 FALLBACK PAGE RELOAD for language change (saveConfiguration)');
                        window.location.reload(true);
                    }, 500);
                    return true;
                }
            }
            
            // Update block notification subscription if setting changed
            console.log('[SAVE DEBUG] live_block_notifications_enabled after save:', formConfig['live_block_notifications_enabled']);
            if (typeof formConfig['live_block_notifications_enabled'] !== 'undefined') {
                if (formConfig['live_block_notifications_enabled']) {
                    console.log('[SAVE DEBUG] Calling subscribeToBlockNotifications after save');
                    subscribeToBlockNotifications();
                } else {
                    console.log('[SAVE DEBUG] Calling unsubscribeFromBlockNotifications after save');
                    unsubscribeFromBlockNotifications();
                }
            }
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

// Global variable to store current notification timeout
let notificationTimeout = null;

function showNotification(message, type = 'success') {
    const notification = document.getElementById('notification');
    if (!notification) return;
    if (window.notificationTimeout) {
        clearTimeout(window.notificationTimeout);
    }
    notification.textContent = message;
    notification.style.background = type === 'success' ? '#38a169' : '#e53e3e';
    notification.style.color = '#fff';
    notification.style.borderRadius = '10px';
    notification.style.padding = '10px 16px';
    notification.style.position = 'fixed';
    notification.style.top = '18px';
    notification.style.left = '50%';
    notification.style.transform = 'translateX(-50%)';
    notification.style.zIndex = '9999';
    notification.style.fontSize = '0.95rem';
    notification.style.minWidth = '240px';
    notification.style.maxWidth = '420px';
    notification.style.width = 'auto';
    notification.style.textAlign = 'center';
    notification.style.display = 'block';
    window.notificationTimeout = setTimeout(hideNotification, 1000);
}

function hideNotification() {
    const notification = document.getElementById('notification');
    if (!notification) return;
    notification.style.display = 'none';
}

// Meme Modal Functions
let currentModalMeme = null;

function openMemeModal(filename, url) {
    currentModalMeme = { filename, url };
    
    // Set basic info with null checks
    const modalTitle = document.getElementById('meme-modal-title');
    const modalFilename = document.getElementById('meme-modal-filename');
    const modalImage = document.getElementById('meme-modal-image');
    const modalDimensions = document.getElementById('meme-modal-dimensions');
    const modalFilesize = document.getElementById('meme-modal-filesize');
    const memeModal = document.getElementById('meme-modal');
    
    if (modalTitle) {
        const previewText = window.translations?.meme_preview || 'Meme Preview';
        modalTitle.textContent = `${previewText} - ${filename}`;
    }
    if (modalImage) {
        modalImage.src = url;
    }
    if (memeModal) {
        memeModal.style.display = 'block';
        // Center the modal horizontally and vertically
        memeModal.style.position = 'fixed';
        memeModal.style.top = '50%';
        memeModal.style.left = '50%';
        memeModal.style.transform = 'translate(-50%, -50%)';
        memeModal.style.zIndex = '9999';
        memeModal.style.margin = '0';
        memeModal.style.maxWidth = '90vw';
        memeModal.style.maxHeight = '90vh';
        memeModal.style.overflow = 'auto';
    }
    
    // Try to get file size via HEAD request
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
                modalFilesize.textContent = 'Unknown';
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
                balanceDisplay.style.color = balance > 0 ? '#4FC3F7' : '#666'; 
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
            notification.style.backgroundColor = '#28a745';
            break;
        case 'warning':
            notification.style.backgroundColor = '#ffc107';
            notification.style.color = '#212529';
            break;
        case 'error':
            notification.style.backgroundColor = '#dc3545';
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
        // Check if live block notifications are enabled and subscribe
        if (typeof live_block_notifications_enabled !== 'undefined' && live_block_notifications_enabled) {
            subscribeToBlockNotifications();
        }
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
        console.log('📊 Received wallet balance update:', data ? Object.keys(data).length + ' addresses (data masked for privacy)' : 'no data');
        updateWalletBalancesFromWebSocket(data);
        showNotification(window.translations?.wallet_balances_updated || 'Wallet balances updated automatically!', 'success');
    });

    // Listen for block notifications
    configSocket.on('new_block_notification', (data) => {
        console.log("🎯 New block notification received:", data && data.height ? 'block ' + data.height + ' (details masked for privacy)' : 'notification data');
        // Store notification state to prevent duplicates
        const state = getNotificationState();
        const now = Date.now();
        if (state.lastNotification && (now - state.lastNotification) < 10000) {
            console.log("⚠️ Duplicate block notification detected, skipping");
            return;
        }
        state.lastNotification = now;
        setNotificationState(state);
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
            console.log('🔔 [CONFIG] ' + (data.message || 'Subscribed to live block notifications'));
        } else if (data.status === 'unsubscribed') {
            console.log('🔕 [CONFIG] Unsubscribed from live block notifications');
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
                    console.log('🔔 Received cross-page block notification');
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
        console.log("🔄 Attempting Config WebSocket reconnect...");
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
                        balanceDisplay.style.color = '#4FC3F7';
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
                    
                    console.log('🔍 [SAVE DEBUG] Starting form collection...');
                    
                    // Collect all form values using the proper method that handles custom getValue() functions
                    document.querySelectorAll('[data-config-key]').forEach(element => {
                        const key = element.dataset.configKey;
                        
                        if (element.getValue) {
                            // Use custom getValue method for boolean switches and other custom elements
                            const value = element.getValue();
                            formConfig[key] = value;
                            console.log(`🔍 [SAVE DEBUG] Collected ${key} via getValue(): ${value} (type: ${typeof value})`);
                        } else if (element.type === 'checkbox') {
                            formConfig[key] = element.checked;
                            console.log(`🔍 [SAVE DEBUG] Collected ${key} via checkbox: ${element.checked}`);
                        } else if (element.type === 'number') {
                            formConfig[key] = parseFloat(element.value) || 0;
                            console.log(`🔍 [SAVE DEBUG] Collected ${key} via number: ${formConfig[key]}`);
                        } else {
                            formConfig[key] = element.value;
                            console.log(`🔍 [SAVE DEBUG] Collected ${key} via value: ${element.value}`);
                        }
                    });
                    
                    console.log('🔍 [SAVE DEBUG] Final formConfig:', formConfig);
                    
                    // Temporary: Show what we collected for boolean fields
                    const booleanFields = ['prioritize_large_scaled_meme', 'color_mode_dark', 'live_block_notifications_enabled', 'show_btc_price_block', 'show_bitaxe_block', 'show_wallet_balances_block', 'e-ink-display-connected'];
                    const booleanData = {};
                    booleanFields.forEach(field => {
                        if (formConfig.hasOwnProperty(field)) {
                            booleanData[field] = formConfig[field];
                        }
                    });
                    console.log('🔍 [SAVE DEBUG] Boolean fields being saved:', booleanData);
                    
                    
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
                        
                        console.log('🔍 Language change detection (nav buttons):', {
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
                            console.log('🔄 LANGUAGE CHANGE DETECTED! (nav buttons) Processing language change from', oldLanguage, 'to', newLanguage);
                            
                            // Show notification and force page reload
                            showNotification('Language changed! Reloading page...', 'success');
                            
                            // Clear the pending change and reload page immediately
                            pendingLanguageChange = null;
                            setTimeout(() => {
                                console.log('🔄 FORCING PAGE RELOAD for language change (nav buttons)');
                                window.location.reload(true); // Force reload from server
                            }, 1000); // Shorter timeout
                        } else {
                            // Fallback check: if language in formConfig is different from what was in currentConfig
                            if (formConfig.language && formConfig.language !== oldLanguage) {
                                console.log('🔄 FALLBACK (nav): Language difference detected via form config!', oldLanguage, '->', formConfig.language);
                                showNotification('Language changed! Reloading page...', 'success');
                                setTimeout(() => {
                                    console.log('🔄 FALLBACK PAGE RELOAD for language change (nav)');
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
                if (confirm(window.translations?.are_you_sure_logout || window.translations?.confirm_logout || 'Are you sure you want to logout?')) {
                    try {
                        await fetch('/api/logout', { method: 'POST' });
                        window.location.href = '/login';
                    } catch (error) {
                        console.error('Logout failed:', error);
                        // Fallback to GET logout if POST fails
                        window.location.href = '/logout';
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
        console.log('🔔 Config page subscribing to live block notifications...');
        configSocket.emit('subscribe_block_notifications', { page: 'config' });
    }
}

function unsubscribeFromBlockNotifications() {
    if (configSocket) {
        console.log('🔕 Config page unsubscribing from live block notifications...');
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
    
    // Create toast element
    const toast = document.createElement('div');
    toast.style.cssText = `
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 16px 20px;
        border-radius: 12px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        backdrop-filter: blur(15px);
        border: 1px solid rgba(255, 255, 255, 0.2);
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
    closeBtn.style.cssText = `
        position: absolute;
        top: 8px;
        right: 12px;
        background: none;
        border: none;
        color: white;
        font-size: 24px;
        cursor: pointer;
        padding: 0;
        width: 24px;
        height: 24px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 50%;
        transition: background-color 0.2s;
    `;
    
    // Format timestamp to local time
    const timestamp = new Date(blockData.timestamp * 1000);
    const timeString = timestamp.toLocaleTimeString();
    
    // Format numbers
    const heightFormatted = blockData.block_height.toLocaleString().replace(/,/g, '.');
    const rewardFormatted = blockData.total_reward_btc.toFixed(8);
    const feesFormatted = blockData.total_fees_btc.toFixed(4);
    const medianFeeFormatted = blockData.median_fee_sat_vb.toFixed(1);
    
    // Create toast content
    toast.innerHTML = `
        <div style="margin-right: 30px;">
            <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px; display: flex; align-items: center;">
                🎯 New Bitcoin Block Found!
            </div>
            <div style="margin-bottom: 6px;">
                <strong>Height:</strong> ${heightFormatted}
            </div>
            <div style="margin-bottom: 6px;">
                <strong>Hash:</strong> ${blockData.block_hash}
            </div>
            <div style="margin-bottom: 6px;">
                <strong>Time:</strong> ${timeString}
            </div>
            <div style="margin-bottom: 6px;">
                <strong>Mining Pool:</strong> ${blockData.pool_name}
            </div>
            <div style="margin-bottom: 6px;">
                <strong>Block Reward:</strong> ${rewardFormatted} BTC
            </div>
            <div style="margin-bottom: 6px;">
                <strong>Total Fees:</strong> ${feesFormatted} BTC
            </div>
            <div>
                <strong>Median Fee:</strong> ${medianFeeFormatted} sat/vB
            </div>
        </div>
    `;
    
    // Add close button to toast
    toast.appendChild(closeBtn);
    
    // Close toast function
    function closeToast() {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 400);
    }
    
    // Close button event listener
    closeBtn.addEventListener('click', closeToast);
    closeBtn.addEventListener('mouseenter', () => {
        closeBtn.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
    });
    closeBtn.addEventListener('mouseleave', () => {
        closeBtn.style.backgroundColor = 'transparent';
    });
    
    // Add toast to container
    toastContainer.appendChild(toast);
    
    // Animate in
    setTimeout(() => {
        toast.style.opacity = '1';
        toast.style.transform = 'translateX(0)';
    }, 10);
    
    // Auto-close after 30 seconds
    setTimeout(closeToast, 30000);
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
    const booleanFields = ['prioritize_large_scaled_meme', 'color_mode_dark', 'live_block_notifications_enabled', 'show_btc_price_block', 'show_bitaxe_block', 'show_wallet_balances_block', 'e-ink-display-connected'];
    
    console.log('📊 Current boolean values:');
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
