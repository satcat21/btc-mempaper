/**
 * Session Management
 * Handles automatic session renewal and provides better UX for session expiration.
 * Shared between the config page and the dashboard (when the viewer is authenticated).
 */

const SESSION_WARNING_LEAD_SECONDS = 30;

let sessionCheckInterval = null;
let warningTimeoutId = null;
let countdownIntervalId = null;
let sessionExpiryEpoch = null;   // ms epoch when the current session is expected to expire
let countdownToastEl = null;     // active "Logging out in..." toast element, if shown
let sessionExpiredHandled = false;

/**
 * Any authenticated request succeeding elsewhere on the page (e.g. clicking
 * Save) renews the session server-side as a side effect.
 */
async function notifySessionRenewed() {
    if (!isCountdownToastVisible()) return;
    await syncSessionStatus();
    showSessionRefreshedMessage();
}

(function () {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async function (input, init) {
        const response = await originalFetch(input, init);
        try {
            const url = typeof input === 'string' ? input : (input && input.url) || '';
            // Skip our own session-endpoint calls to avoid re-triggering ourselves.
            if (response.ok && !url.includes('/api/session/')) {
                // Fire-and-forget - catch so a bug in here fails loud (console)
                // instead of vanishing as a silent unhandled rejection.
                notifySessionRenewed().catch((err) => console.error('notifySessionRenewed failed:', err));
            }
        } catch (e) { /* ignore */ }
        return response;
    };
})();

/**
 * Poll the server for the authoritative session state and (re)schedule the
 * logout countdown around it.
 */
async function syncSessionStatus() {
    try {
        const response = await fetch('/api/session/status');
        const sessionInfo = await response.json();

        if (!sessionInfo.authenticated) {
            handleSessionExpired();
            return;
        }

        sessionExpiredHandled = false;
        scheduleWarning(sessionInfo.time_remaining);

        // Silent auto-refresh while the user is actively editing the config form,
        // so in-progress edits are never interrupted by the logout countdown.
        if (sessionInfo.time_remaining <= 600 && isUserActivelyEditing()) {
            await refreshSession();
        }
    } catch (error) {
        console.warn('Session status check failed:', error);
    }
}

/**
 * Arm (or re-arm) the countdown toast so it appears exactly
 * SESSION_WARNING_LEAD_SECONDS before the session expires.
 */
function scheduleWarning(timeRemainingSeconds) {
    sessionExpiryEpoch = Date.now() + timeRemainingSeconds * 1000;

    if (warningTimeoutId) {
        clearTimeout(warningTimeoutId);
        warningTimeoutId = null;
    }

    const msUntilWarning = (timeRemainingSeconds - SESSION_WARNING_LEAD_SECONDS) * 1000;

    if (msUntilWarning <= 0) {
        if (timeRemainingSeconds <= 0) {
            handleSessionExpired();
            return;
        }
        if (!isCountdownToastVisible()) {
            showCountdownToast();
        }
        return;
    }

    // Session must have been refreshed (e.g. another authenticated request) while
    // the countdown toast was showing - cancel it, it'll be rescheduled below.
    dismissCountdownToast();
    warningTimeoutId = setTimeout(showCountdownToast, msUntilWarning);
}

/**
 * Show the "Logging out in N seconds" toast with a live countdown and a
 * "Stay logged in" button.
 */
function showCountdownToast() {
    if (isCountdownToastVisible() || typeof _buildLiveToast !== 'function') return;

    const t = window.translations || {};
    const remainingSeconds = Math.max(0, Math.ceil((sessionExpiryEpoch - Date.now()) / 1000));
    const btnId = 'session-refresh-toast-btn-' + Date.now();
    const countdownId = 'session-countdown-' + Date.now();
    const countingDownText = (t.session_logging_out_in || 'Logging out in {seconds} seconds.')
        .replace('{seconds}', `<span id="${countdownId}">${remainingSeconds}</span>`);
    const bodyHtml = `${countingDownText} ` +
        `<button id="${btnId}" type="button" style="background:none;border:none;padding:0;` +
        `color:inherit;text-decoration:underline;font-weight:600;cursor:pointer;font-size:inherit;">` +
        `${t.session_stay_logged_in || 'Stay logged in'}</button>`;

    const titleIcon = '<img src="/static/icons/logout.svg" alt="" width="16" height="16" class="toast-title-icon toast-icon-accent">';
    countdownToastEl = _buildLiveToast(titleIcon + (t.session_toast_title || 'Session'), bodyHtml, '#F7931A', (remainingSeconds + 2) * 1000);

    const countdownSpan = document.getElementById(countdownId);
    const btn = document.getElementById(btnId);

    countdownIntervalId = setInterval(() => {
        const secondsLeft = Math.max(0, Math.ceil((sessionExpiryEpoch - Date.now()) / 1000));
        if (countdownSpan) countdownSpan.textContent = secondsLeft;
        if (secondsLeft <= 0) {
            clearInterval(countdownIntervalId);
            countdownIntervalId = null;
            handleSessionExpired();
        }
    }, 1000);

    if (btn) {
        btn.addEventListener('click', async (e) => {
            // The toast itself closes on any click inside it - stop that here
            // so the button gets to show its own "Refreshing…" state first.
            e.stopPropagation();
            btn.disabled = true;
            btn.textContent = t.session_refreshing || 'Refreshing…';
            const success = await refreshSession();
            if (!success) {
                btn.disabled = false;
                btn.textContent = t.session_stay_logged_in || 'Stay logged in';
                showFailedRefreshMessage();
            }
        });
    }
}

function dismissCountdownToast() {
    if (countdownIntervalId) {
        clearInterval(countdownIntervalId);
        countdownIntervalId = null;
    }
    if (countdownToastEl) {
        if (typeof countdownToastEl.closeToast === 'function') {
            countdownToastEl.closeToast();
        }
        countdownToastEl = null;
    }
}

/**
 * Whether the countdown toast is actually visible right now. Toasts can be
 * dismissed by the user clicking anywhere on them (see toast.js), which
 * doesn't go through dismissCountdownToast() - so countdownToastEl can be a
 * stale reference to an already-removed element. Self-heal that here instead
 * of trusting truthiness alone, so a dismissed toast doesn't get treated as
 * "still showing" forever after (e.g. by notifySessionRenewed).
 */
function isCountdownToastVisible() {
    if (countdownToastEl && !countdownToastEl.isConnected) {
        dismissCountdownToast();
    }
    return !!countdownToastEl;
}

/**
 * Refresh the current session to extend its lifetime.
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
                dismissCountdownToast();
                if (warningTimeoutId) {
                    clearTimeout(warningTimeoutId);
                    warningTimeoutId = null;
                }
                const timeRemaining = result.session_info && typeof result.session_info.time_remaining === 'number'
                    ? result.session_info.time_remaining
                    : null;
                if (timeRemaining !== null) {
                    scheduleWarning(timeRemaining);
                }
                showSessionRefreshedMessage();
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
        if (now - lastActivity < 600000) { // Active in last 10 minutes
            return true;
        }
    }
    return false;
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
            handleSessionExpired();
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
function showSessionExpiredMessage() {
    const t = window.translations || {};
    // Config always requires auth, so send it straight to /login. The dashboard
    // route itself decides between showing the public view and redirecting to
    // /login (see allow_public_or_auth) - the client doesn't know which, so the
    // dashboard message can't claim a specific destination like the config one can.
    const isConfigPage = window.location.pathname.startsWith('/config');
    const message = isConfigPage
        ? (t.session_expired || 'Session expired. Redirecting to login...')
        : (t.session_expired_dashboard || 'Session expired. Redirecting…');

    if (typeof _buildLiveToast === 'function') {
        const icon = '<img src="/static/icons/logout.svg" alt="" width="16" height="16" class="toast-title-icon toast-icon-error">';
        _buildLiveToast(icon + (t.session_expired_title || 'Session Expired'), message, '#dc3545', 5000);
    } else if (typeof showAlertModal === 'function') {
        showAlertModal({ title: t.session_expired_title || 'Session Expired', message });
    }

    setTimeout(() => {
        window.location.href = isConfigPage ? '/login' : '/';
    }, 2000);
}

function showSessionRefreshedMessage() {
    const t = window.translations || {};
    if (typeof _buildLiveToast === 'function') {
        const icon = '<img src="/static/icons/check.svg" width="16" height="16" class="toast-title-icon toast-icon-success"> ';
        _buildLiveToast(
            icon + (t.session_renewed_title || 'Session Renewed'),
            t.session_renewed_body || 'Your session has been extended.',
            '#28a745',
            5000
        );
    } else if (typeof showNotification === 'function') {
        showNotification(t.session_renewed_body || 'Session refreshed successfully!', 'success');
    }
}

function showFailedRefreshMessage() {
    const t = window.translations || {};
    const message = t.session_refresh_failed || 'Failed to refresh session.';
    if (typeof showNotification === 'function') {
        showNotification(message, 'error');
    } else if (typeof showAlertModal === 'function') {
        showAlertModal({ title: t.session_error_title || 'Session Error', message });
    }
}

/**
 * Handle a session that has expired (or been confirmed expired server-side).
 * Idempotent - safe to call multiple times (timers, failed refreshes, 401s).
 */
function handleSessionExpired() {
    if (sessionExpiredHandled) return;
    sessionExpiredHandled = true;

    if (warningTimeoutId) {
        clearTimeout(warningTimeoutId);
        warningTimeoutId = null;
    }
    dismissCountdownToast();
    if (sessionCheckInterval) {
        clearInterval(sessionCheckInterval);
        sessionCheckInterval = null;
    }

    showSessionExpiredMessage();
}

/**
 * Initialize session management
 */
function initializeSessionManager() {
    // On the dashboard, unauthenticated (public) viewers have nothing to manage.
    // The config page is always authenticated, so window.isAuthenticated is unset there.
    if (typeof window.isAuthenticated !== 'undefined' && window.isAuthenticated === false) {
        return;
    }

    // Poll for authoritative session state every minute.
    sessionCheckInterval = setInterval(syncSessionStatus, 60000);

    // Initial session check after 5 seconds
    setTimeout(syncSessionStatus, 5000);

    // Track user activity on form elements (no-op on pages without them)
    setTimeout(trackUserActivity, 1000);
}

/**
 * Clean up session manager
 */
function cleanupSessionManager() {
    if (sessionCheckInterval) {
        clearInterval(sessionCheckInterval);
        sessionCheckInterval = null;
    }
    if (warningTimeoutId) {
        clearTimeout(warningTimeoutId);
        warningTimeoutId = null;
    }
    if (countdownIntervalId) {
        clearInterval(countdownIntervalId);
        countdownIntervalId = null;
    }
    countdownToastEl = null;
    sessionExpiredHandled = false;
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
