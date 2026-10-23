# 会话切换的状态缺口与修复

> 基线：`v0.8.3`（`origin/main` @ `ccb4054`）
> 修复分支：`fix/session-switch-state`
> 核对日期：2026-10-23
> 状态：5 项缺口已在分支上全部修复，每项都有离线回归测试

本文记录 0.8.3 中与会话/模型/footer 切换相关的行为缺口、根因定位，以及分支上的
修复方式。上游权威是 [`CONTRIBUTING.md`](../../CONTRIBUTING.md) 与
[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)；本文只做定位与说明。

## 1. 结论

五个缺口同源于一个设计缺口：**切换会话时只清空 UI，没有把目标会话的状态装回去**。
`/new` 甚至没有真正切换 session 文件。

| # | 缺口 | 根因 | 修复 | 回归测试 |
| --- | --- | --- | --- | --- |
| 1 | `/model` 跨 provider 切换会静默改写默认模型 | `save_default \|\| provider 不同` | 只认 `save_default` | `explicit_default_model_selection_still_persists` |
| 2 | `/new`(`/clear`) 只清屏，不换 session 文件 | `ClearChat` 直接清容器 | 新增 `start_new_session` | `new_session_creates_a_file_and_resets_footer_and_banner` |
| 3 | 切换 session 后横幅显示 `Tools (0) none` | 4 处调用空能力版本 | 统一走 `current_capabilities` | 同上（断言技能数） |
| 4 | 切回旧 session 时跑在错误的 model 上 | 不回放 `ModelChange` | 新增 `restore_session_model` | `switching_back_to_a_session_restores_its_footer_and_model` |
| 5 | footer 计数不随 session 重置或恢复 | 无重置入口、回放不折回 | `reset_session_counters` + `render_session_history` 加 `footer` | `reset_session_counters_clears_usage_and_keeps_environment` |

## 2. 逐项说明

### 2.1 `/model` 跨 provider 切换会静默改写默认模型

`crates/rpi-cli/src/interactive_tui/selectors.rs`：

```rust
// 修复前
if save_default || current.provider != model.provider {
```

`/model` 选择器与 Ctrl+P 都传 `save_default = false`，但只要切到**不同 provider**，
后半条即成立，于是走 `set_default_model()` 写 `settings.json`。用户看到的提示只有
"Model set to ..."，无法从输出判断自己改掉了持久化配置。

修复：删除 `current.provider != model.provider`，只保留 `save_default`；`else` 分支
明确提示 "Not saved as the default — use /settings to change it."

### 2.2 `/new`(`/clear`) 只清屏，不换 session 文件

`crates/rpi-cli/src/interactive_tui.rs` 的 `ClearChat` 分支原本只有：

```rust
chat_container.clear();
add_welcome_message(&chat_container);
```

后果是上一个 JSONL 文件持续增长，`/session` 只列得出一个条目。

修复：新增 `start_new_session()`——abort 在跑的 run → `create_jsonl_session` →
经 `set_active_session` 漏斗换 backing（插件通道才能跟着切）→ 重建横幅 →
重置 footer。`ClearChat` 现在转发到它。

### 2.3 切换 session 后横幅显示 `Tools (0) none`

0.8.3 的 4 处切换点（`switch_to_session`、`import_session`、`fork_session`、
树导航）都调用空能力版本的 `add_welcome_message(chat)`，而启动路径反而是对的。

修复：把启动路径的能力快照逻辑抽成 `current_capabilities()` /
`capabilities_from_resources()`，4 处改走 `add_welcome_message_with_capabilities`，
`add_welcome_message` 降为 `#[cfg(test)]`。

### 2.4 切回旧 session 时跑在错误的 model 上

0.8.3 的注释把现状写得很直白：

```rust
/// The current model/footer stay put (v1 doesn't replay the session's ModelChange entries).
```

后果：lane 保留上一次 `/model` 的选择，切回一个用 `second` 的旧会话时实际跑在
`first` 上，而 footer 显示的可能又是第三个。

修复：新增 `restore_session_model()`，从 session 日志的 `ModelChange` / assistant
条目反解 provider+model（复用 `build_session_context`），在 catalog 中命中才
`set_model`；未命中保持现状（best-effort，不因回放失败阻断切换）。

### 2.5 footer 计数不随 session 重置或恢复

两个方向的问题：

- `/new` 后 footer 继承旧 session 的 `↑input ↓output`、成本、cache-hit、session 名；
- 切回旧 session 时 footer 反而一片空白，丢失该会话已有的用量与上下文占比。

修复：

- `rpi-tui/src/footer.rs` 增加 `reset_session_counters()`，清 usage / cache-hit /
  context badge / session 名 / status，**保留** `context_window`、`model`、`cwd`、
  `git_branch`——它们描述环境与当前模型，不属于会话历史。
- `render_session_history` 增加 `footer: Option<&FooterComponent>`，把重放的 usage
  按 live `MessageEnd` 相同的规则折回 footer（含缓存命中率与 context badge）。

`footer` 传 `None` 的只有启动路径——那时 footer 还没构建，计数器交给第一个 live turn。

## 3. 设计取舍

### 3.1 为什么 `render_session_history` 用 `Option<&FooterComponent>`

启动时的调用点在 footer 构建之前（`interactive_tui.rs` 中 `state` 尚未创建），
用 `Option` 避免为了回放而提前构造 footer。切换路径一律传 `Some(&state.footer)`。

### 3.2 为什么 `restore_session_model` 是 best-effort

会话可能来自另一台机器、另一个账号，其记录的 provider/model 未必在当前 catalog 里。
硬失败会让用户无法打开自己的历史会话，因此未命中时保持当前模型并继续。

### 3.3 为什么 `reset_session_counters` 不动 `model`/`context_window`

`model` 与 `context_window` 描述"当前在用什么"，`usage`/`context_tokens` 描述
"这个会话用掉了多少"。`/new` 要清后者，但前者由 `restore_session_model` /
启动路径负责，不属于重置范围。

## 4. 提交前必跑

```bash
cargo fmt --all -- --check
RUSTFLAGS="-D warnings" cargo check --workspace --all-targets --locked
RUSTFLAGS="-D warnings" RUSTDOCFLAGS="-D warnings" cargo test --workspace --locked
```

本机（Windows）默认 `x86_64-pc-windows-msvc` 缺 `link.exe`，须用
`stable-x86_64-pc-windows-gnu`；详见
[贡献规则落地清单](contributing-checklist.md)。

`sh scripts/sync-embedded-docs.sh` 之后 `crates/rpi-cli/embedded-docs` 必须无 diff。
本次只改 `docs/` 下的普通文档与 `docs/README.md`（不在该脚本的 FILES 列表），
无需同步。

### 已知的既有失败

`prebuilt_extensions::tests::downloaded_manifest_and_archive_install_into_an_isolated_profile`
在 gnu 工具链下必失败（`host_target()` 只认 msvc）。该用例在未改动的 `v0.8.3`
树上同样失败，与本分支无关。
