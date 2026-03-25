# How to Generate Piano Roll Videos

## Prerequisites

- Python 3.12 with venv: `.venv/bin/pip install -e .`
- `music21`, `Pillow` installed in the venv
- `fluidsynth` and `ffmpeg` available in PATH
- A MusicXML file (`.xml` or `.musicxml`)
- Optional: `SalamanderGrandPiano.sf2` in project root for high quality audio

## Quick Reference

```
pianola config --musicxml <file> --midi-parts <parts> --audio-parts <parts> main --output <output.mp4> --ssaa <quality> --fps <fps>
```

| Option | Description |
|--------|-------------|
| `--musicxml` | Input MusicXML file |
| `--midi-parts` | Parts to display as notes (comma-separated, 1-based) |
| `--audio-parts` | Parts to play as audio (comma-separated, 1-based) |
| `--soundfont` | Custom SoundFont (.sf2) path |
| `--ssaa` | Supersampling quality (1=fast, 2=high quality) |
| `--fps` | Framerate (30=preview, 60=production) |

## List Available Parts

```bash
.venv/bin/python -c "
from pianola.musicxml import parse_musicxml
data = parse_musicxml('your_file.xml')
for i, name in enumerate(data.part_names):
    print(f'  Part {i+1}: {name}')
"
```

Example output:
```
  Part 1: Voice Only (melody line with lyrics)
  Part 2: Fuller Voice (melody + accompaniment)
  Part 3: Background (accompaniment only)
```

---

## 1. Notes Version — Voice Only + Full Audio

Shows the voice/melody line as falling notes with lyrics attached to each note.
Audio plays all 3 parts for full sound.

- **Video**: Part 1 (Voice Only) — lyrics appear on each note bar
- **Audio**: Parts 1,2,3 — full accompaniment

**Preview:**
```bash
.venv/bin/pianola config \
  --musicxml examples/113362.xml \
  --midi-parts 1 \
  --audio-parts 1,2,3 \
  main --output notes-preview.mp4 --ssaa 1 --fps 30
```

**Production:**
```bash
.venv/bin/pianola config \
  --musicxml examples/113362.xml \
  --midi-parts 1 \
  --audio-parts 1,2,3 \
  main --output notes-hq.mp4 --ssaa 2 --fps 60
```

**What you get:**
- Falling note bars colored by pitch (C=Red, D=Orange, E=Yellow, F=Green, G=Blue, A=Purple, B=Pink)
- Lyrics displayed on each note bar (syllable-by-syllable)
- Chord labels scrolling in the left column
- Piano keys highlighted and labeled for used notes
- Full audio with all parts

---

## 2. Karaoke Version — Fuller Voice + Full Audio

Shows the fuller voice (melody + accompaniment) as falling notes with karaoke-style lyrics overlay.
Two lines of lyrics at the top, highlighting syllable-by-syllable as they play.

- **Video**: Parts 2,3 (Fuller Voice + Background)
- **Audio**: Parts 1,2,3 — full sound including vocal

**Preview:**
```bash
.venv/bin/pianola config \
  --musicxml examples/113362.xml \
  --midi-parts 2,3 \
  --audio-parts 1,2,3 \
  main --output karaoke-preview.mp4 --ssaa 1 --fps 30
```

**Production:**
```bash
.venv/bin/pianola config \
  --musicxml examples/113362.xml \
  --midi-parts 2,3 \
  --audio-parts 1,2,3 \
  main --output karaoke-hq.mp4 --ssaa 2 --fps 60
```

**What you get:**
- Fuller voice + background notes displayed together
- Karaoke lyrics at the top: 2 fixed lines, active syllable highlighted in yellow
- Chord labels in the left column
- Full audio with all parts

---

## 3. Simple Background — Background Only

Shows only the background accompaniment part. Minimal, clean view.
Good for practice or background music videos.

- **Video**: Part 3 (Background only)
- **Audio**: Part 3 — background accompaniment only

**Preview:**
```bash
.venv/bin/pianola config \
  --musicxml examples/113362.xml \
  --midi-parts 3 \
  --audio-parts 3 \
  main --output background-preview.mp4 --ssaa 1 --fps 30
```

**Production:**
```bash
.venv/bin/pianola config \
  --musicxml examples/113362.xml \
  --midi-parts 3 \
  --audio-parts 3 \
  main --output background-hq.mp4 --ssaa 2 --fps 60
```

**What you get:**
- Only background accompaniment notes displayed
- Karaoke lyrics at the top (from Voice part)
- Chord labels in the left column
- Audio plays only the background part

---

## 4. YouTube Shorts (9:16 Vertical)

Vertical format for YouTube Shorts / Instagram Reels / TikTok.
Voice melody with dynamic camera that follows the playing notes.

- **Video**: Part 1 (Voice Only) — 9:16 vertical, dynamic camera
- **Audio**: Parts 1,2,3 — full accompaniment

**Preview:**
```bash
.venv/bin/python -m pianola.shorts examples/113362.xml -o shorts-preview.mp4 --preview
```

**Production:**
```bash
.venv/bin/python -m pianola.shorts examples/113362.xml -o shorts-hq.mp4
```

**What you get:**
- 1080x1920 vertical video (540x960 for preview)
- Dynamic camera zooming and following the playing notes
- Lyrics on note bars, chord labels in left column
- Full audio with all parts

---

## Tips

- **Custom SoundFont**: Use `--soundfont /path/to/your.sf2` to override the default
- **Background image**: Place `background.png` in the project root for a custom roll background
- **MIDI file input**: Use `--midi file.mid` instead of `--musicxml` for plain MIDI files (no lyrics/chords)
- **Render speed**: `--ssaa 1 --fps 30` is ~4x faster than `--ssaa 2 --fps 60`
