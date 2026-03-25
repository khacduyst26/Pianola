"""Text overlay for chord labels and lyrics — builds texture atlases for GPU rendering."""

import struct
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _get_font(size: int = 28) -> ImageFont.FreeTypeFont:
    """Get a suitable font for text rendering."""
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSText.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default(size)


def build_text_atlas(
    labels: list[str],
    font_size: int = 28,
    padding: int = 4,
    align: str = "center",
) -> tuple[np.ndarray, list[dict]]:
    """Render text labels into a texture atlas.

    Returns:
        (atlas_rgba_array, label_metadata)
        atlas_rgba_array: shape (height, width, 4) uint8 RGBA
        label_metadata[i]: {"label": str, "u0": float, "v0": float, "u1": float, "v1": float, "w": int, "h": int}
    """
    if not labels:
        return np.zeros((1, 1, 4), dtype=np.uint8), []

    font = _get_font(font_size)

    # Measure all labels
    temp_img = Image.new("RGBA", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)
    measurements = []
    for label in labels:
        bbox = temp_draw.textbbox((0, 0), label, font=font)
        w = bbox[2] - bbox[0] + padding * 2
        h = bbox[3] - bbox[1] + padding * 2
        measurements.append((w, h, bbox[0], bbox[1]))

    # Uniform row: all entries same width and same height
    max_w = max(m[0] for m in measurements)
    row_h = max(m[1] for m in measurements)
    total_h = row_h * len(labels)

    atlas_w = max_w
    atlas_h = total_h

    atlas = Image.new("RGBA", (atlas_w, atlas_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(atlas)

    metadata = []

    for i, (label, (w, h, bx, by)) in enumerate(zip(labels, measurements)):
        y_cursor = i * row_h
        if align == "left":
            x_offset = padding - bx
        else:
            x_offset = (max_w - w) // 2 + padding - bx
        y_offset = y_cursor + (row_h - h) // 2 + padding - by
        draw.text((x_offset, y_offset), label, font=font, fill=(255, 255, 255, 255))
        metadata.append({
            "label": label,
            "u0": 0.0,
            "v0": y_cursor / atlas_h,
            "u1": 1.0,
            "v1": (y_cursor + row_h) / atlas_h,
            "w": max_w,
            "h": row_h,
        })

    return np.array(atlas), metadata


def build_chord_textures(
    chords: list,
    font_size: int = 48,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Build chord atlas and timing textures.

    Args:
        chords: list of ChordEvent objects

    Returns:
        (atlas_rgba, timing_data, metadata)
        timing_data: shape (N, 1, 4) float32 — each row: (time, atlas_index, u0_v0_packed, u1_v1_packed)
    """
    if not chords:
        return (
            np.zeros((1, 1, 4), dtype=np.uint8),
            np.zeros((1, 1, 4), dtype=np.float32),
            [],
        )

    # Deduplicate labels for atlas, keep mapping
    unique_labels = list(dict.fromkeys(c.label for c in chords))
    label_to_idx = {l: i for i, l in enumerate(unique_labels)}

    atlas, metadata = build_text_atlas(unique_labels, font_size=font_size, align="left")

    # Build timing texture: each chord event → (time, u1, v0_gl, v1_gl)
    # Note: from_numpy flips vertically, so GL v0 = 1 - image_v1, GL v1 = 1 - image_v0
    timing = np.zeros((len(chords), 1, 4), dtype=np.float32)
    for i, chord in enumerate(chords):
        idx = label_to_idx[chord.label]
        m = metadata[idx]
        timing[i, 0] = [chord.time, m["u1"], 1.0 - m["v1"], 1.0 - m["v0"]]

    return atlas, timing, metadata


def build_lyric_textures_on_note(
    lyrics: list,
    verse: int = 1,
    font_size: int = 40,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Build lyric textures for on-note mode (Part 1).

    Each syllable rendered at its note's position in the roll.
    Timing texture: (time, note_midi, v0_gl, v1_gl)
    """
    verse_lyrics = [l for l in lyrics if l.verse == verse]
    if not verse_lyrics:
        return (
            np.zeros((1, 1, 4), dtype=np.uint8),
            np.zeros((1, 1, 4), dtype=np.float32),
            [],
        )

    # Each syllable with hyphen markers
    entries = []
    for lyric in verse_lyrics:
        text = lyric.text
        if lyric.syllabic in ("begin", "middle"):
            text = text + " -"
        elif lyric.syllabic == "end":
            text = "- " + text
        entries.append((lyric.time, text, lyric.note_midi))

    unique_labels = list(dict.fromkeys(e[1] for e in entries))
    label_to_idx = {l: i for i, l in enumerate(unique_labels)}
    atlas, metadata = build_text_atlas(unique_labels, font_size=font_size)

    # Timing: (time, note_midi, v0_gl, v1_gl)
    timing = np.zeros((len(entries), 1, 4), dtype=np.float32)
    for i, (time, text, note_midi) in enumerate(entries):
        m = metadata[label_to_idx[text]]
        timing[i, 0] = [time, float(note_midi), 1.0 - m["v1"], 1.0 - m["v0"]]

    return atlas, timing, metadata


def _group_lyrics_into_lines(lyrics: list, verse: int = 1, max_per_line: int = 8) -> list:
    """Group syllables into lines for karaoke display.

    Returns list of lines, each line = list of (time, text, syllabic).
    Lines break at punctuation or max_per_line syllables.
    """
    verse_lyrics = [l for l in lyrics if l.verse == verse]
    lines = []
    current_line = []

    for lyric in verse_lyrics:
        current_line.append(lyric)
        # Break line at end of word with punctuation, or max length
        is_word_end = lyric.syllabic in ("single", "end")
        has_punct = any(c in lyric.text for c in ".,!?;:")
        if (is_word_end and has_punct) or len(current_line) >= max_per_line:
            lines.append(current_line)
            current_line = []

    if current_line:
        lines.append(current_line)

    return lines


def build_lyric_textures_karaoke(
    lyrics: list,
    verse: int = 1,
    font_size: int = 44,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict]]:
    """Build lyric textures for karaoke mode (Part 2,3).

    Renders full lines of text. Shader shows 2 lines at center, highlights active syllable.

    Returns:
        (atlas_rgba, line_timing, syllable_timing, metadata)
        line_timing: (N_lines, 1, 4) float32 — (start_time, end_time, v0_gl, v1_gl)
        syllable_timing: (N_syllables, 1, 4) float32 — (time, line_index, x_start_ratio, x_end_ratio)
    """
    lines = _group_lyrics_into_lines(lyrics, verse)
    if not lines:
        empty = np.zeros((1, 1, 4), dtype=np.float32)
        return np.zeros((1, 1, 4), dtype=np.uint8), empty, empty, []

    font = _get_font(font_size)

    # Render each line as a single text string
    temp_img = Image.new("RGBA", (1, 1))
    temp_draw = ImageDraw.Draw(temp_img)

    line_texts = []
    line_syllable_info = []  # per line: list of (x_start, x_end) ratios

    for line in lines:
        # Build display text: join syllables into words, space between words only
        full_text = ""
        positions = []  # per syllable: (x_start, x_end) in pixels

        for syl in line:
            # Add space before new word (single or begin), except at start
            if syl.syllabic in ("single", "begin") and full_text:
                full_text += " "

            # Measure x_start before adding this syllable
            bbox_before = temp_draw.textbbox((0, 0), full_text, font=font) if full_text else (0, 0, 0, 0)
            x_start = bbox_before[2]

            full_text += syl.text

            # Measure x_end after adding this syllable
            bbox_after = temp_draw.textbbox((0, 0), full_text, font=font)
            x_end = bbox_after[2]

            positions.append((x_start, x_end))

        line_texts.append(full_text)
        line_syllable_info.append(positions)

    # Build atlas from line texts
    atlas, metadata = build_text_atlas(line_texts, font_size=font_size)

    # Line timing: (start_time, end_time, v0_gl, v1_gl)
    # end_time = start of next line (no overlap)
    line_timing = np.zeros((len(lines), 1, 4), dtype=np.float32)
    for i, line in enumerate(lines):
        start_time = line[0].time
        if i + 1 < len(lines):
            end_time = lines[i + 1][0].time
        else:
            end_time = line[-1].time + 5.0
        m = metadata[i]
        line_timing[i, 0] = [start_time, end_time, 1.0 - m["v1"], 1.0 - m["v0"]]

    # Syllable timing: (time, line_index, x_start_norm, x_end_norm)
    # x positions normalized to 0..1 within atlas width
    # Account for centering offset in the atlas
    total_syllables = sum(len(line) for line in lines)
    syllable_timing = np.zeros((total_syllables, 1, 4), dtype=np.float32)
    atlas_w = atlas.shape[1]
    idx = 0
    for i, (line, positions) in enumerate(zip(lines, line_syllable_info)):
        # Centering offset: text is centered in uniform-width atlas row
        text_w = metadata[i]["w"]  # this is max_w for all entries (uniform)
        # Measure actual text width for this line
        line_bbox = temp_draw.textbbox((0, 0), line_texts[i], font=font)
        actual_w = line_bbox[2] - line_bbox[0] + 8  # padding*2
        center_offset = (atlas_w - actual_w) // 2

        for j, (syl, (x_start, x_end)) in enumerate(zip(line, positions)):
            syllable_timing[idx, 0] = [
                syl.time,
                float(i),
                (x_start + center_offset) / atlas_w,
                (x_end + center_offset) / atlas_w,
            ]
            idx += 1

    return atlas, line_timing, syllable_timing, metadata
