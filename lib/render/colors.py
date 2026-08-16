"""Palette handling: theme color lookup and the e-paper quantisation that
maps a full-color render onto the panel's fixed ink set.
"""

from PIL import Image
from utils.color_lut import ColorLUT


class ColorMixin:
    """Palette handling: theme color lookup and the e-paper quantisation that"""

    def get_color(self, color_name, web_quality=False):
        """
        Get RGB color values for a color key (theme) or named color.
        For web images, uses COLOR_SETS for light/dark mode.
        For e-ink, uses ColorLUT and EPD color mapping.

        Args:
            color_name (str or list): Color key (for theme) or named color or RGB array
            web_quality (bool): True for web display, False for e-ink

        Returns:
            tuple: RGB color tuple
        """
        """
        Get RGB color values for a color key (theme) or named color.
        For web images, uses COLOR_SETS for light/dark mode.
        For e-ink, uses ColorLUT and EPD color mapping.
        """
        # Use self.color_sets for web images
        if web_quality and isinstance(color_name, str) and color_name in self.color_sets["light"]:
            mode = "dark" if self.config.get("color_mode_dark", True) else "light"
            hex_color = self.color_sets[mode].get(color_name, "#ffffff")
            hex_color = hex_color.lstrip("#")
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            return rgb

        # For e-ink images, use dark mode if enabled
        if not web_quality and isinstance(color_name, str) and color_name in self.color_sets["light"]:
            mode = "dark" if self.config.get("eink_dark_mode", False) else "light"
            hex_color = self.color_sets[mode].get(color_name, "#ffffff")

            # For e-ink dark mode background, use pure black for better readability
            if mode == "dark" and color_name == "background":
                hex_color = "#000000"

            hex_color = hex_color.lstrip("#")
            rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            return rgb
    
        # If it's a direct RGB list
        if isinstance(color_name, list) and len(color_name) == 3:
            return tuple(color_name)

        # For named colors (legacy or e-ink)
        if isinstance(color_name, str):
            if web_quality:
                # Use ColorLUT for web display
                display_type = "web"
                rgb_values = ColorLUT.get_color(color_name, display_type)
                return tuple(rgb_values)
            else:
                # Map named colors directly to EPD colors for e-ink
                from utils.epd_color_fix import WAVESHARE_EPD_COLORS
                color_mapping = {
                    'black': WAVESHARE_EPD_COLORS['BLACK'],
                    'white': WAVESHARE_EPD_COLORS['WHITE'],
                    'red': WAVESHARE_EPD_COLORS['RED'],
                    'fire_brick': WAVESHARE_EPD_COLORS['RED'],
                    'green': WAVESHARE_EPD_COLORS['GREEN'],
                    'forest_green': WAVESHARE_EPD_COLORS['GREEN'],
                    'blue': WAVESHARE_EPD_COLORS['BLUE'],
                    'steel_blue': WAVESHARE_EPD_COLORS['BLUE'],
                    'yellow': WAVESHARE_EPD_COLORS['YELLOW'],
                    'goldenrod': WAVESHARE_EPD_COLORS['YELLOW'],
                    'orange': WAVESHARE_EPD_COLORS['ORANGE'],
                    'peru': WAVESHARE_EPD_COLORS['ORANGE'],
                    'chocolate': WAVESHARE_EPD_COLORS['ORANGE'],
                }
                if color_name.lower() in color_mapping:
                    return color_mapping[color_name.lower()]
                else:
                    # Fallback: try ColorLUT then map to closest EPD color
                    try:
                        rgb_values = ColorLUT.get_color(color_name, "eink")
                        from utils.epd_color_fix import get_closest_epd_color
                        return get_closest_epd_color(tuple(rgb_values))
                    except:
                        return WAVESHARE_EPD_COLORS['BLACK']  # Safe fallback

        # Fallback to black
        if web_quality:
            return (0, 0, 0)
        else:
            from utils.epd_color_fix import WAVESHARE_EPD_COLORS
            return WAVESHARE_EPD_COLORS['BLACK']
    
    def convert_to_7color(self, img, use_meme_optimization=False):
        """
        Convert image to 7-color palette suitable for e-Paper display.
        
        Args:
            img (PIL.Image): Input image
            use_meme_optimization (bool): Apply enhanced processing for meme images
            
        Returns:
            PIL.Image: Converted image with 7-color palette
        """
        palette_img = Image.new("P", (1, 1))
        palette_img.putpalette(self.palette)
        
        if use_meme_optimization:
            # Enhanced processing for memes: better color mixing
            # Apply slight contrast boost for better color definition
            from PIL import ImageEnhance
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)
            
            # Use Floyd-Steinberg dithering for better color gradients in memes
            return img.convert("RGB").quantize(palette=palette_img, dither=Image.FLOYDSTEINBERG).convert("RGB")
        else:
            # Clean processing for text areas: no dithering for sharp text
            return img.convert("RGB").quantize(palette=palette_img, dither=Image.NONE).convert("RGB")
    
    def remove_graining_from_pil(self, img, threshold=30):
        """
        Remove graining artifacts from palettized images.
        
        Args:
            img (PIL.Image): Input image in palette mode
            threshold (int): Darkness threshold for pixel cleanup
            
        Returns:
            PIL.Image: Cleaned image
        """
        if img.mode != "P":
            return img
        
        palette = img.getpalette()
        pixels = img.load()
        
        for y in range(img.height):
            for x in range(img.width):
                index = pixels[x, y]
                r, g, b = palette[index * 3 : index * 3 + 3]
                
                if r < threshold and g < threshold and b < threshold:
                    pixels[x, y] = 0  # Set to pure black in palette
        
        return img
