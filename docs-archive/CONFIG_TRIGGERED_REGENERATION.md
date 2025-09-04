# Configuration-Triggered Image Regeneration System

## Overview

This feature automatically regenerates dashboard images when configuration settings that affect the visual appearance are changed, while preserving the currently displayed meme to maintain visual consistency.

## How It Works

### 1. Configuration Change Detection

The system monitors configuration changes through the `ConfigManager` callback system and identifies changes to image-affecting settings:

#### Hardware Settings
- `display_orientation` - Portrait vs landscape layout
- `display_width` / `display_height` - Canvas dimensions  
- `e-ink-display-connected` - Display type affects color rendering
- `omni_device_name` - E-ink device type
- `block_height_area` - Reserved space for block info

#### Design Settings  
- `font_regular` / `font_bold` - Typography affects layout
- `date_color_normal` / `date_color_holiday` - Date text colors
- `holiday_title_color` / `holiday_description_color` - Holiday text colors

#### Display Behavior
- `hide_holiday_if_large_meme` - Holiday display logic
- `language` - Affects text formatting and translations

#### Mempool Settings
- `fee_parameter` - Changes fee type display and block height coloring

### 2. Meme Caching System

**Cache Metadata Structure:**
```json
{
  "block_height": "909153",
  "block_hash": "000...975", 
  "timestamp": 1754645822.512331,
  "image_path": "current.png",
  "eink_image_path": "current_eink.png",
  "current_meme_path": "static/memes/bitcoin_hodl.jpg"
}
```

**Meme Preservation Logic:**
- When generating new images, the selected meme path is cached
- On configuration changes, the same meme is reused for visual consistency
- If cached meme no longer exists, falls back to random selection

### 3. Immediate Regeneration Process

**Trigger Conditions:**
1. Configuration change detected
2. Change affects image-affecting settings
3. Current image cache exists with valid meme

**Regeneration Flow:**
```
Config Change → Detection → Meme Cache Check → Image Regeneration → E-ink Update → Web Client Notification
```

## Implementation Details

### Image Renderer Updates

**New Method: `render_dual_images_with_cached_meme()`**
- Uses pre-selected meme path instead of random selection
- Maintains same rendering pipeline for consistency
- Returns both web and e-ink optimized images

**Enhanced Method: `render_dual_images()`**
- Now returns the selected meme path for caching
- Enables meme persistence across regenerations

### Application Integration

**Configuration Callback: `_on_config_change()`**
- Compares old vs new configuration
- Identifies image-affecting changes
- Triggers immediate regeneration with cached meme

**Cache Management: Enhanced Metadata**
- Extended cache structure includes meme path
- Automatic cache restoration on app restart
- Fallback handling for missing cached memes

## User Experience Benefits

### 1. **Visual Consistency**
- Configuration changes don't disrupt current meme display
- Users can adjust settings without losing their current image

### 2. **Immediate Feedback**
- Color changes appear instantly
- Font adjustments visible immediately  
- Layout changes take effect right away

### 3. **Seamless Integration**
- Works with existing cache system
- No impact on normal block update flow
- Maintains performance optimization

## Example Scenarios

### Scenario 1: Color Theme Change
```
User changes fee_parameter from "minimumFee" to "economyFee"
→ Block height color updates immediately
→ Fee text changes from "Minimum fee: X" to "Economy fee: X"  
→ Same meme remains displayed
→ E-ink display refreshes with new colors
```

### Scenario 2: Language Switch
```
User changes language from "en" to "de"
→ Date format updates to German
→ All labels translate to German
→ Holiday info switches to German text
→ Same meme preserved for continuity
```

### Scenario 3: Display Orientation Change
```
User changes display_orientation from "vertical" to "horizontal"
→ Layout recomputes for landscape format
→ Text positioning adjusts automatically
→ Same meme scales to new aspect ratio
→ E-ink display rotates appropriately
```

## Technical Benefits

### 1. **Performance Optimization**
- No API calls for meme selection during regeneration
- Cached meme reduces processing time
- Efficient dual-image generation pipeline

### 2. **Reliability**
- Graceful fallback if cached meme missing
- Thread-safe regeneration with locks
- Error handling preserves application stability

### 3. **Maintainability**
- Clear separation of concerns
- Extensible setting categories
- Comprehensive error logging

## Configuration Categories

Settings are categorized by impact type:

| Category | Purpose | Examples |
|----------|---------|----------|
| **Hardware** | Device capabilities | display size, e-ink type |
| **Design** | Visual appearance | colors, fonts |
| **Layout** | Content arrangement | orientation, spacing |
| **Content** | Information display | language, fee parameters |

## Future Enhancements

### Potential Additions
- User-selectable meme persistence duration
- Configuration change history tracking
- Batch setting updates with single regeneration
- Preview mode for testing settings

### Integration Opportunities  
- Web interface preview before applying changes
- A/B testing of visual configurations
- Automated theme switching based on time/events
- Custom color scheme creation tools

## Debugging and Monitoring

### Log Messages
```
🔧 Configuration change detected, checking if image refresh needed...
🎨 Image-affecting settings changed: fee_parameter: minimumFee → economyFee  
🔄 Triggering immediate image refresh with cached meme...
📦 Using cached meme: bitcoin_hodl.jpg
✅ Image regeneration completed successfully
```

### Error Handling
- Missing cached meme → fallback to random selection
- Invalid configuration → ignore change, log warning
- Regeneration failure → retry with normal generation
- E-ink display error → continue with web update

This system provides a responsive, user-friendly experience while maintaining the performance and reliability of the dashboard application.
