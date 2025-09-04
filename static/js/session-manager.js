/**
 * Session Management for Mempaper Config Page
 * Handles automatic session renewal and provides better UX for session expiration
 */

// Session management state
let sessionWarningShown = false;
let sessionCheckInterval = null;
let refreshButtonAdded = false;

/**
 * Check the current session status and handle warnings/expiration
 */
async function checkSessionStatus() {
    try {
        const response = await fetch('/api/session/status');
        const sessionInfo = await response.json();
        
        if (!sessionInfo.authenticated) {
            clearInterval(sessionCheckInterval);
            showSessionExpiredMessage();
            return;
        }
        
        // Show warning when 15 minutes left (instead of 5)
        if (sessionInfo.time_remaining <= 900 && !sessionWarningShown) {
            sessionWarningShown = true;
            const minutes = Math.ceil(sessionInfo.time_remaining / 60);
            showSessionWarning(minutes);
            addRefreshSessionButton();
        }
        
        // Auto-refresh session when 10 minutes left if user is actively editing
        if (sessionInfo.time_remaining <= 600 && isUserActivelyEditing()) {
            console.log('Auto-refreshing session due to user activity');
            await refreshSession();
        }
        
    } catch (error) {
        console.warn('Session status check failed:', error);
    }
}

/**
 * Refresh the current session to extend its lifetime
 */
async function refreshSession() {
    try {
        const response = await fetch('/api/session/refresh', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (response.ok) {
            const result = await response.json();
            if (result.success) {
                sessionWarningShown = false;
                refreshButtonAdded = false;
                showSessionRefreshedMessage();
                removeRefreshSessionButton();
                return true;
            }
        }
        
        return false;
    } catch (error) {
        console.error('Session refresh failed:', error);
        return false;
    }
}

/**
 * Check if user is actively editing the configuration
 */
function isUserActivelyEditing() {
    const formElements = document.querySelectorAll('[data-config-key]');
    const now = Date.now();
    
    for (const element of formElements) {
        const lastActivity = element.lastActivityTime || 0;
        if (now - lastActivity < 600000) { // Active in last 10 minutes (increased from 5)
            return true;
        }
    }
    return false;
}

/**
 * Add a temporary refresh session button
 */
function addRefreshSessionButton() {
    if (refreshButtonAdded || document.getElementById('refresh-session-btn')) {
        return; // Already exists
    }
    
    const saveButton = document.getElementById('save-button');
    if (!saveButton) return;
    
    const refreshBtn = document.createElement('button');
    refreshBtn.id = 'refresh-session-btn';
    refreshBtn.className = 'form-button';
    refreshBtn.type = 'button';
    refreshBtn.style.backgroundColor = '#FFC107';
    refreshBtn.style.color = '#000';
    refreshBtn.style.marginLeft = '10px';
    refreshBtn.style.border = 'none';
    refreshBtn.style.padding = '10px 20px';
    refreshBtn.style.borderRadius = '4px';
    refreshBtn.style.cursor = 'pointer';
    refreshBtn.textContent = '🔄 Refresh Session';
    
    refreshBtn.addEventListener('click', async () => {
        refreshBtn.disabled = true;
        refreshBtn.textContent = '🔄 Refreshing...';
        
        const success = await refreshSession();
        
        refreshBtn.disabled = false;
        refreshBtn.textContent = '🔄 Refresh Session';
        
        if (!success) {
            showFailedRefreshMessage();
        }
    });
    
    saveButton.parentNode.insertBefore(refreshBtn, saveButton.nextSibling);
    refreshButtonAdded = true;
}

/**
 * Remove the refresh session button
 */
function removeRefreshSessionButton() {
    const refreshBtn = document.getElementById('refresh-session-btn');
    if (refreshBtn) {
        refreshBtn.remove();
        refreshButtonAdded = false;
    }
}

/**
 * Track user activity on form elements
 */
function trackUserActivity() {
    const formElements = document.querySelectorAll('[data-config-key]');
    formElements.forEach(element => {
        ['input', 'change', 'click', 'focus'].forEach(eventType => {
            element.addEventListener(eventType, () => {
                element.lastActivityTime = Date.now();
            });
        });
    });
}

/**
 * Enhanced save configuration with session handling
 */
async function saveConfigurationWithSessionHandling(configData) {
    try {
        const response = await fetch('/api/config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(configData)
        });
        
        if (response.status === 401) {
            // Session expired - handle gracefully
            showSessionExpiredMessage();
            return { success: false, sessionExpired: true };
        }
        
        if (response.status === 429) {
            const errorData = await response.json();
            const retryAfter = errorData.retry_after || 60;
            return { 
                success: false, 
                rateLimited: true, 
                retryAfter: retryAfter,
                message: `Rate limit exceeded. Please wait ${retryAfter} seconds before trying again.`
            };
        }
        
        const result = await response.json();
        return result;
        
    } catch (error) {
        console.error('Configuration save failed:', error);
        return { 
            success: false, 
            error: true,
            message: 'Network error. Please try again.'
        };
    }
}

// Message display functions
function showSessionWarning(minutes) {
    if (typeof showNotification === 'function') {
        showNotification(`⏰ Session expires in ${minutes} minutes. Click 'Refresh Session' to extend.`, 'warning');
    } else {
        alert(`Session expires in ${minutes} minutes. Please refresh your session to continue.`);
    }
}

function showSessionExpiredMessage() {
    if (typeof showNotification === 'function') {
        showNotification('🔒 Session expired. Redirecting to login...', 'error');
    } else {
        alert('Session expired. Please login again.');
    }
    
    setTimeout(() => {
        window.location.href = '/login';
    }, 2000);
}

function showSessionRefreshedMessage() {
    if (typeof showNotification === 'function') {
        showNotification('✅ Session refreshed successfully!', 'success');
    }
}

function showFailedRefreshMessage() {
    if (typeof showNotification === 'function') {
        showNotification('❌ Failed to refresh session. Please save your work and login again.', 'error');
    } else {
        alert('Failed to refresh session. Please save your work and login again.');
    }
}

/**
 * Initialize session management
 */
function initializeSessionManager() {
    console.log('🔐 Initializing session manager');
    
    // Start session monitoring (check every 2 minutes)
    sessionCheckInterval = setInterval(checkSessionStatus, 120000);
    
    // Initial session check after 5 seconds
    setTimeout(checkSessionStatus, 5000);
    
    // Track user activity on form elements
    setTimeout(trackUserActivity, 1000);
    
    console.log('✅ Session manager initialized');
}

/**
 * Clean up session manager
 */
function cleanupSessionManager() {
    if (sessionCheckInterval) {
        clearInterval(sessionCheckInterval);
        sessionCheckInterval = null;
    }
    removeRefreshSessionButton();
    sessionWarningShown = false;
    refreshButtonAdded = false;
}

// Auto-initialize when this script is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSessionManager);
} else {
    // DOM already loaded
    initializeSessionManager();
}

// Clean up on page unload
window.addEventListener('beforeunload', cleanupSessionManager);
