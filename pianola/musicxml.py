"""MusicXML parser for Pianola — extracts notes, chords, lyrics, and tempo."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ChordEvent:
    time: float
    label: str

@dataclass
class LyricEvent:
    time: float
    text: str
    syllabic: str = "single"
    verse: int = 1
    note_midi: int = 60

@dataclass
class MusicXMLData:
    notes: list = field(default_factory=list)       # list[PianoNote]
    chords: list[ChordEvent] = field(default_factory=list)
    lyrics: list[LyricEvent] = field(default_factory=list)
    tempo_changes: list[tuple[float, float]] = field(default_factory=list)
    part_names: list[str] = field(default_factory=list)
    title: str = ""
    key_signature: str = ""
    initial_bpm: float = 120.0
    scale_pitches: list[int] = field(default_factory=list)  # pitch classes 0-11 in the key's scale


_KIND_LABELS = {
    "major": "",
    "minor": "m",
    "dominant": "7",
    "dominant-seventh": "7",
    "major-seventh": "maj7",
    "minor-seventh": "m7",
    "diminished": "dim",
    "diminished-seventh": "dim7",
    "augmented": "aug",
    "half-diminished": "m7b5",
    "suspended-second": "sus2",
    "suspended-fourth": "sus4",
    "major-sixth": "6",
    "minor-sixth": "m6",
    "major-ninth": "maj9",
    "minor-ninth": "m9",
    "dominant-ninth": "9",
    "power": "5",
}


def _note_name(name: str) -> str:
    """Convert music21 note name to standard: B- → Bb, E# → E#."""
    return name.replace("-", "b").replace("#", "#")


def _build_chord_label(harmony) -> str:
    """Build a readable chord label from a music21 Harmony object."""
    import music21
    if isinstance(harmony, music21.harmony.NoChord):
        return "N.C."
    try:
        root = _note_name(harmony.root().name)
    except Exception:
        return "N.C."

    kind = harmony.chordKind or "major"
    suffix = _KIND_LABELS.get(kind, kind)

    label = root + suffix

    # Slash chord (bass note differs from root)
    try:
        bass = harmony.bass()
        if bass and bass.name != harmony.root().name:
            label += "/" + _note_name(bass.name)
    except Exception:
        pass

    return label


def _get_tempo_map(score, xml_path=None) -> list[tuple[float, float, float]]:
    """Build tempo map: list of (offset_quarters, bpm_quarter, sec_per_quarter).

    Handles dotted-quarter metronome marks (e.g. 55 BPM for dotted quarter = 82.5 BPM for quarter).
    Falls back to <sound tempo> in raw XML if MetronomeMark has no BPM.
    Returns list sorted by offset.
    """
    import music21
    marks = list(score.flatten().getElementsByClass(music21.tempo.MetronomeMark))
    if not marks:
        return [(0.0, 120.0, 0.5)]

    seen_offsets = set()
    result = []
    for mm in marks:
        if mm.number is None:
            continue
        offset = float(mm.offset)
        if offset in seen_offsets:
            continue
        seen_offsets.add(offset)
        quarter_bpm = mm.number * mm.referent.quarterLength
        sec_per_q = 60.0 / quarter_bpm
        result.append((offset, quarter_bpm, sec_per_q))

    # If no valid MetronomeMark, try <sound tempo> from raw XML
    if not result:
        import xml.etree.ElementTree as ET
        try:
            path_str = str(xml_path) if xml_path else ''
            tree = ET.parse(path_str)
            for sound in tree.iter('sound'):
                if 'tempo' in sound.attrib:
                    bpm = float(sound.attrib['tempo'])
                    return [(0.0, bpm, 60.0 / bpm)]
        except Exception:
            pass
        return [(0.0, 120.0, 0.5)]

    result.sort(key=lambda x: x[0])
    return result


def _offset_to_seconds(tempo_map: list[tuple[float, float, float]], offset: float) -> float:
    """Convert a quarter-note offset to absolute seconds using the tempo map."""
    seconds = 0.0
    prev_offset = 0.0
    sec_per_q = tempo_map[0][2]

    for i, (map_offset, _, spq) in enumerate(tempo_map):
        if map_offset > offset:
            break
        seconds += (map_offset - prev_offset) * sec_per_q
        prev_offset = map_offset
        sec_per_q = spq

    seconds += (offset - prev_offset) * sec_per_q
    return seconds


def parse_musicxml(
    path: Path,
    part_indices: Optional[list[int]] = None,
) -> MusicXMLData:
    """Parse a MusicXML file and extract note, chord, and lyric data.

    Args:
        path: Path to .musicxml, .xml, or .mxl file
        part_indices: 1-based part indices to include (None = all parts)

    Returns:
        MusicXMLData with all extracted information
    """
    try:
        import music21
    except ImportError:
        raise ImportError(
            "music21 is required for MusicXML support. "
            "Install it with: pip install music21"
        )

    from shaderflow.piano.notes import PianoNote

    score = music21.converter.parse(str(path))

    # Collect part names and metadata before expanding (expand can reorder)
    result = MusicXMLData()
    for part in score.parts:
        result.part_names.append(part.partName or f"Part {len(result.part_names) + 1}")

    # Extract song metadata
    if score.metadata:
        result.title = score.metadata.title or score.metadata.movementName or ""
    else:
        result.title = ""
    try:
        key = score.analyze('key')
        result.key_signature = f"{_note_name(key.tonic.name)} {'Major' if key.mode == 'major' else 'Minor'}"
        # Extract scale pitch classes (0=C, 1=C#, ..., 11=B)
        scale = key.getScale()
        result.scale_pitches = sorted(set(p.midi % 12 for p in scale.getPitches() if p.midi is not None))
    except Exception:
        result.key_signature = ""

    # Expand repeats so notes/chords/lyrics match actual playback
    try:
        score = score.expandRepeats()
    except Exception:
        pass  # Badly formed repeats — use score as-is

    # Build tempo map from expanded score
    tempo_map = _get_tempo_map(score, xml_path=path)
    result.initial_bpm = tempo_map[0][1]
    for offset, bpm, _ in tempo_map:
        time_sec = _offset_to_seconds(tempo_map, offset)
        result.tempo_changes.append((time_sec, bpm))

    all_parts = list(score.parts)

    # Filter parts
    if part_indices is not None:
        selected = []
        for i in part_indices:
            if 1 <= i <= len(all_parts):
                selected.append(all_parts[i - 1])
            else:
                raise ValueError(f"Part {i} does not exist. Available: 1-{len(all_parts)}")
        parts = selected
    else:
        parts = all_parts

    # Extract notes per part
    for channel, part in enumerate(parts):
        for elem in part.flatten().notes:
            # Skip harmony/chord-symbol elements (they have zero duration)
            if isinstance(elem, music21.harmony.Harmony):
                continue
            velocity = elem.volume.velocity if elem.volume.velocity is not None else 90
            offset = float(elem.offset)
            start_sec = _offset_to_seconds(tempo_map, offset)
            dur_sec = float(elem.duration.quarterLength) * tempo_map[0][2]
            # Find correct tempo for this offset
            for map_offset, _, spq in reversed(tempo_map):
                if map_offset <= offset:
                    dur_sec = float(elem.duration.quarterLength) * spq
                    break

            end_sec = start_sec + dur_sec

            if isinstance(elem, music21.note.Note):
                result.notes.append(PianoNote(
                    note=elem.pitch.midi,
                    start=start_sec,
                    end=end_sec,
                    channel=channel,
                    velocity=velocity,
                ))
            elif isinstance(elem, music21.chord.Chord):
                for pitch in elem.pitches:
                    result.notes.append(PianoNote(
                        note=pitch.midi,
                        start=start_sec,
                        end=end_sec,
                        channel=channel,
                        velocity=velocity,
                    ))

            # Extract lyrics attached to this note
            if hasattr(elem, 'lyrics') and elem.lyrics:
                midi_num = elem.pitch.midi if hasattr(elem, 'pitch') else 60
                for lyric in elem.lyrics:
                    if lyric.text:
                        result.lyrics.append(LyricEvent(
                            time=start_sec,
                            text=lyric.text,
                            syllabic=lyric.syllabic or "single",
                            verse=lyric.number if lyric.number else 1,
                            note_midi=midi_num,
                        ))

    # Extract chord symbols (from all parts — chords are usually on part 0)
    seen_chords = set()
    for part in parts:
        for harmony in part.flatten().getElementsByClass('Harmony'):
            offset = float(harmony.offset)
            time_sec = _offset_to_seconds(tempo_map, offset)
            label = _build_chord_label(harmony)

            # Deduplicate by time+label
            key = (round(time_sec, 4), label)
            if key not in seen_chords:
                seen_chords.add(key)
                result.chords.append(ChordEvent(time=time_sec, label=label))

    result.chords.sort(key=lambda c: c.time)
    result.lyrics.sort(key=lambda l: (l.verse, l.time))

    return result


def musicxml_to_midi(
    path: Path,
    output_path: Path,
    part_indices: Optional[list[int]] = None,
) -> Path:
    """Convert MusicXML to MIDI file (for audio rendering via fluidsynth).

    Args:
        path: Input MusicXML file
        output_path: Where to write the MIDI file
        part_indices: 1-based part indices to include (None = all)

    Returns:
        Path to the written MIDI file
    """
    try:
        import music21
    except ImportError:
        raise ImportError("music21 is required. Install with: pip install music21")

    score = music21.converter.parse(str(path))

    if part_indices is not None:
        all_parts = list(score.parts)
        new_score = music21.stream.Score()
        # Copy tempo markings from original score
        for mm in score.flatten().getElementsByClass(music21.tempo.MetronomeMark):
            new_score.insert(mm.offset, mm)
        for i in part_indices:
            if 1 <= i <= len(all_parts):
                new_score.insert(0, all_parts[i - 1])
        score = new_score

    # Remove chord symbols (Harmony) — they generate unwanted MIDI notes
    # Keep them for single-track files (chords provide accompaniment)
    if len(score.parts) > 1:
        for part in score.parts:
            for h in list(part.recurse().getElementsByClass(music21.harmony.Harmony)):
                part.remove(h, recurse=True)

    # Try to expand repeats first (preserves correct playback order)
    # Fall back to stripping repeats if expand fails
    try:
        score = score.expandRepeats()
    except Exception:
        # Strip all repeat-related elements to avoid crash in score.write('midi')
        for part in score.parts:
            for m in part.getElementsByClass(music21.stream.Measure):
                if m.leftBarline and isinstance(m.leftBarline, music21.bar.Repeat):
                    m.leftBarline = None
                if m.rightBarline and isinstance(m.rightBarline, music21.bar.Repeat):
                    m.rightBarline = None
            for sp in list(part.getElementsByClass(music21.spanner.RepeatBracket)):
                part.remove(sp)
            for re in list(part.recurse().getElementsByClass(music21.repeat.RepeatExpression)):
                part.remove(re, recurse=True)

    score.write("midi", fp=str(output_path))

    # Post-process: force Piano program for SoundFont compatibility
    import pretty_midi
    midi = pretty_midi.PrettyMIDI(str(output_path))
    for inst in midi.instruments:
        inst.program = 0
    midi.write(str(output_path))

    return output_path
