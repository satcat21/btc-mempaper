#!/usr/bin/env python3
"""
Display Mode Switcher

Utility script to easily switch between e-Paper display enabled/disabled modes.
Useful for testing and development.
"""

import json
import os
import sys
import shutil

def load_config():
    """Load current configuration."""
    try:
        with open("config.json") as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ config.json not found")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config.json: {e}")
        return None

def save_config(config):
    """Save configuration to file."""
    try:
        with open("config.json", "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving config: {e}")
        return False

def backup_config():
    """Create backup of current config."""
    if os.path.exists("config.json"):
        shutil.copy("config.json", "config.json.backup")
        print("💾 Backup created: config.json.backup")

def show_status(config):
    """Show current display status."""
    if not config:
        return
    
    display_enabled = config.get("e-ink-display-connected", True)
    status = "ENABLED" if display_enabled else "DISABLED"
    icon = "🖥️" if display_enabled else "🚫"
    
    print(f"\n{icon} Current e-Paper Display Status: {status}")
    
    if display_enabled:
        print("  - Hardware display updates: ON")
        print("  - Display scripts will be called")
        print("  - Requires omni-epd library")
    else:
        print("  - Hardware display updates: OFF")
        print("  - Display-less mode active")
        print("  - No hardware libraries required")

def toggle_display(config):
    """Toggle display mode."""
    if not config:
        return False
    
    current = config.get("e-ink-display-connected", True)
    new_value = not current
    
    config["e-ink-display-connected"] = new_value
    
    if save_config(config):
        old_status = "enabled" if current else "disabled"
        new_status = "enabled" if new_value else "disabled"
        print(f"✅ Display mode changed: {old_status} → {new_status}")
        return True
    
    return False

def set_display_mode(config, enabled):
    """Set specific display mode."""
    if not config:
        return False
    
    config["e-ink-display-connected"] = enabled
    
    if save_config(config):
        status = "enabled" if enabled else "disabled"
        print(f"✅ Display mode set to: {status}")
        return True
    
    return False

def main():
    """Main function."""
    print("🔧 Mempaper Display Mode Switcher")
    print("=" * 40)
    
    # Check command line arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        
        config = load_config()
        if not config:
            sys.exit(1)
        
        backup_config()
        
        if arg in ["on", "enable", "enabled", "true"]:
            set_display_mode(config, True)
        elif arg in ["off", "disable", "disabled", "false"]:
            set_display_mode(config, False)
        elif arg in ["toggle", "switch"]:
            toggle_display(config)
        elif arg in ["status", "show"]:
            show_status(config)
            sys.exit(0)
        else:
            print(f"❌ Unknown argument: {arg}")
            print("Usage: python switch_display.py [on|off|toggle|status]")
            sys.exit(1)
        
        # Show new status
        updated_config = load_config()
        show_status(updated_config)
        
        print("\n🔄 Restart the application for changes to take effect:")
        print("   python serve.py")
        
    else:
        # Interactive mode
        config = load_config()
        if not config:
            sys.exit(1)
        
        show_status(config)
        
        print("\nOptions:")
        print("  1. Toggle display mode")
        print("  2. Enable e-Paper display")
        print("  3. Disable e-Paper display")
        print("  4. Show current status")
        print("  5. Exit")
        
        try:
            choice = input("\nSelect option (1-5): ").strip()
            
            if choice == "1":
                backup_config()
                toggle_display(config)
            elif choice == "2":
                backup_config()
                set_display_mode(config, True)
            elif choice == "3":
                backup_config()
                set_display_mode(config, False)
            elif choice == "4":
                show_status(config)
            elif choice == "5":
                print("👋 Goodbye!")
                sys.exit(0)
            else:
                print("❌ Invalid choice")
                sys.exit(1)
            
            # Show updated status
            updated_config = load_config()
            show_status(updated_config)
            
            print("\n🔄 Restart the application for changes to take effect:")
            print("   python serve.py")
            
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
