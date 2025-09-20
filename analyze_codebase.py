#!/usr/bin/env python3
"""
Codebase Analysis Script
Analyzes all Python files to determine production usage and cleanup opportunities.
"""

import os
import ast
import importlib.util
import sys
from pathlib import Path

def analyze_file_imports(file_path):
    """Extract all imports from a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append(name.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        
        return imports
    except Exception as e:
        print(f"Error analyzing {file_path}: {e}")
        return []

def find_python_files(directory):
    """Find all Python files in directory."""
    python_files = []
    for root, dirs, files in os.walk(directory):
        # Skip common directories
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv', 'venv', 'node_modules']]
        
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    return python_files

def main():
    base_dir = r"c:\Users\scheibs\Documents\Sebastian\btc-mempaper"
    
    # Core production files (entry points and main modules)
    production_files = set([
        "mempaper_app.py",
        "wsgi.py", 
        "mempool_api.py",
        "websocket_client.py",
        "image_renderer.py",
        "config_manager.py",
        "auth_manager.py",
        "security_config.py",
        "technical_config.py",
        "translations.py",
        "btc_price_api.py",
        "wallet_balance_api.py",
        "bitaxe_api.py",
        "address_derivation.py",
        "block_monitor.py"
    ])
    
    # Find all Python files
    all_files = find_python_files(base_dir)
    
    # Categorize files
    print("🔍 CODEBASE ANALYSIS")
    print("=" * 50)
    
    for file_path in sorted(all_files):
        filename = os.path.basename(file_path)
        rel_path = os.path.relpath(file_path, base_dir)
        
        # Skip files in subdirectories for now
        if os.path.dirname(rel_path):
            continue
            
        print(f"\n📄 {filename}")
        
        # Check if it's a known production file
        if filename in production_files:
            print("   ✅ PRODUCTION - Core application file")
        elif filename.startswith('test_'):
            print("   🧪 TEST - Test file (can be removed)")
        elif filename.startswith('debug_'):
            print("   🐛 DEBUG - Debug file (can be removed)")
        elif filename.startswith('dev_'):
            print("   🔧 DEVELOPMENT - Development file (can be removed)")
        elif filename.startswith('diagnose_'):
            print("   🩺 DIAGNOSTIC - Diagnostic file (can be removed)")
        elif filename.startswith('deploy_'):
            print("   🚀 DEPLOYMENT - Deployment script (can be removed)")
        elif filename.startswith('migrate_'):
            print("   📦 MIGRATION - Migration script (can be removed)")
        elif filename.startswith('setup_'):
            print("   ⚙️ SETUP - Setup script (can be removed)")
        elif filename.startswith('analyze_'):
            print("   📊 ANALYSIS - Analysis script (can be removed)")
        elif filename.startswith('check_'):
            print("   ✅ CHECK - Check script (can be removed)")
        elif filename.startswith('clear_'):
            print("   🧹 CLEANUP - Cleanup script (can be removed)")
        elif filename.startswith('fix_'):
            print("   🔧 FIX - Fix script (can be removed)")
        elif filename.startswith('quick_'):
            print("   ⚡ QUICK - Quick test script (can be removed)")
        elif filename.startswith('mock_'):
            print("   🎭 MOCK - Mock/test file (can be removed)")
        elif 'config' in filename and ('cli' in filename or 'manual' in filename):
            print("   ⚙️ CONFIG UTILITY - Configuration utility (keep if needed)")
        else:
            print("   ❓ UNKNOWN - Needs investigation")

if __name__ == "__main__":
    main()
