#!/usr/bin/env python3
"""
Display Device Configuration Helper

Utility script to set up different e-Paper display devices.
Shows available device types and updates configuration accordingly.
"""

import json
import os
import sys

# Common device configurations with typical display dimensions
DEVICE_CONFIGS = {
    "waveshare_epd.epd7in3f": {
        "name": "Waveshare 7.3\" 7-color",
        "width": 800,
        "height": 480,
        "description": "Large 7.3 inch display with 7-color support"
    },
    "waveshare_epd.epd5in83_v2": {
        "name": "Waveshare 5.83\" V2",
        "width": 648,
        "height": 480,
        "description": "Medium sized black/white display"
    },
    "waveshare_epd.epd4in2": {
        "name": "Waveshare 4.2\"",
        "width": 400,
        "height": 300,
        "description": "Popular 4.2 inch black/white display"
    },
    "waveshare_epd.epd2in7": {
        "name": "Waveshare 2.7\"",
        "width": 264,
        "height": 176,
        "description": "Compact black/white display"
    },
    "inky.impression": {
        "name": "Inky Impression 7-color",
        "width": 448,
        "height": 600,
        "description": "Pimoroni 7-color e-ink display"
    },
    "inky.auto": {
        "name": "Inky Auto-detect",
        "width": 400,
        "height": 300,
        "description": "Auto-detect connected Inky display"
    },
    "omni_epd.mock": {
        "name": "Mock Display (Testing)",
        "width": 800,
        "height": 600,
        "description": "Virtual display for testing (no hardware)"
    }
}

def load_config():
    """Load current configuration."""
    try:
        with open("config/config.json") as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ config/config.json not found")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in config/config.json: {e}")
        return None

def save_config(config):
    """Save configuration to file."""
    try:
        with open("config/config.json", "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving config: {e}")
        return False

def show_current_device(config):
    """Show current device configuration."""
    if not config:
        return
    
    device_name = config.get("omni_device_name", "waveshare_epd.epd7in3f")
    display_enabled = config.get("e-ink-display-connected", True)
    width = config.get("display_width", 800)
    height = config.get("display_height", 480)
    
    print(f"\n📺 Current Display Configuration:")
    print(f"  Device: {device_name}")
    if device_name in DEVICE_CONFIGS:
        device_info = DEVICE_CONFIGS[device_name]
        print(f"  Name: {device_info['name']}")
        print(f"  Description: {device_info['description']}")
    print(f"  Status: {'ENABLED' if display_enabled else 'DISABLED'}")
    print(f"  Dimensions: {width}x{height}")

def list_available_devices():
    """List all available device types."""
    print("\n🖥️  Available Display Devices:")
    print("=" * 50)
    
    for i, (device_id, device_info) in enumerate(DEVICE_CONFIGS.items(), 1):
        print(f"{i:2}. {device_info['name']}")
        print(f"    ID: {device_id}")
        print(f"    Size: {device_info['width']}x{device_info['height']}")
        print(f"    {device_info['description']}")
        print()

def set_device(config, device_id):
    """Set device configuration."""
    if device_id not in DEVICE_CONFIGS:
        print(f"❌ Unknown device: {device_id}")
        return False
    
    device_info = DEVICE_CONFIGS[device_id]
    
    # Update configuration
    config["omni_device_name"] = device_id
    config["display_width"] = device_info["width"]
    config["display_height"] = device_info["height"]
    
    # Enable display if setting a real device
    if device_id != "omni_epd.mock":
        config["e-ink-display-connected"] = True
    
    if save_config(config):
        print(f"✅ Display device updated to: {device_info['name']}")
        print(f"   Device ID: {device_id}")
        print(f"   Dimensions: {device_info['width']}x{device_info['height']}")
        return True
    
    return False

def main():
    """Main function."""
    print("🔧 Mempaper Display Device Configurator")
    print("=" * 45)
    
    config = load_config()
    if not config:
        sys.exit(1)
    
    # Show current configuration
    show_current_device(config)
    
    # Handle command line arguments
    if len(sys.argv) > 1:
        device_arg = sys.argv[1]
        
        # Check if it's a number (device selection)
        if device_arg.isdigit():
            device_num = int(device_arg)
            device_list = list(DEVICE_CONFIGS.keys())
            if 1 <= device_num <= len(device_list):
                device_id = device_list[device_num - 1]
                set_device(config, device_id)
            else:
                print(f"❌ Invalid device number: {device_num}")
                list_available_devices()
        
        # Check if it's a device ID
        elif device_arg in DEVICE_CONFIGS:
            set_device(config, device_arg)
        
        # Special commands
        elif device_arg in ["list", "show", "devices"]:
            list_available_devices()
        
        else:
            print(f"❌ Unknown device or command: {device_arg}")
            list_available_devices()
        
        sys.exit(0)
    
    # Interactive mode
    while True:
        list_available_devices()
        
        print("Options:")
        print("  • Enter device number (1-7)")
        print("  • Enter device ID directly")
        print("  • 'q' to quit")
        
        try:
            choice = input("\nSelect device: ").strip()
            
            if choice.lower() in ['q', 'quit', 'exit']:
                print("👋 Goodbye!")
                break
            
            # Check if it's a number
            if choice.isdigit():
                device_num = int(choice)
                device_list = list(DEVICE_CONFIGS.keys())
                if 1 <= device_num <= len(device_list):
                    device_id = device_list[device_num - 1]
                    if set_device(config, device_id):
                        print("\n🔄 Restart the application for changes to take effect:")
                        print("   python serve.py")
                        break
                else:
                    print(f"❌ Invalid selection: {device_num}")
            
            # Check if it's a device ID
            elif choice in DEVICE_CONFIGS:
                if set_device(config, choice):
                    print("\n🔄 Restart the application for changes to take effect:")
                    print("   python serve.py")
                    break
            
            else:
                print(f"❌ Invalid selection: {choice}")
        
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
