"""
Color Look-Up Table (LUT) System for Dual Display Support

This module provides color mapping between web-friendly colors and e-ink optimized colors.
Each named color maps to different RGB values for web display vs e-ink display.
"""

class ColorLUT:
    """Color Look-Up Table for web and e-ink display color mapping."""
    
    # 7-color e-ink palette (official Waveshare intense colors)
    EINK_PALETTE = {
        "black": [0, 0, 0],
        "white": [255, 255, 255], 
        "green": [0, 255, 0],      # Intense green instead of [100, 255, 100]
        "blue": [0, 0, 255],       # Intense blue instead of [150, 200, 255]
        "red": [255, 0, 0],
        "yellow": [255, 255, 0],
        "orange": [255, 128, 0]
    }
    
    # Color definitions with web-friendly and e-ink optimized versions
    COLOR_DEFINITIONS = {
        # Greens
        "forest_green": {
            "web": [34, 139, 34],      # Web-friendly forest green
            "eink": [0, 255, 0],       # E-ink intense green
            "name": "Forest Green"
        },
        "lime_green": {
            "web": [50, 205, 50],      # Web lime green
            "eink": [0, 255, 0],       # E-ink intense green
            "name": "Lime Green"
        },
        "dark_green": {
            "web": [0, 100, 0],        # Web dark green
            "eink": [0, 255, 0],       # E-ink intense green
            "name": "Dark Green"
        },
        
        # Reds
        "fire_brick": {
            "web": [178, 34, 34],      # Web-friendly fire brick
            "eink": [255, 0, 0],       # E-ink red from palette
            "name": "Fire Brick"
        },
        "crimson": {
            "web": [220, 20, 60],      # Web crimson
            "eink": [255, 0, 0],       # E-ink red from palette
            "name": "Crimson"
        },
        "dark_red": {
            "web": [139, 0, 0],        # Web dark red
            "eink": [255, 0, 0],       # E-ink red from palette
            "name": "Dark Red"
        },
        
        # Oranges
        "peru": {
            "web": [205, 133, 63],     # Web-friendly peru
            "eink": [255, 128, 0],     # E-ink orange from palette
            "name": "Peru"
        },
        "chocolate": {
            "web": [210, 105, 30],     # Web chocolate
            "eink": [255, 128, 0],     # E-ink orange from palette
            "name": "Chocolate"
        },
        "saddle_brown": {
            "web": [139, 69, 19],      # Web saddle brown
            "eink": [255, 128, 0],     # E-ink orange from palette
            "name": "Saddle Brown"
        },
        
        # Blues
        "steel_blue": {
            "web": [70, 130, 180],     # Web-friendly steel blue
            "eink": [0, 0, 255],       # E-ink intense blue
            "name": "Steel Blue"
        },
        "royal_blue": {
            "web": [65, 105, 225],     # Web royal blue
            "eink": [0, 0, 255],       # E-ink intense blue
            "name": "Royal Blue"
        },
        "navy_blue": {
            "web": [0, 0, 128],        # Web navy blue
            "eink": [0, 0, 255],       # E-ink intense blue
            "name": "Navy Blue"
        },
        
        # Yellows/Golds
        "goldenrod": {
            "web": [218, 165, 32],     # Web-friendly goldenrod
            "eink": [255, 255, 0],     # E-ink yellow from palette
            "name": "Goldenrod"
        },
        "gold": {
            "web": [255, 215, 0],      # Web gold
            "eink": [255, 255, 0],     # E-ink yellow from palette
            "name": "Gold"
        },
        "dark_goldenrod": {
            "web": [184, 134, 11],     # Web dark goldenrod
            "eink": [255, 255, 0],     # E-ink yellow from palette
            "name": "Dark Goldenrod"
        },
        
        # Neutrals
        "black": {
            "web": [0, 0, 0],          # Black for both
            "eink": [0, 0, 0],         # Black for both
            "name": "Black"
        },
        "gray": {
            "web": [128, 128, 128],    # Web gray
            "eink": [0, 0, 0],         # E-ink black (no gray available)
            "name": "Gray"
        },
        "dark_gray": {
            "web": [64, 64, 64],       # Web dark gray
            "eink": [0, 0, 0],         # E-ink black
            "name": "Dark Gray"
        }
    }
    
    @classmethod
    def get_color(cls, color_name, display_type="web"):
        """
        Get RGB color values for a named color and display type.
        
        Args:
            color_name (str): Named color from COLOR_DEFINITIONS
            display_type (str): "web" or "eink"
            
        Returns:
            list: RGB color values [R, G, B]
        """
        if color_name not in cls.COLOR_DEFINITIONS:
            # Fallback to black if color not found
            return [0, 0, 0]
        
        color_def = cls.COLOR_DEFINITIONS[color_name]
        return color_def.get(display_type, color_def["web"])
    
    @classmethod
    def get_color_options(cls):
        """
        Get list of available color options for web interface.
        
        Returns:
            dict: {color_key: display_name} mapping
        """
        return {key: value["name"] for key, value in cls.COLOR_DEFINITIONS.items()}
    
    @classmethod
    def get_color_categories(cls):
        """
        Get colors organized by category for web interface.
        
        Returns:
            dict: Categories with color options
        """
        return {
            "Greens": {
                "forest_green": "Forest Green",
                "lime_green": "Lime Green", 
                "dark_green": "Dark Green"
            },
            "Reds": {
                "fire_brick": "Fire Brick",
                "crimson": "Crimson",
                "dark_red": "Dark Red"
            },
            "Oranges/Browns": {
                "peru": "Peru",
                "chocolate": "Chocolate",
                "saddle_brown": "Saddle Brown"
            },
            "Blues": {
                "steel_blue": "Steel Blue",
                "royal_blue": "Royal Blue",
                "navy_blue": "Navy Blue"
            },
            "Yellows/Golds": {
                "goldenrod": "Goldenrod",
                "gold": "Gold",
                "dark_goldenrod": "Dark Goldenrod"
            },
            "Neutrals": {
                "black": "Black",
                "gray": "Gray",
                "dark_gray": "Dark Gray"
            }
        }
