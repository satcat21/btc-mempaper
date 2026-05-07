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
        reconnectionDelayMax: 30000,
        withCredentials: false,
        pollingTimeout: 30000
    });
    setupSocketHandlers();
}

function setupSocketHandlers() {
    socket.on('connect', () => {
        console.log("✅ Connected to Mempaper WebSocket");
        reconnectAttempts = 0;
        reconnecting = false;
        if (reconnectBtn) reconnectBtn.style.display = "none";
        // Only request latest image if we don't have one loaded yet
        const dashboardImg = document.getElementById("dashboard");
        if (!dashboardImg.src || dashboardImg.src.includes('placeholder') || dashboardImg.src === window.location.href) {
            socket.emit('request_latest_image');
        }
        // Subscribe to block notifications (always enabled)
        subscribeToBlockNotifications();
    });

    socket.on('disconnect', (reason) => {
        console.log("❌ Disconnected from Mempaper WebSocket:", reason);
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

    // Log transport changes for debugging
    socket.on('upgrade', () => {
        console.log("⬆️ Transport upgraded to:", socket.io.engine.transport.name);
    });

    socket.on('upgradeError', (error) => {
        console.warn("⚠️ Transport upgrade failed:", error);
    });

    // Enhanced transport monitoring
    socket.io.on('error', (error) => {
        console.error("🚫 Socket.IO engine error:", error);
    });

    // Monitor connection state changes
    socket.io.engine.on('upgrade', () => {
        console.log("⚙️ Engine transport upgraded to:", socket.io.engine.transport.name);
    });

    socket.io.engine.on('upgradeError', (error) => {
        console.warn("⚠️ Engine upgrade error:", error);
    });

    // Reconnection attempt
    socket.on('reconnect_attempt', (attemptNumber) => {
        reconnectAttempts = attemptNumber;
        console.log(`⚙️ Reconnection attempt ${attemptNumber}...`);
        
        // Show manual reconnect button after several failed attempts
        if (attemptNumber > 5) {
            if (reconnectBtn) {
                reconnectBtn.style.display = "inline-block";
            }
        }
    });

    // Reconnection successful
    socket.on('reconnect', (attemptNumber) => {
        console.log(`✅ Reconnected after ${attemptNumber} attempts`);
        reconnectAttempts = 0;
        if (reconnectBtn) {
            reconnectBtn.style.display = "none";
        }
    });

    // Reconnection failed
    socket.on('reconnect_failed', () => {
        console.log("❌ Reconnection failed permanently");
        if (reconnectBtn) {
            reconnectBtn.style.display = "inline-block";
        }
    });

    // New image received
    socket.on('new_image', (data) => {
        console.log("📶 New dashboard image received", {
            hasImageData: !!data.image,
            imageLength: data.image ? data.image.length : 0,
            timestamp: new Date().toISOString()
        });
        
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
            console.log("✅ Dashboard image updated successfully", {
                newSrcLength: dashboardImg.src.length,
                timestamp: lastImageUpdate.toISOString()
            });
        };
        
        tempImg.onerror = function() {
            console.error("❌ Failed to load new image");
        };
        
        tempImg.src = data.image;
    });

    // Lightning donation received
    socket.on('donation_received', (data) => {
        const sats = data.amount_sats ? data.amount_sats.toLocaleString() : '?';
        const satLabel = data.amount_sats === 1 ? 'sat' : 'sats';
        const msg = data.message ? ` — "${data.message}"` : '';
        console.log(`⚡ Donation received: ${sats} ${satLabel}${msg}`);

        // Show notification banner on the dashboard
        showNotification(`⚡ Donation: ${sats} ${satLabel}${msg}`, 'success');

        // Request fresh dashboard image to show updated donation block
        socket.emit('request_latest_image');
    });

    // ... other socket event handlers ...
}

function attemptReconnect() {
    if (reconnecting) return;
    reconnecting = true;
    if (reconnectTimeout) clearTimeout(reconnectTimeout);
    reconnectTimeout = setTimeout(() => {
        console.log("⚙️ Attempting WebSocket reconnect...");
        if (socket) socket.connect();
        reconnecting = false;
    }, 2000);
}

// Global variables for socket state
const reconnectBtn = document.getElementById('reconnect-button');
let reconnectAttempts = 0;
let lastImageUpdate = null;
let imageUpdateTimeout = null;

// Initial connection
connectSocket();

// Background processing status updates (for instant startup mode)
socket.on('background_ready', (data) => {
    console.log("✅ Background processing completed", data);
    
    // Request fresh image since background processing is done
    console.log("📶 Requesting fresh image after background completion");
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

        // Create close button (optimized for mobile touch targets: 44x44px minimum)
        const closeBtn = document.createElement('button');
        closeBtn.innerHTML = '×';
        closeBtn.setAttribute('aria-label', 'Close notification');
        closeBtn.style.cssText = `
            position: absolute;
            top: 4px;
            right: 8px;
            background: ${closeBtnBg};
            border: none;
            color: ${closeBtnColor};
            font-size: 24px;
            cursor: pointer;
            width: 44px;
            height: 44px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            transition: background-color 0.2s;
            font-weight: bold;
            z-index: 1;
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
        console.log('✅ Updated block notification with enriched data');
        contentDiv.style.transition = 'opacity 0.2s';
        contentDiv.style.opacity = '0.7';
        setTimeout(() => {
            contentDiv.style.opacity = '1';
        }, 100);
    }
}

// New block notification with toast
socket.on('new_block_notification', (data) => {
    console.log("👁️ New block notification received:", data);
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

// Configuration reloaded notification
socket.on('config_reloaded', (data) => {
    console.log("⚙️ Configuration reloaded from file");
    
    // Request fresh image after config change
    setTimeout(() => {
        socket.emit('request_latest_image');
        refreshCurrentImage();
    }, 500);
});

// Enhanced status monitoring
setInterval(() => {
    const now = new Date();
    
    if (!socket.connected) {
        if (reconnectAttempts > 0) {
            console.log(`⚙️ Reconnecting... (${reconnectAttempts})`);
        } else {
            console.log("🔴 WebSocket disconnected");
        }
    } else {
        // Check for stale image data and auto-request if needed
        if (lastImageUpdate) {
            const timeSinceUpdate = Math.floor((now - lastImageUpdate) / 1000);
            if (timeSinceUpdate > 600) { // 10 minutes
                console.log("⚙️ Auto-requesting image update (stale data)");
                socket.emit('request_latest_image');
                refreshCurrentImage();
            }
        }
    }
}, 10000); // Check every 10 seconds

// Manual reconnection button (if connection completely fails)
function forceReconnect() {
    console.log("⚙️ Manual reconnection triggered");
    socket.disconnect();
    setTimeout(() => {
        socket.connect();
    }, 1000);
}

// Force refresh current dashboard image
function refreshCurrentImage() {
    console.log("⚙️ Refreshing current dashboard image");
    const dashboardImg = document.getElementById("dashboard");
    
    if (dashboardImg && dashboardImg.src) {
        const currentSrc = dashboardImg.src;
        
        // Only refresh if src is a valid HTTP/HTTPS URL (not base64 data: or placeholder)
        if (!currentSrc.startsWith('http://') && !currentSrc.startsWith('https://')) {
            console.log("⏭️ Skipping refresh - image is not an HTTP URL");
            return;
        }
        
        const baseUrl = currentSrc.split('?')[0]; // Remove any existing query parameters
        const timestamp = new Date().getTime();
        const newUrl = baseUrl + "?refresh=" + timestamp + "&cache=" + Math.random();
        
        // Create preloader for smooth transition
        const tempImg = new Image();
        tempImg.onload = function() {
            dashboardImg.src = newUrl;
            console.log("✅ Current image refreshed");
        };
        tempImg.onerror = function() {
            console.warn("⚠️ Failed to refresh current image, keeping existing");
        };
        tempImg.src = newUrl;
    }
}

// Request initial image when page loads
document.addEventListener('DOMContentLoaded', async function() {
    console.log("⚙️ Page loaded.");
    
    // Apply dark mode from localStorage or fetch from backend
    const storedDarkMode = localStorage.getItem('mempaper_dark_mode');
    if (storedDarkMode === 'true') {
        document.body.classList.add('dark-mode');
    } else if (storedDarkMode === 'false') {
        document.body.classList.remove('dark-mode');
    } else {
        // No localStorage value - fetch from backend
        try {
            const response = await fetch('/api/config');
            if (response.ok) {
                const data = await response.json();
                if (data.config && data.config.color_mode_dark !== undefined) {
                    const isDarkMode = data.config.color_mode_dark;
                    if (isDarkMode) {
                        document.body.classList.add('dark-mode');
                    }
                    localStorage.setItem('mempaper_dark_mode', isDarkMode ? 'true' : 'false');
                    console.log(`⚙️ Theme loaded from backend: ${isDarkMode ? 'dark' : 'light'}`);
                }
            }
        } catch (error) {
            console.warn('Failed to fetch theme from backend:', error);
        }
    }
    
    const dashboardImg = document.getElementById("dashboard");
    
    // Check if image is already loaded from server-side
    if (dashboardImg.src && !dashboardImg.src.includes('placeholder')) {
        console.log("📸 Image already loaded from server, skipping WebSocket request");
        lastImageUpdate = new Date(); // Set initial timestamp
        return;
    }
    
    // Wait a bit for socket to establish connection
    setTimeout(() => {
        if (socket.connected) {
            console.log("📶 Requesting initial image via WebSocket");
            socket.emit('request_latest_image');
        } else {
            // If not connected yet, try again when connected
            console.log("⏳ Socket not connected, waiting...");
            const checkConnection = setInterval(() => {
                if (socket.connected) {
                    clearInterval(checkConnection);
                    socket.emit('request_latest_image');
                    console.log("� Initial image requested after connection");
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
                    // Show notification if it's recent (within 5 seconds)
                    console.log('⚙️ Received cross-page block notification');
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
    // Always subscribe, mark page type
    console.log('Subscribing to live block notifications for dashboard page...');
    socket.emit('subscribe_block_notifications', { page: 'dashboard' });
}

// Unsubscribe from block notifications
function unsubscribeFromBlockNotifications() {
    console.log('⚙️ Unsubscribing from live block notifications...');
    socket.emit('unsubscribe_block_notifications');
}

// Add event listeners for block notification subscription events
socket.on('block_notification_status', (data) => {
    if (data.status === 'subscribed') {
        blockNotificationsEnabled = true;
        if (data.message) {
            console.log('[MEMPAPER] ' + data.message);
        } else {
            console.log('[MEMPAPER] Subscribed to live block notifications');
        }
    } else if (data.status === 'unsubscribed') {
        blockNotificationsEnabled = false;
        console.log('[MEMPAPER] Unsubscribed from live block notifications');
    }
});

socket.on('block_notification_error', (data) => {
    console.error('[MEMPAPER] Block notification error:', data.error);
});

// Global functions for enabling/disabling block notifications
window.enableBlockNotifications = function() {
    subscribeToBlockNotifications();
};

window.disableBlockNotifications = function() {
    unsubscribeFromBlockNotifications();
};
