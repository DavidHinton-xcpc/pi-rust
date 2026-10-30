"""Round-trip verify: decode the generated HTML back into a character grid and
diff it against the original ANSI bytes, cell by cell.

This is the check the previous versions lacked. It answers "did the page keep
the exact column of every glyph" without a browser, because the HTML is a plain
character grid: stripping the tags and unescaping entities must reproduce the
ANSI stream's visible text exactly, row for row, column for column.

Any shifted indentation, collapsed space, lost wrap or off-by-one column shows
up as a diff here.
"""

from __future__ import annotations

import html as htmllib
import pathlib
import re
import sys
import unicodedata

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ansi_grid import to_grid  # noqa: E402

HTML = HERE / "glyph-changes-demo.html"
CAPTURE = HERE / "_capture.txt"

SEP_RE = re.compile("<<<SECTION ([a-z0-9-]+)>>>\n")
OSC8_END = "\x1b]8;;\x07"
SGR_RE = re.compile("\x1b\\[[0-9;]*m")
OSC_RE = re.compile("\x1b\\][^\x07]*\x07")
ROW_RE = re.compile(r'<div class="row">(.*?)</div>', re.S)
TAG_RE = re.compile(r"<[^>]+>")
TERM_RE = re.compile(
    r'<div class="term" data-cols="(\d+)" data-rows="(\d+)">(.*?)</div>\s*</figure>',
    re.S,
)
# Presentation selectors occupy no cell. The build does NOT inject VS15 (that
# would rewrite the captured bytes), so selectors are compared verbatim: they
# are zero-width, but stripping them would make "⚠\ufe0f" (the real ANSI) and
# "⚠" (a lost selector) compare equal.
INVISIBLE = {"\ufe0e", "\ufe0f"}


def width(s: str) -> int:
    n = 0
    for ch in s:
        if ch in INVISIBLE or unicodedata.combining(ch):
            continue
        n += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return n


def load_sections() -> dict[str, str]:
    raw = CAPTURE.read_bytes().decode("utf-8")
    parts = SEP_RE.split(raw)
    return {
        parts[i]: parts[i + 1].replace(OSC8_END, "").rstrip("\n")
        for i in range(1, len(parts), 2)
    }


def html_rows_to_text(inner: str) -> list[str]:
    """Decode one pane's markup into its rows of visible text.

    U+FE0E/U+FE0F are presentation selectors: zero-width, but compared verbatim
    so a lost selector is still a diff.
    """
    rows = []
    for raw_row in ROW_RE.findall(inner):
        text = TAG_RE.sub("", raw_row)
        text = htmllib.unescape(text)
        rows.append(text)
    return rows


def ansi_rows_to_text(body: str) -> list[str]:
    """The same rows reconstructed straight from the ANSI bytes."""
    grid = to_grid(body)
    return ["".join(ch for ch, _ in row) for row in grid]


def main() -> None:
    # Allow verifying a specific artefact (CI checks the published
    # `pages/index.html`; a local run defaults to the demo copy).
    html_path = HTML
    if len(sys.argv) > 1:
        html_path = pathlib.Path(sys.argv[1]).resolve()
    html = html_path.read_text(encoding="utf-8")
    print(f"verifying {html_path}")
    sections = load_sections()

    panes = TERM_RE.findall(html)
    if not panes:
        sys.exit("no panes found in HTML")

    fails: list[str] = []
    checked = 0

    for cols, rows, inner in panes:
        cols_i, rows_i = int(cols), int(rows)
        decoded = html_rows_to_text(inner)
        if len(decoded) != rows_i:
            fails.append(f"{cols}x{rows}: {len(decoded)} row divs, expected {rows_i}")

        # which section does this pane belong to? match by content
        match_key = None
        for key, body in sections.items():
            want = ansi_rows_to_text(body)
            if want == decoded:
                match_key = key
                break

        if match_key is None:
            # find the closest section to explain the diff
            best, best_key = None, None
            for key, body in sections.items():
                want = ansi_rows_to_text(body)
                if len(want) == len(decoded):
                    diff = sum(1 for a, b in zip(want, decoded) if a != b)
                    if best is None or diff < best:
                        best, best_key = diff, key
            fails.append(f"{cols}x{rows}: no section matches; closest {best_key} differs on {best} rows")
            continue

        checked += 1
        want_rows = ansi_rows_to_text(sections[match_key])
        for i, (want, got) in enumerate(zip(want_rows, decoded)):
            if want != got:
                fails.append(f"{match_key} row {i}: textual diff")
        for i, (want, got) in enumerate(zip(want_rows, decoded)):
            if width(want) != width(got):
                fails.append(
                    f"{match_key} row {i}: width {width(got)} != {width(want)}"
                )

    print(f"panes in HTML: {len(panes)}")
    print(f"panes matched back to a section: {checked}")

    # declared cols must equal the widest decoded row
    print("\n== declared geometry vs decoded content ==")
    for cols, rows, inner in panes:
        decoded = html_rows_to_text(inner)
        widest = max((width(r) for r in decoded), default=0)
        ok = widest == int(cols) and len(decoded) == int(rows)
        print(
            f"  {cols:>3}x{rows:<3} decoded {widest:>3}x{len(decoded):<3} "
            f"{'OK' if ok else 'MISMATCH'}"
        )
        if not ok:
            fails.append(f"{cols}x{rows}: decoded {widest}x{len(decoded)}")

    print("\n== per-row width uniformity within a pane ==")
    for cols, rows, inner in panes:
        decoded = html_rows_to_text(inner)
        widths = {width(r) for r in decoded}
        if len(widths) > 1:
            # rows shorter than the pane are fine (trailing blanks), but they must
            # never exceed it
            if max(widths) > int(cols):
                fails.append(f"{cols}x{rows}: a row is wider than the pane")
                print(f"  {cols}x{rows}: OVERFLOW rows={sorted(widths)}")
    print("  all rows <= declared width" if not any("wider than" in f for f in fails) else "")

    print("\n== structure ==")
    for tag in ("html", "head", "body", "style", "script", "section", "figure",
                "figcaption", "div", "ul", "li", "code", "h1", "h2", "h3", "h4",
                "p", "button", "span"):
        o = len(re.findall("<" + tag + r"\b", html))
        c = html.count(f"</{tag}>")
        if o != c:
            fails.append(f"tag {tag}: {o} open vs {c} close")
    print(f"  tags balanced: {'OK' if not [f for f in fails if f.startswith('tag ')] else 'BAD'}")
    print(f"  term divs: {html.count('class=\"term\"')}")
    print(f"  row divs: {len(ROW_RE.findall(html))}")

    print()
    if fails:
        print(f"FAILURES ({len(fails)}):")
        for f in fails[:40]:
            print("  -", f)
        sys.exit(1)
    print("ALL CHECKS PASSED — HTML decodes back to the captured grid exactly")


if __name__ == "__main__":
    main()
