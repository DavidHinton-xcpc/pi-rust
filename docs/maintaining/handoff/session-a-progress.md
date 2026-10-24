# Session A 进度落盘

> 最后更新：执行完 [session-a-p1-model-switch.md](session-a-p1-model-switch.md) 全部步骤后
> 状态：**✅ 代码已交付，PR #2 已开，fork 上 CI 全绿**（人工 TUI 测试待做）

---

## 1. 当前状态

| 项 | 状态 |
| --- | --- |
| 分支 | `fix/model-switch-not-persisted` @ `8a87df1`（基于 `origin/main` `ccb4054`） |
| PR | [#2](https://github.com/DavidHinton-xcpc/pi-rust/pull/2)，base `main`，**fork only，未提上游** |
| 提交 | `8a87df1 fix(cli): keep temporary model switches out of settings.json` |
| 本地三条门禁 | ✅ fmt / check / test 全绿（仅 1 个既有环境性失败，见 §4） |
| fork CI | ✅ 6 个 job 全 success（Release automation 按预期 skipped） |
| 反向验证 | ✅ 已做，负向测试在旧代码上失败 |
| 人工 TUI 测试 | ⬜ 未做（交接文档要求 CI 绿后停止，故未执行） |

## 2. 改了什么

`crates/rpi-cli/src/interactive_tui/selectors.rs` —— `apply_model_selection()`：

```diff
-    let current = lane.get_model().await.map_err(|error| error.to_string())?;
     lane.set_model(model.clone()).await...
     state.set_current_model(&model);
     let mut note = format!("Model set to {}/{} — applies to the next message.", ...);
-    if save_default || current.provider != model.provider {
+    if save_default {
         match set_default_model(&model.provider, &model.id) { ... }
+    } else {
+        // Session-scoped switch: point at the explicit way to make it stick
+        // instead of writing the default behind the user's back.
+        note.push_str(" Not saved as the default — use /settings to change it.");
     }
```

- `save_default` 成为**唯一**落盘入口：`/settings` → Default model 传 `true` 仍持久化；
  `/model` 选择器（`selectors.rs:167`）与 Ctrl+P 循环（`interactive_tui.rs:2347`）传 `false`，
  只改内存态。
- `lane.get_model()` 调用整行删除——它在函数内只服务于那个已消失的跨 provider 比较。
  函数 doc comment 已更新，说明 `save_default` 是唯一落盘入口。

`crates/rpi-cli/src/interactive_tui/tests.rs`：

- **新增** `explicit_default_model_selection_still_persists`（正向）：
  `save_default = true` 仍写 `settings.json`，断言
  `default_provider == Some("saved")`、`default_model == Some("saved-model")`。
- **改写** `hot_cycle_crosses_providers_and_anchors_duplicate_ids_to_the_live_lane`（反向）：
  断言 `default_provider == None`、`default_model == None`，且 note 含
  `"Not saved as the default"`。

两个测试都用 `with_isolated_config_dir` + `AgentHarness`（faux provider，`http://*.invalid`），
不触网、不碰真实用户目录。

## 3. 反向验证证据

只 stash `selectors.rs`（`git stash push -- crates/rpi-cli/src/interactive_tui/selectors.rs`）：

```
test interactive_tui::tests::explicit_default_model_selection_still_persists ... ok
test interactive_tui::tests::hot_cycle_crosses_providers_and_anchors_duplicate_ids_to_the_live_lane ... FAILED

thread ... panicked at crates\rpi-cli\src\interactive_tui\tests.rs:749:17:
the note should say the switch was not persisted: Model set to second/shared — applies to the next message. Default saved.

test result: FAILED. 1 passed; 1 failed; 0 ignored; 0 measured; 604 filtered out
```

负向测试在旧代码上失败，报错正是回归签名（旧代码跨 provider 输出 `Default saved.` 并落盘）。
`git stash pop` 恢复后两个测试均通过。

## 4. 本地门禁结果

```bash
export PATH="$HOME/.cargo/bin:$PATH"
export RUSTFLAGS="-D warnings" RUSTDOCFLAGS="-D warnings"
cargo +stable-x86_64-pc-windows-gnu fmt --all -- --check                       # 0
cargo +stable-x86_64-pc-windows-gnu check --workspace --all-targets --locked   # 0
cargo +stable-x86_64-pc-windows-gnu test --workspace --locked                  # 101（仅下述既有失败）
```

`rpi-cli` lib：`603 passed; 1 failed; 2 ignored`，其余 crate 全绿。

**唯一的失败是既有环境问题**：
`prebuilt_extensions::tests::downloaded_manifest_and_archive_install_into_an_isolated_profile`
报 `no supported prebuilt target for this host`。我把全部改动 stash 掉、回到干净的
`origin/main` `ccb4054` 单独跑过该测试，失败信息完全一致 → 与本改动无关。

## 5. fork CI 结果

fork 上 PR 的 `pull_request` 触发**没有生成任何 check run**（`statusCheckRollup` 为空，
`gh pr checks` 报 "no checks reported"）。为得到可引用的结论，我用
`gh workflow run ci.yml --ref fix/model-switch-not-persisted` 在**同一 head SHA `8a87df1`**
上手动触发了一次，check runs 全部挂在该 commit 上：

| Job | 结果 |
| --- | --- |
| Cargo check (ubuntu-latest) | ✅ success |
| Cargo check (windows-latest) | ✅ success |
| Cargo test | ✅ success |
| Windows plugin ABI and DLL lifecycle | ✅ success |
| Windows installer (powershell) | ✅ success |
| Windows installer (pwsh) | ✅ success |
| Release automation | skipped（`if: github.repository == 'bigfish1913/pi-rust'`，fork 上按预期跳过） |

run id `40044956676`，结论 `completed success`。annotations 只有 Node 20 弃用、
ubuntu-latest 标签迁移两条提示，与本改动无关。

**⚠️ 遗留疑点（下个 session 接手时请注意）**：fork 的 PR 事件不触发 CI，原因未查明
（workflow 是 `active`，Actions 权限 `enabled: true` / `allowed_actions: all`，
PR 非跨仓库，`.github/workflows/ci.yml` 的 `pull_request: branches: [main]` 也匹配）。
我没有改任何 CI 配置（交接文档禁止）。后续要么继续用 `workflow_dispatch` 手动触发，
要么查 fork 的 GitHub 侧设置。**不要**因为"PR 页面没绿勾"就以为 CI 失败。

## 6. 环境注意事项（复用）

- **GitHub 必须走本机 Clash Verge 代理**：`127.0.0.1:7897`（`verge-mihomo` 进程）。
  直连 `github.com:443` 会 `Connection reset` / 超时。

  ```bash
  export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897
  ```
- 8080 端口是 `zcode-proxy`，**不是**通用代理，对 GitHub 无效。
- `cargo test` 的链接阶段在 900s timeout 下可能被误判为失败；实际约 1m30s 完成，
  单次跑给足时间即可。
- 写文件给 `gh --body-file` 用时，MSYS 的 `/tmp` 不等于 Windows 的 `%TEMP%`
  （`gh.exe` 是原生 Windows 程序）。用仓库外的真实路径，例如 `E:/pr-a-body.md`。

## 7. 下一步（未完成）

1. **人工 TUI 测试**（交接文档 §8，轻量但必要）。用 release 构建：
   ```bash
   scripts/install-local.sh
   ```
   步骤：记录 `~/.rpi/settings.json` 的 `defaultModel` → 启动 `rpi`，`/model` 切到
   **不同 provider** → 确认提示含 `"Not saved as the default"` → 退出后复查
   `settings.json` 的 `defaultModel` **必须未变** → 再进 `/settings` → Default model
   选一个，确认提示 `"Default saved."` 且文件确实改变。第 4 步是关键。
2. PR #2 的 review 反馈（若有），特别是"行为收紧"这个取舍是否被接受。
3. Session B / C 的交接（见 [README.md](README.md) §2，C 必须等 B 合并）。

## 7.1 其他 session 的并行状态（截至本次落盘）

| Session | 状态 |
| --- | --- |
| A（本文件） | ✅ 代码交付 + CI 全绿，仅剩人工 TUI 测试 |
| B | [PR #3](https://github.com/DavidHinton-xcpc/pi-rust/pull/3)（`fix/session-switch-banner-and-new` @ `5b60934`）OPEN、MERGEABLE、CI 绿，**未合并** |
| C | 未开工，被 PR #3 阻塞；详情见 [session-c-progress-2026-10-24.md](session-c-progress-2026-10-24.md) |

fork `main` 仍指向 `ccb4054`，尚未包含 B 的改动。合并 PR #3 是 C 开工的前置条件。

## 8. 工作区里不属于本任务的遗留物

- `stash@{1}` = `WIP on fix/session-switch-state: ec51c13`：`fix/session-switch-state`
  分支上一处未提交的 `docs/README.md` 改动。我为了切分支把它 stash 了，
  **没有在错误分支上 pop**。请对应 session 自行取回。
- `bin/`、`rpi-linux-verify-0.8.3.tar.gz`、`docs/maintaining/handoff/` 均为 untracked，
  未提交、未推送。

## 9. 明确没有做的事

- ❌ 未 bump 版本、未改 `CHANGELOG.md`
- ❌ 未动 `sessions.rs` / `rendering.rs` / `state.rs` / `footer.rs`
- ❌ 未顺手清理 clippy warning
- ❌ 未提上游 `bigfish1913/pi-rust` 的 PR
- ❌ 未改任何 CI 配置（含 fork PR 不触发 CI 这个疑点）
- ❌ 未执行人工 TUI 测试
