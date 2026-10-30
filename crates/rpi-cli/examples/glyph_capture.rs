//! Capture the REAL rendered ANSI for the glyph-change demo.
//!
//! Run: `cargo run -p rpi-cli --example glyph_capture > glyph_capture.txt`
//!
//! Why this exists: `demo/glyph-changes-demo.html` used to hand-write styled
//! HTML that *approximated* the TUI. That silently diverged from what the
//! terminal actually shows (padding, wrapping, SGR stacking, the 2-column
//! emoji advance). This example instead calls the same components and the same
//! `interactive_tui::rendering` helpers the live TUI calls, and dumps their
//! raw bytes. The HTML then feeds those bytes to a real ANSI terminal emulator,
//! so the "before/after" panes are the renderer's own output, not a drawing.
//!
//! Every section prints between `<<<SECTION name>>>` markers; the extraction
//! script splits on them.

use std::sync::Arc;

use rpi_cli::brand;
use rpi_tui::component::Component;
use rpi_tui::{
    bold, AssistantBlock, AssistantMessageComponent, AssistantMessageOptions,
    BashExecutionComponent, Container, FooterComponent, Markdown, SearchBar, Spacer, Text,
    ThemeColors,
};

/// The exact strings the live TUI uses, with the emoji kept so the emulator
/// shows the real advance width. These are copied from the call sites named in
/// the comment — if the call site changes, this must change with it.
const BOOKS: &str = "📚"; // rendering.rs:235
const PACKAGE: &str = "📦"; // rendering.rs:282
const KEYBOARD: &str = "⌨️"; // rendering.rs:374
const PUZZLE: &str = "🧩"; // rendering.rs:564
const FOLDER: &str = "📂"; // rendering.rs:601
const INFO: &str = "ℹ"; // rendering.rs:535
const PAUSE: &str = "⏸"; // bash_execution.rs:348
const ARROW_TURN: &str = "↳"; // proposed replacement
const CROSS: &str = "✗"; // rendering.rs:474 / tool_execution.rs:400

struct Ren {
    c: ThemeColors,
}

impl Ren {
    fn new() -> Self {
        Self {
            c: rpi_tui::theme().colors,
        }
    }

    /// Replica of `rendering::add_note_message` as it exists on main.
    fn note_before(&self, container: &Container, text: &str) {
        let c = self.c.clone();
        container.add_child(Arc::new(Text::new(
            format!("  {} {}", c.info.fg(INFO), c.muted.fg(text)),
            1,
            0,
        )));
        container.add_child(Arc::new(Spacer::new(1)));
    }

    /// The proposed note: no glyph, `md_heading` color, no bold, no italic —
    /// "same shape as the printed thinking block" (which is italic + thinking_text).
    fn note_after(&self, container: &Container, text: &str) {
        let c = self.c.clone();
        container.add_child(Arc::new(Text::new(
            format!("  {}", c.md_heading.fg(text)),
            1,
            0,
        )));
        container.add_child(Arc::new(Spacer::new(1)));
    }

    /// Replica of `rendering::add_error_message` (rendering.rs:470-479), which is
    /// what an assistant error *should* look like.
    fn error(&self, container: &Container, text: &str) {
        let c = self.c.clone();
        container.add_child(Arc::new(Text::new(
            format!("  {} {}", c.error.fg(CROSS), c.error.fg(text)),
            1,
            0,
        )));
        container.add_child(Arc::new(Spacer::new(1)));
    }

    /// `/help` header, before (emoji inline) and after (emoji removed).
    fn help_header(&self, container: &Container, emoji: bool) {
        let c = self.c.clone();
        let title = if emoji {
            format!("{BOOKS} Available Commands")
        } else {
            "Available Commands".to_string()
        };
        container.add_child(Arc::new(Text::new(
            c.md_heading.fg(&bold(&title)),
            1,
            0,
        )));
        container.add_child(Arc::new(Spacer::new(1)));
    }

    /// `/version` block: `📦 Version Information` + the two body rows.
    fn version_block(&self, container: &Container, emoji: bool) {
        let c = self.c.clone();
        let title = if emoji {
            format!("{PACKAGE} Version Information")
        } else {
            "Version Information".to_string()
        };
        container.add_child(Arc::new(Text::new(
            c.md_heading.fg(&bold(&title)),
            1,
            0,
        )));
        container.add_child(Arc::new(Spacer::new(1)));
        container.add_child(Arc::new(Text::new(
            format!("  {} {}", c.muted.fg("rpi-cli"), c.text.fg("v0.8.4")),
            1,
            0,
        )));
        container.add_child(Arc::new(Text::new(
            format!("  {}", c.dim.fg("Rust implementation of pi coding agent TUI")),
            1,
            0,
        )));
        container.add_child(Arc::new(Spacer::new(1)));
    }

    /// `/hotkeys` block: `⌨️  Keyboard Shortcuts` (note the VS16 + two spaces)
    /// + a couple of key rows.
    fn hotkeys_block(&self, container: &Container, emoji: bool) {
        let c = self.c.clone();
        let title = if emoji {
            format!("{KEYBOARD}  Keyboard Shortcuts")
        } else {
            "Keyboard Shortcuts".to_string()
        };
        container.add_child(Arc::new(Text::new(
            c.md_heading.fg(&bold(&title)),
            1,
            0,
        )));
        container.add_child(Arc::new(Spacer::new(1)));
        let keys: &[(&str, &str)] = &[
            ("Enter", "Send message"),
            ("Shift+Enter", "New line"),
            ("Ctrl+T", "Show/hide reasoning blocks"),
        ];
        for (key, desc) in keys {
            container.add_child(Arc::new(Text::new(
                format!("  {}  {}  {}", c.accent.fg(key), c.dim.fg("—"), c.muted.fg(desc)),
                1,
                0,
            )));
        }
        container.add_child(Arc::new(Spacer::new(1)));
    }

    fn help_rows(&self, container: &Container, n: usize) {
        let c = self.c.clone();
        let cmds: &[(&str, &str)] = &[
            ("/help, /?", "Show this help message"),
            ("/clear, /new", "Clear the conversation"),
            ("/version, /v", "Show version information"),
            ("/model, /m", "Choose a model (live switch)"),
            ("/hotkeys", "Show keyboard shortcuts"),
        ];
        let w = 14usize;
        for (cmd, desc) in cmds.iter().take(n) {
            container.add_child(Arc::new(Text::new(
                format!("  {:<w$}  {}  {}", cmd, c.dim.fg("—"), c.muted.fg(desc)),
                1,
                0,
            )));
        }
    }

    /// `/skills` and `/context` panel header.
    ///
    /// Before: `container_note_block` emits every line as plain `Text`, so the
    /// header carries **no theme colour at all** -- once the emoji is removed the
    /// title is indistinguishable from body text.
    ///
    /// After: the header goes through `md_heading.fg(...)` like every other
    /// transcript title (`/help`, `/version`, `/hotkeys`, add_note_message), and
    /// the body rows keep the plain passthrough colour.
    fn skills_panel(&self, container: &Container, emoji: bool) {
        let c = self.c.clone();
        let head = if emoji {
            format!("{PUZZLE} Skills available in this session:")
        } else {
            c.md_heading.fg("Skills available in this session:")
        };
        let mut body = Vec::new();
        for (name, desc) in [
            ("rpi-release", "发布 rpi Rust workspace 的版本：release-plz Release PR"),
            ("pi-rust-pr", "pi-rust PR loop: fixes, probes, gates, CI, replies."),
        ] {
            body.push(format!("  • {name} — {desc}"));
        }
        body.push("  Invoke with: /skills <name> [instructions]".to_string());
        container.add_child(Arc::new(Text::new(head, 1, 0)));
        for line in &body {
            container.add_child(Arc::new(Text::new(line.clone(), 1, 0)));
        }
        container.add_child(Arc::new(Spacer::new(1)));
    }

    /// `/context` panel — same `container_note_block` passthrough as
    /// `skills_panel`, so it has the same defect and the same fix: the header
    /// takes `md_heading`, the rows stay plain.
    fn context_panel(&self, container: &Container, emoji: bool) {
        let c = self.c.clone();
        let head = if emoji {
            format!("{FOLDER} Discovered resources for this session:")
        } else {
            c.md_heading.fg("Discovered resources for this session:")
        };
        let body = [
            "  Context (2):".to_string(),
            "    • /e/rpi/AGENTS.md".to_string(),
            "    • /e/rpi/.rpi/AGENTS.md".to_string(),
            "  Skills (2):".to_string(),
            "    • rpi-release — 发布 rpi Rust workspace 的版本".to_string(),
            "    • pi-rust-pr — pi-rust PR loop".to_string(),
            "  Prompt templates (1):".to_string(),
            "    • /review — Review the current diff".to_string(),
        ];
        container.add_child(Arc::new(Text::new(head, 1, 0)));
        for line in &body {
            container.add_child(Arc::new(Text::new(line.clone(), 1, 0)));
        }
        container.add_child(Arc::new(Spacer::new(1)));
    }

    /// The real `AssistantMessageComponent`, so thinking/error styling is the
    /// renderer's, not ours.
    fn assistant(&self, blocks: Vec<AssistantBlock>) -> Arc<AssistantMessageComponent> {
        Arc::new(AssistantMessageComponent::new(AssistantMessageOptions {
            output_pad: 1,
            ..Default::default()
        }))
        .tap(|c| c.update_blocks(&blocks))
    }
}

/// Tiny helper so `assistant` reads as a single expression.
trait Tap: Sized {
    fn tap(self, f: impl FnOnce(&Self)) -> Self {
        f(&self);
        self
    }
}
impl<T> Tap for T {}

fn section(name: &str) {
    println!("<<<SECTION {name}>>>");
}

fn dump(component: &dyn Component, width: usize) {
    for line in component.render(width) {
        println!("{line}");
    }
}

fn maybe_unicode_note() {
    // The emulator needs to know whether the capturing terminal could show
    // emoji at all; we always emit the real bytes and let the HTML decide.
}

fn main() {
    let r = Ren::new();
    let width = 78usize;
    maybe_unicode_note();

    // ---- 01 note before ----
    section("01-note-before");
    let chat = Container::new();
    for t in [
        "Model set to anthropic/claude-sonnet-4-5 — applies to the next message.",
        "Thinking set to high.",
        "Theme set to dark (saved).",
        "Reloading extensions + resources…",
        "Switched to session 2026-10-24-a1f3.",
    ] {
        r.note_before(&chat, t);
    }
    dump(&chat, width);

    // ---- 01 note after ----
    section("01-note-after");
    let chat = Container::new();
    for t in [
        "Model set to anthropic/claude-sonnet-4-5 — applies to the next message.",
        "Thinking set to high.",
        "Theme set to dark (saved).",
        "Reloading extensions + resources…",
        "Switched to session 2026-10-24-a1f3.",
    ] {
        r.note_after(&chat, t);
    }
    dump(&chat, width);

    // ---- 02 help before / after ----
    section("02-help-before");
    let chat = Container::new();
    r.help_header(&chat, true);
    r.help_rows(&chat, 5);
    dump(&chat, width);

    section("02-help-after");
    let chat = Container::new();
    r.help_header(&chat, false);
    r.help_rows(&chat, 5);
    dump(&chat, width);

    section("02-version-before");
    let chat = Container::new();
    r.version_block(&chat, true);
    dump(&chat, width);

    section("02-version-after");
    let chat = Container::new();
    r.version_block(&chat, false);
    dump(&chat, width);

    section("02-hotkeys-before");
    let chat = Container::new();
    r.hotkeys_block(&chat, true);
    dump(&chat, width);

    section("02-hotkeys-after");
    let chat = Container::new();
    r.hotkeys_block(&chat, false);
    dump(&chat, width);

    // ---- 03 skills / context panels before after ----
    section("03-skills-before");
    let chat = Container::new();
    r.skills_panel(&chat, true);
    dump(&chat, width);

    section("03-skills-after");
    let chat = Container::new();
    r.skills_panel(&chat, false);
    dump(&chat, width);

    section("03-context-before");
    let chat = Container::new();
    r.context_panel(&chat, true);
    dump(&chat, width);

    section("03-context-after");
    let chat = Container::new();
    r.context_panel(&chat, false);
    dump(&chat, width);

    // ---- 04 search bar: the REAL component, both states ----
    // The live bar formats `{icon} Search: {q}` with the icon hard-coded; the
    // "after" state cannot be produced by the component until it is patched,
    // so we show the real "before" and mark the difference.
    section("04-search-before");
    let bar = SearchBar::new();
    bar.set_visible(true);
    bar.set_query("tool");
    bar.set_match_info(0, 3);
    dump(&bar, width);

    section("04-search-after");
    // Reproduce `SearchBar::render` with `search_icon` deleted: the left side
    // loses one column, so `padding` grows by one and the bar stays 78 wide:
    //   background.fg(left) + " "*padding + dim.fg(right) + "  "
    let chat = Container::new();
    let c2 = r.c.clone();
    let left = " Search: tool";
    let right = "1/3";
    let padding = width - left.chars().count() - right.chars().count() - 2;
    // `SearchBar::render` appends two trailing spaces after the counter; keep
    // them so the "after" bar is the same 78 columns as the real one.
    chat.add_child(Arc::new(Text::new(
        format!(
            "{}{}{}  ",
            c2.background.fg(left),
            " ".repeat(padding),
            c2.dim.fg(right)
        ),
        0,
        0,
    )));
    dump(&chat, width);

    // ---- 05 assistant error: the real component ----
    section("05-error-before");
    let msg = r.assistant(vec![AssistantBlock::Text("我来跑一下测试。".into())]);
    msg.update_error("429 rate_limit_exceeded — retry after 12s", "error");
    dump(msg.as_ref(), width);

    section("05-error-aborted");
    let msg = r.assistant(vec![AssistantBlock::Text("我来跑一下测试。".into())]);
    msg.update_error("user pressed Esc", "aborted");
    dump(msg.as_ref(), width);

    section("05-error-length");
    let msg = r.assistant(vec![AssistantBlock::Text("我来跑一下测试。".into())]);
    msg.update_error("", "length");
    dump(msg.as_ref(), width);

    section("05-error-after");
    let chat = Container::new();
    r.error(&chat, "429 rate_limit_exceeded — retry after 12s");
    r.error(&chat, "Operation aborted: user pressed Esc");
    r.error(&chat, "Response was truncated before completion.");
    dump(&chat, width);

    // ---- 06 bash running panel: real component, both glyphs ----
    // The hint only appears after LONG_RUNNING_HINT_AFTER (60s), so we cannot
    // wait; instead we render the real component for the panel frame and show
    // the hint row composed exactly as bash_execution.rs:348 composes it.
    // The hint row is composed inside `BashExecutionComponent::render` only
    // after 60s, which we cannot wait for — but `append_output` + the panel's
    // own status row is the exact frame the user sees at that moment. We render
    // the panel, then the hint row via the same `Text` path the component uses
    // (`panel_line` + `wrap_text_with_ansi` are private, so `Text` with the same
    // muted color and 1-column pad is the closest faithful reproduction).
    for (name, glyph) in [("06-bash-before", PAUSE), ("06-bash-after", ARROW_TURN)] {
        section(name);
        let bash = BashExecutionComponent::new("cargo test --workspace --all-features");
        bash.append_output("   Compiling rpi-tui v0.8.4");
        bash.append_output("   Compiling rpi-cli v0.8.4");
        dump(&bash, width);
        // The panel's own render already ends with its padded bottom row; the
        // transcript puts one Spacer(1) between the panel and the hint row.
        // `dump` already terminates the last row with a newline, so printing one
        // more newline yields exactly that single blank row.
        let c = r.c.clone();
        let hint = Container::new();
        hint.add_child(Arc::new(Text::new(
            format!("{} Esc / Ctrl+C 中止", c.muted.fg(glyph)),
            1,
            0,
        )));
        dump(&hint, width);
    }

    // ---- 07 保留项：lockup + 真实 markdown 任务列表 ----
    section("07-lockup");
    dump(&brand::BrandLockup::new(), width);
    section("07-lockup-no-crab");
    // `render_lockup(false)` is private; the no-crab form is asserted in
    // brand.rs tests as `rpi` alone. Emit it through the same Text path.
    let chat = Container::new();
    chat.add_child(Arc::new(Text::new(
        r.c.accent.fg(&bold("rpi")),
        1,
        0,
    )));
    dump(&chat, width);

    section("07-md-tasks");
    let md = Markdown::new(
        "发布前检查：\n\n- [x] 跑完 `cargo test --workspace`\n- [x] 更新 `CHANGELOG.md`\n- [ ] 打 tag `v0.8.5`\n- [ ] 写 GitHub Release\n\n普通无序列表：\n\n- first item\n- second item\n",
        1,
        0,
    );
    dump(&md, width);

    // ---- 08 note folding: 11 notes accumulated vs 1 slot ----
    section("08-fold-before");
    let chat = Container::new();
    for t in [
        "Model set to anthropic/claude-sonnet-4-5 — applies to the next message.",
        "Thinking set to high.",
        "Theme set to dark (saved).",
        "Provider switched to openrouter (model qwen3-coder) — applies to the next message. Default saved.",
        "Reloading extensions + resources…",
        "Switched to session 2026-10-24-a1f3.",
        "Copied last reply to the clipboard.",
        "Conversation compacted.",
        "Model set to openrouter/qwen3-coder-480b — applies to the next message.",
        "Theme set to light (saved).",
        "Thinking set to medium.",
    ] {
        r.note_after(&chat, t);
    }
    dump(&chat, width);

    section("08-fold-after");
    // The folded form is ONE slot: `status_container.clear()` then one child.
    let slot = Container::new();
    slot.add_child(Arc::new(Text::new(
        format!("  {}", r.c.md_heading.fg("Thinking set to medium.")),
        1,
        0,
    )));
    dump(&slot, width);

    // ---- footer: real component, for the surrounding frame ----
    section("footer");
    let footer = FooterComponent::new();
    footer.set_cwd("/e/rpi");
    footer.set_git_branch(Some("main"));
    footer.set_model("claude-sonnet-4-5");
    footer.set_thinking_level(Some("high"));
    footer.set_usage(rpi_tui::footer::UsageTotals {
        input: 12_400,
        output: 3_180,
        cache_read: 86_000,
        cache_write: 5_200,
        ..Default::default()
    });
    footer.set_context_usage(Some(31.0), 200_000);
    dump(&footer, width);
}
