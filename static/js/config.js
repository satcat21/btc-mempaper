let currentConfig = {};
let configSchema = {};
let categories = [];
let colorOptions = [];
let pendingLanguageChange = null;
let memeToDelete = null;

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
            saveButton.textContent = 'Saving...';
            
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
    setupUpload();
    setupModals();
});

// Setup modal functionality
function setupModals() {
    // Language change modal
    document.getElementById('confirm-language-change').addEventListener('click', async () => {
        if (pendingLanguageChange) {
            // Save current configuration with new language
            const newConfig = { ...currentConfig, language: pendingLanguageChange };
            
            const success = await saveConfigurationSilent(newConfig);
            if (success) {
                // Refresh the page to apply new language
                window.location.reload();
            } else {
                showNotification('Failed to save configuration', 'error');
                hideLanguageModal();
            }
        }
    });
    
    document.getElementById('cancel-language-change').addEventListener('click', () => {
        hideLanguageModal();
        // Revert language selection
        if (pendingLanguageChange) {
            const languageSelect = document.querySelector('[data-config-key="language"]');
            if (languageSelect) {
                languageSelect.value = currentConfig.language;
            }
        }
    });
    
    // Delete confirmation modal
    document.getElementById('confirm-delete').addEventListener('click', async () => {
        if (memeToDelete) {
            await deleteMeme(memeToDelete);
            hideDeleteModal();
        }
    });
    
    document.getElementById('cancel-delete').addEventListener('click', () => {
        hideDeleteModal();
    });
}

// Modal helper functions
function showLanguageModal(newLanguage) {
    pendingLanguageChange = newLanguage;
    document.getElementById('language-modal').style.display = 'flex';
}

function hideLanguageModal() {
    pendingLanguageChange = null;
    document.getElementById('language-modal').style.display = 'none';
}

function showDeleteModal(filename) {
    memeToDelete = filename;
    document.getElementById('delete-modal').style.display = 'flex';
}

function hideDeleteModal() {
    memeToDelete = null;
    document.getElementById('delete-modal').style.display = 'none';
}

// Setup upload functionality
function setupUpload() {
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('file-input');
    
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
    
    progressDiv.style.display = 'block';
    progressBar.style.width = '0%';
    statusText.textContent = 'Uploading...';
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/upload-meme', {
            method: 'POST',
            body: formData
        });
        
        progressBar.style.width = '100%';
        
        const result = await response.json();
        
        if (result.success) {
            statusText.textContent = window.translations.upload_successful;
            statusText.style.color = '#28a745';
            clearMemeCache(); // Clear cache before reloading
            loadMemes(); // Refresh memes list
            
            setTimeout(() => {
                progressDiv.style.display = 'none';
            }, 2000);
        } else {
            statusText.textContent = result.message || window.translations.upload_failed;
            statusText.style.color = '#dc3545';
        }
    } catch (error) {
        statusText.textContent = window.translations.upload_failed + ': ' + error.message;
        statusText.style.color = '#dc3545';
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
                    console.log('📱 Loaded meme cache from localStorage:', this.cache.size, 'entries');
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
        if (this.loadedPages.has(page) || this.isLoading) {
            return null;
        }
        
        this.isLoading = true;
        console.log(`📥 Loading memes page ${page}...`);
        
        try {
            const response = await fetch(`/api/memes?page=${page}&per_page=${this.perPage}`);
            const data = await response.json();
            
            this.totalMemes = data.total;
            this.loadedPages.add(page);
            
            console.log(`✅ Loaded ${data.memes.length} memes from page ${page}`);
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
        
        // Show loading indicator
        memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #666;">🔄 Loading memes...</div>';
        
        // Load first page
        const data = await memeLoader.loadMemePage(1);
        
        if (!data) {
            memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f44;">❌ Failed to load memes</div>';
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
                        <button class="action-button" onclick="downloadMeme('${meme.filename}')" title="${window.translations.download_meme}">⬇️</button>
                        <button class="action-button delete" onclick="showDeleteModal('${meme.filename}')" title="${window.translations.delete_meme}">🗑️</button>
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
                loadMoreBtn.style.cssText = 'grid-column: 1/-1; padding: 15px; margin: 10px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer;';
                loadMoreBtn.textContent = `📥 Load More (${data.total - data.memes.length} remaining)`;
                loadMoreBtn.onclick = () => loadMoreMemes(data.page + 1, loadMoreBtn);
                memesList.appendChild(loadMoreBtn);
            }
            
        } else {
            memesList.innerHTML = `<p style="grid-column: 1/-1; text-align: center; color: #666;">${window.translations.no_memes_uploaded}</p>`;
        }
        
        console.log(`📊 Meme gallery loaded: ${data.memes.length} of ${data.total} memes`);
        
    } catch (error) {
        console.error('Failed to load memes:', error);
        const memesList = document.getElementById('memes-list');
        memesList.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #f44;">❌ Failed to load memes</div>';
    }
}

async function loadMoreMemes(page, buttonElement) {
    try {
        buttonElement.textContent = '🔄 Loading...';
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
                    <button class="action-button" onclick="downloadMeme('${meme.filename}')" title="${window.translations.download_meme}">⬇️</button>
                    <button class="action-button delete" onclick="showDeleteModal('${meme.filename}')" title="${window.translations.delete_meme}">🗑️</button>
                </div>
                <div class="meme-filename">${meme.filename}</div>
            `;
            
            memeDiv.insertBefore(img, memeDiv.firstChild);
            memesList.insertBefore(memeDiv, buttonElement);
        });
        
        // Update or remove the load more button
        if (data.has_next) {
            const remaining = data.total - (page * memeLoader.perPage);
            buttonElement.textContent = `📥 Load More (${remaining} remaining)`;
            buttonElement.onclick = () => loadMoreMemes(page + 1, buttonElement);
            buttonElement.disabled = false;
        } else {
            buttonElement.remove();
        }
        
    } catch (error) {
        console.error('Failed to load more memes:', error);
        buttonElement.textContent = '❌ Failed to load';
        buttonElement.disabled = false;
    }
}

// Clear cache when memes are uploaded or deleted
function clearMemeCache() {
    memeCache.clear();
    console.log('🗑️ Meme cache cleared');
}

// Logout functionality
document.getElementById('logout-button').addEventListener('click', async () => {
    try {
        await fetch('/api/logout', { method: 'POST' });
        window.location.href = '/';
    } catch (error) {
        console.error('Logout failed:', error);
    }
});

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
        
        console.log('Configuration loaded:', { 
            config: Object.keys(currentConfig).length, 
            schema: Object.keys(configSchema).length,
            categories: categories.length,
            colorOptions: colorOptions.length
        });
        
        // Debug wallet configuration specifically
        if (currentConfig.wallet_balance_addresses_with_comments) {
            console.log('Loaded wallet data:', currentConfig.wallet_balance_addresses_with_comments);
        } else {
            console.log('No wallet_balance_addresses_with_comments found in config');
            console.log('Available config keys:', Object.keys(currentConfig));
        }
        colorOptions = data.color_options || [];
        
        // console.log('Config loaded:', currentConfig);
        // console.log('Schema loaded:', configSchema);
        // console.log('Categories loaded:', categories);
        
        renderConfigurationForm();
    } catch (error) {
        // console.error('Configuration load error:', error);
        showNotification(`Failed to load configuration: ${error.message}`, 'error');
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
        
        const title = document.createElement('div');
        title.className = 'section-title';
        
        // Handle icon: if it's a path (starts with /), create an img tag, otherwise use as text
        let iconHtml;
        if (category.icon && category.icon.startsWith('/')) {
            iconHtml = `<img src="${category.icon}" alt="${category.label}" style="width: 20px; height: 20px; margin-right: 8px; vertical-align: middle;">`;
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
                
                // Trigger save
                const event = new CustomEvent('configChange', {
                    detail: { key: enableToggleKey, value: newValue }
                });
                document.dispatchEvent(event);
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
    console.log('Configuration form rendered successfully');
    
    // Load cached balances for any existing wallet entries after form is rendered
    setTimeout(() => {
        const walletTable = document.querySelector('.wallet-table tbody');
        if (walletTable && walletTable.children.length > 0) {
            console.log('Loading cached balances for existing wallet entries');
            loadCachedWalletBalances(walletTable);
        }
    }, 100); // Small delay to ensure DOM is fully updated
}

function createFormField(key, field, value) {
    const formGroup = document.createElement('div');
    formGroup.className = 'form-group';
    
    const label = document.createElement('label');
    label.className = 'form-label';
    label.textContent = field.label;
    formGroup.appendChild(label);
    
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
            
            // Special handling for language changes
            if (key === 'language') {
                input.addEventListener('change', (e) => {
                    const newLanguage = e.target.value;
                    if (newLanguage !== currentConfig.language) {
                        showLanguageModal(newLanguage);
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
            console.log(`Creating wallet table for key ${key} with value:`, value);
            input = createWalletTableInput(value || [], field);
            break;
            
        case 'bitaxe_table':
            console.log(`Creating bitaxe table for key ${key} with value:`, value);
            input = createBitaxeTableInput(value || [], field);
            break;
            
        case 'block_reward_table':
            console.log(`Creating block reward table for key ${key} with value:`, value);
            input = createBlockRewardTableInput(value || [], field);
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
    
    if (input && input.dataset !== undefined) {
        input.dataset.configKey = key;
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

function createBooleanSwitch(value) {
    const container = document.createElement('div');
    container.className = 'boolean-switch';
    
    const switchEl = document.createElement('div');
    switchEl.className = `switch ${value ? 'active' : ''}`;
    
    const thumb = document.createElement('div');
    thumb.className = 'switch-thumb';
    switchEl.appendChild(thumb);
    
    const label = document.createElement('span');
    label.textContent = value ? window.translations.enabled : window.translations.disabled;
    
    switchEl.addEventListener('click', () => {
        const isActive = switchEl.classList.toggle('active');
        label.textContent = isActive ? window.translations.enabled : window.translations.disabled;
    });
    
    container.appendChild(switchEl);
    container.appendChild(label);
    
    // Add getter for value
    container.getValue = () => switchEl.classList.contains('active');
    
    return container;
}

function createToggleGroup(options, value) {
    const container = document.createElement('div');
    container.className = 'toggle-group';
    
    options.forEach(option => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = `toggle-option ${value === option.value ? 'active' : ''}`;
        button.innerHTML = `${option.icon} ${option.label}`;
        
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
        
        console.log('Wallet table getValue called, returning:', result);
        return result;
    };
    
    // Add value property for compatibility
    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (newValues) => {
            console.log('Wallet table setValue called with:', newValues);
            // Clear existing rows
            tbody.innerHTML = '';
            // Add new rows
            if (Array.isArray(newValues)) {
                newValues.forEach(entry => addWalletTableRow(tbody, entry));
                console.log(`Added ${newValues.length} wallet entries to table`);
                
                // Load cached balances for the newly added entries
                loadCachedWalletBalances(tbody);
            } else {
                console.log('Invalid newValues for wallet table:', newValues);
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
    removeButton.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3,6 5,6 21,6"></polyline><path d="m19,6v14a2,2 0 0,1 -2,2H7a2,2 0 0,1 -2,-2V6m3,0V4a2,2 0 0,1 2,-2h4a2,2 0 0,1 2,2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>';
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
        
        console.log('Bitaxe table getValue called, returning:', result);
        return result;
    };
    
    // Add value property for compatibility
    Object.defineProperty(container, 'value', {
        get: () => container.getValue(),
        set: (newValues) => {
            console.log('Bitaxe table setValue called with:', newValues);
            // Clear existing rows
            tbody.innerHTML = '';
            // Add new rows
            if (Array.isArray(newValues)) {
                newValues.forEach(entry => addBitaxeTableRow(tbody, entry));
                console.log(`Added ${newValues.length} bitaxe entries to table`);
            } else {
                console.log('Invalid newValues for bitaxe table:', newValues);
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
    removeButton.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3,6 5,6 21,6"></polyline><path d="m19,6v14a2,2 0 0,1 -2,2H7a2,2 0 0,1 -2,-2V6m3,0V4a2,2 0 0,1 2,-2h4a2,2 0 0,1 2,2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>';
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
            console.log('Setting block reward table values:', newValues);
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
                console.log('Invalid newValues for block reward table:', newValues);
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
                
                console.log(`Row ${index}: address="${address}", comment="${comment}"`);
                
                if (address) {
                    entries.push({
                        address: address,
                        comment: comment || 'Block Reward Address'
                    });
                }
            }
        });
        
        console.log('Block reward table getValue returning:', entries);
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
    removeButton.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3,6 5,6 21,6"></polyline><path d="m19,6v14a2,2 0 0,1 -2,2H7a2,2 0 0,1 -2,-2V6m3,0V4a2,2 0 0,1 2,-2h4a2,2 0 0,1 2,2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>';
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

// Save configuration
document.getElementById('save-button').addEventListener('click', async () => {
    const button = document.getElementById('save-button');
    button.disabled = true;
    button.textContent = '💾 Saving...';
    
    try {
        const formConfig = {};
        
        // Collect all form values
        document.querySelectorAll('[data-config-key]').forEach(element => {
            const key = element.dataset.configKey;
            
            if (element.getValue) {
                const value = element.getValue();
                formConfig[key] = value;
                if (key.includes('wallet')) {
                    console.log(`Collected wallet config ${key}:`, value);
                }
            } else if (element.type === 'checkbox') {
                formConfig[key] = element.checked;
            } else if (element.type === 'number') {
                formConfig[key] = parseInt(element.value) || 0;
            } else {
                formConfig[key] = element.value;
            }
        });
        
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
            showNotification('Session expired. Redirecting to login...', 'error');
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
            return;
        }
        
        if (response.status === 429) {
            const errorData = await response.json();
            const retryAfter = errorData.retry_after || 60;
            showNotification(`Rate limit exceeded. Please wait ${retryAfter} seconds before trying again.`, 'error');
            return;
        }
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(window.translations.configuration_saved, 'success');
            currentConfig = newConfig;
            window.currentConfig = newConfig; // Make available globally
        } else {
            showNotification(result.message || 'Failed to save configuration', 'error');
        }
    } catch (error) {
        showNotification('Failed to save configuration', 'error');
    } finally {
        button.disabled = false;
        button.textContent = '💾 Save Configuration';
    }
});

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
    
    // Clear any existing timeout
    if (notificationTimeout) {
        clearTimeout(notificationTimeout);
    }
    
    // Create notification content with close button
    const messageSpan = document.createElement('span');
    messageSpan.textContent = message;
    messageSpan.style.flex = '1';
    
    const closeBtn = document.createElement('button');
    closeBtn.className = 'close-btn';
    closeBtn.innerHTML = '×';
    closeBtn.setAttribute('aria-label', 'Close notification');
    closeBtn.onclick = function(e) {
        e.stopPropagation();
        hideNotification();
    };
    
    // Clear notification and add new content
    notification.innerHTML = '';
    notification.appendChild(messageSpan);
    notification.appendChild(closeBtn);
    
    // Set notification style
    notification.className = `notification ${type}`;
    notification.classList.add('show');
    
    // Add click-to-dismiss functionality
    notification.onclick = function() {
        hideNotification();
    };
    
    // Set auto-hide duration based on type
    let duration;
    switch (type) {
        case 'error':
            duration = 15000; // 15 seconds for errors
            break;
        case 'warning':
            duration = 8000;  // 8 seconds for warnings
            break;
        case 'success':
        default:
            duration = 5000;  // 5 seconds for success/info
            break;
    }
    
    // Auto-hide notification after duration
    notificationTimeout = setTimeout(() => {
        hideNotification();
    }, duration);
}

function hideNotification() {
    const notification = document.getElementById('notification');
    notification.classList.remove('show');
    
    // Clear timeout if it exists
    if (notificationTimeout) {
        clearTimeout(notificationTimeout);
        notificationTimeout = null;
    }
    
    // Remove click handler
    notification.onclick = null;
}

// Meme Modal Functions
let currentModalMeme = null;

function openMemeModal(filename, url) {
    currentModalMeme = { filename, url };
    
    // Set basic info
    document.getElementById('meme-modal-title').textContent = `Meme Preview - ${filename}`;
    document.getElementById('meme-modal-filename').textContent = filename;
    document.getElementById('meme-modal-image').src = url;
    
    // Reset dimensions and file size
    document.getElementById('meme-modal-dimensions').textContent = 'Loading...';
    document.getElementById('meme-modal-filesize').textContent = 'Loading...';
    
    // Show modal
    document.getElementById('meme-modal').style.display = 'flex';
    
    // Load image info
    loadMemeInfo(url, filename);
    
    // Add escape key listener
    document.addEventListener('keydown', handleMemeModalKeydown);
}

function closeMemeModal() {
    document.getElementById('meme-modal').style.display = 'none';
    currentModalMeme = null;
    
    // Remove escape key listener
    document.removeEventListener('keydown', handleMemeModalKeydown);
}

function handleMemeModalKeydown(event) {
    if (event.key === 'Escape') {
        closeMemeModal();
    }
}

function loadMemeInfo(url, filename) {
    // Create temporary image to get dimensions
    const img = new Image();
    
    img.onload = function() {
        document.getElementById('meme-modal-dimensions').textContent = `${this.naturalWidth} × ${this.naturalHeight}px`;
    };
    
    img.onerror = function() {
        document.getElementById('meme-modal-dimensions').textContent = 'Unable to load';
    };
    
    img.src = url;
    
    // Try to get file size via HEAD request
    fetch(url, { method: 'HEAD' })
        .then(response => {
            const contentLength = response.headers.get('content-length');
            if (contentLength) {
                const bytes = parseInt(contentLength);
                const size = formatFileSize(bytes);
                document.getElementById('meme-modal-filesize').textContent = size;
            } else {
                document.getElementById('meme-modal-filesize').textContent = 'Unknown';
            }
        })
        .catch(() => {
            document.getElementById('meme-modal-filesize').textContent = 'Unknown';
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
document.getElementById('meme-modal').addEventListener('click', function(event) {
    if (event.target === this) {
        closeMemeModal();
    }
});

// Load cached wallet balances for display in config table
async function loadCachedWalletBalances(tbody) {
    try {
        console.log('🔍 [DEBUG] loadCachedWalletBalances started');
        console.log('🔍 [DEBUG] window.currentConfig exists:', !!window.currentConfig);
        console.log('🔍 [DEBUG] currentConfig exists:', !!currentConfig);
        
        let walletEntries = [];
        const rows = tbody.querySelectorAll('tr');
        
        console.log('🔍 [DEBUG] Found', rows.length, 'rows in table');
        
        // First check if we have config data with cached balances
        const configToUse = window.currentConfig || currentConfig;
        if (configToUse && configToUse.wallet_balance_addresses_with_comments) {
            console.log('🔍 [DEBUG] Found wallet addresses in config:', configToUse.wallet_balance_addresses_with_comments);
            
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
            
            console.log('🔍 [DEBUG] Loaded wallet entries from config with balances:', walletEntries);
        } else {
            // Fallback: Try to get wallet entries from form inputs
            rows.forEach((row, index) => {
                const addressInput = row.querySelector('.wallet-address-input');
                const commentInput = row.querySelector('.wallet-comment-input');
                const address = addressInput ? addressInput.value.trim() : '';
                const comment = commentInput ? commentInput.value.trim() : '';
                
                console.log(`🔍 [DEBUG] Row ${index}: address="${address}", comment="${comment}"`);
                
                if (address) {
                    walletEntries.push({
                        address: address,
                        comment: comment,
                        type: detectAddressType(address)
                    });
                }
            });
            
            console.log('🔍 [DEBUG] Wallet entries from form inputs:', walletEntries);
        }
        
        // If no entries from either source, try fallback API
        if (walletEntries.length === 0) {
            console.log('🔍 [DEBUG] No wallet entries found, trying API fallback...');
            
            try {
                const testResponse = await fetch('/api/test-wallet-config');
                if (testResponse.ok) {
                    const testData = await testResponse.json();
                    console.log('🔍 [DEBUG] Test API response:', testData);
                    
                    if (testData.success && testData.wallet_addresses_from_regular_config) {
                        const apiEntries = testData.wallet_addresses_from_regular_config;
                        console.log('🔍 [DEBUG] Found wallet entries from test API:', apiEntries);
                        
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
                console.log('🔍 [DEBUG] Test API error:', apiError);
            }
        }
        
        if (walletEntries.length === 0) {
            console.log('🔍 [DEBUG] No wallet entries to display');
            return;
        }
        
        console.log('🔍 [DEBUG] Processing', walletEntries.length, 'wallet entries');
        
        // Check if we already have cached balances in the config
        const hasBalancesInConfig = walletEntries.some(entry => entry.cached_balance !== undefined);
        
        if (hasBalancesInConfig) {
            console.log('🔍 [DEBUG] Using cached balances from config');
            // Use cached balances directly from config
            await updateWalletTableWithEntries(tbody, walletEntries);
        } else {
            console.log('🔍 [DEBUG] No cached balances in config, fetching from API...');
            // Fetch balances from API
            await fetchAndUpdateBalances(tbody, walletEntries);
        }
        
    } catch (error) {
        console.error('🔍 [DEBUG] Error loading cached wallet balances:', error);
    }
}

// Helper function to update wallet table with entries (including balances)
async function updateWalletTableWithEntries(tbody, walletEntries) {
    let currentRows = tbody.querySelectorAll('tr');
    
    // Add more rows if needed
    while (currentRows.length < walletEntries.length) {
        console.log('🔍 [DEBUG] Adding missing row for wallet entry');
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
                console.log(`🔍 [DEBUG] Set address input ${index} to: ${entry.address}`);
            }
            if (commentInput && !commentInput.value) {
                commentInput.value = entry.comment;
                console.log(`🔍 [DEBUG] Set comment input ${index} to: ${entry.comment}`);
            }
            
            // Update the balance display
            const balanceDisplay = row.querySelector('.wallet-balance-display');
            if (balanceDisplay) {
                const balance = entry.cached_balance || 0.0;
                balanceDisplay.textContent = `${balance.toFixed(8)}`;
                balanceDisplay.style.color = balance > 0 ? '#4FC3F7' : '#666';
                console.log(`🔍 [DEBUG] Set balance display ${index} to: ${balance.toFixed(8)}`);
                
                // Add styling to indicate cached data
                if (balance > 0) {
                    balanceDisplay.style.opacity = '0.8';
                    balanceDisplay.title = 'Cached balance data from configuration';
                }
            }
        }
    });
    
    console.log('🔍 [DEBUG] Successfully updated wallet table with config data');
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
    
    console.log('🔍 [DEBUG] Cached balance API response status:', response.status);
    
    if (response.ok) {
        const balanceData = await response.json();
        console.log('🔍 [DEBUG] Cached balance data received:', balanceData);
        
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
        console.log('🔍 [DEBUG] Could not load cached wallet balances:', response.status, errorText);
        
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

function initializeWebSocket() {
    if (typeof io !== 'undefined') {
        try {
            configSocket = io();
            
            configSocket.on('connect', () => {
                console.log('🔌 Config WebSocket connected');
            });
            
            configSocket.on('disconnect', () => {
                console.log('🔌 Config WebSocket disconnected');
            });
            
            // Listen for wallet balance updates
            configSocket.on('wallet_balance_updated', (data) => {
                console.log('📊 Received wallet balance update:', data);
                updateWalletBalancesFromWebSocket(data);
                showNotification('Wallet balances updated automatically!', 'success');
            });
            
        } catch (error) {
            console.log('WebSocket not available or failed to connect:', error);
        }
    } else {
        console.log('Socket.IO not available');
    }
}

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
                const originalHTML = button.innerHTML;
                // Show different saving text for mobile (icon only) vs desktop
                if (button.id.includes('mobile')) {
                    button.innerHTML = '<span style="font-size: 12px;">•••</span>';
                } else {
                    button.innerHTML = '<span>Saving...</span>';
                }
                
                try {
                    const formConfig = {};
                    
                    // Collect all form values
                    document.querySelectorAll('[data-config-key]').forEach(element => {
                        const key = element.getAttribute('data-config-key');
                        let value;
                        
                        if (element.type === 'checkbox') {
                            value = element.checked;
                        } else if (element.type === 'number') {
                            value = parseFloat(element.value) || 0;
                        } else {
                            value = element.value;
                        }
                        
                        formConfig[key] = value;
                    });
                    
                    console.log('Saving configuration:', formConfig);
                    
                    const response = await fetch('/api/config', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(formConfig)
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        showNotification(window.translations.configuration_saved || 'Configuration saved successfully!');
                        // Update current config
                        currentConfig = { ...currentConfig, ...formConfig };
                    } else {
                        showNotification(result.message || 'Failed to save configuration', 'error');
                    }
                } catch (error) {
                    console.error('Error saving configuration:', error);
                    showNotification('Failed to save configuration', 'error');
                } finally {
                    button.disabled = false;
                    button.innerHTML = originalHTML;
                }
            });
        }
    };
    
    // Logout button functionality (both desktop and mobile)
    const setupLogoutButton = (buttonId) => {
        const button = document.getElementById(buttonId);
        if (button) {
            button.addEventListener('click', () => {
                if (confirm(window.translations.confirm_logout || 'Are you sure you want to logout?')) {
                    window.location.href = '/logout';
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

// Initialize WebSocket when page loads
document.addEventListener('DOMContentLoaded', () => {
    // Setup navigation buttons
    setupNavigationButtons();
    
    // Delay WebSocket initialization to ensure everything is loaded
    setTimeout(initializeWebSocket, 1000);
});
