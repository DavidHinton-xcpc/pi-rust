"""Build demo/glyph-changes-demo.html as an exact static character grid.

Pipeline
--------
1. ``cargo run -q -p rpi-cli --example glyph_capture > demo/_capture.txt``
   That example calls the same components (and the same
   ``interactive_tui::rendering`` helpers) the live TUI calls, so the bytes are
   the renderer's own output.
2. ``python demo/build_glyph_demo.py``
   Parses those bytes into a per-cell grid (``ansi_grid.py``) and emits plain
   HTML: one monospace character per column, padding as a real DOM box.

Why no terminal emulator
------------------------
xterm.js positions ``.xterm-screen canvas`` absolutely and derives its own
geometry from element measurement, so a parent width/padding fights it. That is
what kept shifting and clipping every pane. A static grid has nothing to
negotiate: grid column N is preceded by exactly N characters, every cell is one
``ch`` wide, and short rows are padded to the pane width so all rows of a pane
share one right edge. Nothing is measured at render time, so nothing can drift.

Layout rule
-----------
A captured section is a *concatenation of independent components*, so its real
size is (rows, widest line), not the 78 columns the capture happened to render
at:

* short sections (``07-lockup`` is 22x5, ``07-lockup-no-crab`` is 4x1) must not
  be stretched to 78 columns -- that was the padded emptiness;
* the 79-column search-bar pane must not be clipped to 78 -- the one-column
  overflow *is* the bug that pane demonstrates, so it renders at 79 and is
  called out.
"""

from __future__ import annotations

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from ansi_grid import grid_to_html, to_grid  # noqa: E402

CAPTURE = HERE / "_capture.txt"
OUT = HERE / "glyph-changes-demo.html"

# "<<<SECTION name>>>\n" markers from the capture example.
SEP_RE = re.compile("<<<SECTION ([a-z0-9-]+)>>>\n")
# OSC 8 hyperlink terminators carry no visible width.
OSC8_END = "\x1b]8;;\x07"


def load_sections() -> dict[str, str]:
    raw = CAPTURE.read_bytes().decode("utf-8")
    parts = SEP_RE.split(raw)
    out: dict[str, str] = {}
    for i in range(1, len(parts), 2):
        out[parts[i]] = parts[i + 1].replace(OSC8_END, "").rstrip("\n")
    return out


def metrics(body: str) -> tuple[int, int]:
    rows = to_grid(body)
    return len(rows), (len(rows[0]) if rows else 0)


GROUPS = [
    {
        "num": "01",
        "title": "note 消息 · 模型切换提示",
        "caption": (
            "真实行为：<code>add_note_message</code> 在字符串里写 <code>\"  {}\"</code>，"
            "<code>Text::new(..., 1, 0)</code> 再加 1 列 pad，所以正文从第 4 列开始。"
            "左栏是现有实现的输出，右栏是同一条 <code>Text</code> 路径换成"
            "「无图标 + <code>md_heading</code> 色 + 不加粗」后的输出。"
        ),
        "panes": [
            ("改动前", "before", "01-note-before"),
            ("改动后", "after", "01-note-after"),
        ],
        "delta_before": [
            "前缀 <code>ℹ</code>（U+2139），色 <code>info</code> = <code>Ansi256(81)</code>",
            "正文 <code>muted</code> = <code>Ansi256(244)</code>",
            "彩色终端把 <code>ℹ</code> 抬成图形后占 2 列 → 整行右移",
        ],
        "delta_after": [
            "无图标，只留 <code>\"  {}\"</code> + 1 列 pad",
            "色换成 <code>md_heading</code> = <code>Ansi256(179)</code>，与回答标题同色",
            "不加粗、不斜体；行宽恢复准确",
        ],
    },
    {
        "num": "02",
        "title": "<code>/help</code> · <code>/version</code> · <code>/hotkeys</code> 表头",
        "caption": (
            "这三处是 <code>md_heading.fg(&amp;bold(title))</code>，emoji 直接写在标题字符串里。"
            "注意 <code>⌨️</code> 是 <code>⌨</code> + VS16 <code>U+FE0F</code>，后面还跟两个空格。"
            "<b>emoji 只占一个前缀，去掉后标题仍是 <code>md_heading</code> 黄色加粗</b>，"
            "颜色与字重不变。"
        ),
        "cols": 2,
        "panes": [
            ("/help · 改动前", "before", "02-help-before"),
            ("/help · 改动后", "after", "02-help-after"),
            ("/version · 改动前", "before", "02-version-before"),
            ("/version · 改动后", "after", "02-version-after"),
            ("/hotkeys · 改动前", "before", "02-hotkeys-before"),
            ("/hotkeys · 改动后", "after", "02-hotkeys-after"),
        ],
        "delta_before": [
            "<code>\"📚 Available Commands\"</code>、<code>\"📦 Version Information\"</code>、"
            "<code>\"⌨️  Keyboard Shortcuts\"</code>",
            "emoji 占 2 列，标题起始列随终端字体漂移",
        ],
        "delta_after": [
            "三个字符串砍成纯文字；<code>⌨️</code> 连同 <code>U+FE0F</code> 与多余空格一并删掉",
            "<code>md_heading</code> = <code>#d7af5f</code> + <code>bold</code> 完全保留",
        ],
    },
    {
        "num": "03",
        "title": "<code>/skills</code> · <code>/context</code> 面板标题",
        "caption": (
            "这两处走 <code>container_note_block</code>：逐行 <code>Text::new(line, 1, 0)</code>，"
            "<b>不带任何主题色</b>，整段用终端默认前景色。去掉 emoji 后，标题就和正文一样是"
            "默认白，看不出是个标题。<b>改动后标题改走 <code>md_heading</code></b>，"
            "与 <code>/help</code>、<code>/version</code>、<code>/hotkeys</code> 和 note 消息同色；"
            "正文行保持无色不变。"
        ),
        "cols": 2,
        "panes": [
            ("/skills · 改动前", "before", "03-skills-before"),
            ("/skills · 改动后", "after", "03-skills-after"),
            ("/context · 改动前", "before", "03-context-before"),
            ("/context · 改动后", "after", "03-context-after"),
        ],
        "delta_before": [
            "<code>\"🧩 Skills available in this session:\"</code>",
            "<code>\"📂 Discovered resources for this session:\"</code>",
            "整段无 <code>fg()</code>：标题与正文同为默认白",
        ],
        "delta_after": [
            "首行改为 <code>c.md_heading.fg(\"…\")</code> → <code>Ansi256(179)</code> / <code>#d7af5f</code>",
            "正文行（<code>•</code> 列表、<code>Context (2):</code> 等）保持无色",
            "标题不加粗，与 <code>add_note_message</code> 的形制一致",
        ],
    },
    {
        "num": "04",
        "title": "搜索栏 · Ctrl+F",
        "caption": (
            "左栏是 <code>SearchBar</code> <b>真实组件</b>的输出，实际占 <b>79 列</b>："
            "<code>padding</code> 用 <code>left.chars().count()</code> 把 <code>🔍</code> 当 1 列，"
            "而它实占 2 列，于是整行撑出 1 列。这一列溢出<b>就是</b>本栏要展示的缺陷，"
            "所以左栏按 79 列如实呈现，不做裁切。"
        ),
        "panes": [
            ("改动前", "before", "04-search-before"),
            ("改动后", "after", "04-search-after"),
        ],
        "delta_before": [
            "<code>let search_icon = \"🔍\";</code> → <code>format!(\"{} Search: {}\", …)</code>",
            "宽度按 <code>chars().count()</code> 算，emoji 少算 1 列 → 整行 79 列",
        ],
        "delta_after": [
            "删掉 <code>search_icon</code>，格式串变 <code>\" Search: {}\"</code>",
            "合计 78 列整，不再溢出",
        ],
    },
    {
        "num": "05",
        "title": "助手错误横幅",
        "caption": (
            "前三个是 <code>AssistantMessageComponent::update_error</code> 针对三种 "
            "<code>stop_reason</code> 的<b>真实输出</b>。它整行 <code>Text::new</code> 且"
            "<b>不带主题色</b>——「这是错误」全靠 emoji 本体表达。"
        ),
        "cols": 2,
        "panes": [
            ("stop_reason=error", "before", "05-error-before"),
            ("stop_reason=aborted", "before", "05-error-aborted"),
            ("stop_reason=length", "before", "05-error-length"),
            ("改动后（统一形制）", "after", "05-error-after"),
        ],
        "delta_before": [
            "<code>\"❌ Error: {}\"</code> ／ <code>\"❌ Operation aborted: {}\"</code> ／ "
            "<code>\"⚠️ Response was truncated…\"</code>",
            "<code>❌</code> 是 <code>EAW=W</code>（2 列）、<code>⚠️</code> 带 VS16 也是 2 列",
        ],
        "delta_after": [
            "改用 <code>add_error_message</code> 已在用的 <code>✗</code> + "
            "<code>error</code>（<code>Ansi256(131)</code>）",
            "必须补主题色，否则纯 <code>✗</code> 在默认前景色里看不出是错误",
        ],
    },
    {
        "num": "06",
        "title": "长时命令中止提示 · <code>⏸</code> → <code>↳</code>",
        "caption": (
            "上半是 <code>BashExecutionComponent</code> 的真实渲染：没有边框，而是"
            "<b>背景色整行铺满</b>的色带，含 <code>●</code> 状态点与耗时。"
            "末行是 <code>bash_execution.rs:348</code> 的 hint，只在 "
            "<code>LONG_RUNNING_HINT_AFTER = 60s</code> 之后才出现。"
        ),
        "panes": [
            ("改动前", "before", "06-bash-before"),
            ("改动后", "after", "06-bash-after"),
        ],
        "delta_before": [
            "<code>format!(\"{} Esc / Ctrl+C 中止\", colors.muted.fg(\"⏸\"))</code>",
            "<code>⏸</code> U+23F8：<code>Emoji=Yes</code> / <code>EAW=N</code>，彩色终端抬成 2 列",
        ],
        "delta_after": [
            "同一 <code>colors.muted</code>，仅换字形为 <code>↳</code>（U+21B3）",
            "与 <code>set_pending_queue</code> 的 <code>\"↳ {} to edit all queued messages\"</code> 对齐",
        ],
    },
    {
        "num": "07",
        "title": "保留不动 · 🦀 与 ☐ / ☒",
        "caption": (
            "两个例外给全。<code>BrandLockup</code> 是真实组件；任务列表走真实的 "
            "<code>Markdown</code> 渲染器——注意真实输出里行内 code 两侧的空格残留。"
        ),
        "panes": [
            ("🦀 lockup（真实组件）", "keep", "07-lockup"),
            ("☐ / ☒ 任务列表（真实渲染器）", "keep", "07-md-tasks"),
        ],
        "delta_before": [
            "<code>RPI_NO_EMOJI=1</code> 时 <code>plain_name()</code> 只输出 <code>rpi</code>，见下：",
            "<code>render_lockup(false)</code> 去掉 <code>· 🦀</code> 与分隔符，不留尾随空格",
        ],
        "sidecar": "07-lockup-no-crab",
        "sidecar_label": "<code>RPI_NO_EMOJI=1</code> 的真实输出",
        "delta_after": [
            "<code>☐</code> U+2610 ／ <code>☒</code> U+2612：<code>EAW=N</code>、"
            "<code>Emoji_Presentation=No</code>，稳定单宽",
        ],
    },
    {
        "num": "08",
        "title": "note 折叠 · 连续变更只占一行，原地迭代",
        "caption": (
            "左栏 11 条 note 的真实渲染：22 行（含折行共 23 行），全部写进 transcript 并永久"
            "留在滚动缓冲区。右栏是 <code>status_container</code> 的单槽位——"
            "先 <code>clear()</code> 再 <code>add_child(...)</code>，与 "
            "<code>state.rs:1535 show_retry</code> 同一套机制。"
        ),
        "panes": [
            ("改动前 · 逐行累积", "before", "08-fold-before"),
            ("改动后 · 单行原地迭代", "after", "08-fold-after"),
        ],
        "delta_before": [
            "<code>add_child(Text)</code> + <code>add_child(Spacer(1))</code>，一条 note = 2 行高",
            "105 个调用点全部指向 <code>&amp;ctx.chat</code> / <code>&amp;state.chat_container</code>",
            "长文案（那条 99 字符的 provider 提示）被 <code>wrap_text_with_ansi</code> 折成 2 行",
        ],
        "delta_after": [
            "复用 <code>status_container</code>：<code>clear()</code> + 一条 <code>Text</code>",
            "<code>RunStatus::Working/Aborting/Idle</code> 三个分支本就会 <code>clear()</code>，note 自动让位",
            "取消 <code>Spacer(1)</code>，行高 2 → 1",
        ],
    },
]

WARNINGS = {
    "05": [
        "<b>删掉 <code>❌</code>／<code>⚠️</code> 后必须补主题色。</b>"
        "原实现整行没有 <code>fg()</code>，唯一的视觉信号就是 emoji 本身；"
        "只换字形会让错误行退化成普通文本。",
    ],
    "08": [
        "<b>历史丢失。</b>覆盖后旧 note 就没了。<code>Default saved.</code>／"
        "<code>Could not save the default: …</code> 这类<b>带结果</b>的提示被覆盖后，"
        "用户回翻时无法确认「刚才那次到底存没存上」。建议只折叠纯状态类 note。",
        "<b>错误路径不该折叠。</b><code>add_error_message</code> 与一次性确认"
        "（<code>Copied …</code>、<code>Default saved.</code>）应继续写进 transcript。",
        "<b>与 retry 抢槽位。</b><code>show_retry</code> 也写 <code>status_container</code>，"
        "note 在重试期间到达会顶掉 <code>StatusIndicator::retry</code> 的 spinner，反之亦然。",
        "<b>并非严格一行。</b>dock 宽度不足时长文案仍会折成 2 行。",
    ],
}


def build(out: pathlib.Path | None = None) -> None:
    sections = load_sections()
    metrics_by_key = {k: metrics(v) for k, v in sections.items()}

    needed = {k for g in GROUPS for _, _, k in g["panes"]}
    needed |= {g["sidecar"] for g in GROUPS if g.get("sidecar")}
    missing = sorted(needed - set(sections))
    if missing:
        sys.exit(
            "capture is missing "
            + str(missing)
            + "; re-run `cargo run -p rpi-cli --example glyph_capture > demo/_capture.txt`"
        )

    blocks = []
    for g in GROUPS:
        ncols = g.get("cols") or min(len(g["panes"]), 2)
        panes_html = []
        for label, kind, key in g["panes"]:
            rows, cols = metrics_by_key[key]
            over = cols > 78
            badge = f'<span class="overflow">超出 78 列 · {cols}</span>' if over else ""
            panes_html.append(
                '<figure class="pane">'
                f'<figcaption class="panehead {kind}">'
                '<span class="dot"></span>'
                f'<span class="plabel">{label}</span>'
                f"{badge}"
                f'<span class="dims">{cols}×{rows}</span>'
                "</figcaption>"
                f'<div class="term" data-cols="{cols}" data-rows="{rows}">'
                f"{grid_to_html(to_grid(sections[key]))}"
                "</div>"
                "</figure>"
            )

        def deltas(items, kind):
            if not items:
                return ""
            head = "改动前" if kind == "b" else "改动后"
            body = "".join(f"<li>{x}</li>" for x in items)
            return f'<div class="box {kind}"><h4>{head}</h4><ul>{body}</ul></div>'

        sidecar = ""
        if g.get("sidecar"):
            sk = g["sidecar"]
            r, c = metrics_by_key[sk]
            sidecar = (
                '<figure class="pane sidecarPane">'
                '<figcaption class="panehead keep"><span class="dot"></span>'
                f'<span class="plabel">{g.get("sidecar_label", "对照")}</span>'
                f'<span class="dims">{c}×{r}</span>'
                "</figcaption>"
                f'<div class="term" data-cols="{c}" data-rows="{r}">'
                f"{grid_to_html(to_grid(sections[sk]))}"
                "</div>"
                "</figure>"
            )

        warn = ""
        if g["num"] in WARNINGS:
            body = "".join(f"<li>{x}</li>" for x in WARNINGS[g["num"]])
            warn = f'<div class="warnbox"><h4>需要你拍板</h4><ul>{body}</ul></div>'

        blocks.append(
            '<section class="group">'
            '<header class="ghead">'
            f'<h2><span class="num">{g["num"]}</span>{g["title"]}</h2>'
            f'<p class="caption">{g["caption"]}</p>'
            "</header>"
            f'<div class="panes" style="--cols:{ncols}">{"".join(panes_html)}</div>'
            f"{sidecar}"
            f'<div class="delta">{deltas(g["delta_before"], "b")}{deltas(g["delta_after"], "a")}</div>'
            f"{warn}"
            "</section>"
        )

    html = TEMPLATE.format(
        body="".join(blocks),
        n_groups=len(GROUPS),
        n_panes=len(needed),
        total_rows=sum(metrics_by_key[k][0] for k in needed),
    )
    target = out or OUT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    print(f"wrote {target} ({len(html.encode()):,} bytes)")
    print(f"  {len(GROUPS)} groups, {len(needed)} panes")
    for g in GROUPS:
        parts = [f"{k}={metrics_by_key[k][1]}x{metrics_by_key[k][0]}" for _, _, k in g["panes"]]
        print(f"  {g['num']}: " + "  ".join(parts))


TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>rpi glyph 调整 · 真机 ANSI 逐格回放对比</title>
<style>
  :root {{
    --mx: 24px;
    --page: 1560px;
    --bg: #0b0b0e;
    --panel: #121216;
    --line: #23232b;
    --fg: #d8d8d8;
    --fg-dim: #8b8b96;
    --ui: system-ui, -apple-system, "Segoe UI", "PingFang SC",
          "Microsoft YaHei", sans-serif;
    /* One font stack for every pane, so column advance is identical everywhere
       and a cell is exactly 1ch. */
    --term-font: "Cascadia Mono", "JetBrains Mono", "Sarasa Mono SC", Consolas,
                 "DejaVu Sans Mono", "Noto Sans Mono CJK SC", monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--fg);
    font-family: var(--ui); line-height: 1.6;
  }}
  code {{
    font-family: var(--term-font); font-size: .9em; background: #1e1e25;
    padding: 1px 5px; border-radius: 4px; color: #c6c6d2;
    white-space: nowrap;
  }}

  /* ---------- header ---------- */
  .page {{ max-width: var(--page); margin: 0 auto; padding: 44px var(--mx) 0; }}
  .page h1 {{ font-size: 28px; margin: 0 0 10px; letter-spacing: -.015em; }}
  .page .lede {{ margin: 0; color: var(--fg-dim); font-size: 14.5px; max-width: 96ch; }}

  /* ---------- toolbar ---------- */
  .toolbar {{
    position: sticky; top: 0; z-index: 20;
    margin: 22px auto 0; max-width: var(--page); padding: 10px var(--mx);
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    background: rgba(11,11,14,.9); backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--line); font-size: 13px; color: var(--fg-dim);
  }}
  .toolbar button {{
    font: inherit; font-size: 12.5px; padding: 5px 14px; border-radius: 7px;
    border: 1px solid #2c2c35; background: #17171c; color: #cfcfd8; cursor: pointer;
  }}
  .toolbar button[aria-pressed="true"] {{
    border-color: #4a6f68; background: #1b2a27; color: #9fd0c8;
  }}
  .toolbar .grow {{ flex: 1 1 auto; }}
  .toolbar .stat {{ font-family: var(--term-font); font-size: 11.5px; color: #55555f; }}

  /* ---------- group ---------- */
  .group {{ max-width: var(--page); margin: 44px auto 0; padding: 0 var(--mx); }}
  .group + .group {{ border-top: 1px solid #181820; padding-top: 40px; }}
  .ghead h2 {{
    font-size: 18px; margin: 0 0 6px; font-weight: 700; color: #ececf2;
    line-height: 1.35;
  }}
  .ghead h2 .num {{
    font-family: var(--term-font); font-size: 13px; color: #5c5c68;
    margin-right: 10px; vertical-align: 2px;
  }}
  .ghead .caption {{
    margin: 0 0 16px; color: var(--fg-dim); font-size: 13.5px; max-width: 116ch;
  }}
  .ghead .caption b {{ color: #c2c2ce; font-weight: 600; }}

  /* ---------- panel grid ---------- */
  .panes {{
    display: grid;
    grid-template-columns: repeat(var(--cols, 2), minmax(0, 1fr));
    gap: 18px 20px;
    align-items: start;
  }}
  @media (max-width: 1100px) {{
    .panes {{ grid-template-columns: repeat(min(var(--cols, 2), 2), minmax(0, 1fr)); }}
  }}
  @media (max-width: 780px) {{ .panes {{ grid-template-columns: minmax(0, 1fr); }} }}
  .pane {{ margin: 0; min-width: 0; display: flex; flex-direction: column; }}
  .sidecarPane {{ margin-top: 14px; }}

  .panehead {{
    display: flex; align-items: center; gap: 7px;
    font-size: 11px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; margin-bottom: 7px;
    font-family: var(--ui); white-space: nowrap;
  }}
  .panehead .plabel {{ overflow: hidden; text-overflow: ellipsis; min-width: 0; }}
  .panehead .dot {{ width: 7px; height: 7px; border-radius: 50%; flex: none; }}
  .panehead.before {{ color: #d97b7b; }}
  .panehead.before .dot {{ background: #d97b7b; }}
  .panehead.after {{ color: #7bc48c; }}
  .panehead.after .dot {{ background: #7bc48c; }}
  .panehead.keep {{ color: #7f9fd6; }}
  .panehead.keep .dot {{ background: #7f9fd6; }}
  .panehead .dims {{
    margin-left: auto; font-weight: 400; letter-spacing: 0; text-transform: none;
    color: #55555f; font-family: var(--term-font); font-size: 10.5px; flex: none;
  }}
  .panehead .overflow {{
    font-weight: 600; letter-spacing: 0; text-transform: none;
    color: #e8c884; background: #2a2312; border: 1px solid #4d3f24;
    border-radius: 999px; padding: 1px 7px; font-size: 10px; flex: none;
  }}

  /* ---------- terminal: static character grid ---------- */
  .term {{
    font-family: var(--term-font);
    font-size: 13px;
    line-height: 1.28;
    /* `ch` is exact in a monospace font: one cell per column. */
    padding: 9px 11px;
    margin: 0;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #101014;
    color: #e4e4e4;
    box-shadow: 0 8px 26px rgba(0,0,0,.45);
    /* Each row is its own block, so a short row keeps the pane's full width
       instead of collapsing and shifting its neighbours. */
    white-space: pre;
    overflow-x: auto;
    overflow-y: hidden;
    /* Ligatures and kerning would merge or shift glyphs off the grid. */
    text-rendering: optimizeSpeed;
    font-variant-ligatures: none;
    font-kerning: none;
    font-synthesis: none;
    align-self: start;
    max-width: 100%;
  }}
  .term > div {{ min-height: 1.28em; }}

  /* ---------- delta ---------- */
  .delta {{
    margin-top: 14px; display: grid; gap: 12px;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    font-size: 13px;
  }}
  .box, .warnbox {{
    border: 1px solid var(--line); border-radius: 8px; padding: 11px 14px;
    background: var(--panel);
  }}
  .box h4, .warnbox h4 {{
    margin: 0 0 7px; font-size: 11px; letter-spacing: .07em; text-transform: uppercase;
  }}
  .box.b h4 {{ color: #d97b7b; }}
  .box.a h4 {{ color: #7bc48c; }}
  .box ul, .warnbox ul {{ margin: 0; padding-left: 18px; color: #a9a9b4; }}
  .box li, .warnbox li {{ margin: 4px 0; }}
  .warnbox {{ margin-top: 12px; border-color: #3a3320; background: #151208; }}
  .warnbox h4 {{ color: #e8c884; }}
  .warnbox ul {{ color: #c3bca8; }}

  /* ---------- footnotes ---------- */
  .footnotes {{
    max-width: var(--page); margin: 40px auto 72px; padding: 30px var(--mx) 0;
    border-top: 1px solid #181820; color: var(--fg-dim); font-size: 13px;
  }}
  .footnotes h3 {{ color: #b9b9c4; font-size: 14px; margin: 22px 0 8px; }}
  .footnotes h3:first-child {{ margin-top: 0; }}
  .footnotes ul {{ padding-left: 20px; margin: 0; }}
  .footnotes li {{ margin: 6px 0; }}
  .footnotes code {{ white-space: normal; }}

  /* light preset */
  body.light {{
    --bg: #ffffff; --panel: #f6f6f7; --line: #dcdce2;
    --fg: #1f1f1f; --fg-dim: #5f5f6b;
  }}
  body.light code {{ background: #ececf0; color: #33333d; }}
  body.light .term {{
    background: #ffffff; color: #1f1f1f; border-color: #dcdce2;
    box-shadow: 0 6px 20px rgba(0,0,0,.08);
  }}
  body.light .toolbar {{ background: rgba(255,255,255,.92); }}
  body.light .box, body.light .warnbox {{ background: var(--panel); }}
  body.light .box.b h4 {{ color: #b04a4a; }}
  body.light .box.a h4 {{ color: #3f7a4f; }}
  body.light .warnbox {{ background: #fdf8e8; border-color: #e2d5a8; }}
  body.light .warnbox h4 {{ color: #8a6a12; }}
</style>
</head>
<body>

<div class="page">
  <h1>rpi glyph 调整 · 真机 ANSI 逐格回放对比</h1>
  <p class="lede">
    每个面板都是 <code>rpi-tui</code> 组件输出的真实字节流，逐格转成 HTML：
    网格第 N 列前面正好有 N 个字符，每个 cell 恒为 <code>1ch</code>，短行补足到面板宽度，
    所以同一面板内所有行共用一条右边界。颜色是 <code>theme.rs</code> 真实的
    <code>Ansi256</code> 索引换算成的十六进制值。<b>不在渲染期做任何测量</b>，
    因此列位置不会漂移。
  </p>
</div>

<div class="toolbar">
  <span>主题预设</span>
  <button id="btn-dark" aria-pressed="true">dark</button>
  <button id="btn-light" aria-pressed="false">light</button>
  <span class="grow"></span>
  <span class="stat">{n_groups} 组 · {n_panes} 个面板 · {total_rows} 行</span>
</div>

{body}

<div class="footnotes">
  <h3>生成方式</h3>
  <ul>
    <li><code>crates/rpi-cli/examples/glyph_capture.rs</code> 调用真实组件
      （<code>AssistantMessageComponent</code>、<code>BashExecutionComponent</code>、
      <code>Markdown</code>、<code>SearchBar</code>、<code>FooterComponent</code>、
      <code>BrandLockup</code>）与 <code>interactive_tui/rendering.rs</code> 的
      note/error 助手，把原始字节流打到 stdout。</li>
    <li><code>demo/ansi_grid.py</code> 把 SGR 序列解析成逐格网格：
      <code>38;5;N</code> 按 xterm 256 色表换算，<code>38;2;r;g;b</code> / <code>48;2;…</code>
      原样保留，<code>1</code>/<code>22</code> 映射到 <code>font-weight</code>。</li>
    <li>重新生成：
      <code>cargo run -q -p rpi-cli --example glyph_capture &gt; demo/_capture.txt</code>
      然后 <code>python demo/build_glyph_demo.py</code>。</li>
  </ul>

  <h3>与真机的差异（诚实说明）</h3>
  <ul>
    <li><b>字形来自你系统的字体</b>，与 Windows Terminal / WezTerm 不同；但<b>列位置、
      颜色索引、折行点</b>由字节流决定，与真机一致。</li>
    <li><b><code>ℹ ⏸ ✗ ⚠ ↳ ☐ ☒</code></b> 这些 <code>EAW=N</code> 但
      <code>Emoji=Yes</code> 的符号，本页统一追加 <code>U+FE0E</code>（VS15，文本呈现）
      并按 1 列排版，与组件输出的列数一致。如果你的终端把它们画成 2 列，那一处会差 1 列。</li>
    <li><b>01/02/03/05 的「改动后」与 08 的折叠版</b>是用同一套组件与字符串渲染的
      <b>提案态</b>（尚未写进源码），不是现有行为。</li>
    <li>未包含 alt-screen 外框、editor 输入框、footer 分隔线等布局元素；取样单元是
      transcript 内的单条内容。</li>
  </ul>
</div>

<script>
(function () {{{{
  var bd = document.getElementById('btn-dark');
  var bl = document.getElementById('btn-light');
  function setTheme(light) {{{{
    document.body.classList.toggle('light', light);
    bd.setAttribute('aria-pressed', String(!light));
    bl.setAttribute('aria-pressed', String(light));
    // The captured bytes carry explicitly-indexed colours (38;5;N / 38;2;…),
    // which a real terminal does NOT recolour when the app theme changes. The
    // panes therefore keep their captured colours; only the page chrome
    // switches, and the light theme restyles the pane surface for contrast.
  }}}}
  bd.addEventListener('click', function () {{{{ setTheme(false); }}}});
  bl.addEventListener('click', function () {{{{ setTheme(true); }}}});
}}}})();
</script>
</body>
</html>
"""


def _main(argv: list[str]) -> None:
    out = None
    if "--out" in argv:
        out = pathlib.Path(argv[argv.index("--out") + 1]).resolve()
    build(out)


if __name__ == "__main__":
    _main(sys.argv[1:])
