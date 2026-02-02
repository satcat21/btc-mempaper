#!/usr/bin/python

# Import required modules
import json
import os
import sys
import time
from omni_epd import displayfactory
from prepare_image import Processor
from argparse import ArgumentParser
from PIL import Image

def quantize_to_exact_epd_colors(img):
    """
    Quantize image to exact Waveshare EPD colors using nearest-neighbor mapping.
    This ensures every pixel uses exactly one of the 7 EPD colors.
    """
    # Exact Waveshare 7.3F colors (from official driver)
    epd_colors = [
        (0, 0, 0),       # Black
        (255, 255, 255), # White  
        (0, 255, 0),     # Green
        (0, 0, 255),     # Blue
        (255, 0, 0),     # Red
        (255, 255, 0),   # Yellow
        (255, 128, 0),   # Orange
    ]
    
    # Convert image to RGB if not already
    if img.mode != 'RGB':
        img = img.convert('RGB')
    
    # Create new image with exact colors
    width, height = img.size
    pixels = img.load()
    new_img = Image.new('RGB', (width, height))
    new_pixels = new_img.load()
    
    # Map each pixel to closest EPD color
    for y in range(height):
        for x in range(width):
            original_color = pixels[x, y]
            closest_color = find_closest_epd_color(original_color, epd_colors)
            new_pixels[x, y] = closest_color
    
    return new_img

def find_closest_epd_color(rgb_color, epd_colors):
    """
    Find the closest EPD color using Euclidean distance.
    """
    r, g, b = rgb_color
    min_distance = float('inf')
    closest_color = epd_colors[0]  # Default to black
    
    for epd_color in epd_colors:
        er, eg, eb = epd_color
        # Calculate Euclidean distance in RGB space
        distance = ((r - er) ** 2 + (g - eg) ** 2 + (b - eb) ** 2) ** 0.5
        
        if distance < min_distance:
            min_distance = distance
            closest_color = epd_color
    
    return closest_color

def process_vertical_image(image_path, display_width, display_height, message=None):
    """
    SIMPLIFIED processing for vertical display orientation:
    1. Load 480x800 portrait image
    2. Rotate 90° counter-clockwise (ROTATE_270) to get landscape
    3. Scale to fit 800x480 display
    
    Args:
        image_path: Path to the image file (should be 480x800)
        display_width: Physical display width (800)
        display_height: Physical display height (480)
        message: Optional text message overlay
        
    Returns:
        Processed image ready for 800x480 e-ink display
    """
    from PIL import Image
    
    # Load the original image (should be 480x800 for vertical orientation)
    img = Image.open(image_path)
    original_width, original_height = img.size
    print(f"show_image.py: Original image size: {original_width}x{original_height}")
    
    # CRITICAL FIX: Quantize to exact EPD colors FIRST
    # This prevents any processing from creating intermediate colors
    img = quantize_to_exact_epd_colors(img)
    print("show_image.py: Quantized to exact EPD colors")
    
    # Apply text message if provided (before rotation)
    if message and len(message) > 1:
        try:
            from PIL import ImageDraw, ImageFont
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("arial.ttf", 36)
            except OSError:
                font = ImageFont.load_default()
            draw.rectangle([(0, 0), (img.width, 75)], fill=(0, 0, 0), outline=None)  # EPD BLACK
            draw.text((10, 30), message, font=font, fill=(255, 255, 255))  # EPD WHITE
        except Exception as e:
            print(f"show_image.py: Error adding text overlay: {e}")
    
    # Step 1: Rotate 90° clockwise (ROTATE_90) 
    # This turns 480x800 portrait into 800x480 landscape
    rotated_img = img.transpose(method=Image.Transpose.ROTATE_90)
    print(f"show_image.py: Rotated 90° clockwise: {rotated_img.size}")
    
    # Step 2: Scale to exact display dimensions if needed
    if rotated_img.size != (display_width, display_height):
        # CRITICAL FIX: Use NEAREST resampling to preserve exact EPD colors
        # LANCZOS creates intermediate colors that destroy the 7-color palette
        final_img = rotated_img.resize((display_width, display_height), Image.Resampling.NEAREST)
        print(f"show_image.py: Scaled to {display_width}x{display_height} (NEAREST resampling)")
    else:
        final_img = rotated_img
        print(f"show_image.py: Already correct size {display_width}x{display_height}")
    
    # DISABLED: Let omni-epd handle 7-color quantization via palette_filter in .ini file
    # This prevents double quantization which can cause grayscale conversion
    
    # CRITICAL FIX: Final quantization to ensure exact EPD colors
    final_img = quantize_to_exact_epd_colors(final_img)
    print("show_image.py: Final quantization to exact EPD colors")
    
    return final_img


def try_display_with_exponential_backoff(device_name, image_path, message=None, max_retries=4):
    """
    Try to display image with exponential backoff on GPIO busy errors.
    Delays: 5s, 10s, 20s, 40s, then abort
    """
    delays = [5, 10, 20, 40]  # Exponential backoff delays
    
    for attempt in range(max_retries):
        try:
            print(f"show_image.py: Display attempt {attempt + 1}/{max_retries}")
            
            # Instantiate the display
            epd = displayfactory.load_display_driver(device_name)
            epd.prepare()
            print("show_image.py: Prepared display.")
            
            # Prepare the image with special handling for vertical orientation
            # Load config to check display orientation
            try:
                import json
                config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
                with open(config_path, 'r') as f:
                    config = json.load(f)
                eink_orientation = config.get("eink_orientation", "vertical").lower()
                
                # For vertical orientation, we need special processing to avoid cropping
                if eink_orientation == "vertical":
                    # Process image with rotation-aware scaling
                    processed_img = process_vertical_image(image_path, epd.width, epd.height, message)
                    # Create a dummy processor object to maintain compatibility
                    proc = type('DummyProcessor', (), {'img': processed_img})()
                else:
                    # Standard processing for horizontal orientation
                    proc = Processor(img_path=image_path,
                                   display_width=epd.width,
                                   display_height=epd.height,
                                   textmsg=message)
                    proc.process()
                
                print(f"show_image.py: Physical display dimensions: {epd.width}x{epd.height}")
                print(f"show_image.py: Display orientation setting: {eink_orientation}")
                
            except Exception as e:
                print(f"show_image.py: Could not load config, assuming vertical: {e}")
                eink_orientation = "vertical"
                # Fallback to standard processing
                proc = Processor(img_path=image_path,
                               display_width=epd.width,
                               display_height=epd.height,
                               textmsg=message)
                proc.process()
            
            print("show_image.py: Prepared image.")
            
            # Show the image and close out the display
            epd.display(proc.img)
            epd.close()
            print("show_image.py: Updated display & exiting.")
            return True  # Success!
            
        except Exception as e:
            error_msg = str(e)
            print(f"show_image.py: Attempt {attempt + 1} failed: {error_msg}")
            
            # Check if it's a GPIO busy error
            if "GPIO busy" in error_msg or "KeyError" in error_msg:
                if attempt < max_retries - 1:  # Not the last attempt
                    delay = delays[attempt]
                    print(f"show_image.py: GPIO busy, waiting {delay}s before retry...")
                    time.sleep(delay)
                    continue
                else:
                    print("show_image.py: Max retries reached, GPIO still busy. Aborting.")
                    return False
            else:
                # Different error, don't retry
                print(f"show_image.py: Non-GPIO error, aborting: {error_msg}")
                return False
    
    return False

# Handle argument parsing
parser = ArgumentParser()
parser.add_argument("image_file_path", help = "Path to the image to display")
parser.add_argument("--message", "-m", help = "Banner text do overlay on top of the image")
args = parser.parse_args()

# Load configuration to get device name
# Try multiple possible locations for config.json
config_paths = [
    "config.json",           # Current directory
    "../config.json",        # Parent directory (if run from display folder)
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")  # Project root
]

config = None
device_name = "waveshare_epd.epd7in3f"  # Default

for config_path in config_paths:
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        device_name = config.get("omni_device_name", "waveshare_epd.epd7in3f")
        print(f"show_image.py: Using display device: {device_name} (config from: {config_path})")
        break
    except (FileNotFoundError, json.JSONDecodeError) as e:
        continue

if config is None:
    print(f"show_image.py: Warning - Could not load config from any location, using default device: {device_name}")

# Try to display with exponential backoff retry mechanism
success = try_display_with_exponential_backoff(device_name, args.image_file_path, args.message)

if success:
    print("show_image.py: Display completed successfully.")
    sys.exit(0)
else:
    print("show_image.py: Display failed after all retries.")
    sys.exit(1)