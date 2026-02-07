#!/usr/bin/python
# -*- coding:utf-8 -*-

"""
Simple subprocess wrapper for e-paper display to avoid threading issues.
This script runs the Waveshare display in isolation.
"""

import sys

def main():
    if len(sys.argv) < 2:
        print("Usage: python display_subprocess.py <image_path>")
        sys.exit(1)
    
    image_path = sys.argv[1]
    
    try:
        # Import and run the display
        from display.waveshare_display import WaveshareDisplay
        
        # Create display with default config
        display = WaveshareDisplay()
        
        # Display the image
        success = display.display_image(image_path)
        
        if success:
            # Don't print success - parent logs it
            sys.exit(0)
        else:
            print("❌ Display failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
