#!/usr/bin/env python
"""MusicXML to Video pipeline with part selection.

Usage:
    python xml2video.py input.musicxml -o output.mp4
    python xml2video.py input.musicxml --midi-parts 1       # only part 1 in MIDI/video
    python xml2video.py input.musicxml --midi-parts 1,2     # parts 1 and 2 (default: all)
    python xml2video.py input.musicxml --audio-parts 2      # audio only part 2
    python xml2video.py input.musicxml --midi-parts 1 --audio-parts 1,2  # different selections
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_parts(value: str) -> list[int]:
    """Parse part string like '1', '2', '1,2' into list of 0-based indices."""
    return [int(t.strip()) - 1 for t in value.split(",")]


def list_parts(xml_path: str):
    """List available parts in the MusicXML file."""
    import music21
    score = music21.converter.parse(xml_path)
    for i, part in enumerate(score.parts):
        n_notes = len(part.flatten().notes)
        print(f"  Part {i + 1}: {part.partName} ({n_notes} notes)")
    return score


def xml_to_midi(xml_path: str, midi_path: str, part_indices: list[int]):
    """Convert MusicXML to MIDI, keeping only selected parts."""
    import music21
    score = music21.converter.parse(xml_path)

    if part_indices is None:
        part_indices = list(range(len(score.parts)))

    for idx in part_indices:
        if idx < 0 or idx >= len(score.parts):
            print(f"Error: Part {idx + 1} does not exist. Available: 1-{len(score.parts)}")
            sys.exit(1)

    if len(part_indices) == len(score.parts):
        # Keep all tracks
        score.write("midi", fp=midi_path)
    else:
        # Filter to selected tracks
        new_score = music21.stream.Score()
        for idx in part_indices:
            new_score.insert(0, score.parts[idx])
        new_score.write("midi", fp=midi_path)

    print(f"  MIDI: {midi_path} (parts: {[i+1 for i in part_indices]})")
    return score


def midi_to_audio(midi_path: str, audio_path: str, soundfont: str):
    """Convert MIDI to audio using fluidsynth."""
    cmd = [
        "fluidsynth", "-ni", soundfont, midi_path,
        "-F", audio_path,
        "-r", "44100",
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"  Audio: {audio_path}")


def midi_to_video(midi_path: str, video_path: str, ssaa: int = 2):
    """Convert MIDI to video using Pianola (no audio)."""
    pianola_bin = Path(sys.executable).parent / "pianola"
    cmd = [
        str(pianola_bin),
        "config", "--midi", midi_path,
        "main", "--output", video_path, "--ssaa", str(ssaa),
    ]
    subprocess.run(cmd, check=True)
    print(f"  Video (no audio): {video_path}")


def merge_audio_video(video_path: str, audio_path: str, output_path: str):
    """Merge audio into video using ffmpeg."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", video_path,
        "-i", audio_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-y", output_path,
    ]
    subprocess.run(cmd, check=True)
    print(f"  Final: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="MusicXML to Video pipeline")
    parser.add_argument("input", help="MusicXML file path")
    parser.add_argument("-o", "--output", help="Output video path (default: input stem + .mp4)")
    parser.add_argument("--midi-parts", default=None,
                        help="Parts for MIDI/video: 1, 2, or 1,2 (default: all)")
    parser.add_argument("--audio-parts", default=None,
                        help="Parts for audio: 1, 2, or 1,2 (default: follow --midi-parts)")
    parser.add_argument("--ssaa", type=int, default=2, help="Supersampling (default: 2)")
    parser.add_argument("--soundfont", default=None, help="SoundFont path (default: Pianola's GeneralUser)")
    parser.add_argument("--list", action="store_true", help="List available parts and exit")

    args = parser.parse_args()

    input_path = args.input
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found")
        sys.exit(1)

    # List parts mode
    if args.list:
        print(f"Parts in {input_path}:")
        list_parts(input_path)
        return

    # Parse part selections
    midi_parts = parse_parts(args.midi_parts) if args.midi_parts else None
    audio_parts = parse_parts(args.audio_parts) if args.audio_parts else midi_parts

    # Resolve paths
    input_dir = str(Path(input_path).parent)
    stem = Path(input_path).stem
    output_path = args.output or os.path.join(input_dir, f"{stem}.mp4")
    midi_path = os.path.join(input_dir, f"{stem}.mid")
    soundfont = args.soundfont or os.path.expanduser(
        "~/Library/Application Support/pianola/GeneralUser_LV2.sf2"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        midi_for_audio = os.path.join(tmpdir, "audio.mid")
        audio_path = os.path.join(tmpdir, "audio.wav")
        video_noaudio = os.path.join(tmpdir, "video_noaudio.mp4")

        # Step 1: MusicXML → MIDI (for video, saved alongside source file)
        print("Step 1: MusicXML → MIDI (video)")
        score = xml_to_midi(input_path, midi_path, midi_parts)

        # Step 2: MusicXML → MIDI (for audio, may differ from video parts)
        print("Step 2: MusicXML → MIDI (audio)")
        if audio_parts == midi_parts or (audio_parts is None and midi_parts is None):
            midi_for_audio = midi_path
            print(f"  Reusing video MIDI (same parts)")
        else:
            xml_to_midi(input_path, midi_for_audio, audio_parts)

        # Step 3: MIDI → Audio
        print("Step 3: MIDI → Audio")
        midi_to_audio(midi_for_audio, audio_path, soundfont)

        # Step 4: MIDI → Video (no audio)
        print("Step 4: MIDI → Video")
        midi_to_video(midi_path, video_noaudio, args.ssaa)

        # Step 5: Merge audio + video
        print("Step 5: Merge audio + video")
        merge_audio_video(video_noaudio, audio_path, output_path)

    print(f"\nDone! Output: {output_path}")
    print(f"       MIDI:   {midi_path}")


if __name__ == "__main__":
    main()
