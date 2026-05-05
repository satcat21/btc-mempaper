#!/usr/bin/python
# -*- coding:utf-8 -*-

"""
Simple subprocess wrapper for e-paper display to avoid threading issues.
This script runs the Waveshare display in isolation.
"""

import sys
import traceback

def main():
    if len(sys.argv) < 2:
        print("Usage: python display_subprocess.py <image_path>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    try:
        # Import display and config manager
        from display.waveshare_display import WaveshareDisplay
        from managers.config_manager import ConfigManager
        
        # Load configuration
        config_manager = ConfigManager()
        config = config_manager.config
        
        # Create display with config (includes display dimensions and device name)
        display = WaveshareDisplay(config=config)
        
        # Display the image
        success = display.display_image(image_path)
        
        if success:
            # Don't print success - parent logs it
            sys.exit(0)
        else:
            print("❌ Display failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Display subprocess error: {e}")
        print(f"   Traceback:")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
