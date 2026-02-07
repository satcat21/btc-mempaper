#!/usr/bin/python
# -*- coding:utf-8 -*-

"""
Waveshare E-Paper Display Module

This module provides direct interface to Waveshare e-paper displays
using the native Waveshare Python library instead of omni-epd.
"""

import sys
import os
import time
import logging
import threading
import queue
from PIL import Image, ImageDraw

# Add the Waveshare library path to sys.path
epaper_lib_path_parallel = os.path.join(os.path.dirname(__file__), '..', '..', 'e-Paper', 'RaspberryPi_JetsonNano', 'python', 'lib')

if os.path.exists(epaper_lib_path_parallel):
    sys.path.append(epaper_lib_path_parallel)

try:
    from waveshare_epd import epd7in3f
    WAVESHARE_AVAILABLE = True
except ImportError as e:
    WAVESHARE_AVAILABLE = False
    print(f"❌ Waveshare EPD library not available: {e}")
except Exception as e:
    WAVESHARE_AVAILABLE = False
    print(f"❌ Waveshare EPD library error: {e}")

class WaveshareDisplay:
    """Direct interface to Waveshare 7.3" F 7-color e-paper display."""
    
    def __init__(self, config=None):
        """
        Initialize the Waveshare display.
        
        Args:
            config (dict, optional): Configuration dictionary
        """
        self.config = config or {}
        self.epd = None
        self.width = 800
        self.height = 480
        self.enabled = self.config.get("e-ink-display-connected", True)
        self.skip_clear = self.config.get("skip_clear_display", True)  # Skip clear by default (saves ~31s)
        
        # Don't initialize display in constructor to avoid blocking
        # Initialize only when needed in display_image method
        if not WAVESHARE_AVAILABLE:
            print("⚠️ Waveshare library not available - display will use fallback only")
        elif not self.enabled:
            print("⚙️ E-paper display disabled in configuration")
        
        # Color constants from the EPD library
        if WAVESHARE_AVAILABLE:
            try:
                # Get color constants from the module
                self.BLACK = getattr(epd7in3f, 'BLACK', 0x000000)
                self.WHITE = getattr(epd7in3f, 'WHITE', 0xFFFFFF)
                self.RED = getattr(epd7in3f, 'RED', 0xFF0000)
                self.GREEN = getattr(epd7in3f, 'GREEN', 0x00FF00)
                self.BLUE = getattr(epd7in3f, 'BLUE', 0x0000FF)
                self.YELLOW = getattr(epd7in3f, 'YELLOW', 0xFFFF00)
                self.ORANGE = getattr(epd7in3f, 'ORANGE', 0xFF8000)
            except:
                # Fallback to standard color values
                self.BLACK = 0x000000
                self.WHITE = 0xFFFFFF
                self.RED = 0xFF0000
                self.GREEN = 0x00FF00
                self.BLUE = 0x0000FF
                self.YELLOW = 0xFFFF00
                self.ORANGE = 0xFF8000
        else:
            # Fallback color values
            self.BLACK = 0x000000
            self.WHITE = 0xFFFFFF
            self.RED = 0xFF0000
            self.GREEN = 0x00FF00
            self.BLUE = 0x0000FF
            self.YELLOW = 0xFFFF00
            self.ORANGE = 0xFF8000

    def init_display(self):
        """Initialize the e-paper display hardware."""
        if not self.epd:
            print("⚙️ EPD not available - skipping hardware initialization")
            return False
            
        try:
            print("Initializing e-paper display...")
            self.epd.init()
            print("✅ E-paper display initialized")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize display: {e}")
            return False

    def clear_display(self):
        """Clear the e-paper display to white."""
        if not self.epd:
            print("⚙️ EPD not available - skipping clear")
            return
            
        try:
            print("Clearing e-paper display...")
            self.epd.Clear()
            print("✅ E-paper display cleared")
        except Exception as e:
            print(f"❌ Failed to clear display: {e}")

    def convert_to_7color_palette(self, image):
        """
        Convert image to 7-color palette suitable for Waveshare 7.3F display.
        
        Args:
            image (PIL.Image): Input image
            
        Returns:
            PIL.Image: Image with 7-color palette
        """
        # Define the 7-color palette for Waveshare 7.3F
        palette_colors = [
            (0, 0, 0),        # Black
            (255, 255, 255),  # White
            (255, 0, 0),      # Red
            (0, 255, 0),      # Green
            (0, 0, 255),      # Blue
            (255, 255, 0),    # Yellow
            (255, 165, 0),    # Orange
        ]
        
        # Create palette image
        pal_image = Image.new('P', (1, 1))
        palette_flat = []
        for color in palette_colors:
            palette_flat.extend(color)
        # Pad remaining palette entries with black
        palette_flat.extend([0, 0, 0] * (256 - len(palette_colors)))
        pal_image.putpalette(palette_flat)
        
        # Convert input to RGB if needed
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Quantize to 7-color palette with Floyd-Steinberg dithering
        quantized = image.quantize(palette=pal_image, dither=Image.Dither.FLOYDSTEINBERG)
        
        # Convert back to RGB for display
        return quantized.convert('RGB')

    def _run_with_timeout(self, func, timeout=30, *args, **kwargs):
        """
        Run a function with a timeout to prevent hanging.
        
        Args:
            func: Function to run
            timeout: Timeout in seconds
            *args, **kwargs: Arguments for the function
            
        Returns:
            Result of function or None if timeout/error
        """
        import threading
        import queue
        
        result_queue = queue.Queue()
        exception_queue = queue.Queue()
        
        def target():
            try:
                result = func(*args, **kwargs)
                result_queue.put(result)
            except Exception as e:
                exception_queue.put(e)
        
        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            print(f"⏰ Function {func.__name__} timed out after {timeout}s")
            return None
        
        if not exception_queue.empty():
            e = exception_queue.get()
            print(f"❌ Function {func.__name__} failed: {e}")
            return None
        
        if not result_queue.empty():
            return result_queue.get()
        
        return None

    def display_image(self, image_path, message=None, process_vertical=True):
        """
        Display an image on the e-paper display.
        
        Args:
            image_path (str): Path to the image file
            message (str, optional): Text message to overlay
            process_vertical (bool): Whether to process vertical orientation
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Load the image
            if isinstance(image_path, str):
                img = Image.open(image_path)
            else:
                # Assume it's already a PIL Image
                img = image_path
            
            # Process image for vertical orientation if needed
            if process_vertical and img.size == (480, 800):
                # Add message overlay before rotation if provided
                if message and len(message) > 1:
                    try:
                        draw = ImageDraw.Draw(img)
                        from PIL import ImageFont
                        try:
                            font = ImageFont.truetype("arial.ttf", 36)
                        except OSError:
                            font = ImageFont.load_default()
                        draw.rectangle([(0, 0), (img.width, 75)], fill=(0, 0, 0))
                        draw.text((10, 30), message, font=font, fill=(255, 255, 255))
                    except Exception as e:
                        print(f"Warning: Could not add message overlay: {e}")
                
                # Rotate 90° clockwise to convert portrait to landscape
                img = img.transpose(Image.Transpose.ROTATE_90)
            
            # Ensure image is the correct size for the display
            if img.size != (self.width, self.height):
                img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)
            
            # Convert to 7-color palette
            img = self.convert_to_7color_palette(img)
            
            # Save processed image for debugging
            debug_path = "current_processed.png"
            img.save(debug_path)
            
            # Check if hardware display is available and enabled
            if not WAVESHARE_AVAILABLE:
                return True
                
            if not self.enabled:
                return True
            
            # Lazy initialization of EPD hardware
            if not self.epd:
                try:
                    self.epd = epd7in3f.EPD()
                except Exception as e:
                    print(f"❌ EPD initialization failed: {e}")
                    return False
            
            # Display on hardware
            try:
                total_start = time.time()
                
                # Initialize display
                self.epd.init()
                
                # Clear display (optional - skipping saves ~31s)
                if not self.skip_clear:
                    self.epd.Clear()
                
                # Display the image
                self.epd.display(self.epd.getbuffer(img))
                
                # Put display to sleep
                time.sleep(1)
                self.epd.sleep()
                
                # total_time = time.time() - total_start
                return True
                
            except Exception as e:
                print(f"❌ Display error: {e}")
                
                # Try to clean up if there was an error
                try:
                    if hasattr(self.epd, 'sleep'):
                        self.epd.sleep()
                except:
                    pass
                
                return False
                
        except Exception as e:
            print(f"❌ Display error: {e}")
            return False

    def sleep(self):
        """Put the display to sleep to save power."""
        if self.epd:
            try:
                self.epd.sleep()
                print("✅ Display put to sleep")
            except Exception as e:
                print(f"❌ Error putting display to sleep: {e}")

    def cleanup(self):
        """Clean up display resources."""
        if self.epd:
            try:
                if WAVESHARE_AVAILABLE:
                    epd7in3f.epdconfig.module_exit(cleanup=True)
                print("✅ Display cleanup completed")
            except Exception as e:
                print(f"❌ Error during cleanup: {e}")


def main():
    """Test the Waveshare display functionality."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Display image on Waveshare 7.3F e-paper')
    parser.add_argument('image_path', help='Path to image file')
    parser.add_argument('--message', help='Text message to overlay')
    parser.add_argument('--no-vertical', action='store_true', 
                       help='Skip vertical orientation processing')
    
    args = parser.parse_args()
    
    # Create display instance
    display = WaveshareDisplay()
    
    try:
        # Display the image
        success = display.display_image(
            args.image_path, 
            message=args.message,
            process_vertical=not args.no_vertical
        )
        
        if success:
            print("✅ Image display completed successfully")
        else:
            print("❌ Image display failed")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        # Clean up
        display.cleanup()


if __name__ == "__main__":
    main()
