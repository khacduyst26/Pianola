# How to Generate Piano Roll Videos

## Prerequisites

- Python 3.12 with venv: `.venv/bin/pip install -e .`
- `music21`, `Pillow` installed in the venv
- `fluidsynth` and `ffmpeg` available in PATH
- A MusicXML file (`.xml` or `.musicxml`) with 3 parts:
  - Part 1: Voice Only (melody line with lyrics)
  - Part 2: Fuller Voice (melody + accompaniment)
  - Part 3: Background (accompaniment only)
- `SalamanderGrandPiano.sf2` in project root (default SoundFont)

---

## Batch Render — All 4 Versions at Once (Recommended)

One command generates all video versions from a single MusicXML file.

**Production (highest quality — 1920x1080/1080x1920, 60fps, SSAA 2x):**
```bash
.venv/bin/python -m pianola.batch your_song.xml
```

**Preview (fast — 960x540/540x960, 30fps, SSAA 1x):**
```bash
.venv/bin/python -m pianola.batch your_song.xml --preview
```

**Custom output directory:**
```bash
.venv/bin/python -m pianola.batch your_song.xml --output-dir output/
```

**Custom SoundFont:**
```bash
.venv/bin/python -m pianola.batch your_song.xml --soundfont /path/to/soundfont.sf2
```

**Output files:**

| File | Video | Audio | Format | Description |
|------|-------|-------|--------|-------------|
| `songname-voice.mp4` | Part 1 | Parts 1,2,3 | 1920x1080 | Voice melody with lyrics on notes |
| `songname-karaoke.mp4` | Parts 2,3 | Parts 1,2,3 | 1920x1080 | Piano with karaoke lyrics overlay |
| `songname-bg-only.mp4` | Part 3 | Part 3 | 1920x1080 | Background accompaniment only |
| `songname-short.mp4` | Part 1 | Parts 1,2,3 | 1080x1920 | YouTube Shorts with dynamic camera |

---

## Individual Renders

### 1. Voice Version — Melody + Full Audio

Shows the voice/melody line as falling notes with lyrics attached to each note bar.

```bash
# Preview
.venv/bin/pianola config \
  --musicxml your_song.xml \
  --midi-parts 1 \
  --audio-parts 1,2,3 \
  main --output songname-voice.mp4 --ssaa 1 --fps 30

# Production
.venv/bin/pianola config \
  --musicxml your_song.xml \
  --midi-parts 1 \
  --audio-parts 1,2,3 \
  main --output songname-voice.mp4 --ssaa 2 --fps 60
```

**Features:** Note-colored bars (C=Red, D=Orange, E=Yellow, F=Green, G=Blue, A=Purple, B=Pink), lyrics on note bars, chord labels in left column, highlighted piano keys with labels.

### 2. Karaoke Version — Piano + Lyrics Overlay

Shows piano parts as falling notes with karaoke-style lyrics at the top. Two fixed lines, active syllable highlighted in yellow.

```bash
# Preview
.venv/bin/pianola config \
  --musicxml your_song.xml \
  --midi-parts 2,3 \
  --audio-parts 1,2,3 \
  main --output songname-karaoke.mp4 --ssaa 1 --fps 30

# Production
.venv/bin/pianola config \
  --musicxml your_song.xml \
  --midi-parts 2,3 \
  --audio-parts 1,2,3 \
  main --output songname-karaoke.mp4 --ssaa 2 --fps 60
```

**Features:** Fuller voice + background notes together, karaoke lyrics (2 lines, syllable highlight), chord labels, full audio.

### 3. Background Only — Accompaniment

Shows only the background accompaniment part with its own audio.

```bash
# Preview
.venv/bin/pianola config \
  --musicxml your_song.xml \
  --midi-parts 3 \
  --audio-parts 3 \
  main --output songname-bg-only.mp4 --ssaa 1 --fps 30

# Production
.venv/bin/pianola config \
  --musicxml your_song.xml \
  --midi-parts 3 \
  --audio-parts 3 \
  main --output songname-bg-only.mp4 --ssaa 2 --fps 60
```

**Features:** Background notes only, karaoke lyrics from Voice part, chord labels, single-part audio.

### 4. YouTube Shorts — Vertical 9:16

Vertical format for YouTube Shorts / Instagram Reels / TikTok. Dynamic camera follows the playing notes.

```bash
# Preview
.venv/bin/python -m pianola.shorts your_song.xml -o songname-short.mp4 --preview

# Production
.venv/bin/python -m pianola.shorts your_song.xml -o songname-short.mp4
```

**Features:** 1080x1920 vertical, dynamic camera zoom, voice melody with lyrics, larger chord column, full audio.

---

## CLI Options Reference

### Config options (`pianola config`)

| Option | Default | Description |
|--------|---------|-------------|
| `--musicxml` | — | Input MusicXML file |
| `--midi` | — | Input MIDI file (no lyrics/chords) |
| `--midi-parts` | all | Parts to display: `1`, `2,3`, etc. |
| `--audio-parts` | follow midi-parts | Parts for audio: `1,2,3`, etc. |
| `--soundfont` | SalamanderGrandPiano.sf2 | SoundFont (.sf2) path |
| `--rolltime` | 2.0 | How long falling notes are visible (seconds) |
| `--height` | 0.275 | Piano height ratio (0-1) |
| `--sidekeys` | 6 | Extra keys around playing range |
| `--fixed-camera` | true | Lock camera to full range |
| `--no-fixed-camera` | — | Enable dynamic camera zoom |

### Render options (`main`)

| Option | Default | Description |
|--------|---------|-------------|
| `--output` | — | Output video file path |
| `--ssaa` | 1 | Supersampling (1=fast, 2=high quality) |
| `--fps` | 60 | Framerate |

---

## Customization

- **Background image**: Place `background.png` in the project root
- **SoundFont**: Place `.sf2` file and use `--soundfont` or set as default in `scene.py`
- **Note colors**: Edit `getNoteColor()` in `pianola/resources/pianola.glsl`
- **Key labels**: Edit `_build_key_label_atlas()` in `pianola/scene.py`
