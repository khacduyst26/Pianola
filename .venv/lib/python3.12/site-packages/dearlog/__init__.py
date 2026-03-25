import time

# Warn: dearlog must be your first import
REFTIME: float = time.monotonic()
"""Instant the program started, means nothing alone"""

from importlib.metadata import metadata

__meta__:   dict = metadata(__package__)
__about__:   str = __meta__.get("Summary")
__author__:  str = __meta__.get("Author")
__version__: str = __meta__.get("Version")

import builtins
import os
import sys
from abc import ABC, abstractmethod
from datetime import datetime
from functools import partialmethod
from pathlib import Path
from typing import Iterable

from attrs import Factory, define


@define
class LogLevel:

    name: str
    """Name and identifier"""

    @property
    def uname(self) -> str:
        """Uppercase level name"""
        return self.name.upper()

    enabled: bool = True
    """Whether this level should be logged"""

    color: str = ""
    """Base color for this level"""

    emoji: str = ""
    """Optional emoji for this level"""

    extra: dict = Factory(dict)
    """Custom formatting metadata"""

# ---------------------------------------------------------------------------- #

class Levels:
    TRACE = LogLevel(name="trace", emoji="🔷", color="dark_turquoise", enabled=False)
    DEBUG = LogLevel(name="debug", emoji="🔵", color="turquoise4", enabled=False)
    INFO  = LogLevel(name="info",  emoji="⚪️", color="bright_white")
    NOTE  = LogLevel(name="note",  emoji="🔎", color="bright_blue")
    OK    = LogLevel(name="ok",    emoji="✅", color="green")
    MINOR = LogLevel(name="minor", emoji="🔘", color="grey42")
    SKIP  = LogLevel(name="skip",  emoji="♻️", color="grey42")
    TODO  = LogLevel(name="todo",  emoji="✏️", color="dark_blue")
    TIP   = LogLevel(name="tip",   emoji="💡", color="dark_cyan")
    FIXME = LogLevel(name="fixme", emoji="🚧", color="cyan")
    WARN  = LogLevel(name="warn",  emoji="⚠️", color="yellow")
    ERROR = LogLevel(name="error", emoji="❌", color="red")
    CRIT  = LogLevel(name="crit",  emoji="💥", color="red")

# ---------------------------------------------------------------------------- #

@define(frozen=True)
class LogEntry:
    """An event that happened and shall be logged"""

    level: LogLevel
    """Verbosity level of the event"""

    args: tuple = Factory(tuple)
    """Direct arguments sent"""

    kwargs: dict = Factory(dict)
    """Keyword arguments sent"""

    @property
    def message(self) -> Iterable[str]:
        yield from map(str, self.args)
        if self.kwargs:
            yield str(self.kwargs)

    def __str__(self) -> str:
        return ''.join(self.message)

    date: datetime = Factory(datetime.now)
    """Absolute time the event happened (Local Timezone)"""

    @property
    def utc(self) -> datetime:
        """Absolute time the event happened (UTC Timezone)"""
        return self.date.astimezone(datetime.timezone.utc)

    uptime: float = Factory(lambda: time.monotonic() - REFTIME)
    """Relative time the event happened since program start"""

    echo: bool = True
    """Whether to echo the message to stdout/stderr"""

    @property
    def minsec(self) -> str:
        """Get a natural `MM'SS.sss`"""
        return f"{int(self.uptime//60)}'{(self.uptime%60):06.3f}"

# ---------------------------------------------------------------------------- #

class LogFormat:

    def simple(e: LogEntry) -> Iterable[str]:
        """Just the message contents"""
        yield from e.message

    def stopwatch(e: LogEntry) -> Iterable[str]:
        yield f"│[green]{e.minsec}[/]├"
        yield f"┤[{e.level.color} bold]{e.level.name:5}[/]│"
        yield " "
        yield from e.message

    def default(e: LogEntry) -> Iterable[str]:
        ...

    @staticmethod
    def unrich(text: str) -> str:
        """Strip rich markup from a string"""
        import re
        return re.sub(r"\[/?[^\]]+\]", "", text)

# ---------------------------------------------------------------------------- #

@define
class LogHandler(ABC):

    format: callable = LogFormat.stopwatch
    """Format callable for log messages"""

    enabled: bool = True
    """Whether this handler is enabled"""

    def _format(self, entry: LogEntry) -> str:
        return ''.join(self.format(entry))

    @abstractmethod
    def handle(self, entry: LogEntry) -> None:
        ...

# ---------------------------------------------------------------------------- #

@define
class _CommonIoHandler(LogHandler):

    rich: bool = True
    """Whether to use rich formatting or plain text"""

    # Children must set this
    _sink: object = None
    """Sink target, children must set this"""

    def handle(self, event: LogEntry) -> None:
        if self.rich:
            try:
                from rich import print
            except ImportError:
                self.rich = False
        else:
            print = builtins.print
        print(
            self._format(event),
            file=self._sink,
            flush=True,
        )

@define
class StdoutHandler(_CommonIoHandler):
    _sink: object = sys.stdout

@define
class StderrHandler(_CommonIoHandler):
    _sink: object = sys.stderr

@define
class FileHandler(_CommonIoHandler):
    path: Path = None
    mode: str = "a"

    def __attrs_post_init__(self) -> None:
        self._sink = open(self.path, self.mode)

# ---------------------------------------------------------------------------- #

@define
class DearLogger:

    handlers: list[LogHandler] = Factory(list)
    """Collection of handlers to process records"""

    def setlevels(self, config: str) -> None:
        """
        Parse a configuration string for loglevels (case-insensitive).

        Examples:
        - `info`: Enables all levels up to and including info
        - `+all`: Enable all levels
        - `-all,+warn`: Only enable the warn level
        """
        for token in config.split(","):
            ...

    def log(self,
        *args: str,
        __level__: LogLevel,
        **kwargs: dict,
    ) -> LogEntry:
        """The main, and only one, logging method."""

        # Issue a log entry
        entry = LogEntry(
            args=args,
            kwargs=kwargs,
            level=__level__,
        )

        if not __level__.enabled:
            return entry

        # Guarantee message order across handlers
        # Fixme: Should be a FIFO per handler?
        for handler in self.handlers:
            if handler.enabled:
                handler.handle(entry)

        return entry

    trace = partialmethod(log, __level__=Levels.TRACE)
    debug = partialmethod(log, __level__=Levels.DEBUG)
    info  = partialmethod(log, __level__=Levels.INFO)
    note  = partialmethod(log, __level__=Levels.NOTE)
    ok    = partialmethod(log, __level__=Levels.OK)
    minor = partialmethod(log, __level__=Levels.MINOR)
    skip  = partialmethod(log, __level__=Levels.SKIP)
    todo  = partialmethod(log, __level__=Levels.TODO)
    tip   = partialmethod(log, __level__=Levels.TIP)
    fixme = partialmethod(log, __level__=Levels.FIXME)
    warn  = partialmethod(log, __level__=Levels.WARN)
    error = partialmethod(log, __level__=Levels.ERROR)
    crit  = partialmethod(log, __level__=Levels.CRIT)

# ---------------------------------------------------------------------------- #

logger: DearLogger = DearLogger()
"""Global logger instance"""

# Add default handlers
logger.handlers.append(StdoutHandler())
logger.setlevels(os.getenv("DEARLEVEL", ""))
