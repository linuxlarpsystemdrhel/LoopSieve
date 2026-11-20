"""Original pixel-art terminal mascot. No external image or font dependency."""
from __future__ import annotations

# A compact, original 16x16-ish character. Each glyph is deliberately plain so
# it renders in a normal terminal without graphics protocols.
_PIP = [
    "        ▄▄▄▄▄▄        ",
    "     ▄██████████▄     ",
    "   ▄████▀▀▀▀▀▀████▄   ",
    "  ████  ▄▄  ▄▄  ████  ",
    "  ████  ██  ██  ████  ",
    "  ████  ▀▀  ▀▀  ████  ",
    "   ▀████▄▄▄▄▄▄████▀   ",
    "     ▀██████████▀     ",
    "      ██  ██  ██      ",
    "     ██   ██   ██     ",
    "    ██    ██    ██    ",
    "   ██     ██     ██   ",
    "  ██      ██      ██  ",
    " ██       ██       ██ ",
    "██        ██        ██",
    "          ██          ",
]

# 4-frame idle animation. It only changes the antenna and eyes, so redraws are cheap.
_FRAMES = [
    _PIP,
    [line.replace('▄▄  ▄▄', '▀▀  ▀▀') if '████  ▄▄' in line else line for line in _PIP],
    [line.replace('██  ██  ██', '██  ▀▀  ██') if '████  ▄▄' in line else line for line in _PIP],
    _PIP,
]


def pixel_mascot(frame: int = 0) -> list[str]:
    return list(_FRAMES[frame % len(_FRAMES)])


def mascot_frames() -> list[list[str]]:
    return [list(frame) for frame in _FRAMES]


def mascot_text(frame: int = 0) -> str:
    return '\n'.join(pixel_mascot(frame))
