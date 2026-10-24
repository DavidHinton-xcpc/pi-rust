# 会话切换缺口修复 · 交接总览

> 基线：`origin/main` @ `ccb4054`（workspace 0.8.3）
> 目标：修复 5 个已核实的缺陷，分 3 个并行 session、共 3 个 PR
> 交付方式：每个 session 推 **fork**、等 CI 绿、**停止**并回报

---

## 1. 三个 session 的分工

| Session | PR | 缺陷 | 交接文档 | 状态 |
| --- | --- | --- | --- | --- |
| **A** | 1 | `/model` 临时切换静默改写 `settings.json` | [session-a-p1-model-switch.md](session-a-p1-model-switch.md) | ✅ 已交付 · [进度](session-a-progress.md) · [PR #2](https://github.com/DavidHinton-xcpc/pi-rust/pull/2) |
| **B** | 1 | 横幅 `Tools (0) none` + `/new` 不换 session 文件 | [session-b-p2p3-banner-and-new.md](session-b-p2p3-banner-and-new.md) | ✅ 代码就绪 · [PR #3](https://github.com/DavidHinton-xcpc/pi-rust/pull/3) · **待合并** |
| **C** | 1 | 切回旧会话 model 错 + footer 计数脱节 | [session-c-p4p5-restore-state.md](session-c-p4p5-restore-state.md) | ⛔ 被阻塞 · [快照](session-c-progress-2026-10-24.md) · 等 PR #3 合并 |

## 2. 依赖关系（重要）

```
A ────────────────────────→ 可立即并行开工

B ──────→ C                必须串行：C 等 B 合并后再开
```

### 为什么 C 必须等 B

| B 先落地的产物 | C 如何使用 |
| --- | --- |
| `render_session_history` 的 `footer: Option<&FooterComponent>` 参数（传 `None`） | C 换成 `Some(&state.footer)` 并实现 usage 折叠 |
| `TuiState::reset_session_state()` | C 直接复用，不重复实现 |
| `FooterComponent::reset_session_counters()` | C 直接复用 |
| `current_capabilities()` | C 的 `switch_to_session` 改动依赖它已存在 |

若 C 在 B 合并前开工，会在 `sessions.rs` 与 `interactive_tui.rs` 上产生冲突，
且 `current_capabilities` 不存在导致编译失败。

### 为什么 A 可以完全并行

A 只改 `selectors.rs` 一个条件表达式 + 一个测试，与 B/C 的文件零重叠。

## 3. 五个缺陷在 0.8.3 上的核实结论

全部已用 `main` 源码逐行核对，**均真实存在**。取证命令写在各自交接文档里。

| # | 缺陷 | `main` 证据 | 归属 |
| --- | --- | --- | --- |
| 1 | `/model` 跨 provider 静默写 `defaultModel` | `selectors.rs:230` 的 `save_default \|\| current.provider != model.provider` | A |
| 2 | `/new` 只清屏不换 session 文件 | `interactive_tui.rs:2975` 只 `chat_container.clear()`；`start_new_session` 不存在 | B |
| 3 | 切换后横幅 `Tools (0) none` | `rendering.rs:10` 传空切片；4 处切换点全用它 | B |
| 4 | 切回旧会话 model 错 | `sessions.rs:101` 注释自认 "model/footer stay put"；`restore_session_model` 不存在 | C |
| 5 | footer 计数不重置/不恢复 | `footer.rs` 无 `reset_*`；`render_session_history` 无 `footer` 参数 | C |

### 缺陷 3 的关键对照

0.8.3 **只在启动时横幅正确**：`interactive_tui.rs:999` 用
`add_welcome_message_with_capabilities` + 真实快照，且 `:948-960` 有
「active_tools 为空则回退全量工具」的处理。一切换会话就退化——这是回归性质的
遗漏，不是设计选择。

## 4. 所有 session 共用的前置知识

### 4.1 工具链（本机已实测）

```bash
cd /e/rpi
export PATH="$HOME/.cargo/bin:$PATH"
export RUSTFLAGS="-D warnings" RUSTDOCFLAGS="-D warnings"

cargo +stable-x86_64-pc-windows-gnu fmt --all -- --check
cargo +stable-x86_64-pc-windows-gnu check --workspace --all-targets --locked
cargo +stable-x86_64-pc-windows-gnu test --workspace --locked
```

**必须用 gnu toolchain**：默认 `stable-x86_64-pc-windows-msvc` 缺 `link.exe`
（本机未装 Visual Studio C++ build tools），且 MSYS 的 `/usr/bin/link.exe` 会抢占
`link`。

### 4.2 已装工具清单

| 工具 | 版本 | 备注 |
| --- | --- | --- |
| stable (msvc) | 1.99.0 | 默认，**不能链接** |
| stable (gnu) | 1.99.1 | 实际使用 |
| 1.78 (msvc/gnu) | 1.78.0 | MSRV 工具链（但仓库 lockfile 已不兼容，见下） |
| clippy | 0.1.99 | 两个 toolchain 都有；**不在 CI** |
| rustfmt | 1.10.0 | — |
| gh | 2.97.0 | 已登录 `DavidHinton-xcpc` |
| gcc (MinGW) | 16.1.0 | gnu 链接所需 |
| python / node | 3.12.10 / 24.18.0 | CI 脚本用 |

### 4.3 已知的环境性失败（不要试图修）

`prebuilt_extensions::tests::downloaded_manifest_and_archive_install_into_an_isolated_profile`
在 gnu 上报 `no supported prebuilt target for this host`。该用例在**未改动的
`origin/main`** 上同样失败，属 gnu 工具链既有问题。在 PR 里声明即可。

### 4.4 三个必须声明的盲区

| 盲区 | 影响 | 处理 |
| --- | --- | --- |
| 缺 `x86_64-linux-gnu-gcc` | **无法本地验证 Linux 目标** | 每个 PR 声明"依赖 CI 结论" |
| MSRV 1.78 不可用 | `Cargo.lock` 里 `icu_collections 2.3.0` 要求 `edition2024` | 已在 `main` 上存在，非本次改动；不要试图修 |
| Pester 3.4.0 | CI 用较新版 | 本批任务不涉及 installer |

**Linux dead-code 是真实风险**：PR #91 曾因 `PASTE_RUN_MIN_CHARS` 在 Linux 报
never used 而 CI 失败。B 和 C 都新增了符号，务必自查每个新符号在所有 target 上
是否都有使用者。

### 4.5 clippy 不在 CI

仓库有 53 个既有 clippy warning（`rpi-telemetry`、`rpi-plugin-sdk` 等）。
**不要顺手清理**——那会让 PR 变成无关的混合体，违反「最小改动」。
其中一个值得注意：`rpi-plugin-sdk/src/dialogs.rs:72` 用了 `is_none_or`（需 1.82），
与 `rust-version = "1.78"` 矛盾，但**不是本批任务的范围**。

## 5. 交接点清单（B → C）

B 完成后**必须明确告知 C** 以下四项已就绪：

1. `render_session_history` 已带 `footer: Option<&rpi_tui::FooterComponent>` 参数，
   所有调用点传 `None`，函数体内**未实现**折叠逻辑
2. `TuiState::reset_session_state()` 已实现，5 个调用点已接好
3. `FooterComponent::reset_session_counters()` 已实现（`rpi-tui` 公开 API 增量）
4. `current_capabilities()` / `capabilities_from_resources()` 已在 `rendering.rs` 落地，
   `add_welcome_message` 已降为 `#[cfg(test)]`，非测试调用点已清零

## 6. 每个 session 的完成标准

全部满足才算完成：

- [ ] 三条门禁命令本地全绿（gnu toolchain）
- [ ] 新增测试**反向验证过**（回退修复后必然失败）
- [ ] 已推 fork 分支并开 PR（base = fork 的 `main`）
- [ ] **fork 上的 CI 全绿**（尤其 Linux check / Linux test）
- [ ] PR 描述按 `PULL_REQUEST_TEMPLATE.md` 填全，含盲区声明
- [ ] 回报修复结果 + 人工 TUI 测试建议

**CI 绿之后停止。** 不要顺手做别的 session 的工作，不要提上游 PR。

### 6.1 实际进度

逐 session 更新这一节，并把细节写进各自的 `session-*-progress.md`。

| Session | 完成情况 |
| --- | --- |
| A | 本地门禁 ✅ / 反向验证 ✅ / PR ✅ / CI ✅（6 job 全 success，`workflow_dispatch` 手动触发）/ 描述 ✅ / 回报 ✅ —— 仅剩**人工 TUI 测试**未做 |
| B | 代码与 CI 就绪（[PR #3](https://github.com/DavidHinton-xcpc/pi-rust/pull/3)，`fix/session-switch-banner-and-new` @ `5b60934`），**未合并** |
| C | 未开工，硬性阻塞于 PR #3 未合并；核查与恢复动作已写入 [session-c-progress-2026-10-24.md](session-c-progress-2026-10-24.md) |

A 的完整取证与遗留物见 [session-a-progress.md](session-a-progress.md)，
其中记录了一个**待查的环境疑点**：fork 上 PR 的 `pull_request` 事件不生成任何 check run。
C 的快照里独立复现了同一现象（B 的 CI 是 push 触发的），可交叉印证。

**下一步的关键动作**（需 operator 决定）：合并 fork 上的 PR #3，之后 C 才能开工。

## 7. 人工 TUI 测试的必要性

三个 PR 都涉及用户可感知行为，都建议人工验证。优先度：

| Session | 人工测试必要性 | 核心验证点 |
| --- | --- | --- |
| A | 轻 | `/model` 跨 provider 后 `settings.json` **未变** |
| B | 中 | `/new` 后 `/session` 能看到**两个**条目，磁盘上有**两个**文件 |
| C | **最需要** | 切回旧会话后 model 与 footer 数字**都是该会话自己的** |

C 最需要人工测试的原因：自动化测试只能断言 `lane.get_model()`，无法验证
「用户看到的 model 显示与 footer 数字是否自洽」——而后者正是这个 bug 的
用户可见形态。

## 8. 未纳入本批的任务

以下内容在当前工作区存在，但**与本批 5 个缺陷无关**，不应塞进任何上述 PR：

| 内容 | 说明 |
| --- | --- |
| `docs/debugging/selection-and-shift-enter.md`（282 行） | 记录「拖选无法复制」「Shift+Enter 失效」两个**独立**缺陷，根因在 `rpi-tui/src/terminal.rs`，属另一条工作线 |
| `scripts/ci-linux.sh`（90 行） | Linux 验证脚本，属 CI 工具，与 bug 修复无关 |
| `docs/maintaining/contributing-checklist.md` | 流程文档 |

建议这些单独提 `docs:` / `chore(ci):` PR。
