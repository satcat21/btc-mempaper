# Waveshare EPD Drivers

This directory holds Waveshare e-Paper display driver files bundled directly
with the mempaper project for convenience.

## Files

| File | Display | Colors |
|------|---------|--------|
| `epd13in3E.py` | 13.3inch e-Paper HAT+ (E) | 6-color (BWRYGBl) |
| `epd7in3f.py` | 7.3inch e-Paper HAT (F) | 7-color (BWRYGBO) |
| `epdconfig.py` | Shared hardware config (SPI/GPIO) | — |

## Installation

Run the display configuration tool from the project root:

```bash
python scripts/configure_display.py
```

This downloads the official Waveshare driver files for your selected display
and places them in the appropriate subdirectory here.

## License

These driver files are copyright Waveshare Electronics and are released under
the **MIT License**. The mempaper project (GPL-3.0) bundles them with
attribution as permitted by the MIT license.

Original sources:
- 13.3E: https://www.waveshare.com/wiki/13.3inch_e-Paper_HAT%2B_(E)
- 7.3F: https://github.com/waveshare/e-Paper
