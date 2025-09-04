const socket = io({
    // Transport configuration - polling only to match server
    transports: ['polling'],                // Match server polling-only configuration
    upgrade: false,                         // Disable transport upgrades
    rememberUpgrade: false,                 // Don't remember upgrades
    
    // Connection settings
    autoConnect: true,
    forceNew: false,                        // Reuse connections when possible
    timeout: 20000,                         // Increased timeout for initial connection
    
    // Reconnection settings
    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,        // Start with 1 second
    reconnectionDelayMax: 30000,    // Max 30 seconds between attempts
    
    // CORS and compatibility
    withCredentials: false,         // Disable credentials
    
    // Polling-specific settings for initial connection
    pollingTimeout: 30000
});

const statusEl = null; // WebSocket status element removed from UI
const reconnectBtn = document.getElementById('reconnect-button');
let reconnectAttempts = 0;
let lastImageUpdate = null;
let imageUpdateTimeout = null; // For debouncing image updates

// Connection successful
socket.on('connect', () => {
    console.log("✅ Connected to Mempaper WebSocket");
    reconnectAttempts = 0; // Reset counter
    if (statusEl) {
        statusEl.textContent = "🟢 " + window.translations.websocket_connected;
        statusEl.className = "status-item status-connected";
    }
    reconnectBtn.style.display = "none"; // Hide reconnect button
    
    // Only request latest image if we don't have one loaded yet
    const dashboardImg = document.getElementById("dashboard");
    if (!dashboardImg.src || dashboardImg.src.includes('placeholder') || dashboardImg.src === window.location.href) {
        console.log("📱 Requesting latest image (no current image or placeholder)");
        socket.emit('request_latest_image');
    } else {
        console.log("📸 Valid image already loaded, skipping automatic request");
        console.log("   Current src length:", dashboardImg.src.length);
    }
});

// Connection lost
socket.on('disconnect', (reason) => {
    console.log("❌ Disconnected from Mempaper WebSocket:", reason);
    if (statusEl) {
        statusEl.textContent = "🔴 " + window.translations.websocket_disconnected;
        statusEl.className = "status-item status-disconnected";
    }
});

// Connection errors
socket.on('connect_error', (error) => {
    console.error("🚫 Socket.IO connection error:", error);
    if (statusEl) {
        statusEl.textContent = "🚫 Connection failed";
        statusEl.className = "status-item status-error";
    }
});

// Transport errors
socket.on('error', (error) => {
    console.error("⚠️ Socket.IO transport error:", error);
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
    console.log("🔄 Engine transport upgraded to:", socket.io.engine.transport.name);
});

socket.io.engine.on('upgradeError', (error) => {
    console.warn("⚠️ Engine upgrade error:", error);
});

// Reconnection attempt
socket.on('reconnect_attempt', (attemptNumber) => {
    reconnectAttempts = attemptNumber;
    console.log(`🔄 Reconnection attempt ${attemptNumber}...`);
    if (statusEl) {
        statusEl.textContent = `🔄 Reconnecting... (${attemptNumber})`;
        statusEl.className = "status-item status-reconnecting";
    }
    
    // Show manual reconnect button after several failed attempts
    if (attemptNumber > 5) {
        reconnectBtn.style.display = "inline-block";
    }
});

// Reconnection successful
socket.on('reconnect', (attemptNumber) => {
    console.log(`✅ Reconnected after ${attemptNumber} attempts`);
    if (statusEl) {
        statusEl.textContent = "🟢 " + window.translations.websocket_connected + ` (reconnected)`;
        statusEl.className = "status-item status-connected";
    }
    reconnectAttempts = 0;
    reconnectBtn.style.display = "none"; // Hide reconnect button
});

// Reconnection failed
socket.on('reconnect_failed', () => {
    console.log("❌ Reconnection failed permanently");
    if (statusEl) {
        statusEl.textContent = "❌ Connection failed - refresh page";
        statusEl.className = "status-item status-error";
    }
    reconnectBtn.style.display = "inline-block"; // Show reconnect button
});

// Connection error
socket.on('connect_error', (error) => {
    console.log("🚨 Connection error:", error.message);
    if (statusEl) {
        statusEl.textContent = `🚨 Connection error: ${error.message}`;
        statusEl.className = "status-item status-error";
    }
});

// New image received
socket.on('new_image', (data) => {
    console.log("📱 New dashboard image received", {
        hasImageData: !!data.image,
        imageLength: data.image ? data.image.length : 0,
        timestamp: new Date().toISOString()
    });
    
    // Validate image data
    if (!data.image || !data.image.startsWith('data:image/png;base64,') || data.image.length < 100) {
        console.error("❌ Invalid image data received", data);
        return; // Don't try to load invalid data
    }
    
    const dashboardImg = document.getElementById("dashboard");
    const timestamp = new Date().getTime();
    
    // Use the image data directly (it's already a data URL)
    const imageUrl = data.image;
    
    // Create a new image element to preload and ensure loading
    const tempImg = new Image();
    tempImg.onload = function() {
        // Once loaded, update the main image
        dashboardImg.src = imageUrl;
        lastImageUpdate = new Date();
        if (statusEl) {
            statusEl.textContent = "✨ " + window.translations.updated + ": " + lastImageUpdate.toLocaleTimeString();
            statusEl.className = "status-item status-connected";
        }
        console.log("✅ Dashboard image updated successfully", {
            newSrcLength: dashboardImg.src.length,
            timestamp: lastImageUpdate.toISOString()
        });
    };
    
    tempImg.onerror = function() {
        console.error("❌ Failed to load new dashboard image", {
            imageDataStart: data.image.substring(0, 100) + "...",
            imageDataLength: data.image.length,
            error: "Image load failed"
        });
        if (statusEl) {
            statusEl.textContent = "⚠️ Failed to load new image";
            statusEl.className = "status-item status-warning";
        }
        
        // Don't try fallback with invalid data
        console.log("� Skipping fallback due to invalid image data");
    };
    
    // Start loading the new image
    tempImg.src = imageUrl;
});

// Background processing status updates (for instant startup mode)
socket.on('background_ready', (data) => {
    console.log("🚀 Background processing completed", data);
    
    // Update status to show background processing is complete
    if (statusEl && (statusEl.textContent.includes('Loading') || statusEl.textContent.includes('background'))) {
        statusEl.textContent = "✅ " + (window.translations.background_ready || "Background loading complete");
        statusEl.className = "status-item status-connected";
    }
    
    // Request fresh image since background processing is done
    console.log("📱 Requesting fresh image after background completion");
    socket.emit('request_latest_image');
    
    // Show a brief notification
    showNotification("Background processing complete!", "success");
});

socket.on('background_error', (data) => {
    console.warn("⚠️ Background processing error", data);
    if (statusEl) {
        statusEl.textContent = "⚠️ " + (window.translations.background_error || "Background loading failed");
        statusEl.className = "status-item status-warning";
    }
    
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
        success: 'background-color: #28a745;',
        error: 'background-color: #dc3545;',
        warning: 'background-color: #ffc107; color: black;',
        info: 'background-color: #17a2b8;'
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

// Configuration reloaded notification
socket.on('config_reloaded', (data) => {
    console.log("⚙️ Configuration reloaded from file");
    
    // Show temporary notification
    const originalText = statusEl.textContent;
    const originalClass = statusEl.className;
    
    statusEl.textContent = "⚙️ Configuration reloaded";
    statusEl.className = "status-item status-config-reload";
    
    // Request fresh image after config change
    setTimeout(() => {
        socket.emit('request_latest_image');
        refreshCurrentImage();
    }, 500);
    
    // Restore original status after 3 seconds
    setTimeout(() => {
        if (lastImageUpdate) {
            statusEl.textContent = "✨ " + window.translations.updated + ": " + lastImageUpdate.toLocaleTimeString();
        } else {
            statusEl.textContent = originalText;
        }
        statusEl.className = originalClass;
    }, 3000);
});

// Enhanced status monitoring
setInterval(() => {
    const now = new Date();
    
    if (!socket.connected) {
        if (reconnectAttempts > 0) {
            statusEl.textContent = `� Reconnecting... (${reconnectAttempts})`;
        } else {
            statusEl.textContent = "🔴 " + window.translations.websocket_disconnected;
        }
        statusEl.className = "status-item status-disconnected";
    } else {
        // Show last update time if available
        if (lastImageUpdate) {
            const timeSinceUpdate = Math.floor((now - lastImageUpdate) / 1000);
            if (timeSinceUpdate > 300) { // 5 minutes
                statusEl.textContent = `🟡 Last update: ${Math.floor(timeSinceUpdate/60)}min ago`;
                statusEl.className = "status-item status-warning";
                
                // Auto-request new image if too old
                if (timeSinceUpdate > 600) { // 10 minutes
                    console.log("🔄 Auto-requesting image update (stale data)");
                    socket.emit('request_latest_image');
                    refreshCurrentImage();
                }
            }
        }
    }
}, 10000); // Check every 10 seconds

// Manual reconnection button (if connection completely fails)
function forceReconnect() {
    console.log("🔄 Manual reconnection triggered");
    socket.disconnect();
    setTimeout(() => {
        socket.connect();
    }, 1000);
}

// Force refresh current dashboard image
function refreshCurrentImage() {
    console.log("🔄 Refreshing current dashboard image");
    const dashboardImg = document.getElementById("dashboard");
    
    if (dashboardImg && dashboardImg.src) {
        const currentSrc = dashboardImg.src;
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
document.addEventListener('DOMContentLoaded', function() {
    console.log("📄 Page loaded - checking if image request needed");
    
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
            console.log("📱 Requesting initial image via WebSocket");
            socket.emit('request_latest_image');
        } else {
            // If not connected yet, try again when connected
            console.log("⏳ Socket not connected, waiting...");
            const checkConnection = setInterval(() => {
                if (socket.connected) {
                    clearInterval(checkConnection);
                    socket.emit('request_latest_image');
                    console.log("📄 Initial image requested after connection");
                }
            }, 500);
            
            // Stop checking after 10 seconds
            setTimeout(() => clearInterval(checkConnection), 10000);
        }
    }, 1000);
});

// Console Logging functionality
let consoleLoggingEnabled = false;

// Add event listeners for console log events
socket.on('console_logs', (data) => {
    if (consoleLoggingEnabled && data.logs && Array.isArray(data.logs)) {
        data.logs.forEach(logEntry => {
            try {
                const { level, msg, timestamp } = logEntry;
                const formattedMsg = `[${timestamp}] ${msg}`;
                
                // Output to browser console with appropriate level
                switch (level.toLowerCase()) {
                    case 'error':
                        console.error(`🔴 [MEMPAPER] ${formattedMsg}`);
                        break;
                    case 'warning':
                    case 'warn':
                        console.warn(`🟡 [MEMPAPER] ${formattedMsg}`);
                        break;
                    case 'info':
                        console.info(`🔵 [MEMPAPER] ${formattedMsg}`);
                        break;
                    case 'debug':
                        console.debug(`⚪ [MEMPAPER] ${formattedMsg}`);
                        break;
                    default:
                        console.log(`🟢 [MEMPAPER] ${formattedMsg}`);
                }
            } catch (e) {
                console.error('Error processing log entry:', e, logEntry);
            }
        });
    }
});

socket.on('console_log_status', (data) => {
    if (data.status === 'enabled') {
        consoleLoggingEnabled = true;
        if (data.message) {
            console.log('🟢 [MEMPAPER] ' + data.message);
        } else {
            console.log('🟢 [MEMPAPER] Console log streaming enabled');
        }
    } else if (data.status === 'disabled') {
        consoleLoggingEnabled = false;
        console.log('🔴 [MEMPAPER] Console log streaming disabled');
    }
});

socket.on('console_log_enabled', (data) => {
    consoleLoggingEnabled = true;
    console.log('🟢 [MEMPAPER] ' + data.message);
});

socket.on('console_log_error', (data) => {
    console.error('❌ [MEMPAPER] Console log error:', data.error);
});

// Global functions for enabling/disabling console logs
window.enableMempaperLogs = function() {
    console.log('🔌 [MEMPAPER] Requesting console log streaming...');
    socket.emit('enable_console_logs');
};

window.disableMempaperLogs = function() {
    console.log('🔌 [MEMPAPER] Disabling console log streaming...');
    socket.emit('disable_console_logs');
};

// Display instructions for console logging
if (typeof window !== 'undefined') {
    console.log('%c🎯 MEMPAPER CONSOLE LOGGING', 'color: #ff6b35; font-size: 16px; font-weight: bold;');
    console.log('%cConsole logging is automatic when enabled in Settings', 'color: #4ecdc4; font-weight: bold;');
    console.log('%cManual controls: enableMempaperLogs() / disableMempaperLogs()', 'color: #4ecdc4; font-weight: bold;');
    console.log('%cNote: Enable "Browser Console Logging" in Settings page', 'color: #ffd93d;');
}
