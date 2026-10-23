# 拖选无法复制 与 Shift+Enter 失效 审查报告

> 基线：`origin/main` @ `a1826b1`（workspace 0.8.3，与 `ccb4054` 同版本）
> 核对日期：2026-10-23
> 涉及仓库：`bigfish1913/pi-rust`（`crates/rpi-tui`、`crates/rpi-cli`）
> 审查环境：Windows

本文记录两个上报问题的定位、逐版本取证与修复方案。两个问题都被判定为
**长期存在的上游缺陷**，不是 0.8.x 区间的版本回归。

## 0. 结论

| # | 上报现象 | 判定 | 根因位置 |
| --- | --- | --- | --- |
| 1 | TUI 内所有文字无法选中复制 | ✅ 缺陷存在，**非版本回归** | `rpi-tui/src/terminal.rs:333` 的 `?1002h` |
| 2 | 0.8.3 无法用 Shift+Enter 换行 | ✅ 缺陷存在，**非版本回归** | `rpi-tui/src/terminal.rs:55,351` 的 `#[cfg(unix)]` |

两条关键取证：

```
git diff 92c6f72 a1826b1 -- crates/rpi-tui/src/terminal.rs   → 空
git diff 92c6f72 a1826b1 -- crates/rpi-tui/src/windows_paste.rs → 空
```

0.8.0 到 0.8.3 之间，鼠标跟踪序列、键盘协议协商、Shift+Enter 处理分支、
Windows 粘贴路径**逐字节相同**。因此这两个问题不可能由 0.8.x 的迭代引入。

## 1. 版本边界定位

仓库只打了 `v0.8.0` 和 `v0.8.1` 两个 tag；0.8.2 / 0.8.3 没有 tag，只是
`Cargo.toml` 的 `version` 字段递增。按该字段定位版本提交：

| 版本 | 提交 | tag | 备注 |
| --- | --- | --- | --- |
| 0.8.0 | `92c6f72` | `v0.8.0` | `chore(release): prepare 0.8.0` |
| 0.8.1 | `06f14cb` | `v0.8.1` | `chore(release): sync bundled release documentation` |
| 0.8.2 | `8d3292e` | 无 | 仅版本号 |
| 0.8.3 | `a1826b1` | 无 | 仅版本号（= `origin/main` @ `ccb4054`） |

0.8.0 → 0.8.3 共 48 个提交，**只有 3 个改动 TUI**：

```
d37f46c  tui: share transcript rows and slice the viewport in fullscreen
d31f469  fix(tui): preserve working caret and isolate theme cache revisions
cae16f9  fix(cli): preserve session roots and safely fork and import logs
```

`d37f46c` 引入 `RenderedDocument`（共享 `Arc<Vec<String>>` 行块 + 视口切片），
是渲染性能重构，不改变终端控制序列，与选区/按键无关。

## 2. 问题 1：拖选无法复制

### 2.1 根因

`crates/rpi-tui/src/terminal.rs:331-338`

```rust
fn enable_mouse(&self) {
    // Enable mouse tracking (SGR mode)
    self.write("\x1b[?1000h\x1b[?1002h\x1b[?1006h");
}

fn disable_mouse(&self) {
    self.write("\x1b[?1006l\x1b[?1002l\x1b[?1000l");
}
```

- `?1000h` — 上报按键按下/释放
- `?1002h` — **button-event tracking：按住拖动时持续上报移动事件**
- `?1006h` — SGR 坐标编码

`?1002h` 是直接原因。按 xterm 语义，终端一旦把拖动作为事件上报，就不再执行
原生拖选。滚轮（button 4/5）只需要 `?1000h`，`?1002h` 纯粹为拖拽服务。

叠加 `tui_alt_screen.rs` 的 `\x1b[?1049h` 进入备用屏幕，选区与回滚都交给应用。

### 2.2 为什么 Windows/Linux 必然触发

| 环节 | 位置 |
| --- | --- |
| Windows/Linux 默认 `Fullscreen` | `crates/rpi-cli/src/args.rs:90-96` |
| 构造 alt-screen TUI | `crates/rpi-cli/src/interactive_tui.rs:988` |
| `start_readerless()` → 非 main-screen 时 `enable_mouse()` | `crates/rpi-tui/src/tui_alt_screen.rs:1310-1322` |
| `enter_raw_mode()` → `configure_mouse_tracking()`（非 macOS 即开） | `crates/rpi-tui/src/terminal.rs:232-238, 340` |

macOS 之所以正常，是两处叠加的结果：

```rust
// crates/rpi-tui/src/terminal.rs:18-23
/// Mouse tracking prevents native text selection in macOS terminal emulators.
/// RPI only consumes wheel events, so keep the platform default selectable.
const fn mouse_tracking_enabled_for(is_macos: bool) -> bool {
    !is_macos   // macOS 关闭，其他平台开启
}
```

加上 `args.rs:92` 让 macOS 默认走 `Regular`（主屏，不进 alt-screen），
选区完全交还终端。

### 2.3 应用侧替代方案同样不可用

`crates/rpi-cli/src/interactive_tui.rs:1798-1846` 记录 `selection_start` /
`selection_end` 并在 `Up` 时自动写剪贴板，但：

1. **没有任何选区高亮渲染**。`selection_start`/`selection_end` 只存坐标，
   全仓 `grep selection` 在 `render.rs` / `scroll_view.rs` / `rendering.rs`
   只命中一行帮助文案，拖选时屏幕零反馈。
2. **`extract_selected_text` 坐标与内容都错**（`crates/rpi-cli/src/interactive_tui/run.rs:341-378`）：

```rust
let lines = chat_container.render(80); // Use a reasonable width
```

- 宽度写死 `80`，与真实终端宽度不符 → 换行位置不同 → 行号整体错位；
- 用鼠标的**绝对屏幕行号**切**容器相对行号**，滚动后完全错位；
- 未 `strip_ansi`，而 `chat_container.render()` 返回带 ANSI 的串
  （`markdown.rs` 大量 `\x1b[`）→ 剪贴板内容混入转义码。

### 2.4 逐版本取证

| 检查项 | 0.8.0 | 0.8.1 | 0.8.2 | 0.8.3 |
| --- | --- | --- | --- | --- |
| `?1000h?1002h?1006h` | ✅ `:333` | ✅ `:333` | ✅ `:333` | ✅ `:333` |
| `mouse_tracking_enabled_for`（仅 macOS 关闭） | ✅ | ✅ | ✅ | ✅ |
| Windows/Linux 默认 `Fullscreen` | ✅ | ✅ | ✅ | ✅ |
| `start_readerless` → `enable_mouse()` | ✅ `:1321` | ✅ | ✅ | ✅ |
| `extract_selected_text` 硬编码 `render(80)` | ✅ | ✅ | ✅ | ✅ |
| 选区反显渲染 | ❌ 无 | ❌ 无 | ❌ 无 | ❌ 无 |

再往前追溯：`?1002h` 自 `f4670c5`（2026-08-22，crate 初建）就存在，
`git log -S '1002h'` 显示**没有任何提交修改过这一行**。

### 2.5 验证方法

同一终端下对比，即可证明与版本无关：

```bash
rpi --tui-mode fullscreen   # 拖选失效
rpi --tui-mode regular      # 拖选恢复（主屏 + 关鼠标跟踪）
```

`--tui-mode regular` 路径会显式 `terminal.disable_mouse()`
（`tui_alt_screen.rs:1315-1316`），选区与滚动回交给终端。

## 3. 问题 2：Shift+Enter 无法换行

### 3.1 根因

`crates/rpi-tui/src/terminal.rs:351-356`

```rust
#[cfg(unix)]
if keyboard_protocol_enabled() && self.is_tty() && io::stdin().is_terminal() {
    self.enable_keyboard_protocol(|| {
        cterm::supports_keyboard_enhancement().unwrap_or(false)
    });
}
```

kitty 键盘协议（`\x1b[>7u`）是区分 `Enter` 与 `Shift+Enter` 的关键——
flag 1 = disambiguate escape codes。该协商被 `#[cfg(unix)]` 限定，
**Windows 永不进入此分支**，始终走 legacy 输入路径。

`keyboard_protocol_enabled()` 本身也是 `#[cfg(unix)]`（`terminal.rs:55`）。

### 3.2 editor 侧逻辑是正确的

`crates/rpi-tui/src/editor.rs:1317-1320`

```rust
// Shift+Enter inserts a newline (mirrors `tui.input.newLine`).
(KeyModifiers::SHIFT, KeyCode::Enter)
| (KeyModifiers::SHIFT, KeyCode::Char('\r'))
| (KeyModifiers::SHIFT, KeyCode::Char('\n')) => self.insert("\n"),
```

`keybindings.rs:499-506` 的 `tui.input.newLine` 默认 `[Shift+Enter, Ctrl+J]`。
两者在 0.8.0 与 0.8.3 中逐字相同。

即：**按键处理没问题，是 Shift 修饰符在 Windows 上没能到达 editor**。

### 3.3 Windows 上的实际路径

crossterm 在 Windows 上确实能读到 Shift
（`crossterm-0.27.0/src/event/sys/windows/parse.rs:79-94`，
`ControlKeyState::SHIFT_PRESSED` → `KeyModifiers::SHIFT`），
但 rpi 未启用 `ENABLE_VIRTUAL_TERMINAL_INPUT`：

```
grep -rn "ENABLE_VIRTUAL_TERMINAL_INPUT\|SetConsoleMode" crates/  → 无命中
```

在 legacy 控制台输入模式下，`Shift+Enter` 与 `Enter` 产生的
`KEY_EVENT_RECORD` 在 `wVirtualKeyCode` 上同为 `VK_RETURN`，
上游 Pi 的 TS 版为此专门调用 `enableWindowsVTInput()` 打开 VT 输入，
rpi 的 Rust 移植没有对应实现。

### 3.4 逐版本取证

| 检查项 | 0.8.0 | 0.8.1 | 0.8.2 | 0.8.3 |
| --- | --- | --- | --- | --- |
| `editor.rs` 的 `SHIFT + Enter` 分支 | ✅ | ✅ | ✅ | ✅ |
| `tui.input.newLine` = `[Shift+Enter, Ctrl+J]` | ✅ | ✅ | ✅ | ✅ |
| kitty 协议协商被 `#[cfg(unix)]` 限定 | ✅ `:351` | ✅ | ✅ | ✅ |
| `windows_paste.rs`（Enter 拦截路径） | ✅ 存在 | ✅ | ✅ | ✅ |

`git diff 92c6f72 a1826b1 -- crates/rpi-tui/src/windows_paste.rs` 为空；
`interactive_tui.rs` 的 `windows_enter_in_paste` 分支在两版同为 `:2712/:2731`。

### 3.5 立即规避

`Ctrl+J` 在四个版本中都可换行，且不依赖键盘协议
（`editor.rs:1383-1386`，`keybindings.rs:503`）：

```rust
// Ctrl+J inserts a newline (pi tui.input.newLine alongside Shift+Enter).
(KeyModifiers::CONTROL, KeyCode::Char('j')) => self.insert_no_undo("\n"),
```

## 4. 修复方案

### 4.1 选区（最小改动，保住滚轮）

`crates/rpi-tui/src/terminal.rs:333` 去掉 `?1002h`：

```rust
fn enable_mouse(&self) {
    // Button press/release + SGR coordinates. `?1002h` (button-event
    // tracking) is deliberately omitted: it reports drag motion, which makes
    // the terminal stop doing native text selection. Wheel is button 4/5 and
    // is already covered by `?1000h`.
    self.write("\x1b[?1000h\x1b[?1006h");
}
```

配套清理：`crates/rpi-cli/src/interactive_tui.rs:1798-1846` 中依赖
`MouseEventKind::Drag` 的 copy-on-select 分支会失去触发条件（`is_drag`
恒为 `false`），应删除或改为 `Ctrl+X` 显式复制。同时建议删除
`run.rs:341` 的 `extract_selected_text`（坐标映射错误 + 未 strip ANSI）。

### 4.2 Shift+Enter（Windows 启用 VT 输入）

在 `terminal.rs` 的 Windows 分支上打开 `ENABLE_VIRTUAL_TERMINAL_INPUT`，
并把 `keyboard_protocol_enabled` / `enable_keyboard_protocol` 的 `#[cfg(unix)]`
扩展到 `windows`：

```rust
#[cfg(windows)]
fn enable_windows_vt_input() {
    // 参考 Pi TS 的 enableWindowsVTInput()：必须在 enable_raw_mode 之后调用，
    // 因为 raw mode 会重置控制台模式位。
    // ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200
}
```

需注意：`crossterm::supports_keyboard_enhancement()` 在 Windows Terminal 上
可用，但在 conhost 上会超时回退，`enable_keyboard_protocol` 已有
`keyboard.detected` 缓存与 `\x1b[<u` 回退，可复用。

**替代方案**（改动更小、风险更低）：在 legacy 路径上按上游 Apple Terminal
的做法，用 Win32 `GetKeyState(VK_SHIFT)` 在收到未带修饰符的 `Enter` 时补上
`SHIFT`。`terminal.rs:534-539` 的 `normalize_native_shift_enter` 已经是这个
形状，只需把 `#[cfg(any(target_os = "macos", test))]` 的调用点扩展到 Windows。

### 4.3 可选：给用户一个开关

两条修复都会改变默认行为，建议同时提供环境变量旁路，便于回归对照：

- `RPI_MOUSE_TRACKING=0` — 完全关闭鼠标跟踪（等价于 macOS 默认）
- `RPI_KITTY_KEYBOARD=1` — 已存在（`terminal.rs:56-59`），但仅 Unix 生效，
  扩展到 Windows 后即可强制启用

## 5. 复核清单

下次遇到同类症状，按以下顺序验证：

1. `rpi --tui-mode regular` 是否恢复拖选 → 是则问题在 `?1002h`，与版本无关
2. `RPI_DEBUG_KEYS=1 rpi` 下按 `Shift+Enter`，看 `key_trace` 记录的
   `mods=` 是否含 `SHIFT` → 不含则问题在协议协商层
3. `Ctrl+J` 是否能换行 → 能则 editor 侧逻辑正常，缺陷在输入层
4. `git diff <旧版本> <新版本> -- crates/rpi-tui/src/terminal.rs` 是否为空
   → 空则排除版本回归
