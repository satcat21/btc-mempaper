#!/usr/bin/env python3
"""
Advanced Color Intensity Booster for E-ink Display

This script provides multiple options to boost color intensity:
1. Enhanced image preprocessing with gamma correction
2. Color saturation boosting 
3. Advanced omni-epd settings
4. Color channel intensity amplification
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageEnhance, ImageOps
import json

def create_enhanced_omni_config():
    """Create an enhanced omni-epd configuration with maximum color intensity"""
    
    enhanced_config = """# Configuration for Waveshare 7.3" F 7-color e-ink display
# ENHANCED VERSION - Maximum Color Intensity

# No EPD section - let omni-epd use default mode for this display

[Display]
rotate=0
flip_horizontal=False
flip_vertical=False
dither=None

[Image Enhancements]
# MAXIMUM INTENSITY SETTINGS for brightest possible e-ink colors
# Using official Waveshare palette with maximum intensity RGB values
palette_filter=[[0,0,0], [255,255,255], [0,255,0], [0,0,255], [255,0,0], [255,255,0], [255,128,0]]

# BOOST ALL ENHANCEMENT VALUES for maximum color intensity
contrast=1.5       # Maximum contrast boost (was 1.2)
brightness=1.5     # Maximum brightness boost (was 1.3) 
sharpness=1.2      # Slight sharpness boost for color definition
saturation=1.4     # NEW: Color saturation boost for more vivid colors

# Additional advanced settings for color intensity
gamma=0.8          # Lower gamma for brighter mid-tones
auto_level=True    # Auto-level for optimal color range
"""

    # Write the enhanced config
    with open("waveshare_epd.epd7in3f.enhanced.ini", "w") as f:
        f.write(enhanced_config)
    
    print("✅ Enhanced omni-epd config created: waveshare_epd.epd7in3f.enhanced.ini")
    return "waveshare_epd.epd7in3f.enhanced.ini"

def boost_image_colors(image_path, output_path=None):
    """
    Apply advanced color intensity boosting to an image before e-ink display.
    
    Args:
        image_path (str): Path to input image
        output_path (str): Path for boosted output image
        
    Returns:
        PIL.Image: Color-boosted image
    """
    if output_path is None:
        output_path = image_path.replace(".png", "_boosted.png")
    
    print(f"🎨 Boosting colors in: {image_path}")
    
    # Load image
    img = Image.open(image_path)
    original_img = img.copy()
    
    # Step 1: Gamma correction for brighter mid-tones
    print("  📈 Applying gamma correction...")
    gamma = 0.8  # Lower gamma = brighter
    gamma_table = [int(((i / 255.0) ** gamma) * 255) for i in range(256)]
    img = img.point(gamma_table * 3)  # Apply to all RGB channels
    
    # Step 2: Saturation boost for more vivid colors
    print("  🌈 Boosting color saturation...")
    enhancer = ImageEnhance.Color(img)
    img = enhancer.enhance(1.6)  # 60% more saturated colors
    
    # Step 3: Contrast enhancement for better color separation
    print("  ⚡ Enhancing contrast...")
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.3)  # 30% more contrast
    
    # Step 4: Brightness boost
    print("  💡 Boosting brightness...")
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.2)  # 20% brighter
    
    # Step 5: Color channel amplification for e-ink colors
    print("  🔥 Amplifying color channels...")
    pixels = img.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b = pixels[x, y]
            
            # Amplify primary colors that match e-ink palette
            if g > r and g > b:  # Green dominant
                g = min(255, int(g * 1.1))  # Boost green
            elif b > r and b > g:  # Blue dominant  
                b = min(255, int(b * 1.1))  # Boost blue
            elif r > g and r > b:  # Red dominant
                r = min(255, int(r * 1.1))  # Boost red
            elif r > 200 and g > 200:  # Yellow (red + green)
                r = min(255, int(r * 1.05))
                g = min(255, int(g * 1.05))
            elif r > 200 and g > 100 and b < 100:  # Orange (red + some green)
                r = min(255, int(r * 1.05))
                g = min(255, int(g * 1.1))
            
            pixels[x, y] = (r, g, b)
    
    # Save boosted image
    img.save(output_path)
    print(f"✅ Color-boosted image saved: {output_path}")
    
    return img

def test_color_intensity_levels():
    """Test different intensity levels and generate comparison images"""
    print("=== TESTING MULTIPLE COLOR INTENSITY LEVELS ===\n")
    
    # Create test images with different intensity levels
    test_configs = [
        ("Conservative", {"contrast": 1.2, "brightness": 1.3, "saturation": 1.0}),
        ("Moderate", {"contrast": 1.4, "brightness": 1.4, "saturation": 1.2}),
        ("Aggressive", {"contrast": 1.5, "brightness": 1.5, "saturation": 1.4}),
        ("Maximum", {"contrast": 1.7, "brightness": 1.6, "saturation": 1.6})
    ]
    
    for level_name, settings in test_configs:
        print(f"📊 Creating {level_name} intensity config...")
        
        config_content = f"""# {level_name} Color Intensity Configuration
[Display]
rotate=0
flip_horizontal=False
flip_vertical=False
dither=None

[Image Enhancements]
palette_filter=[[0,0,0], [255,255,255], [0,255,0], [0,0,255], [255,0,0], [255,255,0], [255,128,0]]
contrast={settings['contrast']:.1f}
brightness={settings['brightness']:.1f}
sharpness=1.1
saturation={settings['saturation']:.1f}
gamma=0.8
"""
        
        filename = f"waveshare_epd.epd7in3f.{level_name.lower()}.ini"
        with open(filename, "w") as f:
            f.write(config_content)
        
        print(f"  ✅ {filename} created")
        print(f"     Contrast: {settings['contrast']:.1f}x, Brightness: {settings['brightness']:.1f}x, Saturation: {settings['saturation']:.1f}x")
    
    print(f"\n🎛️ Created 4 different intensity configurations!")
    print("Test them by renaming the desired config to 'waveshare_epd.epd7in3f.ini'")

def analyze_current_setup():
    """Analyze the current color setup and suggest improvements"""
    print("=== CURRENT COLOR SETUP ANALYSIS ===\n")
    
    # Check current omni-epd config
    config_file = "waveshare_epd.epd7in3f.ini"
    if os.path.exists(config_file):
        print(f"📋 Current omni-epd config ({config_file}):")
        with open(config_file, "r") as f:
            content = f.read()
            
        # Extract current settings
        lines = content.split('\n')
        current_settings = {}
        for line in lines:
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.split('#')[0].strip()  # Remove comments
                if key in ['contrast', 'brightness', 'sharpness']:
                    try:
                        current_settings[key] = float(value)
                    except:
                        pass
        
        print("  Current enhancement values:")
        for key, value in current_settings.items():
            intensity_level = "LOW" if value <= 1.0 else "MEDIUM" if value <= 1.3 else "HIGH"
            print(f"    {key}: {value} ({intensity_level})")
        
        # Suggest improvements
        print("\n💡 Suggestions for brighter colors:")
        if current_settings.get('brightness', 1.0) < 1.5:
            print(f"  🔆 Increase brightness from {current_settings.get('brightness', 1.0)} to 1.5")
        if current_settings.get('contrast', 1.0) < 1.4:
            print(f"  ⚡ Increase contrast from {current_settings.get('contrast', 1.0)} to 1.4")
        if 'saturation' not in current_settings:
            print(f"  🌈 Add saturation=1.3 for more vivid colors")
    
    else:
        print(f"❌ omni-epd config not found: {config_file}")
    
    # Check if show_image.py has color quantization disabled
    show_image_path = "display/show_image.py"
    if os.path.exists(show_image_path):
        with open(show_image_path, "r") as f:
            content = f.read()
        
        if "# try:" in content or "DISABLED" in content:
            print(f"\n📝 show_image.py analysis:")
            print("  ✅ Color quantization is disabled (good - lets omni-epd handle it)")
        else:
            print(f"\n⚠️ show_image.py might be doing additional color processing")
    
    print(f"\n🎯 RECOMMENDATION: Try the 'Aggressive' or 'Maximum' intensity configs!")

if __name__ == "__main__":
    print("🎨 E-INK COLOR INTENSITY BOOSTER")
    print("=" * 50)
    
    # Analyze current setup
    analyze_current_setup()
    
    print("\n" + "=" * 50)
    
    # Create enhanced configurations
    test_color_intensity_levels()
    
    print("\n" + "=" * 50)
    print("🚀 NEXT STEPS:")
    print("1. Try the 'Maximum' intensity config:")
    print("   mv waveshare_epd.epd7in3f.maximum.ini waveshare_epd.epd7in3f.ini")
    print("2. Test the display with a colorful image")
    print("3. If still too dark, the issue might be hardware-related")
    print("   (e-ink display calibration or driver limitations)")
