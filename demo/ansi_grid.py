"""Turn captured ANSI into an exact static HTML character grid.

Why not xterm.js
----------------
xterm.js lays the grid out itself: ``.xterm-screen canvas`` is absolutely
positioned and the canvas dimensions are computed from its *own* measurement of
the element, so a parent ``padding`` or a CSS width fights it. The result is
the shifted, clipped, double-spaced panes that kept appearing. Every pane had
to agree with xterm's internal geometry, and it never quite did.

A static grid has no such negotiation. Each cell is one ``ch`` wide because the
font is monospace, the padding is a real DOM box, and the column of every glyph
is fixed by the bytes: a glyph at grid column 12 is preceded by exactly 12
characters. Nothing is measured, so nothing can drift.

The only fidelity loss versus a real terminal is glyph advance width, which the
browser takes from the font's own monospace metrics -- the same source a
terminal emulator uses.
"""

from __future__ import annotations

import html as htmllib
import re
import unicodedata

# ---- ANSI SGR -> (fg, bg, bold) -------------------------------------------

SGR_RE = re.compile("\x1b\\[([0-9;]*)m")
OSC_RE = re.compile("\x1b\\][^\x07]*\x07")

DEFAULT_FG = None
DEFAULT_BG = None


def xterm256_to_hex(n: int) -> str:
    """The xterm 256-colour palette, exactly as a terminal resolves it."""
    base16 = [
        "#000000", "#800000", "#008000", "#808000", "#000080", "#800080",
        "#008080", "#c0c0c0", "#808080", "#ff0000", "#00ff00", "#ffff00",
        "#0000ff", "#ff00ff", "#00ffff", "#ffffff",
    ]
    if n < 16:
        return base16[n]
    if n < 232:
        n -= 16
        r, g, b = n // 36, (n % 36) // 6, n % 6
        steps = [0, 95, 135, 175, 215, 255]
        return "#%02x%02x%02x" % (steps[r], steps[g], steps[b])
    v = 8 + (n - 232) * 10
    return "#%02x%02x%02x" % (v, v, v)


class Style:
    """One cell's resolved appearance."""

    __slots__ = ("fg", "bg", "bold", "italic")

    def __init__(self, fg=None, bg=None, bold=False, italic=False):
        self.fg = fg
        self.bg = bg
        self.bold = bold
        self.italic = italic

    def key(self):
        return (self.fg, self.bg, self.bold, self.italic)

    def copy(self):
        return Style(self.fg, self.bg, self.bold, self.italic)

    def css(self):
        parts = []
        if self.fg:
            parts.append(f"color:{self.fg}")
        if self.bg:
            parts.append(f"background:{self.bg}")
        if self.bold:
            parts.append("font-weight:700")
        if self.italic:
            parts.append("font-style:italic")
        return ";".join(parts)


def apply_sgr(style: Style, params: str) -> Style:
    """Mutate `style` in place per one SGR sequence."""
    if params == "":
        return Style()
    nums = [int(p) if p else 0 for p in params.split(";")]
    i = 0
    while i < len(nums):
        n = nums[i]
        if n == 0:
            style = Style()
        elif n == 1:
            style.bold = True
        elif n == 3:
            style.italic = True
        elif n == 22:
            style.bold = False
        elif n == 23:
            style.italic = False
        elif n == 39:
            style.fg = DEFAULT_FG
        elif n == 49:
            style.bg = DEFAULT_BG
        elif n == 38 and i + 2 < len(nums) and nums[i + 1] == 5:
            style.fg = xterm256_to_hex(nums[i + 2])
            i += 2
        elif n == 48 and i + 2 < len(nums) and nums[i + 1] == 5:
            style.bg = xterm256_to_hex(nums[i + 2])
            i += 2
        elif n == 38 and i + 4 < len(nums) and nums[i + 1] == 2:
            style.fg = "#%02x%02x%02x" % tuple(nums[i + 2 : i + 5])
            i += 4
        elif n == 48 and i + 4 < len(nums) and nums[i + 1] == 2:
            style.bg = "#%02x%02x%02x" % tuple(nums[i + 2 : i + 5])
            i += 4
        i += 1
    return style


def cell_width(ch: str) -> int:
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def to_grid(text: str) -> list[list[tuple[str, Style]]]:
    """Parse SGR text into rows of (char, style) cells, one cell per column.

    Wide glyphs occupy two cells: the glyph then an empty continuation cell, so
    every row has the same length and column N is the same screen column in
    every row.
    """
    text = OSC_RE.sub("", text)
    rows: list[list[tuple[str, Style]]] = []
    cur: list[tuple[str, Style]] = []
    style = Style()

    i = 0
    while i < len(text):
        m = SGR_RE.match(text, i)
        if m:
            style = apply_sgr(style, m.group(1))
            i = m.end()
            continue
        ch = text[i]
        if ch == "\n":
            rows.append(cur)
            cur = []
            i += 1
            continue
        w = cell_width(ch)
        if w == 0:
            i += 1
            continue
        cur.append((ch, style.copy()))
        if w == 2:
            cur.append(("", style.copy()))
        i += 1
    rows.append(cur)

    width = max((len(r) for r in rows), default=0)
    for r in rows:
        r.extend([(" ", Style())] * (width - len(r)))
    return rows


def grid_to_html(rows: list[list[tuple[str, Style]]]) -> str:
    """Render the grid as one <span> per styled run, preserving every column.

    A row is emitted as consecutive runs plus a trailing block of explicit
    ``&nbsp;``/spaces up to the pane width, so a short row still occupies the
    full grid. Runs never cross a row boundary, which keeps each row's DOM
    independent of its neighbours.
    """
    out = []
    for row in rows:
        cells = []
        i = 0
        while i < len(row):
            ch, st = row[i]
            # a continuation cell (wide glyph) emits nothing: the glyph before it
            # already covers the column
            if ch == "":
                i += 1
                continue
            j = i + 1
            while j < len(row) and row[j][1].key() == st.key() and row[j][0] != "":
                j += 1
            segment = "".join(c for c, _ in row[i:j])
            css = st.css()
            # Every space is a cell, so it must not be collapsed by HTML: "a  b"
            # has to stay three columns wide, not become "a b". `white-space:
            # pre` on `.term` already preserves them; escaping only the markup
            # characters keeps the font's own space glyph (an &nbsp; can have a
            # different advance in some monospace CJK fonts).
            esc = htmllib.escape(segment, quote=False)
            cells.append(f'<span style="{css}">{esc}</span>' if css else esc)
            i = j
        out.append('<div class="row">' + "".join(cells) + "</div>")
    return "\n".join(out)
