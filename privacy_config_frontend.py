#!/usr/bin/env python3
"""
Enhanced Configuration Frontend with Privacy Controls and Dynamic UI Management.
Provides intelligent form controls based on enabled features and privacy settings.
"""

from flask import request, jsonify, render_template_string
from privacy_config_manager import privacy_manager
from typing import Dict, List

def register_privacy_config_routes(app, config_manager):
    """Register privacy-aware configuration routes."""
    
    @app.route('/api/config/privacy-status', methods=['GET'])
    def get_privacy_status():
        """Get current privacy status and recommendations."""
        try:
            config = config_manager.get_config()
            recommendations = privacy_manager.get_configuration_recommendations(config)
            
            return jsonify({
                'success': True,
                'privacy_status': recommendations
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/api/config/validate-mempool', methods=['POST'])
    def validate_mempool():
        """Validate mempool instance configuration."""
        try:
            data = request.get_json()
            mempool_ip = data.get('mempool_ip', '')
            mempool_port = int(data.get('mempool_port', 0))
            
            if not mempool_ip or not mempool_port:
                return jsonify({
                    'success': False,
                    'error': 'Missing mempool IP or port'
                }), 400
            
            validation = privacy_manager.validate_mempool_connection(mempool_ip, mempool_port)
            
            return jsonify({
                'success': True,
                'validation': validation
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/api/config/dynamic-fields', methods=['POST'])
    def get_dynamic_field_states():
        """Get which fields should be enabled/disabled based on current configuration."""
        try:
            data = request.get_json()
            config = data.get('config', {})
            
            # Get disabled features for each block type
            disabled_features = {}
            for block_type in ["btc_price", "bitaxe", "wallet_balances", "display"]:
                disabled_features[block_type] = privacy_manager.get_disabled_features_for_block(block_type, config)
            
            # Get privacy violations
            privacy_violations = privacy_manager.get_privacy_violations(config)
            
            # Build field states
            field_states = {}
            
            # Disable features when their parent blocks are disabled
            for block_type, disabled_fields in disabled_features.items():
                for field in disabled_fields:
                    field_states[field] = {
                        'enabled': False,
                        'reason': f'Disabled because {block_type} block is not enabled',
                        'block_dependency': block_type
                    }
            
            # Disable privacy-sensitive features when using public mempool
            mempool_ip = config.get("mempool_ip", "")
            mempool_port = config.get("mempool_rest_port", 443)
            
            if privacy_manager.is_public_mempool_instance(mempool_ip, mempool_port):
                privacy_sensitive_fields = [
                    'wallet_balance_addresses',
                    'block_reward_addresses_table',
                    'show_wallet_balances_block',
                    'bitaxe_miner_table',
                    'show_bitaxe_block'
                ]
                
                for field in privacy_sensitive_fields:
                    field_states[field] = {
                        'enabled': False,
                        'reason': '🔒 Privacy: Disabled with public mempool instance',
                        'privacy_risk': True
                    }
            
            return jsonify({
                'success': True,
                'field_states': field_states,
                'privacy_violations': privacy_violations
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

# Enhanced configuration page template with privacy controls
ENHANCED_CONFIG_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Configuration - BTC MemPaper</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
        .privacy-status { margin-bottom: 20px; padding: 15px; border-radius: 6px; }
        .privacy-optimal { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
        .privacy-warning { background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; }
        .privacy-danger { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
        .section { margin: 20px 0; padding: 15px; border: 1px solid #e0e0e0; border-radius: 6px; }
        .field-group { margin: 15px 0; }
        .field-disabled { opacity: 0.5; pointer-events: none; position: relative; }
        .field-disabled::after { content: "🔒"; position: absolute; top: 5px; right: 10px; }
        .privacy-violation { background: #f8d7da; padding: 8px; margin: 5px 0; border-radius: 4px; font-size: 12px; }
        .validation-result { margin: 10px 0; padding: 10px; border-radius: 4px; }
        .validation-success { background: #d4edda; color: #155724; }
        .validation-error { background: #f8d7da; color: #721c24; }
        .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; margin: 5px; }
        .btn-primary { background: #007cba; color: white; }
        .btn-warning { background: #ffc107; color: black; }
        .btn-danger { background: #dc3545; color: white; }
        .tooltip { position: relative; display: inline-block; }
        .tooltip .tooltiptext { visibility: hidden; width: 300px; background-color: #555; color: #fff; text-align: center; border-radius: 6px; padding: 5px; position: absolute; z-index: 1; bottom: 125%; left: 50%; margin-left: -150px; opacity: 0; transition: opacity 0.3s; }
        .tooltip:hover .tooltiptext { visibility: visible; opacity: 1; }
        .tabs { border-bottom: 1px solid #e0e0e0; margin-bottom: 20px; }
        .tab { display: inline-block; padding: 10px 20px; cursor: pointer; border-bottom: 2px solid transparent; }
        .tab.active { border-bottom-color: #007cba; color: #007cba; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        
        /* Wallet Entry Styles */
        .wallet-entry { margin-bottom: 10px; padding: 10px; border: 1px solid #e0e0e0; border-radius: 4px; background: #f9f9f9; }
        .wallet-entry-row { display: flex; gap: 10px; align-items: center; }
        .wallet-address-input { flex: 2; padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-family: monospace; }
        .wallet-comment-input { flex: 1.5; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        .wallet-type-select { padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        .add-btn { background: #28a745; color: white; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; margin-top: 10px; }
        .remove-btn { background: #dc3545; color: white; border: none; padding: 6px 10px; border-radius: 4px; cursor: pointer; }
        .add-btn:hover { background: #218838; }
        .remove-btn:hover { background: #c82333; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 Enhanced Configuration</h1>
        
        <div id="privacy-status" class="privacy-status">
            <h3>🔒 Privacy Status</h3>
            <div id="privacy-details">Loading privacy status...</div>
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="showTab('mempool')">Mempool Settings</div>
            <div class="tab" onclick="showTab('blocks')">Info Blocks</div>
            <div class="tab" onclick="showTab('display')">Display Settings</div>
            <div class="tab" onclick="showTab('privacy')">Privacy Controls</div>
        </div>
        
        <div id="mempool-tab" class="tab-content active">
            <div class="section">
                <h3>🌐 Mempool Configuration</h3>
                <div class="field-group">
                    <label>Mempool IP Address:</label>
                    <input type="text" id="mempool_ip" placeholder="192.168.1.100" onchange="validateMempoolConfig()">
                    <div class="tooltip">
                        <span>ℹ️</span>
                        <span class="tooltiptext">IP address or hostname of your local mempool instance. Never use public instances for privacy.</span>
                    </div>
                </div>
                <div class="field-group">
                    <label>REST Port:</label>
                    <input type="number" id="mempool_rest_port" placeholder="4081" onchange="validateMempoolConfig()">
                </div>
                <div class="field-group">
                    <label>WebSocket Port:</label>
                    <input type="number" id="mempool_ws_port" placeholder="8999">
                </div>
                <button class="btn btn-primary" onclick="testMempoolConnection()">🔍 Test Connection</button>
                <div id="mempool-validation" class="validation-result" style="display: none;"></div>
            </div>
        </div>
        
        <div id="blocks-tab" class="tab-content">
            <div class="section">
                <h3>📊 Info Blocks Configuration</h3>
                
                <div class="field-group">
                    <label>
                        <input type="checkbox" id="show_btc_price_block" onchange="updateDynamicFields()"> 
                        Show BTC Price Block
                    </label>
                    <div id="btc-price-fields" class="sub-fields">
                        <div class="field-group">
                            <label>Currency:</label>
                            <select id="btc_price_currency">
                                <option value="USD">USD</option>
                                <option value="EUR">EUR</option>
                            </select>
                        </div>
                    </div>
                </div>
                
                <div class="field-group">
                    <label>
                        <input type="checkbox" id="show_bitaxe_block" onchange="updateDynamicFields()"> 
                        Show Bitaxe Block
                    </label>
                    <div id="bitaxe-fields" class="sub-fields">
                        <!-- Bitaxe miner table will be rendered by the main config system -->
                    </div>
                </div>
                
                <div class="field-group">
                    <label>
                        <input type="checkbox" id="show_wallet_balances_block" onchange="updateDynamicFields()"> 
                        Show Wallet Balances Block
                    </label>
                    <div id="wallet-fields" class="sub-fields">
                        <div class="field-group">
                            <label>Wallet Addresses & XPUBs with Comments:</label>
                            <div id="wallet-entries-container">
                                <!-- Dynamic wallet entries will be added here -->
                            </div>
                            <button type="button" onclick="addWalletEntry()" class="add-btn">➕ Add Address/XPUB</button>
                        </div>
                        <div class="field-group">
                            <label>XPUB Derivation Count:</label>
                            <input type="number" id="xpub_derivation_count" min="10" max="200" value="20">
                            <div class="tooltip">
                                <span>ℹ️</span>
                                <span class="tooltiptext">Initial number of addresses to derive from each XPUB/ZPUB key.</span>
                            </div>
                        </div>
                        <div class="field-group">
                            <label>
                                <input type="checkbox" id="xpub_enable_gap_limit"> 
                                Enable Gap Limit Detection
                            </label>
                            <div class="tooltip">
                                <span>ℹ️</span>
                                <span class="tooltiptext">Automatically derive more addresses when recent addresses show usage (BIP-44 standard).</span>
                            </div>
                        </div>
                        <div class="field-group">
                            <label>Gap Limit (addresses to check):</label>
                            <input type="number" id="xpub_gap_limit" min="5" max="50" value="20">
                            <div class="tooltip">
                                <span>ℹ️</span>
                                <span class="tooltiptext">Number of recent addresses to check for usage. BIP-44 standard is 20.</span>
                            </div>
                        </div>
                        <div class="field-group">
                            <label>Derivation Increment:</label>
                            <input type="number" id="xpub_derivation_increment" min="5" max="50" value="20">
                            <div class="tooltip">
                                <span>ℹ️</span>
                                <span class="tooltiptext">Number of additional addresses to derive when gap limit triggers.</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="display-tab" class="tab-content">
            <div class="section">
                <h3>🖥️ Display Settings</h3>
                
                <div class="field-group">
                    <label>
                        <input type="checkbox" id="e-ink-display-connected" onchange="updateDynamicFields()"> 
                        E-ink Display Connected
                    </label>
                </div>
                
                <div id="display-fields" class="sub-fields">
                    <div class="field-group">
                        <label>Display Width:</label>
                        <input type="number" id="display_width" value="800">
                    </div>
                    <div class="field-group">
                        <label>Display Height:</label>
                        <input type="number" id="display_height" value="480">
                    </div>
                    <div class="field-group">
                        <label>Device Name:</label>
                        <input type="text" id="omni_device_name" placeholder="waveshare_epd.epd7in3f">
                    </div>
                </div>
            </div>
        </div>
        
        <div id="privacy-tab" class="tab-content">
            <div class="section">
                <h3>🔒 Privacy Controls</h3>
                <div id="privacy-recommendations">
                    <p>Loading privacy recommendations...</p>
                </div>
                <div id="privacy-violations"></div>
                
                <button class="btn btn-warning" onclick="analyzePrivacyRisks()">🔍 Analyze Privacy Risks</button>
                <button class="btn btn-primary" onclick="applyPrivacyOptimizations()">🛡️ Apply Privacy Optimizations</button>
            </div>
        </div>
        
        <div class="section">
            <button class="btn btn-primary" onclick="saveConfiguration()">💾 Save Configuration</button>
            <button class="btn btn-warning" onclick="resetToDefaults()">🔄 Reset to Defaults</button>
        </div>
    </div>

    <script>
        let currentConfig = {};
        let fieldStates = {};
        
        // Load initial data
        window.onload = function() {
            loadConfiguration();
            loadPrivacyStatus();
        };
        
        function showTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            
            // Show selected tab
            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
        }
        
        async function loadConfiguration() {
            try {
                const response = await fetch('/api/config');
                const data = await response.json();
                
                if (data.success) {
                    currentConfig = data.config;
                    populateForm(data.config);
                    updateDynamicFields();
                }
            } catch (error) {
                console.error('Failed to load configuration:', error);
            }
        }
        
        async function loadPrivacyStatus() {
            try {
                const response = await fetch('/api/config/privacy-status');
                const data = await response.json();
                
                if (data.success) {
                    displayPrivacyStatus(data.privacy_status);
                }
            } catch (error) {
                console.error('Failed to load privacy status:', error);
            }
        }
        
        function displayPrivacyStatus(status) {
            const statusDiv = document.getElementById('privacy-status');
            const detailsDiv = document.getElementById('privacy-details');
            
            let statusClass = 'privacy-optimal';
            let statusIcon = '✅';
            
            if (status.status === 'ERROR') {
                statusClass = 'privacy-danger';
                statusIcon = '❌';
            } else if (status.status === 'PRIVACY_RISK') {
                statusClass = 'privacy-danger';
                statusIcon = '🔴';
            } else if (status.status === 'PUBLIC_MEMPOOL') {
                statusClass = 'privacy-warning';
                statusIcon = '⚠️';
            }
            
            statusDiv.className = `privacy-status ${statusClass}`;
            
            let html = `
                <h4>${statusIcon} Privacy Score: ${status.privacy_score}/100</h4>
                <p><strong>Status:</strong> ${status.status}</p>
            `;
            
            if (status.recommendations.length > 0) {
                html += '<p><strong>Recommendations:</strong></p><ul>';
                status.recommendations.forEach(rec => {
                    html += `<li>${rec}</li>`;
                });
                html += '</ul>';
            }
            
            detailsDiv.innerHTML = html;
            
            // Update privacy recommendations tab
            const recDiv = document.getElementById('privacy-recommendations');
            recDiv.innerHTML = html;
            
            // Display privacy violations
            if (status.privacy_violations.length > 0) {
                const violationsDiv = document.getElementById('privacy-violations');
                let violationsHtml = '<h4>🚨 Privacy Violations:</h4>';
                
                status.privacy_violations.forEach(violation => {
                    violationsHtml += `
                        <div class="privacy-violation">
                            <strong>${violation.category.toUpperCase()}</strong>: ${violation.message}<br>
                            <em>Recommendation: ${violation.recommendation}</em>
                        </div>
                    `;
                });
                
                violationsDiv.innerHTML = violationsHtml;
            }
        }
        
        async function updateDynamicFields() {
            try {
                const config = getCurrentFormData();
                
                const response = await fetch('/api/config/dynamic-fields', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config: config })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    fieldStates = data.field_states;
                    applyFieldStates();
                }
            } catch (error) {
                console.error('Failed to update dynamic fields:', error);
            }
        }
        
        function applyFieldStates() {
            Object.keys(fieldStates).forEach(fieldId => {
                const element = document.getElementById(fieldId);
                const state = fieldStates[fieldId];
                
                if (element) {
                    const fieldGroup = element.closest('.field-group');
                    
                    if (state.enabled === false) {
                        if (fieldGroup) {
                            fieldGroup.classList.add('field-disabled');
                            fieldGroup.title = state.reason;
                        }
                        element.disabled = true;
                    } else {
                        if (fieldGroup) {
                            fieldGroup.classList.remove('field-disabled');
                            fieldGroup.title = '';
                        }
                        element.disabled = false;
                    }
                }
            });
            
            // Handle sub-field visibility
            updateSubFieldVisibility();
        }
        
        function updateSubFieldVisibility() {
            const blockTypes = ['btc-price', 'bitaxe', 'wallet', 'display'];
            
            blockTypes.forEach(type => {
                const checkbox = document.getElementById(`show_${type.replace('-', '_')}_block`) || 
                                document.getElementById('e-ink-display-connected');
                const fields = document.getElementById(`${type}-fields`);
                
                if (checkbox && fields) {
                    fields.style.display = checkbox.checked ? 'block' : 'none';
                }
            });
        }
        
        function getCurrentFormData() {
            const form = {};
            
            // Get all form inputs
            document.querySelectorAll('input, select, textarea').forEach(element => {
                if (element.type === 'checkbox') {
                    form[element.id] = element.checked;
                } else if (element.type === 'number') {
                    form[element.id] = parseInt(element.value) || 0;
                } else {
                    form[element.id] = element.value;
                }
            });
            
            // Add wallet entries with comments
            form.wallet_balance_addresses_with_comments = getWalletEntriesData();
            
            return form;
        }
        
        function populateForm(config) {
            Object.keys(config).forEach(key => {
                const element = document.getElementById(key);
                if (element) {
                    if (element.type === 'checkbox') {
                        element.checked = config[key];
                    } else if (Array.isArray(config[key])) {
                        element.value = config[key].join('\\n');
                    } else {
                        element.value = config[key];
                    }
                }
            });
            
            // Load wallet entries with comments
            loadWalletEntries(config);
        }
        
        async function validateMempoolConfig() {
            const ip = document.getElementById('mempool_ip').value;
            const port = document.getElementById('mempool_rest_port').value;
            
            if (!ip || !port) return;
            
            try {
                const response = await fetch('/api/config/validate-mempool', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ mempool_ip: ip, mempool_port: parseInt(port) })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    displayMempoolValidation(data.validation);
                }
            } catch (error) {
                console.error('Mempool validation failed:', error);
            }
        }
        
        function displayMempoolValidation(validation) {
            const div = document.getElementById('mempool-validation');
            div.style.display = 'block';
            
            if (validation.is_valid_mempool) {
                div.className = 'validation-result validation-success';
                div.innerHTML = `✅ Valid mempool instance (${validation.response_time}ms)`;
            } else {
                div.className = 'validation-result validation-error';
                div.innerHTML = `❌ ${validation.error || 'Invalid mempool instance'}`;
            }
            
            if (validation.is_public) {
                div.innerHTML += '<br>🔒 Warning: This appears to be a public instance!';
            }
        }
        
        async function testMempoolConnection() {
            await validateMempoolConfig();
        }
        
        async function analyzePrivacyRisks() {
            await loadPrivacyStatus();
        }
        
        async function applyPrivacyOptimizations() {
            // Auto-disable privacy-sensitive features when using public mempool
            const config = getCurrentFormData();
            
            if (fieldStates) {
                Object.keys(fieldStates).forEach(fieldId => {
                    const state = fieldStates[fieldId];
                    if (state.privacy_risk) {
                        const element = document.getElementById(fieldId);
                        if (element && element.type === 'checkbox') {
                            element.checked = false;
                        }
                    }
                });
            }
            
            alert('🛡️ Privacy optimizations applied! Privacy-sensitive features have been disabled.');
            updateDynamicFields();
        }
        
        async function saveConfiguration() {
            const config = getCurrentFormData();
            
            try {
                const response = await fetch('/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                
                const data = await response.json();
                
                if (data.success) {
                    alert('✅ Configuration saved successfully!');
                    loadPrivacyStatus(); // Refresh privacy status
                } else {
                    alert('❌ Failed to save configuration: ' + data.error);
                }
            } catch (error) {
                alert('❌ Error saving configuration: ' + error.message);
            }
        }
        
        // Wallet entry management functions
        let walletEntryCount = 0;
        
        function addWalletEntry(address = '', comment = '', type = 'address') {
            const container = document.getElementById('wallet-entries-container');
            const entryId = `wallet-entry-${walletEntryCount++}`;
            
            const entryDiv = document.createElement('div');
            entryDiv.className = 'wallet-entry';
            entryDiv.id = entryId;
            entryDiv.innerHTML = `
                <div class="wallet-entry-row">
                    <input type="text" 
                           placeholder="Address or XPUB/ZPUB key" 
                           class="wallet-address-input" 
                           value="${address}"
                           onchange="detectWalletType(this)">
                    <input type="text" 
                           placeholder="Comment (e.g., Hardware Wallet, Cold Storage)" 
                           class="wallet-comment-input" 
                           value="${comment}">
                    <select class="wallet-type-select">
                        <option value="address" ${type === 'address' ? 'selected' : ''}>Address</option>
                        <option value="xpub" ${type === 'xpub' ? 'selected' : ''}>XPUB/ZPUB</option>
                    </select>
                    <button type="button" onclick="removeWalletEntry('${entryId}')" class="remove-btn">🗑️</button>
                </div>
            `;
            
            container.appendChild(entryDiv);
        }
        
        function removeWalletEntry(entryId) {
            const entry = document.getElementById(entryId);
            if (entry) {
                entry.remove();
            }
        }
        
        function detectWalletType(input) {
            const value = input.value.toLowerCase();
            const typeSelect = input.parentElement.querySelector('.wallet-type-select');
            
            if (value.startsWith('xpub') || value.startsWith('zpub') || value.startsWith('ypub')) {
                typeSelect.value = 'xpub';
            } else if (value.startsWith('bc1') || value.startsWith('1') || value.startsWith('3')) {
                typeSelect.value = 'address';
            }
        }
        
        function loadWalletEntries(config) {
            const container = document.getElementById('wallet-entries-container');
            container.innerHTML = '';
            
            // Load from new format first
            const entriesWithComments = config.wallet_balance_addresses_with_comments || [];
            if (entriesWithComments.length > 0) {
                entriesWithComments.forEach(entry => {
                    if (typeof entry === 'object' && entry.address) {
                        addWalletEntry(entry.address, entry.comment || '', entry.type || 'address');
                    }
                });
            } else {
                // Fallback to old format
                const oldEntries = config.wallet_balance_addresses || [];
                oldEntries.forEach(address => {
                    const type = address.toLowerCase().startsWith('xpub') || address.toLowerCase().startsWith('zpub') ? 'xpub' : 'address';
                    addWalletEntry(address, `Imported ${type}`, type);
                });
            }
            
            // Always have at least one empty entry
            if (walletEntryCount === 0) {
                addWalletEntry();
            }
        }
        
        function getWalletEntriesData() {
            const entries = [];
            const walletEntries = document.querySelectorAll('.wallet-entry');
            
            walletEntries.forEach(entry => {
                const addressInput = entry.querySelector('.wallet-address-input');
                const commentInput = entry.querySelector('.wallet-comment-input');
                const typeSelect = entry.querySelector('.wallet-type-select');
                
                const address = addressInput.value.trim();
                const comment = commentInput.value.trim();
                const type = typeSelect.value;
                
                if (address) {
                    entries.push({
                        address: address,
                        comment: comment || (type === 'xpub' ? 'Hardware Wallet' : 'Address'),
                        type: type
                    });
                }
            });
            
            return entries;
        }
        
        async function resetToDefaults() {
            if (confirm('Are you sure you want to reset to default configuration?')) {
                try {
                    const response = await fetch('/api/config/reset', { method: 'POST' });
                    const data = await response.json();
                    
                    if (data.success) {
                        alert('🔄 Configuration reset to defaults!');
                        location.reload();
                    }
                } catch (error) {
                    alert('❌ Error resetting configuration: ' + error.message);
                }
            }
        }
    </script>
</body>
</html>
"""

def get_enhanced_config_page():
    """Return enhanced configuration page HTML."""
    return ENHANCED_CONFIG_TEMPLATE
