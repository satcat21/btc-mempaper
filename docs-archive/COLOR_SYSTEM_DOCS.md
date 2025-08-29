# Color Configuration Documentation

## New Color System with LUT Support

Your configuration now uses named colors instead of RGB arrays. This provides:

1. **Dual Display Support**: Different colors for web vs e-ink automatically
2. **User-Friendly Names**: No more complex RGB arrays
3. **Dropdown Selection**: Easy color picking in web interface

## Current Configuration

```json
{
  "date_color_normal": "forest_green",
  "date_color_holiday": "fire_brick", 
  "holiday_title_color": "peru",
  "holiday_description_color": "chocolate"
}
```

## Available Color Options

### Greens
- `forest_green` - Forest Green (web: soft, e-ink: bright)
- `lime_green` - Lime Green  
- `dark_green` - Dark Green

### Reds
- `fire_brick` - Fire Brick (web: muted, e-ink: pure red)
- `crimson` - Crimson
- `dark_red` - Dark Red

### Oranges/Browns
- `peru` - Peru (web: earthy, e-ink: bright orange)
- `chocolate` - Chocolate
- `saddle_brown` - Saddle Brown

### Blues
- `steel_blue` - Steel Blue (web: soft, e-ink: bright blue)
- `royal_blue` - Royal Blue
- `navy_blue` - Navy Blue

### Yellows/Golds
- `goldenrod` - Goldenrod (web: muted, e-ink: bright yellow)
- `gold` - Gold
- `dark_goldenrod` - Dark Goldenrod

### Neutrals
- `black` - Black
- `gray` - Gray (web: gray, e-ink: black)
- `dark_gray` - Dark Gray

## How It Works

1. **Web Display**: Uses soft, eye-friendly colors
2. **E-ink Display**: Automatically maps to 7-color e-ink palette
3. **Configuration**: Single color name works for both displays

## Benefits

- ✅ **No more RGB arrays** - Just friendly color names
- ✅ **Automatic optimization** - Web gets soft colors, e-ink gets optimized colors
- ✅ **Easy configuration** - Dropdown menus instead of number inputs
- ✅ **Future-proof** - Add new colors without changing config format
