import struct
import subprocess
import tempfile
from typing import Annotated, Any, Iterable, Optional
from pathlib import Path

import numpy as np
import pooch
from attrs import Factory, define
from cyclopts import Parameter
from shaderflow.audio import ShaderAudio
from shaderflow.message import ShaderMessage
from shaderflow.piano import ShaderPiano
from shaderflow.scene import ShaderScene
from shaderflow.texture import ShaderTexture
from shaderflow.variable import ShaderVariable, Uniform

import pianola


def _parse_parts(value: Optional[str]) -> Optional[list[int]]:
    """Parse '1,2,3' into [1, 2, 3]. Returns None if input is None."""
    if value is None:
        return None
    return [int(p.strip()) for p in value.split(",") if p.strip()]


@define(kw_only=True)
class PianolaConfig:
    """Pianola style and inputs configuration"""

    # --------------------------------------|
    # Piano

    rolltime: Annotated[float, Parameter(group="Piano")] = 2.0
    """How long falling notes are visible"""

    height: Annotated[float, Parameter(group="Piano")] = 0.275
    """Ratio of the screen used for the piano"""

    black: Annotated[float, Parameter(group="Piano")] = 0.6
    """How long are black keys compared to white keys"""

    sidekeys: Annotated[int, Parameter(group="Piano")] = 6
    """Extends the dynamic focus on playing notes"""

    fixed_camera: Annotated[bool, Parameter(group="Piano")] = True
    """Lock camera to show all notes (disable dynamic zoom)"""

    start_from: Annotated[float, Parameter(group="Piano")] = 0.0
    """Start rendering from this time in seconds (default: 0)"""

    duration: Annotated[Optional[float], Parameter(group="Piano")] = None
    """Duration to render in seconds (default: full song)"""

    vertical: Annotated[bool, Parameter(group="Piano")] = False
    """Vertical/Shorts mode: larger chord column and labels"""

    # --------------------------------------|
    # Input

    audio: Annotated[Optional[Path], Parameter(group="Input")] = None
    """Optional pre-rendered final video audio"""

    # Public Domain https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=263
    midi: Annotated[Optional[Path], Parameter(group="Input")] = None
    """Midi file for realtime or rendering"""

    musicxml: Annotated[Optional[Path], Parameter(group="Input")] = None
    """MusicXML file input (auto-parsed for notes, chords, lyrics)"""

    midi_parts: Annotated[Optional[str], Parameter(group="Input")] = None
    """Parts for video display: 1, 2, or 1,2 (default: all)"""

    audio_parts: Annotated[Optional[str], Parameter(group="Input")] = None
    """Parts for audio: 1, 2, or 1,2 (default: follow --midi-parts)"""

    midi_gain: Annotated[float, Parameter(group="Input")] = 1.5
    """Master gain for rendered midi files"""

    samplerate: Annotated[int, Parameter(group="Input")] = 44100
    """Sample rate for rendered midi files"""

    # --------------------------------------|
    # SoundFont

    # Default: SalamanderGrandPiano if available, otherwise download GeneralUser
    soundfont: Annotated[Path, Parameter(group="SoundFont")] = Path(
        str(Path(__file__).parent.parent / "SalamanderGrandPiano.sf2")
        if (Path(__file__).parent.parent / "SalamanderGrandPiano.sf2").exists()
        else pooch.retrieve(
            url="https://github.com/x42/gmsynth.lv2/raw/b899b78640e0b99ec84d939c51dea2058673a73a/sf2/GeneralUser_LV2.sf2",
            known_hash="xxh128:25586f570092806dccbf834d2c3517b9",
            path=pianola.directories.user_data_path,
            fname="GeneralUser_LV2.sf2",
            progressbar=True,
        )
    )
    """SoundFont for realtime or rendering audio"""

# ---------------------------------------------------------------------------- #

@define
class PianolaScene(ShaderScene):
    config: PianolaConfig = Factory(PianolaConfig)

    def smartset(self, object: Any) -> Any:
        if isinstance(object, PianolaConfig):
            self.config = object
        return object

    def commands(self):
        self.cli.help = pianola.__about__
        self.cli.version = pianola.__version__
        self.cli.command(
            PianolaConfig, name="config",
            result_action=self.smartset
        )

    def build(self):
        self.shader.fragment = (pianola.resources/"pianola.glsl")
        self.audio = ShaderAudio(scene=self, name="iAudio")
        self.piano = ShaderPiano(scene=self)
        self.piano.fluid_install()
        self.piano.fluid_start()

        # Text overlay textures
        self.chord_atlas = ShaderTexture(scene=self, name="iChordAtlas")
        self.chord_atlas.from_numpy(np.zeros((1, 1, 4), dtype=np.uint8))
        self.chord_timing = ShaderTexture(scene=self, name="iChordTiming")
        self.chord_timing.from_numpy(np.zeros((1, 1, 4), dtype=np.float32))
        self.lyric_atlas = ShaderTexture(scene=self, name="iLyricAtlas")
        self.lyric_atlas.from_numpy(np.zeros((1, 1, 4), dtype=np.uint8))
        self.lyric_timing = ShaderTexture(scene=self, name="iLyricTiming")
        self.lyric_timing.from_numpy(np.zeros((1, 1, 4), dtype=np.float32))
        self.syllable_timing = ShaderTexture(scene=self, name="iSyllableTiming")
        self.syllable_timing.from_numpy(np.zeros((1, 1, 4), dtype=np.float32))
        self._chord_count = 0
        self._lyric_count = 0
        self._syllable_count = 0
        self._lyric_mode = 0  # 0=on-note, 1=karaoke
        self._chord_atlas_size = (1, 1)
        self._lyric_atlas_size = (1, 1)

        # Used keys texture: 128x1, value=1.0 if key is used in the song
        self.used_keys_tex = ShaderTexture(scene=self, name="iUsedKeys")
        self.used_keys_tex.from_numpy(np.zeros((1, 128, 1), dtype=np.float32))

        # Key label atlas: pre-rendered note names
        self.key_label_atlas = ShaderTexture(scene=self, name="iKeyLabelAtlas")
        self._build_key_label_atlas()

    def handle(self, message: ShaderMessage) -> None:
        ShaderScene.handle(self, message)

        if isinstance(message, ShaderMessage.Window.FileDrop):
            file = Path(message.files[0])

            if file.suffix == ".mid":
                self.config.midi = file
                self.config.musicxml = None
            elif file.suffix in (".musicxml", ".xml", ".mxl"):
                self.config.musicxml = file
                self.config.midi = None
            elif (file.suffix == ".sf2"):
                self.config.soundfont = file

            self.setup()

    def _setup_musicxml(self) -> None:
        """Load MusicXML: parse notes into ShaderPiano, prepare audio."""
        from pianola.musicxml import parse_musicxml, musicxml_to_midi

        xml_path = Path(self.config.musicxml)
        video_parts = _parse_parts(self.config.midi_parts)
        audio_parts = _parse_parts(self.config.audio_parts)
        if audio_parts is None:
            audio_parts = video_parts

        # Parse MusicXML for video display (selected parts only for notes)
        mxml_data = parse_musicxml(xml_path, part_indices=video_parts)
        self._musicxml_data = mxml_data

        # Check if the selected parts have their own lyrics
        lyrics_from_own_part = bool(mxml_data.lyrics)

        # Parse ALL parts for chords/lyrics (they may be on a different part)
        mxml_all = parse_musicxml(xml_path, part_indices=None)
        if mxml_all.chords and len(mxml_all.chords) > len(mxml_data.chords):
            mxml_data.chords = mxml_all.chords
        if mxml_all.lyrics and not mxml_data.lyrics:
            mxml_data.lyrics = mxml_all.lyrics

        # Feed notes into ShaderPiano
        for note in mxml_data.notes:
            self.piano.add_note(note)

        # Mark used keys for highlighting
        self._update_used_keys(mxml_data.notes)

        # Feed tempo changes
        self.piano.tempo.clear()
        for when, bpm in mxml_data.tempo_changes:
            self.piano.tempo.append((when, bpm))
        self.piano.tempo_texture.clear()
        for offset, (when, bpm) in enumerate(self.piano.tempo):
            self.piano.tempo_texture.write(
                data=struct.pack("ff", when, bpm),
                viewport=(0, offset, 1, 1)
            )

        # Build text overlay textures
        self._load_text_overlays(mxml_data, lyrics_from_own_part)

        # Pre-render audio: MusicXML → MIDI → fluidsynth → WAV
        # Store for post-render muxing (shaderflow audio pipeline has bugs)
        if (self.exporting) and (self.config.audio is None):
            self._midi_tmp = tempfile.NamedTemporaryFile(suffix=".mid", delete=False)
            musicxml_to_midi(xml_path, Path(self._midi_tmp.name), part_indices=audio_parts)

            self._audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            subprocess.check_call((
                "fluidsynth", "-qni",
                "-F", self._audio.name,
                "-r", str(self.config.samplerate),
                "-g", str(self.config.midi_gain),
                self.config.soundfont,
                self._midi_tmp.name,
            ))
            self._pending_audio = Path(self._audio.name)

    def _setup_midi(self) -> None:
        """Load MIDI file (original flow)."""
        midi_path = self.config.midi or (pianola.resources / "entertainer.mid")
        self.piano.load_midi(midi_path)

        # Pre-render audio for post-render muxing
        if (self.exporting) and (self.config.audio is None):
            self._audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            subprocess.check_call((
                "fluidsynth", "-qni",
                "-F", self._audio.name,
                "-r", str(self.config.samplerate),
                "-g", str(self.config.midi_gain),
                self.config.soundfont,
                str(midi_path),
            ))
            self._pending_audio = Path(self._audio.name)

    def _build_key_label_atlas(self) -> None:
        """Build atlas with note name labels (C D E F G A B) for white keys."""
        from PIL import Image, ImageDraw, ImageFont
        from pianola.text_overlay import _get_font

        labels = ["C", "D", "E", "F", "G", "A", "B"]
        font = _get_font(32)
        temp = Image.new("RGBA", (1, 1))
        td = ImageDraw.Draw(temp)

        # Measure max size
        max_w = max(td.textbbox((0, 0), l, font=font)[2] for l in labels) + 8
        row_h = max(td.textbbox((0, 0), l, font=font)[3] for l in labels) + 8
        atlas_h = row_h * 7

        atlas = Image.new("RGBA", (max_w, atlas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(atlas)
        for i, label in enumerate(labels):
            bbox = td.textbbox((0, 0), label, font=font)
            x = (max_w - (bbox[2] - bbox[0])) // 2 - bbox[0]
            y = i * row_h + (row_h - (bbox[3] - bbox[1])) // 2 - bbox[1]
            draw.text((x, y), label, font=font, fill=(255, 255, 255, 255))

        self.key_label_atlas.from_numpy(np.array(atlas))
        self._key_label_atlas_size = (max_w, atlas_h)
        self._key_label_row_h = row_h

    def _update_used_keys(self, notes) -> None:
        """Mark which MIDI keys are used in the song."""
        used = np.zeros((1, 128, 1), dtype=np.float32)
        for note in notes:
            if 0 <= note.note < 128:
                used[0, note.note, 0] = 1.0
        self.used_keys_tex.from_numpy(np.flipud(used))

    def _load_text_overlays(self, mxml_data, lyrics_from_own_part: bool) -> None:
        """Build and load chord/lyric atlas textures from parsed MusicXML data."""
        from pianola.text_overlay import (
            build_chord_textures, build_lyric_textures_on_note,
            build_lyric_textures_karaoke,
        )

        if mxml_data.chords:
            atlas, timing, _ = build_chord_textures(mxml_data.chords)
            self.chord_atlas.from_numpy(atlas)
            # Pre-flip timing so from_numpy's flipud results in correct order
            self.chord_timing.from_numpy(np.flipud(timing))
            self._chord_count = timing.shape[0]
            self._chord_atlas_size = (atlas.shape[1], atlas.shape[0])
        else:
            self._chord_count = 0

        if mxml_data.lyrics:
            if lyrics_from_own_part and not self.config.vertical:
                # Mode 0: lyrics on note bars (not used in vertical/shorts mode)
                self._lyric_mode = 0
                atlas, timing, _ = build_lyric_textures_on_note(mxml_data.lyrics, verse=1)
                self.lyric_atlas.from_numpy(atlas)
                self.lyric_timing.from_numpy(np.flipud(timing))
                self._lyric_count = timing.shape[0]
                self._lyric_atlas_size = (atlas.shape[1], atlas.shape[0])
                self._syllable_count = 0
            else:
                # Mode 1: karaoke overlay
                self._lyric_mode = 1
                atlas, line_timing, syl_timing, _ = build_lyric_textures_karaoke(
                    mxml_data.lyrics, verse=1
                )
                self.lyric_atlas.from_numpy(atlas)
                self.lyric_timing.from_numpy(np.flipud(line_timing))
                self.syllable_timing.from_numpy(np.flipud(syl_timing))
                self._lyric_count = line_timing.shape[0]
                self._syllable_count = syl_timing.shape[0]
                self._lyric_atlas_size = (atlas.shape[1], atlas.shape[0])
        else:
            self._lyric_count = 0
            self._syllable_count = 0

    def pipeline(self) -> Iterable[ShaderVariable]:
        yield from super().pipeline()
        yield Uniform("int", "iChordCount", self._chord_count)
        yield Uniform("int", "iLyricCount", self._lyric_count)
        yield Uniform("int", "iSyllableCount", self._syllable_count)
        yield Uniform("int", "iLyricMode", self._lyric_mode)
        yield Uniform("vec2", "iChordAtlasSize", self._chord_atlas_size)
        yield Uniform("vec2", "iLyricAtlasSize", self._lyric_atlas_size)
        yield Uniform("vec2", "iKeyLabelAtlasSize", self._key_label_atlas_size)
        yield Uniform("float", "iKeyLabelRowH", float(self._key_label_row_h))
        yield Uniform("int", "iVerticalMode", int(self.config.vertical))

    def setup(self) -> None:
        self.piano.clear()
        self.piano.fluid_all_notes_off()

        if self.config.musicxml is not None:
            self._setup_musicxml()
        else:
            self._setup_midi()

        self.piano.fluid_load(self.config.soundfont)

        # Mirror common settings
        self.piano.height = self.config.height
        self.piano.roll_time = self.config.rolltime
        self.piano.black_ratio = self.config.black
        self.piano.extra_keys = self.config.sidekeys

        # Store global note range for fixed camera
        self._fixed_note_range = (
            self.piano.global_minimum_note,
            self.piano.global_maximum_note,
        )

        # Apply start time offset
        if self.config.start_from > 0:
            self.time = self.config.start_from

    def main(self, **kwargs):
        # Apply start_from/duration to shaderflow's time param
        if self.config.duration is not None:
            kwargs.setdefault("time", self.config.duration)

        output = super().main(**kwargs)

        # Mux audio into video after render (workaround for shaderflow audio bug)
        if hasattr(self, '_pending_audio') and output and isinstance(output, (str, Path)):
            video_path = Path(output)
            if video_path.exists() and self._pending_audio.exists():
                muxed = video_path.with_stem(video_path.stem + "_muxed")
                audio_args = []
                if self.config.start_from > 0:
                    audio_args = ["-ss", str(self.config.start_from)]
                subprocess.check_call((
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-i", str(video_path),
                    *audio_args,
                    "-i", str(self._pending_audio),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-shortest", "-y", str(muxed),
                ))
                muxed.replace(video_path)
                self._pending_audio.unlink(missing_ok=True)
                if hasattr(self, '_midi_tmp'):
                    Path(self._midi_tmp.name).unlink(missing_ok=True)

        return output

    # Mouse drag time scroll to match piano roll size
    def update(self) -> None:
        self._mouse_drag_time_factor = (self.piano.roll_time/(self.piano.height - 1))*self.camera.zoom.value

        # Fixed camera: override dynamic zoom to show all notes
        if self.config.fixed_camera and hasattr(self, "_fixed_note_range"):
            self.piano.note_range_dynamics.value[:] = self._fixed_note_range
            self.piano.note_range_dynamics.target[:] = self._fixed_note_range
