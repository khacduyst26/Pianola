"""YouTube Shorts renderer — 9:16 vertical format with dynamic camera.

Usage:
    python -m pianola.shorts examples/113362.xml -o output.mp4
    python -m pianola.shorts examples/113362.xml -o output.mp4 --preview
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Generate YouTube Shorts piano roll video (9:16)")
    parser.add_argument("input", help="MusicXML file path")
    parser.add_argument("-o", "--output", help="Output video path (default: input_shorts.mp4)")
    parser.add_argument("--preview", action="store_true", help="Fast preview (lower quality)")
    parser.add_argument("--soundfont", default=None, help="Custom SoundFont path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    output = args.output or str(input_path.with_name(input_path.stem + "_shorts.mp4"))

    if args.preview:
        width, height, ssaa, fps = 540, 960, 1, 30
    else:
        width, height, ssaa, fps = 1080, 1920, 2, 60

    print(f"Rendering YouTube Shorts: {width}x{height} @ {fps}fps")
    print(f"Input: {input_path}")
    print(f"Output: {output}")
    print()

    from pianola import PianolaScene
    from shaderflow.scene import WindowBackend

    # Auto-detect parts
    import music21
    score = music21.converter.parse(str(input_path))
    num_parts = len(score.parts)
    all_parts = ",".join(str(i) for i in range(1, num_parts + 1))

    scene = PianolaScene(backend=WindowBackend.Headless)
    scene.config.musicxml = input_path
    scene.config.midi_parts = "1"
    scene.config.audio_parts = all_parts
    scene.config.sidekeys = 2           # tighter framing for narrow width
    scene.config.fixed_camera = False    # dynamic camera movement
    scene.config.vertical = True         # larger chord column and labels

    if args.soundfont:
        scene.config.soundfont = Path(args.soundfont)

    scene.main(
        output=output,
        width=width,
        height=height,
        ssaa=ssaa,
        fps=fps,
    )

    print(f"\nDone! Output: {output}")


if __name__ == "__main__":
    main()
