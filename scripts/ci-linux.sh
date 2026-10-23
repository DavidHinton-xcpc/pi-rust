#!/usr/bin/env bash
# 在 Linux 上复现 CI 的 Linux 门槛。用法：
#   bash ci-linux.sh            # 跑全部
#   bash ci-linux.sh --quick    # 只跑 fmt + check
#
# 与 .github/workflows/ci.yml 的对应关系见文末表格。
set -uo pipefail

QUICK=0
[[ "${1:-}" == "--quick" ]] && QUICK=1

FAILED=()
PASSED=()

run() {
    local name="$1"; shift
    echo
    echo "=============================================================="
    echo ">>> $name"
    echo "=============================================================="
    if "$@"; then
        PASSED+=("$name")
        echo "--- PASS: $name"
    else
        FAILED+=("$name")
        echo "--- FAIL: $name"
    fi
}

# --- 环境检查 -------------------------------------------------------------
echo "=== 环境 ==="
rustc --version || { echo "缺少 rustc；先跑 rustup 安装"; exit 1; }
cargo --version
python3 --version || echo "警告：缺少 python3，release-automation 测试会被跳过"
cc --version | head -1 || echo "警告：缺少 C 编译器，rusqlite bundled 会失败"

export RUSTFLAGS="-D warnings"
export RUSTDOCFLAGS="-D warnings"

# --- 对应 CI 的 check job（ubuntu-latest）----------------------------------
run "fmt" cargo fmt --all -- --check
run "check workspace" cargo check --workspace --all-targets --locked
run "check extensions all-features" cargo check -p rpi-extensions --all-features --tests --locked

if [[ $QUICK -eq 1 ]]; then
    echo
    echo "=== --quick：跳过测试 ==="
else
    # --- 对应 CI 的 test job（ubuntu-latest）------------------------------
    run "embedded docs in sync" bash -c '
        sh scripts/sync-embedded-docs.sh
        if ! git diff --exit-code -- crates/rpi-cli/embedded-docs; then
            echo "embedded-docs 与仓库文档不同步：运行 sh scripts/sync-embedded-docs.sh 并提交结果"
            exit 1
        fi'

    run "workspace tests" cargo test --workspace --locked
    run "plugin-sdk provider" cargo test -p rpi-plugin-sdk --features provider --locked
    run "plugin stub smoke" bash -c '
        cargo build -p plugin-stub --locked
        cargo test -p rpi-extensions --features provider-performance --test plugin_stub_smoke --locked'
    run "plugin-sdk no-default-features" cargo check -p rpi-plugin-sdk --no-default-features --locked
    run "provider bridge" cargo test -p rpi-extensions --features provider-performance --locked "provider::"

    if command -v python3 >/dev/null 2>&1; then
        run "prebuilt release manifests" python3 scripts/test_prebuilt_release.py
        run "release automation" python3 scripts/test_release_automation.py
        run "release channels" python3 scripts/test_release_channels.py
    fi
fi

# --- 汇总 -----------------------------------------------------------------
echo
echo "=============================================================="
echo "汇总"
echo "=============================================================="
printf '通过 %d 项\n' "${#PASSED[@]}"
for p in "${PASSED[@]}"; do echo "  ✓ $p"; done
if [[ ${#FAILED[@]} -gt 0 ]]; then
    printf '\n失败 %d 项\n' "${#FAILED[@]}"
    for f in "${FAILED[@]}"; do echo "  ✗ $f"; done
    echo
    echo "注意：Windows 上已知的既有失败"
    echo "  prebuilt_extensions::tests::downloaded_manifest_and_archive_install_into_an_isolated_profile"
    echo "  在 gnu 工具链下必失败（host_target 只认 msvc）。若 Linux 上同样失败，请记录但"
    echo "  不要归因于本分支——需在未改动的 v0.8.3 上复验一次。"
    exit 1
fi
echo
echo "全部通过。"
