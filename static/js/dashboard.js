let socket = null;
let reconnecting = false;
let reconnectTimeout = null;

function connectSocket() {
    socket = io({
        transports: ['polling'],
        upgrade: false,
        rememberUpgrade: false,
        autoConnect: true,
        forceNew: false,
        timeout: 20000,
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 3000,
        withCredentials: false,
        pollingTimeout: 30000
    });
    setupSocketHandlers();
}

function setupSocketHandlers() {
    socket.on('connect', () => {
        reconnectAttempts = 0;
        reconnecting = false;
        if (reconnectBtn) reconnectBtn.style.display = "none";
        // Always request the latest image on connect so the page never shows a
        // stale browser-cached version. The server sends it from memory (~1–2 ms on LAN).
        socket.emit('request_latest_image');
        pendingImageRefresh = false;
        // Subscribe to block notifications (always enabled)
        subscribeToBlockNotifications();
        // Detect any restart (auto-update, manual systemctl restart, etc.) by comparing
        // the server's process start time against what we saw at page load.
        // _restartPending handles announced restarts; _pageLoadStarted handles silent ones.
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
                        window._restartPending = null;
                        if (_tag) sessionStorage.setItem('mempaper_updated_to', _tag);
                        location.reload();
                    }
                })
                .catch(() => {});
        }
    });

    socket.on('disconnect', (reason) => {
        pendingImageRefresh = true;
        attemptReconnect();
    });

    socket.on('connect_error', (error) => {
        console.error("🚫 Socket.IO connection error:", error);
        attemptReconnect();
    });

    socket.on('error', (error) => {
        console.error("⚠️ Socket.IO transport error:", error);
        attemptReconnect();
    });

    socket.on('upgradeError', (error) => {
        console.warn("⚠️ Transport upgrade failed:", error);
    });

    socket.io.on('error', (error) => {
        console.error("🚫 Socket.IO engine error:", error);
    });

    socket.io.engine.on('upgradeError', (error) => {
        console.warn("⚠️ Engine upgrade error:", error);
    });

    // Reconnection attempt
    socket.on('reconnect_attempt', (attemptNumber) => {
        reconnectAttempts = attemptNumber;

        // Show manual reconnect button after several failed attempts
        if (attemptNumber > 5) {
            if (reconnectBtn) {
                reconnectBtn.style.display = "inline-block";
            }
        }
    });

    // Reconnection successful
    socket.on('reconnect', (attemptNumber) => {
        reconnectAttempts = 0;
        if (reconnectBtn) {
            reconnectBtn.style.display = "none";
        }
    });

    // Reconnection failed
    socket.on('reconnect_failed', () => {
        if (reconnectBtn) {
            reconnectBtn.style.display = "inline-block";
        }
    });

    // New image received
    socket.on('new_image', (data) => {
        // Validate image data
        if (!data.image || !data.image.startsWith('data:image/png;base64,') || data.image.length < 100) {
            console.error("❌ Invalid image data received", data);
            return;
        }
        
        const dashboardImg = document.getElementById("dashboard");
        
        // Create a new image element to preload and ensure loading
        const tempImg = new Image();
        tempImg.onload = function() {
            dashboardImg.src = data.image;
            lastImageUpdate = new Date();
            // Persist so F5 restores the latest image instead of the stale server-rendered URL
            try { localStorage.setItem('mempaper_last_image', data.image); } catch (e) {}
        };
        
        tempImg.onerror = function() {
            console.error("❌ Failed to load new image");
        };
        
        tempImg.src = data.image;
    });

    // Lightning donation received (authenticated + feature enabled only)
    socket.on('donation_received', (data) => {
        const sats = data.amount_sats ? data.amount_sats.toLocaleString() : '?';
        const satLabel = data.amount_sats === 1 ? 'sat' : 'sats';
        const msg = data.message ? ` — "${data.message}"` : '';

        if (window.isAuthenticated && window.featureFlags && window.featureFlags.donations) {
            showDashboardToast('⚡', `Donation: ${sats} ${satLabel}${msg}`);
        }

        // Request fresh dashboard image to show updated donation block
        socket.emit('request_latest_image');
    });

    // Wallet balance updates (authenticated + wallet enabled only)
    socket.on('wallet_balance_updated', (data) => {
        if (!window.isAuthenticated || !window.featureFlags || !window.featureFlags.wallet) return;
        const allEntries = [].concat(data.addresses || [], data.xpubs || []);
        const allPrev = [].concat(data.prev_addresses || [], data.prev_xpubs || []);
        const isStartup = data.startup_refresh || data.after_config_save || false;

        allEntries.forEach(entry => {
            const label = entry.comment || entry.xpub_short || 'Wallet';
            const bal = entry.balance_btc || 0;
            const addr = entry.address || entry.xpub || '';
            const prev = allPrev.find(p => (p.address || p.xpub) === addr);
            const prevBal = prev ? (prev.balance_btc || 0) : -1;

            if (prevBal < 0 || isStartup) {
                // Skip toast on startup/config-save — only toast for genuinely new wallets
            } else if (bal !== prevBal) {
                showDashboardToast('💰', `Wallet '${label}' balance: ${prevBal.toFixed(8)} → ${bal.toFixed(8)} BTC`);
            }
        });

        // Request fresh image
        socket.emit('request_latest_image');
    });

    // Bitaxe stats updates (authenticated + bitaxe enabled only)
    socket.on('bitaxe_stats_updated', (data) => {
        if (!window.isAuthenticated || !window.featureFlags || !window.featureFlags.bitaxe) return;
        if (!data || !data.miners) return;
        for (const [ip, minerData] of Object.entries(data.miners)) {
            const label = minerData.label || ip;
            if (minerData.best_diff > 0 && minerData.best_diff !== minerData.prev_best_diff) {
                showDashboardToast('⛏️', `New best diff for ${label}: ${_formatDiff(minerData.best_diff)}`);
            }
            if (minerData.online !== minerData.prev_online) {
                if (minerData.online) {
                    showDashboardToast('🟢', `${label} is back online`);
                } else {
                    showDashboardToast('🔴', `${label} went offline`);
                }
            }
        }
    });

    // Found blocks updates (authenticated + bitaxe enabled only)
    socket.on('found_blocks_updated', (data) => {
        if (!window.isAuthenticated || !window.featureFlags || !window.featureFlags.bitaxe) return;
        if (!data || !data.blocks) return;
        for (const [addr, blockData] of Object.entries(data.blocks)) {
            if (blockData.count > blockData.prev_count) {
                const diff = blockData.count - blockData.prev_count;
                showDashboardToast('🏆', `${blockData.label}: ${diff} new block${diff > 1 ? 's' : ''} found! (total: ${blockData.count})`);
            }
        }
    });

    // Auto-update started notification (authenticated only)
    socket.on('auto_update_started', () => {
        if (!window.isAuthenticated) return;
        const t = window.translations || {};
        _buildLiveToast(
            '<img src="/static/icons/update.svg" width="16" height="16" class="toast-title-icon toast-icon-accent"> ' + (t.auto_update_started || 'Auto-update started'),
            t.auto_update_started_body || 'Checking for system and software updates...',
            '#F7931A',
            10000
        );
    });

    // Service restart (after auto-update or manual restart) — mark pending and poll until back
    socket.on('service_restarting', (data) => {
        if (!window.isAuthenticated) return;
        fetch('/api/health', { cache: 'no-store' })
            .then(r => r.ok ? r.json() : null)
            .then(h => { window._restartPending = { oldStarted: h ? h.started : null, tag: data.tag }; })
            .catch(() => { window._restartPending = { oldStarted: null, tag: data.tag }; });
    });

    // ... other socket event handlers ...
}

function attemptReconnect() {
    if (reconnecting) return;
    reconnecting = true;
    if (reconnectTimeout) clearTimeout(reconnectTimeout);
    reconnectTimeout = setTimeout(() => {
        if (socket) socket.connect();
        reconnecting = false;
    }, 2000);
}

// Global variables for socket state
const reconnectBtn = document.getElementById('reconnect-button');
let reconnectAttempts = 0;
let lastImageUpdate = null;
let imageUpdateTimeout = null;
let pendingImageRefresh = false;

// Capture the server's process start time on page load so we can detect
// a restart (including manual systemctl restarts that send no socket event).
fetch('/api/health', { cache: 'no-store' })
    .then(r => r.ok ? r.json() : null)
    .then(h => { if (h) window._pageLoadStarted = h.started; })
    .catch(() => {});

// Show success toast if we just reloaded after a software update.
(function() {
    const _updatedTag = sessionStorage.getItem('mempaper_updated_to');
    if (!_updatedTag) return;
    sessionStorage.removeItem('mempaper_updated_to');
    setTimeout(() => {
        const t = window.translations || {};
        const icon = '<img src="/static/icons/update.svg" width="16" height="16" class="toast-title-icon toast-icon-success"> ';
        _buildLiveToast(
            icon + (t.update_success_title || 'Update successful'),
            (t.update_success_body || 'mempaper updated to') + ' <strong>' + _updatedTag + '</strong>',
            '#28a745',
            8000
        );
    }, 800);
}());

// Initial connection
connectSocket();

// Reload immediately when the tab becomes visible again if a service restart was pending.
document.addEventListener('visibilitychange', () => {
    if (document.hidden || !window._restartPending) return;
    const { oldStarted } = window._restartPending;
    fetch('/api/health', { cache: 'no-store' })
        .then(r => r.ok ? r.json() : null)
        .then(h => {
            if (h && (!oldStarted || h.started > oldStarted)) {
                const _tag = window._restartPending?.tag;
                window._restartPending = null;
                if (_tag) sessionStorage.setItem('mempaper_updated_to', _tag);
                location.reload();
            }
        })
        .catch(() => {});
});

// Allow bfcache by closing the socket when the page is hidden and restoring on return
window.addEventListener('pagehide', () => {
    if (socket) {
        socket.disconnect();
        pendingImageRefresh = true; // image may be stale after we come back
    }
});
window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
        if (socket && socket.disconnected) {
            socket.connect();
        } else if (!socket) {
            connectSocket();
        }
    }
});

// Background processing status updates (for instant startup mode)
socket.on('background_ready', (data) => {
    socket.emit('request_latest_image');
    
    // Show a brief notification
    showNotification("Background processing complete!", "success");
});

socket.on('background_error', (data) => {
    console.warn("⚠️ Background processing error", data);
    
    // Show error notification
    showNotification("Background processing failed: " + data.message, "error");
});

// Function to show brief notifications
function showNotification(message, type = "info") {
    // Create notification element if it doesn't exist
    let notification = document.getElementById('notification');
    if (!notification) {
        notification = document.createElement('div');
        notification.id = 'notification';
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 6px;
            color: white;
            font-weight: bold;
            z-index: 1000;
            opacity: 0;
            transition: opacity 0.3s ease;
            max-width: 300px;
            word-wrap: break-word;
        `;
        document.body.appendChild(notification);
    }
    
    // Set style based on type
    const styles = {
        success: 'background-color: #38a169;',
        error: 'background-color: #e53e3e;',
        warning: 'background-color: #d69e2e; color: black;',
        info: 'background-color: #4da6ff;'
    };
    
    notification.style.cssText += styles[type] || styles.info;
    notification.textContent = message;
    notification.style.opacity = '1';
    
    // Auto-hide after 4 seconds
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 4000);
}

// Show block notification toast
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
    // Ensure container is the last body child so it paints above nav backdrop-filter elements
    if (toastContainer.nextSibling) document.body.appendChild(toastContainer);
    
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

        // Create close button (optimized for mobile touch targets: 44x44px minimum)
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

        closeBtn.addEventListener('mouseenter', () => {
            closeBtn.style.backgroundColor = closeBtnHoverBg;
        });

        closeBtn.addEventListener('mouseleave', () => {
            closeBtn.style.backgroundColor = closeBtnBg;
        });
        
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
        
        // Close button click handler
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            closeToast();
        });
        
        // Mobile-friendly: tap anywhere on toast to dismiss
        toast.addEventListener('click', closeToast);
        toast.style.cursor = 'pointer';
        
        // Append close button to toast
        toast.appendChild(closeBtn);
        
        // Store close function for later updates
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
        contentDiv.style.cssText = 'margin-right: 20px;';
        toast.appendChild(contentDiv);
    }
    
    // Update content (works for both new and enriched data)
    contentDiv.innerHTML = `
        <div style="font-weight: bold; font-size: 16px; margin-bottom: 8px; color: #F7931A;">
            New Block ${heightFormatted}
        </div>
        <div style="margin-bottom: 4px;">
            <span style="opacity: 0.6;">Time:</span> <span style="font-weight: 500;">${timeString}</span>
        </div>
        <div style="margin-bottom: 4px;">
            <span style="opacity: 0.6;">Hash:</span> <span style="font-family: monospace; font-size: 12px;">${blockData.block_hash}</span>
        </div>
        <div style="margin-bottom: 4px;">
            <span style="opacity: 0.6;">Pool:</span> <span style="font-weight: 500;">${blockData.pool_name}</span>
        </div>
        <div style="margin-bottom: 4px;">
            <span style="opacity: 0.6;">Reward:</span> <span style="font-weight: 500; color: #68d391;">${rewardFormatted} BTC</span>
            <span style="font-size: 12px; opacity: 0.5;">(+${feesFormatted} fees)</span>
        </div>
        <div>
            <span style="opacity: 0.6;">Median Fee:</span> <span style="font-weight: 500;">${medianFeeFormatted} sat/vB</span>
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
        setTimeout(toast.closeToast, 30000);
    } else {
        // Existing toast - just updated content, add subtle flash effect
        contentDiv.style.transition = 'opacity 0.2s';
        contentDiv.style.opacity = '0.7';
        setTimeout(() => {
            contentDiv.style.opacity = '1';
        }, 100);
    }
}

// New block notification with toast
socket.on('new_block_notification', (data) => {
    if (data.page && data.page !== 'dashboard') {
        // console.log('[DEBUG] Block notification for other page, ignoring.');
        return;
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

// Configuration reloaded notification
socket.on('config_reloaded', (data) => {
    // Request fresh image after config change
    setTimeout(() => {
        socket.emit('request_latest_image');
        refreshCurrentImage();
    }, 500);
});

// Enhanced status monitoring
setInterval(() => {
    const now = new Date();
    
    if (socket.connected) {
        // Check for stale image data and auto-request if needed
        if (lastImageUpdate) {
            const timeSinceUpdate = Math.floor((now - lastImageUpdate) / 1000);
            if (timeSinceUpdate > 600) { // 10 minutes
                socket.emit('request_latest_image');
                refreshCurrentImage();
            }
        }
    }
}, 10000); // Check every 10 seconds

// Manual reconnection button (if connection completely fails)
function forceReconnect() {
    socket.disconnect();
    setTimeout(() => {
        socket.connect();
    }, 1000);
}

// Force refresh current dashboard image
function refreshCurrentImage() {
    const dashboardImg = document.getElementById("dashboard");

    if (dashboardImg && dashboardImg.src) {
        const currentSrc = dashboardImg.src;

        // Only refresh if src is a valid HTTP/HTTPS URL (not base64 data: or placeholder)
        if (!currentSrc.startsWith('http://') && !currentSrc.startsWith('https://')) {
            return;
        }
        
        const baseUrl = currentSrc.split('?')[0]; // Remove any existing query parameters
        const timestamp = new Date().getTime();
        const newUrl = baseUrl + "?refresh=" + timestamp + "&cache=" + Math.random();
        
        // Create preloader for smooth transition
        const tempImg = new Image();
        tempImg.onload = function() {
            dashboardImg.src = newUrl;
        };
        tempImg.onerror = function() {
            console.warn("⚠️ Failed to refresh current image, keeping existing");
        };
        tempImg.src = newUrl;
    }
}

// Request initial image when page loads
document.addEventListener('DOMContentLoaded', async function() {
    const dashboardImg = document.getElementById("dashboard");

    // Immediately restore the last known image from localStorage.
    // The server-rendered src is a stale URL (/image?v=old_block) — the base64
    // image stored here is always the latest one the browser has actually seen.
    try {
        const cached = localStorage.getItem('mempaper_last_image');
        if (cached && cached.startsWith('data:image/png;base64,')) {
            dashboardImg.src = cached;
            lastImageUpdate = new Date();
        }
    } catch (e) {}

    // Always request the latest image via WebSocket on load so we stay current
    // (previously skipped when a server URL was present — that caused stale images)
    setTimeout(() => {
        if (socket.connected) {
            socket.emit('request_latest_image');
        } else {
            const checkConnection = setInterval(() => {
                if (socket.connected) {
                    clearInterval(checkConnection);
                    socket.emit('request_latest_image');
                }
            }, 500);
            
            // Stop checking after 10 seconds
            setTimeout(() => clearInterval(checkConnection), 10000);
        }
    }, 1000);
});

// Block notification subscription functionality
let blockNotificationsEnabled = false;
let notificationTimeoutId = null;

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

// Check if live block notifications are enabled from server config
document.addEventListener('DOMContentLoaded', function() {
    // Always register and subscribe for notifications if authenticated
    registerPageForNotifications('dashboard');
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
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    unregisterPageForNotifications('dashboard');
});

// Subscribe to block notifications
function subscribeToBlockNotifications() {
    socket.emit('subscribe_block_notifications', { page: 'dashboard' });
}

// Unsubscribe from block notifications
function unsubscribeFromBlockNotifications() {
    socket.emit('unsubscribe_block_notifications');
}

// Add event listeners for block notification subscription events
socket.on('block_notification_status', (data) => {
    if (data.status === 'subscribed') {
        blockNotificationsEnabled = true;
    } else if (data.status === 'unsubscribed') {
        blockNotificationsEnabled = false;
    }
});

socket.on('block_notification_error', () => {
    // subscription errors are non-fatal; silently ignore
});

// Global functions for enabling/disabling block notifications
window.enableBlockNotifications = function() {
    subscribeToBlockNotifications();
};

window.disableBlockNotifications = function() {
    unsubscribeFromBlockNotifications();
};

// Format difficulty value for display
function _formatDiff(value) {
    if (!value || value === 0) return '-';
    if (value >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
    if (value >= 1e9) return `${(value / 1e9).toFixed(2)}G`;
    if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(2)}k`;
    return `${Math.round(value)}`;
}

// Dashboard live-update toast — uses shared glass-card style from toast.js
function showDashboardToast(icon, message) {
    _buildLiveToast(icon, message, '#F7931A', 6000);
}
