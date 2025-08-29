#!/usr/bin/python

# Import the required libraries
import os
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw 

class Processor():
    def __init__(self, img_path = None, display_width = None, display_height = None, textmsg = None, padding_color = (0, 0, 0)):
        self.img = Image.open(img_path)
        self.display_width = display_width
        self.display_height = display_height
        self.textmsg = textmsg
        self.padding_color = padding_color

    def process(self):
        # Manages the overall preparation of the image, from scaling, centering,
        # and overlaying an optional text warning.
        
        # CRITICAL FIX: Quantize to exact EPD colors BEFORE any processing
        # This prevents scaling/resampling from creating intermediate colors
        self.img = self.quantize_to_exact_epd_colors(self.img)
        
        # Scale and center with color preservation
        self.img = self.scale_preserve_colors(self.img)
        self.img = self.center(self.img)
        
        # Add text overlay
        if self.textmsg is not None and len(self.textmsg) > 1:
            self.img = self.add_text(self.img)
        
        # Final quantization to ensure exact colors after any text overlay
        self.img = self.quantize_to_exact_epd_colors(self.img)
    
    def quantize_to_exact_epd_colors(self, img):
        """
        Quantize to exact Waveshare EPD colors using nearest-neighbor mapping.
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
                closest_color = self.find_closest_epd_color(original_color, epd_colors)
                new_pixels[x, y] = closest_color
        
        return new_img
    
    def find_closest_epd_color(self, rgb_color, epd_colors):
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
    
    def scale_preserve_colors(self, img):
        """
        Scale image while preserving exact EPD colors.
        Uses nearest-neighbor resampling to avoid color interpolation.
        """
        # Get original dimensions
        orig_width, orig_height = img.size
        target_width, target_height = self.display_width, self.display_height
        
        # If already correct size, return as-is
        if (orig_width, orig_height) == (target_width, target_height):
            return img
        
        # Calculate scaling factors for both dimensions
        scale_x = target_width / orig_width
        scale_y = target_height / orig_height
        
        # Use the larger scale factor to ensure the image fills the screen
        scale = max(scale_x, scale_y)
        
        # Calculate new dimensions
        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)
        
        # CRITICAL: Use NEAREST resampling to preserve exact colors
        # LANCZOS creates intermediate colors that don't match EPD palette
        img = img.resize((new_width, new_height), Image.Resampling.NEAREST)
        
        # If the scaled image is larger than display, crop from center
        if new_width > target_width or new_height > target_height:
            left = (new_width - target_width) // 2
            top = (new_height - target_height) // 2
            right = left + target_width
            bottom = top + target_height
            img = img.crop((left, top, right, bottom))
        
        return img
    
    def quantize_to_waveshare_7color(self, img):
        """
        Quantize image to exact Waveshare 7.3" F display colors
        Based on official Waveshare library palette
        """
        # Ensure RGB mode
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Create palette exactly as Waveshare library does
        palette_colors = [
            (0, 0, 0),       # Black
            (255, 255, 255), # White  
            (0, 255, 0),     # Green
            (0, 0, 255),     # Blue
            (255, 0, 0),     # Red
            (255, 255, 0),   # Yellow
            (255, 128, 0),   # Orange (Waveshare uses 128, not 165)
        ]
        
        # Create palette image with exact same method as Waveshare
        pal_image = Image.new("P", (1, 1))
        # Flatten RGB tuples and pad to 256 colors * 3 values = 768 total
        palette_flat = []
        for color in palette_colors:
            palette_flat.extend(color)
        # Pad remaining slots with black
        palette_flat.extend([0, 0, 0] * (256 - len(palette_colors)))
        pal_image.putpalette(palette_flat)
        
        # Quantize with Floyd-Steinberg dithering (same as Waveshare)
        quantized = img.quantize(palette=pal_image, dither=Image.Dither.FLOYDSTEINBERG)
        
        # Convert back to RGB for display driver
        return quantized.convert('RGB')

    def scale(self, img):
        """
        Resizes the image to fill the entire display.
        Uses smart scaling to maintain aspect ratio with minimal cropping.
        """
        # Get original dimensions
        orig_width, orig_height = img.size
        target_width, target_height = self.display_width, self.display_height
        
        # Calculate scaling factors for both dimensions
        scale_x = target_width / orig_width
        scale_y = target_height / orig_height
        
        # Use the larger scale factor to ensure the image fills the screen
        # This may crop some content but eliminates black borders
        scale = max(scale_x, scale_y)
        
        # Calculate new dimensions
        new_width = int(orig_width * scale)
        new_height = int(orig_height * scale)
        
        # Resize the image
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # If the scaled image is larger than display, crop from center
        if new_width > target_width or new_height > target_height:
            left = (new_width - target_width) // 2
            top = (new_height - target_height) // 2
            right = left + target_width
            bottom = top + target_height
            img = img.crop((left, top, right, bottom))
        
        return img

    def add_text(self, img):
        try:
            # Try to use the project's font first
            font_path = os.path.join("..", "fonts", "Roboto-Regular.ttf")
            if not os.path.exists(font_path):
                # Fallback to a system font or Pillow default
                try:
                    font = ImageFont.truetype("arial.ttf", 36)
                except OSError:
                    # Use default font if no TrueType font is available
                    font = ImageFont.load_default()
            else:
                font = ImageFont.truetype(font_path, 36)
        except Exception:
            # Fallback to default font
            font = ImageFont.load_default()
            
        draw = ImageDraw.Draw(img)
        
        # CRITICAL: Use exact EPD colors for text overlay
        draw.rectangle([(0, 0), (img.width, 75)],
                       fill=(0, 0, 0),        # EPD BLACK
                       outline=None)
        draw.text((10, 30), self.textmsg, font=font, fill=(255, 255, 255))  # EPD WHITE

        return img

    def center(self, img):
        """
        Ensure the image exactly matches display dimensions.
        Uses nearest-neighbor resampling to preserve exact colors.
        """
        if img.size == (self.display_width, self.display_height):
            return img
        
        # CRITICAL: Use NEAREST resampling to preserve exact EPD colors
        img = img.resize((self.display_width, self.display_height), Image.Resampling.NEAREST)
        return img