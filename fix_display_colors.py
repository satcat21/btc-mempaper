#!/usr/bin/python
"""
COMPLETE FIX for Waveshare 7.3F color display issues.

This script provides multiple approaches to fix the black/white color problem:
1. Direct Waveshare library approach (like working test script)
2. Fixed omni-epd approach with proper color preservation
3. Diagnostic tools to identify the issue

Usage:
1. Copy this script to your Raspberry Pi
2. Run: python fix_display_colors.py simple_intensity_test_enhanced.png
3. The script will try multiple approaches and show which one works
"""

import sys
import os
import time
from argparse import ArgumentParser
from PIL import Image

def approach_1_direct_waveshare(image_path, message=None):
    """
    Approach 1: Direct Waveshare library (replicates working epd_7in3f_test.py)
    """
    print("\n" + "="*60)
    print("APPROACH 1: Direct Waveshare Library (like working test)")
    print("="*60)
    
    try:
        # Add Waveshare library path
        possible_paths = [
            '/home/pi/e-Paper/RaspberryPi_JetsonNano/python/lib',
            '../e-Paper/RaspberryPi_JetsonNano/python/lib',
            '../../e-Paper/RaspberryPi_JetsonNano/python/lib',
        ]
        
        for lib_path in possible_paths:
            if os.path.exists(lib_path):
                sys.path.insert(0, lib_path)
                print(f"✓ Found Waveshare library: {lib_path}")
                break
        
        from waveshare_epd import epd7in3f
        
        print("Initializing display...")
        epd = epd7in3f.EPD()
        epd.init()
        
        print(f"Loading image: {image_path}")
        image = Image.open(image_path)
        
        # Ensure RGB mode (like working test)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Resize if needed
        if image.size != (epd.width, epd.height):
            print(f"Resizing from {image.size} to {epd.width}x{epd.height}")
            image = image.resize((epd.width, epd.height), Image.Resampling.LANCZOS)
        
        # Add message overlay using EPD colors
        if message:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(image)
            try:
                font = ImageFont.truetype("arial.ttf", 36)
            except:
                font = ImageFont.load_default()
            draw.rectangle([(0, 0), (image.width, 75)], fill=epd.BLACK)
            draw.text((10, 30), message, font=font, fill=epd.WHITE)
        
        print("Displaying with: epd.display(epd.getbuffer(image))")
        epd.display(epd.getbuffer(image))
        
        print("✓ SUCCESS: Direct Waveshare approach worked!")
        return True
        
    except ImportError as e:
        print(f"✗ Waveshare library not available: {e}")
        return False
    except Exception as e:
        print(f"✗ Direct Waveshare failed: {e}")
        return False

def approach_2_fixed_omni_epd(image_path, message=None):
    """
    Approach 2: Fixed omni-epd with color preservation
    """
    print("\n" + "="*60)
    print("APPROACH 2: Fixed omni-epd with Color Preservation")
    print("="*60)
    
    try:
        from omni_epd import displayfactory
        
        print("Loading display driver...")
        epd = displayfactory.load_display_driver("waveshare_epd.epd7in3f")
        epd.prepare()
        
        print(f"Loading and processing image: {image_path}")
        
        # Load image
        image = Image.open(image_path)
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Quantize to exact EPD colors BEFORE any processing
        image = quantize_to_epd_colors(image)
        
        # Resize using nearest-neighbor to preserve exact colors
        if image.size != (epd.width, epd.height):
            print(f"Resizing from {image.size} to {epd.width}x{epd.height} (nearest-neighbor)")
            image = image.resize((epd.width, epd.height), Image.Resampling.NEAREST)
        
        # Add message overlay
        if message:
            image = add_text_overlay(image, message)
        
        # Final quantization to ensure exact colors
        image = quantize_to_epd_colors(image)
        
        print("Displaying with omni-epd...")
        epd.display(image)
        epd.close()
        
        print("✓ SUCCESS: Fixed omni-epd approach worked!")
        return True
        
    except ImportError as e:
        print(f"✗ omni-epd not available: {e}")
        return False
    except Exception as e:
        print(f"✗ Fixed omni-epd failed: {e}")
        return False

def quantize_to_epd_colors(img):
    """
    Quantize image to exact Waveshare EPD colors.
    """
    epd_colors = [
        (0, 0, 0),       # Black
        (255, 255, 255), # White  
        (0, 255, 0),     # Green
        (0, 0, 255),     # Blue
        (255, 0, 0),     # Red
        (255, 255, 0),   # Yellow
        (255, 128, 0),   # Orange
    ]
    
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    width, height = img.size
    pixels = img.load()
    new_img = Image.new('RGB', (width, height))
    new_pixels = new_img.load()
    
    for y in range(height):
        for x in range(width):
            original_color = pixels[x, y]
            closest_color = find_closest_color(original_color, epd_colors)
            new_pixels[x, y] = closest_color
    
    return new_img

def find_closest_color(rgb_color, color_palette):
    """Find closest color in palette using Euclidean distance."""
    r, g, b = rgb_color
    min_distance = float('inf')
    closest_color = color_palette[0]
    
    for color in color_palette:
        er, eg, eb = color
        distance = ((r - er) ** 2 + (g - eg) ** 2 + (b - eb) ** 2) ** 0.5
        if distance < min_distance:
            min_distance = distance
            closest_color = color
    
    return closest_color

def add_text_overlay(image, message):
    """Add text overlay using exact EPD colors."""
    from PIL import ImageDraw, ImageFont
    
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except:
        font = ImageFont.load_default()
    
    # Use exact EPD colors
    draw.rectangle([(0, 0), (image.width, 75)], fill=(0, 0, 0))  # EPD BLACK
    draw.text((10, 30), message, font=font, fill=(255, 255, 255))  # EPD WHITE
    
    return image

def diagnose_current_setup():
    """
    Diagnose the current display setup to identify issues.
    """
    print("\n" + "="*60)
    print("DIAGNOSTIC: Current Display Setup")
    print("="*60)
    
    # Check for Waveshare library
    try:
        sys.path.append('/home/pi/e-Paper/RaspberryPi_JetsonNano/python/lib')
        from waveshare_epd import epd7in3f
        print("✓ Waveshare library available")
    except ImportError:
        print("✗ Waveshare library not found")
    
    # Check for omni-epd
    try:
        from omni_epd import displayfactory
        print("✓ omni-epd available")
        
        # Check configuration
        config_files = [
            'waveshare_epd.epd7in3f.ini',
            'omni-epd.ini'
        ]
        
        for config_file in config_files:
            if os.path.exists(config_file):
                print(f"✓ Found config: {config_file}")
            else:
                print(f"✗ Missing config: {config_file}")
                
    except ImportError:
        print("✗ omni-epd not available")
    
    # Check display device
    try:
        epd = displayfactory.load_display_driver("waveshare_epd.epd7in3f")
        print(f"✓ Display driver loaded: {epd.width}x{epd.height}")
    except Exception as e:
        print(f"✗ Cannot load display driver: {e}")

def main():
    """
    Main function that tries all approaches to fix color display.
    """
    parser = ArgumentParser(description="Fix Waveshare 7.3F color display issues")
    parser.add_argument("image_path", help="Path to test image")
    parser.add_argument("-m", "--message", help="Text message overlay")
    parser.add_argument("--diagnose-only", action="store_true", help="Only run diagnostics")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.image_path):
        print(f"Error: Image file not found: {args.image_path}")
        return 1
    
    print("WAVESHARE 7.3F COLOR DISPLAY FIX")
    print(f"Image: {args.image_path}")
    print(f"Message: {args.message if args.message else 'None'}")
    
    # Run diagnostics
    diagnose_current_setup()
    
    if args.diagnose_only:
        return 0
    
    success = False
    
    # Try approach 1: Direct Waveshare (like working test)
    if approach_1_direct_waveshare(args.image_path, args.message):
        success = True
    
    # Try approach 2: Fixed omni-epd
    if not success:
        if approach_2_fixed_omni_epd(args.image_path, args.message):
            success = True
    
    if success:
        print("\n🎉 SUCCESS! At least one approach worked.")
        print("Colors should now display correctly on your e-ink display.")
    else:
        print("\n❌ All approaches failed.")
        print("Please check:")
        print("1. Display hardware connections")
        print("2. Waveshare library installation")
        print("3. omni-epd configuration files")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
