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

# Add the Waveshare library paths to sys.path
# Try multiple common locations where Waveshare modules might be installed
waveshare_lib_paths = [
    # Location 1: User's home directory - separate programs structure (13.3E actual location)
    os.path.expanduser('~/e-Paper/E-paper_Separate_Program/13.3inch_e-Paper_E/RaspberryPi/python/lib'),
    # Location 2: User's home directory - unified structure (7.3F location)
    os.path.expanduser('~/e-Paper/RaspberryPi_JetsonNano/python/lib'),
    # Location 3: Parallel to project - separate programs structure
    os.path.join(os.path.dirname(__file__), '..', '..', 'e-Paper', 'E-paper_Separate_Program', '13.3inch_e-Paper_E', 'RaspberryPi', 'python', 'lib'),
    # Location 4: Parallel to project - unified structure
    os.path.join(os.path.dirname(__file__), '..', '..', 'e-Paper', 'RaspberryPi_JetsonNano', 'python', 'lib'),
    # Location 5: Project's lib directory (if modules were copied there)
    os.path.join(os.path.dirname(__file__), '..', 'lib'),
    # Location 6: Directly in display directory
    os.path.dirname(__file__),
]

for lib_path in waveshare_lib_paths:
    if os.path.exists(lib_path) and lib_path not in sys.path:
        sys.path.append(lib_path)

# Dynamic module loading - import each module individually
# This allows partial availability (only some displays work)
WAVESHARE_AVAILABLE = False
WAVESHARE_MODULES = {}

# Try to import 7.3F display
try:
    import epd7in3f
    WAVESHARE_MODULES['epd7in3f'] = epd7in3f
    WAVESHARE_AVAILABLE = True
except ImportError:
    pass  # Module not available, skip

# Try to import 13.3E display
try:
    import epd13in3E
    WAVESHARE_MODULES['epd13in3E'] = epd13in3E
    WAVESHARE_AVAILABLE = True
except ImportError:
    pass  # Module not available, skip

# Try to import 13.3k display (Black & White)
try:
    import epd13in3k
    WAVESHARE_MODULES['epd13in3k'] = epd13in3k
    WAVESHARE_AVAILABLE = True
except ImportError:
    pass  # Module not available, skip

if not WAVESHARE_AVAILABLE:
    print(f"❌ No Waveshare EPD modules available")
    print(f"   Searched paths:")
    for path in waveshare_lib_paths:
        exists = "✓" if os.path.exists(path) else "✗"
        print(f"   [{exists}] {path}")
else:
    pass  # Modules loaded successfully

class WaveshareDisplay:
    """Dynamic interface to Waveshare e-paper displays (7.3F and 13.3E supported)."""
    
    def __init__(self, config=None):
        """
        Initialize the Waveshare display.
        
        Args:
            config (dict, optional): Configuration dictionary
        """
        self.config = config or {}
        self.epd = None
        
        # Read display dimensions from config
        self.width = self.config.get("display_width", 800)
        self.height = self.config.get("display_height", 480)
        
        # Parse device name from config (e.g., "waveshare_epd.epd7in3f" -> "epd7in3f")
        device_name = self.config.get("omni_device_name", "waveshare_epd.epd7in3f")
        self.module_name = device_name.split('.')[-1] if '.' in device_name else device_name
        
        # Normalize module name - handle case variations (e.g., epd13in3e -> epd13in3E)
        # Create alias for lowercase variant to uppercase (the actual module name)
        if self.module_name == 'epd13in3e':  # Old config value
            self.module_name = 'epd13in3E'  # Correct module name
        
        self.enabled = self.config.get("e-ink-display-connected", True)
        self.skip_clear = self.config.get("skip_clear_display", True)  # Skip clear by default (saves ~31s)
        
        # Determine color support based on module
        self.supports_orange = self.module_name == 'epd7in3f'  # Only 7.3F has orange
        # 13.3K is black & white only (2 colors), 13.3E is 6 colors, 7.3F is 7 colors
        if self.module_name == 'epd13in3k':
            self.color_count = 2  # Black & White only
        elif self.module_name == 'epd13in3E':
            self.color_count = 6  # Spectra 6 colors
        elif self.supports_orange:
            self.color_count = 7  # 7.3F with orange
        else:
            self.color_count = 6  # Default for other displays
        
        # Don't initialize display in constructor to avoid blocking
        # Initialize only when needed in display_image method
        if not WAVESHARE_AVAILABLE:
            print("⚠️ Waveshare library not available - display will use fallback only")
        elif not self.enabled:
            print("⚙️ E-paper display disabled in configuration")
        else:
            pass  # Display configured
        
        # Color constants from the EPD library
        if WAVESHARE_AVAILABLE and self.module_name in WAVESHARE_MODULES:
            try:
                # Get color constants from the configured module
                epd_module = WAVESHARE_MODULES[self.module_name]
                self.BLACK = getattr(epd_module, 'BLACK', 0x000000)
                self.WHITE = getattr(epd_module, 'WHITE', 0xFFFFFF)
                self.RED = getattr(epd_module, 'RED', 0xFF0000)
                self.GREEN = getattr(epd_module, 'GREEN', 0x00FF00)
                self.BLUE = getattr(epd_module, 'BLUE', 0x0000FF)
                self.YELLOW = getattr(epd_module, 'YELLOW', 0xFFFF00)
                self.ORANGE = getattr(epd_module, 'ORANGE', 0xFF8000) if self.supports_orange else None
            except:
                # Fallback to standard color values
                self.BLACK = 0x000000
                self.WHITE = 0xFFFFFF
                self.RED = 0xFF0000
                self.GREEN = 0x00FF00
                self.BLUE = 0x0000FF
                self.YELLOW = 0xFFFF00
                self.ORANGE = 0xFF8000 if self.supports_orange else None
        else:
            # Fallback color values
            self.BLACK = 0x000000
            self.WHITE = 0xFFFFFF
            self.RED = 0xFF0000
            self.GREEN = 0x00FF00
            self.BLUE = 0x0000FF
            self.YELLOW = 0xFFFF00
            self.ORANGE = 0xFF8000 if self.supports_orange else None

    def _detect_epd_methods(self):
        """
        Detect which method naming convention the EPD uses.
        Different displays use different case conventions (init vs Init, Clear vs clear).
        """
        if not self.epd:
            return
        
        # Detect init method (init vs Init)
        if hasattr(self.epd, 'Init'):
            self._init_method = 'Init'
        elif hasattr(self.epd, 'init'):
            self._init_method = 'init'
        else:
            self._init_method = None
            print(f"⚠️ No init/Init method found on EPD")
        
        # Detect clear method (Clear vs clear)
        if hasattr(self.epd, 'Clear'):
            self._clear_method = 'Clear'
        elif hasattr(self.epd, 'clear'):
            self._clear_method = 'clear'
        else:
            self._clear_method = None
        
        # Detect sleep method (sleep vs Sleep)
        if hasattr(self.epd, 'sleep'):
            self._sleep_method = 'sleep'
        elif hasattr(self.epd, 'Sleep'):
            self._sleep_method = 'Sleep'
        else:
            self._sleep_method = None
    
    def _call_epd_init(self):
        """Call the appropriate init method based on detected naming."""
        if self._init_method:
            return getattr(self.epd, self._init_method)()
        else:
            raise AttributeError(f"EPD object has no init method")
    
    def _call_epd_clear(self):
        """Call the appropriate clear method based on detected naming."""
        if self._clear_method:
            return getattr(self.epd, self._clear_method)()
        else:
            raise AttributeError(f"EPD object has no clear method")
    
    def _call_epd_sleep(self):
        """Call the appropriate sleep method based on detected naming."""
        if self._sleep_method:
            return getattr(self.epd, self._sleep_method)()
        else:
            raise AttributeError(f"EPD object has no sleep method")

    def init_display(self):
        """Initialize the e-paper display hardware."""
        if not self.epd:
            print("⚙️ EPD not available - skipping hardware initialization")
            return False
            
        try:
            print("Initializing e-paper display...")
            self._call_epd_init()
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
            self._call_epd_clear()
            print("✅ E-paper display cleared")
        except Exception as e:
            print(f"❌ Failed to clear display: {e}")

    def convert_to_epd_palette(self, image):
        """
        Convert image to EPD color palette (6 or 7 colors based on display).
        
        Args:
            image (PIL.Image): Input image
            
        Returns:
            PIL.Image: Image with EPD palette
        """
        # Define color palette based on display capabilities
        if self.supports_orange:
            # 7-color palette for Waveshare 7.3F
            palette_colors = [
                (0, 0, 0),        # Black
                (255, 255, 255),  # White
                (255, 0, 0),      # Red
                (0, 255, 0),      # Green
                (0, 0, 255),      # Blue
                (255, 255, 0),    # Yellow
                (255, 165, 0),    # Orange
            ]
        else:
            # 6-color palette for Waveshare 13.3E and similar
            palette_colors = [
                (0, 0, 0),        # Black
                (255, 255, 255),  # White
                (255, 0, 0),      # Red
                (255, 255, 0),    # Yellow
                (0, 255, 0),      # Green
                (0, 0, 255),      # Blue
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
            # Check if hardware display is available and enabled
            if not WAVESHARE_AVAILABLE:
                return True
                
            if not self.enabled:
                return True
            
            # Initialize EPD hardware FIRST to get correct dimensions
            if not self.epd:
                try:
                    if self.module_name not in WAVESHARE_MODULES:
                        print(f"❌ Module {self.module_name} not available in loaded modules")
                        print(f"Available modules: {list(WAVESHARE_MODULES.keys())}")
                        return False
                    
                    epd_module = WAVESHARE_MODULES[self.module_name]
                    self.epd = epd_module.EPD()

                    # Read actual display dimensions from the EPD module/object
                    # This ensures we use the correct native orientation
                    if hasattr(self.epd, 'width') and hasattr(self.epd, 'height'):
                        epd_width = self.epd.width
                        epd_height = self.epd.height
                        if (self.width, self.height) != (epd_width, epd_height):
                            self.width = epd_width
                            self.height = epd_height
                    elif hasattr(epd_module, 'EPD_WIDTH') and hasattr(epd_module, 'EPD_HEIGHT'):
                        epd_width = epd_module.EPD_WIDTH
                        epd_height = epd_module.EPD_HEIGHT
                        if (self.width, self.height) != (epd_width, epd_height):
                            self.width = epd_width
                            self.height = epd_height
                    
                    # Detect method naming convention (init vs Init, Clear vs clear, etc.)
                    self._detect_epd_methods()
                    
                except Exception as e:
                    print(f"❌ EPD initialization failed: {e}")
                    return False
            
            # Now load and process the image with correct dimensions
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
                print(f"⚙️ Resizing image from {img.size} to {self.width}×{self.height}")
                img = img.resize((self.width, self.height), Image.Resampling.LANCZOS)

            # Convert to EPD color palette (6 or 7 colors)
            img = self.convert_to_epd_palette(img)
            
            # Save processed image for debugging
            debug_path = "current_processed.png"
            img.save(debug_path)
            
            # Display on hardware
            try:
                total_start = time.time()

                # Initialize display
                self._call_epd_init()

                # Clear display (optional - skipping saves ~31s)
                if not self.skip_clear:
                    self._call_epd_clear()

                # Display the image
                buffer_data = self.epd.getbuffer(img)
                self.epd.display(buffer_data)

                # Put display to sleep
                time.sleep(1)
                self._call_epd_sleep()
                
                total_time = time.time() - total_start
                print(f"✅ Display update completed in {total_time:.2f}s")
                return True
                
            except Exception as e:
                import traceback
                print(f"❌ Display hardware error: {e}")
                print(f"   Error type: {type(e).__name__}")
                print(f"   Traceback:")
                traceback.print_exc()
                
                # Try to clean up if there was an error
                try:
                    if hasattr(self.epd, 'sleep') or hasattr(self.epd, 'Sleep'):
                        print(f"🔧 Attempting emergency sleep...")
                        self._call_epd_sleep()
                except Exception as cleanup_error:
                    print(f"⚠️ Cleanup also failed: {cleanup_error}")
                
                return False
                
        except Exception as e:
            import traceback
            print(f"❌ Display image processing error: {e}")
            print(f"   Error type: {type(e).__name__}")
            print(f"   Traceback:")
            traceback.print_exc()
            return False

    def sleep(self):
        """Put the display to sleep to save power."""
        if self.epd:
            try:
                self._call_epd_sleep()
                print("✅ Display put to sleep")
            except Exception as e:
                print(f"❌ Error putting display to sleep: {e}")

    def cleanup(self):
        """Clean up display resources."""
        if self.epd:
            try:
                if WAVESHARE_AVAILABLE and self.module_name in WAVESHARE_MODULES:
                    epd_module = WAVESHARE_MODULES[self.module_name]
                    if hasattr(epd_module, 'epdconfig'):
                        epd_module.epdconfig.module_exit(cleanup=True)
                print("✅ Display cleanup completed")
            except Exception as e:
                print(f"❌ Error during cleanup: {e}")


def main():
    """Test the Waveshare display functionality."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Display image on Waveshare e-paper display')
    parser.add_argument('image_path', help='Path to image file')
    parser.add_argument('--message', help='Text message to overlay')
    parser.add_argument('--no-vertical', action='store_true', 
                       help='Skip vertical orientation processing')
    
    args = parser.parse_args()
    
    # Try to load config for proper display settings
    try:
        from managers.config_manager import ConfigManager
        config_manager = ConfigManager()
        config = config_manager.config
        print(f"✅ Loaded config: {config.get('display_width')}x{config.get('display_height')}, {config.get('omni_device_name')}")
    except Exception as e:
        print(f"⚠️  Could not load config, using defaults: {e}")
        config = {}
    
    # Create display instance with config
    display = WaveshareDisplay(config=config)
    
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
