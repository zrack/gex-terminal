"""Color-aware Textual screenshot exports."""

from __future__ import annotations

import io
from typing import Any

from rich.console import Console
from rich.terminal_theme import TerminalTheme


GEX_TERMINAL_THEME = TerminalTheme(
    background=(8, 10, 13),
    foreground=(233, 238, 243),
    normal=[
        (8, 10, 13),
        (251, 113, 133),
        (74, 222, 128),
        (251, 191, 36),
        (56, 189, 248),
        (139, 92, 246),
        (56, 189, 248),
        (226, 232, 240),
    ],
    bright=[
        (100, 116, 139),
        (251, 113, 133),
        (74, 222, 128),
        (251, 191, 36),
        (56, 189, 248),
        (167, 139, 250),
        (125, 211, 252),
        (248, 250, 252),
    ],
)


TERMINAL_SVG_COLOR_REPLACEMENTS = {
    "#0f0f0f": "#0b1118",
    "#101010": "#080a0d",
    "#111111": "#0f172a",
    "#141414": "#111827",
    "#161616": "#111827",
    "#171717": "#111827",
    "#191919": "#0d141c",
    "#1b1b1b": "#0f172a",
    "#1e1e1e": "#1e293b",
    "#202020": "#1e293b",
    "#242424": "#1e293b",
    "#2d2d2d": "#1e293b",
    "#303030": "#263445",
    "#363636": "#263445",
    "#393939": "#263445",
    "#444444": "#334155",
    "#5c5c5c": "#4ade80",
    "#656565": "#38bdf8",
    "#727272": "#64748b",
    "#909090": "#94a3b8",
    "#959595": "#94a3b8",
    "#a1a1a1": "#94a3b8",
    "#a5a5a5": "#38bdf8",
    "#a6a6a6": "#38bdf8",
    "#b0b0b0": "#fbbf24",
    "#b8b8b8": "#cbd5e1",
    "#c1c1c1": "#fbbf24",
    "#c2c2c2": "#e2e8f0",
    "#c5c8c6": "#e9eef3",
    "#c9c9c9": "#e2e8f0",
    "#d4d4d4": "#e2e8f0",
    "#e0e0e0": "#f8fafc",
    "#e4e4e4": "#4ade80",
    "#eaeaea": "#fb7185",
    "#ededed": "#f8fafc",
    "#f4f4f4": "#f8fafc",
}


def colorize_terminal_svg(svg: str) -> str:
    """Map Textual's grayscale SVG export colors onto the README preview palette."""
    for source, replacement in TERMINAL_SVG_COLOR_REPLACEMENTS.items():
        svg = svg.replace(source, replacement)
    trailing_newline = "\n" if svg.endswith("\n") else ""
    return "\n".join(line.rstrip() for line in svg.splitlines()) + trailing_newline


def export_app_screenshot_svg(
    app: Any,
    *,
    title: str | None = None,
    simplify: bool = False,
) -> str:
    """Export a Textual app screenshot using the gex-terminal color theme."""
    width, height = app.size
    console = Console(
        width=width,
        height=height,
        file=io.StringIO(),
        force_terminal=True,
        color_system="truecolor",
        record=True,
        legacy_windows=False,
        safe_box=False,
    )
    screen_render = app.screen._compositor.render_update(
        full=True,
        screen_stack=app._background_screens,
        simplify=simplify,
    )
    console.print(screen_render)
    svg = console.export_svg(title=title or app.title, theme=GEX_TERMINAL_THEME)
    return colorize_terminal_svg(svg)
