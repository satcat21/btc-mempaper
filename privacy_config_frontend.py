#!/usr/bin/env python3
"""
Simple Local Mempool Configuration Frontend.
Provides basic mempool validation for local instances only.
"""

from flask import request, jsonify
from privacy_config_manager import LocalMempoolManager

mempool_manager = LocalMempoolManager()

def register_mempool_config_routes(app, config_manager):
    """Register simple mempool configuration routes."""
    
    @app.route('/api/config/mempool-status', methods=['GET'])
    def get_mempool_status():
        """Get current mempool status."""
        try:
            config = config_manager.get_config()
            status = mempool_manager.get_mempool_status(config)
            
            return jsonify({
                'success': True,
                'mempool_status': status
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
            
            validation = mempool_manager.validate_mempool_instance(mempool_ip, mempool_port)
            
            return jsonify({
                'success': True,
                'validation': validation
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
