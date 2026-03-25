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
        # Center text horizontally in the row
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

    atlas, metadata = build_text_atlas(unique_labels, font_size=font_size)

    # Build timing texture: each chord event → (time, u1, v0_gl, v1_gl)
    # Note: from_numpy flips vertically, so GL v0 = 1 - image_v1, GL v1 = 1 - image_v0
    timing = np.zeros((len(chords), 1, 4), dtype=np.float32)
    for i, chord in enumerate(chords):
        idx = label_to_idx[chord.label]
        m = metadata[idx]
        timing[i, 0] = [chord.time, m["u1"], 1.0 - m["v1"], 1.0 - m["v0"]]

    return atlas, timing, metadata


def build_lyric_textures(
    lyrics: list,
    verse: int = 1,
    font_size: int = 40,
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """Build lyric atlas and timing textures for a specific verse.

    Each syllable is displayed individually, synced to its note.

    Returns:
        (atlas_rgba, timing_data, metadata)
    """
    # Filter to requested verse
    verse_lyrics = [l for l in lyrics if l.verse == verse]
    if not verse_lyrics:
        return (
            np.zeros((1, 1, 4), dtype=np.uint8),
            np.zeros((1, 1, 4), dtype=np.float32),
            [],
        )

    # Each syllable is its own entry, with hyphen for begin/middle
    words = []  # list of (time, display_text)
    for lyric in verse_lyrics:
        text = lyric.text
        if lyric.syllabic in ("begin", "middle"):
            text = text + " -"
        elif lyric.syllabic == "end":
            text = "- " + text
        words.append((lyric.time, text))

    # Deduplicate labels for atlas
    unique_labels = list(dict.fromkeys(w[1] for w in words))
    label_to_idx = {l: i for i, l in enumerate(unique_labels)}

    atlas, metadata = build_text_atlas(unique_labels, font_size=font_size)

    # Build timing texture (GL V is flipped by from_numpy)
    timing = np.zeros((len(words), 1, 4), dtype=np.float32)
    for i, (time, word) in enumerate(words):
        idx = label_to_idx[word]
        m = metadata[idx]
        timing[i, 0] = [time, m["u1"], 1.0 - m["v1"], 1.0 - m["v0"]]

    return atlas, timing, metadata
