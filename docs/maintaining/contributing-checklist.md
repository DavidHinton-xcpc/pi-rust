# 贡献规则落地清单

本文把根目录 [CONTRIBUTING.md](../../CONTRIBUTING.md) 与
[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 的**强制要求**整理成
可直接执行的检查项，用于提交前自检与 review 时核对。上游文档是唯一权威；
两者冲突时以 `CONTRIBUTING.md` 与 CI 配置为准。

## 1. 工具链

| 项 | 要求 |
| --- | --- |
| Rust | stable；涉及 MSRV 的改动需在 **1.78** 上复验（MSRV 受强制约束，`rust-toolchain` 未 pin） |
| 链接器 | Windows 需 MSVC linker；`rusqlite` 使用 `bundled`，需 C 工具链 |
| `task` | 仅发版/部署目标需要，普通构建不需要 |

本机注意：若未安装 Visual Studio C++ build tools，`stable-x86_64-pc-windows-msvc`
会链接失败，且 MSYS 的 `/usr/bin/link` 会抢占 `link.exe`。改用
`stable-x86_64-pc-windows-gnu`。

## 2. 提交前必跑命令

CI 在 Linux 与 Windows 上都以 `-D warnings` 编译，包含 test 与 example target；
Linux 测试任务额外以 `-D warnings` 跑 rustdoc。

```bash
cargo fmt --all -- --check
RUSTFLAGS="-D warnings" cargo check --workspace --all-targets --locked
RUSTFLAGS="-D warnings" RUSTDOCFLAGS="-D warnings" cargo test --workspace --locked
```

PowerShell：

```powershell
$env:RUSTFLAGS = "-D warnings"
$env:RUSTDOCFLAGS = "-D warnings"
```

Clippy **不属于** CI，仅作本地附加检查。

CI 另有两项容易被忽略的硬性门槛：

- `sh scripts/sync-embedded-docs.sh` 之后 `crates/rpi-cli/embedded-docs` 必须无
  diff（改了 `README.md` / `docs/` 就必须同步并提交）。
- 网络依赖测试必须门控；**禁止**把需要真实 provider 的测试放进默认
  `cargo test` 路径（`rpi-ai` 的 `faux` provider 保证离线可跑）。

## 3. 代码准则

- 已发布 crate 的公开 API 在 minor 版本内保持**增量式**；破坏性变更需版本
  bump 与 `CHANGELOG.md` 条目。
- **最小改动**：修复不需要的重构应拆到独立 PR。
- 新行为必须带测试，优先用内存执行环境与 `faux` provider，不碰网络与用户真实
  文件系统。
- 错误信息要指明失败组件与用户下一步能做什么。
- 公开项应有文档注释（`#![warn(missing_docs)]` 尚未全局启用，属 review 期望
  而非构建失败）。
- 依赖方向单向，不得新增反向边：

  ```
  rpi-telemetry → rpi-ai → rpi-agent → rpi-tools → rpi-harness → rpi-cli
  ```

  `rpi-plugin-sdk` 是零依赖叶子，`rpi-extensions` 位于其上。

## 4. 提交信息

遵循 [Conventional Commits](https://www.conventionalcommits.org/)：

```
fix(cli): preserve caret when the theme cache is rebuilt
docs: sync website package data
```

- subject 用祈使句，**约 72 字符以内**。
- 中英文 subject 都可接受，但 type 前缀与 scope 必须是约定形式。

## 5. PR 要求

1. 从 `main` 拉分支，分支只聚焦**一个**改动。
2. 填完 PR 模板：受影响的 crate、变更类型、验证方式。
3. CI 必须绿：`Cargo test` 与两个 `Cargo check`（Linux + Windows）无警告通过。
4. 预期会收到关于 API 增量的 review 意见——公开面刻意保持小而稳定。

需要**显式声明**的场景：

- 触及插件 ABI（`rpi-plugin-sdk`）：ABI 变更影响所有已构建扩展，需给出协商
  方案。
- 触及会话持久化（`rpi-harness`）：需说明相关操作中途崩溃时的恢复行为。

## 6. 发版

发版由维护者执行，**贡献者不得**在 PR 中 bump 版本或发布 crate。

1. 更新 `CHANGELOG.md`，在 workspace `Cargo.toml` 中 bump 版本。
2. `task publish` 推导下一版本、bump/tag/push 并跑完整渠道与 crates.io 流水线；
   `task publish:crates` 只按依赖顺序发布九个 crate，不动 git。
3. 推送 `vX.Y.Z` tag 并创建对应 GitHub Release；版本 bump 进入 `main` 后 CI
   自动发布。

## 7. 外部贡献者的 CI 门禁

首次外部贡献者的 workflow 需要维护者批准才会运行。`gh pr checks <n>` 显示
"no checks reported" 且 run 状态为 `action_required` 时，**不代表 CI 通过**，
也不代表 CI 失败——只是尚未运行。此时应请维护者点 "Approve and run"，不要以
本地结果代替线上证据。

## 8. 安全

安全问题不要开公开 issue，按 [SECURITY.md](../../SECURITY.md) 流程上报。
