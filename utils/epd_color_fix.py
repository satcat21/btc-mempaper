"""
CRITICAL COLOR FIX for Waveshare 7.3F Display

This module provides the EXACT color mappings required for the Waveshare 7.3" F-color display.
The display only recognizes these specific RGB values - any other colors will be dithered
to black/white or appear incorrectly.

Based on official Waveshare epd7in3f.py driver color definitions.
"""

# EXACT Waveshare 7.3F EPD Color Definitions (from epd7in3f.py)
# These are the ONLY RGB values the display recognizes properly
WAVESHARE_EPD_COLORS = {
    'BLACK':  (0x00, 0x00, 0x00),  # Pure black
    'WHITE':  (0xFF, 0xFF, 0xFF),  # Pure white  
    'RED':    (0xFF, 0x00, 0x00),  # Pure red
    'GREEN':  (0x00, 0xFF, 0x00),  # Pure green
    'BLUE':   (0x00, 0x00, 0xFF),  # Pure blue
    'YELLOW': (0xFF, 0xFF, 0x00),  # Pure yellow
    'ORANGE': (0xFF, 0x80, 0x00),  # Pure orange
}

# RGB values as integers for easy comparison
WAVESHARE_RGB_VALUES = [
    (0, 0, 0),      # BLACK
    (255, 255, 255), # WHITE
    (255, 0, 0),    # RED
    (0, 255, 0),    # GREEN
    (0, 0, 255),    # BLUE
    (255, 255, 0),  # YELLOW
    (255, 128, 0),  # ORANGE
]

def get_closest_epd_color(rgb_color):
    """
    Map any RGB color to the closest Waveshare EPD color.
    
    Args:
        rgb_color: Tuple of (R, G, B) values (0-255)
        
    Returns:
        Tuple of (R, G, B) values for closest EPD color
    """
    r, g, b = rgb_color
    
    # Calculate distance to each EPD color
    min_distance = float('inf')
    closest_color = WAVESHARE_RGB_VALUES[0]  # Default to black
    
    for epd_color in WAVESHARE_RGB_VALUES:
        er, eg, eb = epd_color
        # Euclidean distance in RGB space
        distance = ((r - er) ** 2 + (g - eg) ** 2 + (b - eb) ** 2) ** 0.5
        
        if distance < min_distance:
            min_distance = distance
            closest_color = epd_color
    
    return closest_color

def fix_image_colors(image):
    """
    Convert any PIL Image to use only Waveshare EPD colors.
    
    Args:
        image: PIL Image object
        
    Returns:
        PIL Image with colors mapped to EPD palette
    """
    from PIL import Image
    
    # Convert to RGB if not already
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # Get image data
    pixels = image.load()
    width, height = image.size
    
    # Create new image with fixed colors
    fixed_image = Image.new('RGB', (width, height))
    fixed_pixels = fixed_image.load()
    
    # Map each pixel to closest EPD color
    for y in range(height):
        for x in range(width):
            original_color = pixels[x, y]
            fixed_color = get_closest_epd_color(original_color)
            fixed_pixels[x, y] = fixed_color
    
    return fixed_image

def create_fee_colors_corrected():
    """
    Return fee scale colors using EXACT EPD colors.
    This replaces the problematic fee_to_color function.
    """
    return {
        'green': WAVESHARE_EPD_COLORS['GREEN'],    # Low fees
        'yellow': WAVESHARE_EPD_COLORS['YELLOW'],  # Medium fees  
        'orange': WAVESHARE_EPD_COLORS['ORANGE'],  # High fees
        'red': WAVESHARE_EPD_COLORS['RED'],        # Very high fees
        'blue': WAVESHARE_EPD_COLORS['BLUE'],      # Extreme fees
        'black': WAVESHARE_EPD_COLORS['BLACK'],    # Maximum fees
    }

def validate_color_mapping():
    """Test function to validate color mappings"""
    print("Waveshare 7.3F EPD Color Validation:")
    print("=" * 50)
    
    for name, rgb in WAVESHARE_EPD_COLORS.items():
        print(f"{name:8}: RGB{rgb} = #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")
    
    print("\nFee Scale Colors:")
    print("-" * 30)
    fee_colors = create_fee_colors_corrected()
    for fee_level, rgb in fee_colors.items():
        print(f"{fee_level:8}: RGB{rgb} = #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}")

if __name__ == "__main__":
    validate_color_mapping()
