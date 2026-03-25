"""Batch render all video versions from a single MusicXML file.

Usage:
    python -m pianola.batch examples/113362.xml
    python -m pianola.batch examples/113362.xml --output-dir output/
    python -m pianola.batch examples/113362.xml --preview
"""

import argparse
import subprocess
import sys
from pathlib import Path


def render_subprocess(config_lines: list[str], main_kwargs: dict):
    """Run render in a separate Python process to isolate OpenGL context."""
    config_code = "\n".join(f"scene.config.{line}" for line in config_lines)
    main_args = ", ".join(f"{k}={repr(v)}" for k, v in main_kwargs.items())
    script = (
        "from pianola import PianolaScene\n"
        "from shaderflow.scene import WindowBackend\n"
        "from pathlib import Path\n"
        "scene = PianolaScene(backend=WindowBackend.Headless)\n"
        f"{config_code}\n"
        f"scene.main({main_args})\n"
    )
    subprocess.run([sys.executable, "-c", script], check=True)


def main():
    parser = argparse.ArgumentParser(description="Batch render all video versions from MusicXML")
    parser.add_argument("input", help="MusicXML file path (must have 3 parts: Voice, Fuller Voice, Background)")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: same as input file)")
    parser.add_argument("--preview", action="store_true", help="Fast preview (540p, 30fps, ssaa 1)")
    parser.add_argument("--soundfont", default=None, help="Custom SoundFont path")
    parser.add_argument("--duration", type=float, default=None, help="Render only N seconds (default: full song)")
    parser.add_argument("--start-from", type=float, default=0.0, help="Start from N seconds (default: 0)")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        sys.exit(1)

    stem = input_path.stem
    out_dir = Path(args.output_dir).resolve() if args.output_dir else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.preview:
        ssaa, fps = 1, 30
        w_land, h_land = 960, 540
        w_short, h_short = 540, 960
    else:
        ssaa, fps = 2, 60
        w_land, h_land = 1920, 1080
        w_short, h_short = 1080, 1920

    sf_line = []
    if args.soundfont:
        sf_line = [f'soundfont = Path("{Path(args.soundfont).resolve()}")']

    time_lines = []
    if args.duration is not None:
        time_lines.append(f'duration = {args.duration}')
    if args.start_from > 0:
        time_lines.append(f'start_from = {args.start_from}')

    base_config = [
        f'musicxml = Path("{input_path}")',
    ] + sf_line + time_lines

    versions = [
        {
            "name": "voice",
            "desc": "Voice melody + full audio",
            "config": base_config + [
                'midi_parts = "1"',
                'audio_parts = "1,2,3"',
                'fixed_camera = True',
                'vertical = False',
            ],
            "main": dict(width=w_land, height=h_land, ssaa=ssaa, fps=fps),
        },
        {
            "name": "karaoke",
            "desc": "Karaoke (piano + lyrics overlay)",
            "config": base_config + [
                'midi_parts = "2,3"',
                'audio_parts = "1,2,3"',
                'fixed_camera = True',
                'vertical = False',
            ],
            "main": dict(width=w_land, height=h_land, ssaa=ssaa, fps=fps),
        },
        {
            "name": "bg-only",
            "desc": "Background accompaniment only",
            "config": base_config + [
                'midi_parts = "3"',
                'audio_parts = "3"',
                'fixed_camera = True',
                'vertical = False',
            ],
            "main": dict(width=w_land, height=h_land, ssaa=ssaa, fps=fps),
        },
        {
            "name": "short",
            "desc": "YouTube Shorts (9:16 vertical)",
            "config": base_config + [
                'midi_parts = "1"',
                'audio_parts = "1,2,3"',
                'fixed_camera = False',
                'vertical = True',
                'sidekeys = 2',
            ],
            "main": dict(width=w_short, height=h_short, ssaa=ssaa, fps=fps),
        },
    ]

    total = len(versions)
    for i, v in enumerate(versions, 1):
        output = out_dir / f"{stem}-{v['name']}.mp4"
        w = v["main"]["width"]
        h = v["main"]["height"]
        f = v["main"]["fps"]
        print(f"\n{'='*60}")
        print(f"[{i}/{total}] {v['desc']}")
        print(f"  Output: {output}")
        print(f"  Resolution: {w}x{h} @ {f}fps")
        print(f"{'='*60}\n")

        main_kwargs = {**v["main"], "output": str(output)}

        try:
            render_subprocess(v["config"], main_kwargs)
        except subprocess.CalledProcessError as e:
            print(f"\n  ERROR: Failed to render {v['name']} (exit code {e.returncode})")
            continue

    print(f"\n{'='*60}")
    print(f"All done! Files in: {out_dir}/")
    for v in versions:
        f = out_dir / f"{stem}-{v['name']}.mp4"
        status = "OK" if f.exists() else "MISSING"
        print(f"  [{status}] {f.name}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
