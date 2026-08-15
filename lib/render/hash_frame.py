"""The block-hash frame around the meme and the block info drawn inside it.
"""

from PIL import Image
from PIL import ImageDraw


class HashFrameMixin:
    """The block-hash frame around the meme and the block info drawn inside it."""

    def add_rounded_corners(self, img, radius):
        # Create mask
        mask = Image.new('L', img.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, img.size[0], img.size[1]], radius=radius, fill=255)
        # Apply mask
        img_rounded = img.copy()
        img_rounded.putalpha(mask)
        return img_rounded

    def interpolate_color(self, start, end, t):
        return tuple(int(start[i] + (end[i] - start[i]) * t) for i in range(3))

    def draw_hash_frame(self, draw, x_init, y_init, block_hash, rect_width=760, rect_height=80, max_width=None, web_quality=True, center=False):
        """
        Draws a block hash as a rectangular frame starting at (x, y).
        """
        padding = self._scale_px(40, min_value=16)
        # On wide screens increase interior breathing room so fee text stays inside the frame.
        extra_space = self._scale_px(11, min_value=3) if self.width >= 1000 else self._scale_px(8, min_value=3)
        # On holidays use the holiday gradient so hashframe matches the holiday date text
        if self.get_today_btc_holiday():
            start_color = self.get_color("holiday_start", web_quality)
            end_color   = self.get_color("holiday_end",   web_quality)
        else:
            start_color = self.get_color("hash_start", web_quality)
            end_color   = self.get_color("hash_end",   web_quality)

        total_chars = len(block_hash)
        block_hash_colors = [self.interpolate_color(start_color, end_color, i / max(total_chars - 1, 1)) for i in range(total_chars)]
        
        is_wide_screen = self.width >= 1000

        # Resolution-aware spacing between 2-char groups in the hash frame.
        # Keep 480x800 baseline unchanged while opening spacing on larger canvases.
        def _pair_gap_px() -> int:
            gap_px = self._scale_px(6, min_value=2)
            if self.ui_scale > 1.0:
                gap_px += int(round((self.ui_scale - 1.0) * 2))
            return gap_px

        # The width estimate below deliberately assumes the tighter 3 px gap
        # rather than the 6 px the frame actually draws with. It only feeds the
        # decision of whether to shrink the font to fit max_width, and the
        # smaller number is what the current layout was tuned against.
        def _estimated_pair_gap_px() -> int:
            gap_px = self._scale_px(3, min_value=1)
            if self.ui_scale > 1.0:
                gap_px += int(round((self.ui_scale - 1.0) * 2))
            if is_wide_screen:
                gap_px += self._scale_px(5, min_value=1)
            return gap_px

        font_size = self._scale_font_size(11, min_value=8)
        # --- Optional scaling if max_width is given ---
        if max_width is not None:
            # Calculate required width for standard font 11
            # 23 pairs in top row. Each pair (2 chars) takes roughly:
            # bbox("0") width * 2 + extra_space.
            # Plus gaps between pairs (6px).
            # This is an approximation since we don't know the font metrics perfectly without loading.
            
            # Load font to measure
            temp_font = self._get_font(self.font_mono, self._scale_font_size(11, min_value=8))
            bbox = temp_font.getbbox("0")
            cw = bbox[2] - bbox[0]
            # Top row logic: 2 chars then gap.
            # Total width = 46 chars + 23 gaps.
            # Horizontal gap is 3px (smaller than vertical's 6px) to fit the larger font
            
            _est_horizontal_pairs = 24 if is_wide_screen else 23
            _est_horizontal_chars = _est_horizontal_pairs * 2
            _est_gaps = max(0, _est_horizontal_pairs - 1)
            estimated_full_width = (_est_horizontal_chars * cw) + (_est_gaps * _estimated_pair_gap_px()) + self._scale_px(20, min_value=8)
            
            if estimated_full_width > max_width:
                 scale_factor = max_width / estimated_full_width
                 font_size = int(self._scale_font_size(11, min_value=8) * scale_factor)
                 if font_size < 1: font_size = 1
                 
                 # Adjust spacing by scale too
                 extra_space = int(max(1, extra_space * scale_factor))

        font = self._get_font(self.font_mono, font_size)
    
        # Character size
        bbox = font.getbbox("0")
        char_w = bbox[2] - bbox[0]
        char_h = bbox[3] - bbox[1]

        # Hash frame geometry profile.
        # Wide screens: 24 pairs wide x 9 pairs high.
        # Default profile: 23 pairs wide x 10 pairs high.
        # The sequence length follows the overlap model: N = W + H - 1.
        horizontal_pairs = 24 if is_wide_screen else 23
        vertical_pairs_total = 9 if is_wide_screen else 10
        side_pairs_middle = max(0, vertical_pairs_total - 2)
        sequence_pair_count = horizontal_pairs + vertical_pairs_total - 1

        # Build two-character pairs from the block hash, wrapping if needed.
        hash_text = (block_hash or "").strip()
        if len(hash_text) < 2:
            hash_text = "00" * max(32, sequence_pair_count)

        pair_chars = []
        pair_colors = []
        for i in range(sequence_pair_count):
            c0 = hash_text[(2 * i) % len(hash_text)]
            c1 = hash_text[(2 * i + 1) % len(hash_text)]
            pair_chars.append(c0 + c1)
            pair_colors.append(block_hash_colors[(2 * i) % total_chars])

        # Two-pass edge construction:
        # pass 1: top starts at upper-left and uses first W pairs, then right uses remaining pairs.
        # pass 2: left starts at upper-left and uses first H pairs, then bottom uses remaining pairs.
        top_pairs_chars = pair_chars[:horizontal_pairs]
        top_pairs_colors = pair_colors[:horizontal_pairs]

        # Side columns are only the middle rows, excluding both corners.
        left_pairs_chars = pair_chars[1:1 + side_pairs_middle]
        left_pairs_colors = pair_colors[1:1 + side_pairs_middle]
        right_pairs_chars = pair_chars[horizontal_pairs:horizontal_pairs + side_pairs_middle]
        right_pairs_colors = pair_colors[horizontal_pairs:horizontal_pairs + side_pairs_middle]

        # Bottom keeps full width and starts at the lower-left corner value.
        bottom_start = vertical_pairs_total - 1
        bottom_pairs_chars = pair_chars[bottom_start:bottom_start + horizontal_pairs]
        bottom_pairs_colors = pair_colors[bottom_start:bottom_start + horizontal_pairs]

        # Use the same effective gap value as the draw loop below.
        gap = _pair_gap_px()

        # Optional deterministic centering based on the actual frame geometry.
        top_pair_count = len(top_pairs_chars)
        top_effective_gaps = max(0, top_pair_count - 1)
        frame_width = (top_pair_count * 2 * int(char_w)) + (top_effective_gaps * gap)
        if center:
            x_init = max(0, (self.width - frame_width) // 2)

        # --- TOP EDGE ---
        x = x_init
        y = y_init
        for i, pair in enumerate(top_pairs_chars):
            draw.text((x, y), pair, fill=top_pairs_colors[i], font=font)
            x += (2 * int(char_w))
            if i < len(top_pairs_chars) - 1:
                x += gap

        # --- LEFT VERTICAL SIDE with horizontal pairs ---
        x_left = x_init
        x = x_left
        y = y_init + int(char_h) + extra_space
        base_side_pairs = 10
        base_side_step = int(char_h) + extra_space
        if vertical_pairs_total > 1:
            # Wide profile: moderate spacing to fit fee text inside without excess vertical room.
            if is_wide_screen:
                target_span = (vertical_pairs_total - 1) * base_side_step
            else:
                target_span = (base_side_pairs - 1) * base_side_step
            side_step = max(1, int(round(target_span / (vertical_pairs_total - 1))))
        else:
            side_step = base_side_step
        for i, pair in enumerate(left_pairs_chars):
            draw.text((x, y), pair, fill=left_pairs_colors[i], font=font)
            y += side_step

        # --- RIGHT VERTICAL SIDE ---
        x_right = x_init + frame_width - (2 * int(char_w))
        x = x_right
        y = y_init + int(char_h) + extra_space
        # Keep both sides on the same vertical cadence to avoid asymmetric heights.
        right_step = side_step
        for i, pair in enumerate(right_pairs_chars):
            draw.text((x, y), pair, fill=right_pairs_colors[i], font=font)
            y += right_step

        # --- BOTTOM EDGE ---
        # Place bottom edge from deterministic frame geometry.
        # Keep a small vertical breathing room below side pairs and scale by resolution.
        left_pair_count = max(1, len(left_pairs_chars))
        right_pair_count = max(1, len(right_pairs_chars))
        last_left_y = y_init + int(char_h) + extra_space + (left_pair_count - 1) * side_step
        last_right_y = y_init + int(char_h) + extra_space + (right_pair_count - 1) * right_step
        last_side_y = max(last_left_y, last_right_y)
        bottom_edge_nudge = self._scale_px(4, min_value=1)
        y = last_side_y + int(char_h) + max(1, extra_space // 2) + bottom_edge_nudge

        x = x_init
        for i, pair in enumerate(bottom_pairs_chars):
            draw.text((x, y), pair, fill=bottom_pairs_colors[i], font=font)
            x += (2 * int(char_w))
            if i < len(bottom_pairs_chars) - 1:
                x += gap

    def _render_block_info_with_data(self, img, draw, block_height, block_hash, font_block_label,
                                    font_block_value, mempool_api, configured_fee,
                                    api_block_height, web_quality, y_override=None,
                                    skip_hash_frame=False, precached_fee=None):
        """
        Render block information using pre-collected fee and block data.

        Args:
            skip_hash_frame: If True, skip drawing the decorative hash border.
                            Used for pre-rendering where hash is not yet known.
            precached_fee: Already-fetched fee recommendations dict, reused instead
                            of an extra API call when refreshing the gradient cache.
        """
        # Use pre-collected data instead of making new API calls
        if api_block_height is not None:
            display_block_height = str(api_block_height)
        else:
            display_block_height = str(block_height)

        # Refresh the fee cache if the block height changed, or if the entry for
        # this height has no usable fee data (e.g. a prior fetch for this same
        # height failed/timed out) — otherwise a single transient API failure
        # permanently locks the gradient to grey until the next block.
        _cached_fee_data = self.block_fee_cache.get(display_block_height, {}).get('fee_data')
        if self._block_fee_cache["current"]["height"] != display_block_height or not _cached_fee_data:
            fee_data = precached_fee or (mempool_api.get_fee_recommendations() if mempool_api else None)
            # Compute fee_color or use a default
            fee_color = self.get_color("fee", web_quality) if hasattr(self, 'get_color') else "gray"
            self._update_block_fee_cache(display_block_height, fee_data, fee_color)
        # Colour reads the fee the user actually cares about - the configured
        # tier - against the rolling median of block medians. The tier is the
        # question being asked: "is next-block inclusion expensive right now"
        # and "is a min-fee transaction worth broadcasting" are different
        # questions with different answers, and the scale is meant to shift
        # with the one selected. fastestFee therefore sits warm of the median
        # and minimumFee cool of it, by design rather than by accident.
        fee_parameter = self.config.get("fee_parameter", "minimumFee")
        _fee_cache = self._block_fee_cache
        prev_fee = self._get_fee_for_parameter(_fee_cache["previous"]["height"], fee_parameter)
        curr_fee = self._get_fee_for_parameter(_fee_cache["current"]["height"], fee_parameter)
        # The network's own minimum, from the same recommendations the tier
        # comes from. Below it there is nothing cheaper to wait for; it goes to
        # zero on a cleared mempool, where no floor is the right answer.
        cheap_floor = self._get_fee_for_parameter(_fee_cache["current"]["height"],
                                                  "minimumFee")
        block_height_start_color, block_height_end_color = self.fee_to_colors(
            curr_fee, prev_fee, web_quality, cheap_floor)
        # Position block info (same as existing _render_block_info)
        if y_override is not None:
            y = y_override
        else:
            # Use the full block_height_area so the hash frame bottom row stays within the image.
            y = self.height - self.block_height_area

        # Calculate Max Width for Responsive Layout
        max_available_width = self.width - self._scale_px(24, min_value=8)

        # Compute the inner width of the hash frame so we can target exactly
        # 8 px of margin between the block-height number and the frame chars.
        # The frame uses IBMPlexMono-Bold 11 pt; char advance = getbbox("0") width.
        # top row: 46 chars, gap of 6 px (vertical) or 3 px (horizontal) after every 2.
        # Inner left  = x_init + 2*cw   (left side draws pairs of 2 chars)
        # Inner right = x_init + 44*cw + 22*gap  (= top_positions[-2])
        # Inner width = 42*cw + 22*gap
        _MARGIN = self._scale_px(8, min_value=3)  # desired px gap on each side
        try:
            _mono_font = self._get_font(self.font_mono, self._scale_font_size(11, min_value=8))
            _cw = _mono_font.getbbox("0")[2] - _mono_font.getbbox("0")[0]
            _gap_frame = self._scale_px(6, min_value=2)
            if self.ui_scale > 1.0:
                _gap_frame += int(round((self.ui_scale - 1.0) * 2))
            _horizontal_pairs = 24 if self.width >= 1000 else 23
            _horizontal_chars = _horizontal_pairs * 2
            _horizontal_gaps = max(0, _horizontal_pairs - 1)
            _inner_frame_width = (_horizontal_chars - 4) * _cw + _horizontal_gaps * _gap_frame
            frame_target_width = max(self._scale_px(200, min_value=80), _inner_frame_width - 2 * _MARGIN)
        except Exception:
            frame_target_width = max_available_width - self._scale_px(20, min_value=8)

        # Format block height string
        if mempool_api:
            formatted_height = mempool_api.format_block_height(display_block_height)
        else:
            try:
                height_int = int(display_block_height)
                formatted_height = f"{height_int:,}".replace(",", ".")
            except (ValueError, TypeError):
                formatted_height = str(display_block_height)

        # Dot-advance compression: tighter dots narrow the number so it fits
        # comfortably inside the hash frame with the desired margin.
        # 0.35 means each '.' uses 35 % of its natural advance width.
        _DOT_FRACTION = 0.35

        # Scale block-height font so the squeezed text fits inside frame_target_width
        used_font_block_value = font_block_value
        text_width = self._squeezed_text_width(formatted_height, used_font_block_value, _DOT_FRACTION)

        if text_width > frame_target_width:
            ratio = frame_target_width / text_width
            new_size = max(self._scale_font_size(20, min_value=12), int(self._scale_font_size(124, min_value=52) * ratio))
            try:
                used_font_block_value = self._get_font(self.font_block_height, new_size)
                # Re-measure after font size change
                text_width = self._squeezed_text_width(formatted_height, used_font_block_value, _DOT_FRACTION)
            except Exception as e:
                print(f"Error scaling font: {e}")

        # Draw "Block Height" label
        # None
        
        # Fixed geometry: the canvas is always portrait.
        # Draw hash frame centered using measured geometry
        if not skip_hash_frame:
            self.draw_hash_frame(draw, 12, y+3, block_hash, web_quality=web_quality, center=True)
        y = y + self._scale_px(24, min_value=8)

        # When the font is scaled down (7-digit number), shift the text down by
        # half the height reduction so it stays vertically centred in the frame.
        base_ascent = font_block_value.getmetrics()[0]
        used_ascent = used_font_block_value.getmetrics()[0]
        vertical_centering_offset = max(0, (base_ascent - used_ascent) // 2)

        # Draw block height with color based on current fees (move up by 10px)
        value_y = y - self._scale_px(25, min_value=8) + vertical_centering_offset
        x = (self.width - text_width) // 2  # text_width already squeezed+scaled above
        self.draw_vertical_gradient_text(img, draw, formatted_height, x, value_y + self._scale_px(10, min_value=3),
                                         used_font_block_value,
                                         block_height_start_color, block_height_end_color,
                                         dot_fraction=_DOT_FRACTION)
        
        # Add fee information as small text if available
        if configured_fee is not None:
            # Fee parameter translation logic replicated locally or reused if possible?
            # The surrounding code already sets up fee variables but let's reuse the structure at the end of the function if possible?
            # The current structure has fee logic embedded at the end.
            # I will define `fee_y` here and let the common block handle text generation if possible, but the positioning is specific.
            
            # Get fee text (duplicate logic for safety or refactor later)
            fee_parameter = self.config.get("fee_parameter", "minimumFee")
            fee_type_keys = {
                "fastestFee": "fastest", "halfHourFee": "half_hour", "hourFee": "hour", "economyFee": "economy", "minimumFee": "minimum"
            }
            fee_key = fee_type_keys.get(fee_parameter, "minimum")
            fee_type_display = self.t.get(fee_key, "Unknown")
            fee_text = f"{fee_type_display}: {self._format_fee(configured_fee)} sat/vB"
            
            try:
                font_small = self._get_font(self.font_regular, self._scale_font_size(12, min_value=8))
            except:
                font_small = font_block_label
                
            bbox = used_font_block_value.getbbox(formatted_height)
            fee_y = value_y + bbox[3] - bbox[1] + self._scale_px(42, min_value=14)
            
            # Fee label always uses bottom color of gradient
            fee_color = block_height_end_color
            self.draw_centered(draw, fee_text, fee_y, font_small, fee_color)

    
    def patch_hash_frame_on_image(self, img, block_hash, web_quality, y_override=None):
        """
        Draw only the hash frame border onto an existing pre-rendered image.
        
        Used to stamp the actual block hash onto a pre-rendered image that was
        generated with skip_hash_frame=True. This avoids a full re-render when
        only the decorative hash border needs updating.
        
        Args:
            img: PIL Image to draw on (modified in-place)
            block_hash: The actual block hash string
            web_quality: True for web image, False for e-ink
            y_override: Override y position (for split-screen block_info_img)
        """
        draw = ImageDraw.Draw(img)
        
        # Replicate the y calculation from _render_block_info_with_data
        if y_override is not None:
            y = y_override
        else:
            y = self.height - self.block_height_area

        self.draw_hash_frame(draw, 12, y + 3, block_hash, web_quality=web_quality, center=True)
