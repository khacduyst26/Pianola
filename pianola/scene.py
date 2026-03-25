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

    # Courtesy http://www.schristiancollins.com/generaluser.php
    soundfont: Annotated[Path, Parameter(group="SoundFont")] = Path(pooch.retrieve(
        url="https://github.com/x42/gmsynth.lv2/raw/b899b78640e0b99ec84d939c51dea2058673a73a/sf2/GeneralUser_LV2.sf2",
        known_hash="xxh128:25586f570092806dccbf834d2c3517b9",
        path=pianola.directories.user_data_path,
        fname="GeneralUser_LV2.sf2",
        progressbar=True,
    ))
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
        self._chord_count = 0
        self._lyric_count = 0
        self._chord_atlas_size = (1, 1)
        self._lyric_atlas_size = (1, 1)

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

        # Parse ALL parts for chords/lyrics (they may be on a different part)
        mxml_all = parse_musicxml(xml_path, part_indices=None)
        if mxml_all.chords and not mxml_data.chords:
            mxml_data.chords = mxml_all.chords
        if mxml_all.lyrics and not mxml_data.lyrics:
            mxml_data.lyrics = mxml_all.lyrics

        # Feed notes into ShaderPiano
        for note in mxml_data.notes:
            self.piano.add_note(note)

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
        self._load_text_overlays(mxml_data)

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

    def _load_text_overlays(self, mxml_data) -> None:
        """Build and load chord/lyric atlas textures from parsed MusicXML data."""
        from pianola.text_overlay import build_chord_textures, build_lyric_textures

        if mxml_data.chords:
            atlas, timing, _ = build_chord_textures(mxml_data.chords)
            self.chord_atlas.from_numpy(atlas)
            self.chord_timing.from_numpy(timing)
            self._chord_count = timing.shape[0]
            self._chord_atlas_size = (atlas.shape[1], atlas.shape[0])
        else:
            self._chord_count = 0

        if mxml_data.lyrics:
            atlas, timing, _ = build_lyric_textures(mxml_data.lyrics, verse=1)
            self.lyric_atlas.from_numpy(atlas)
            self.lyric_timing.from_numpy(timing)
            self._lyric_count = timing.shape[0]
            self._lyric_atlas_size = (atlas.shape[1], atlas.shape[0])
        else:
            self._lyric_count = 0

    def pipeline(self) -> Iterable[ShaderVariable]:
        yield from super().pipeline()
        yield Uniform("int", "iChordCount", self._chord_count)
        yield Uniform("int", "iLyricCount", self._lyric_count)
        yield Uniform("vec2", "iChordAtlasSize", self._chord_atlas_size)
        yield Uniform("vec2", "iLyricAtlasSize", self._lyric_atlas_size)

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

    def main(self, **kwargs):
        output = super().main(**kwargs)

        # Mux audio into video after render (workaround for shaderflow audio bug)
        if hasattr(self, '_pending_audio') and output and isinstance(output, (str, Path)):
            video_path = Path(output)
            if video_path.exists() and self._pending_audio.exists():
                muxed = video_path.with_stem(video_path.stem + "_muxed")
                subprocess.check_call((
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-i", str(video_path),
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
        if hasattr(self, "_fixed_note_range"):
            self.piano.note_range_dynamics.value[:] = self._fixed_note_range
            self.piano.note_range_dynamics.target[:] = self._fixed_note_range
