# glyph-changes · rpi 图标调整对照页

**线上地址**：<https://davidhinton-xcpc.github.io/pi-rust/>

`index.html` 是**生成产物**，不要手改。

## 本地预览

```powershell
python -m http.server 4173 --directory pages
# 打开 http://localhost:4173/
```

单文件、零外部依赖（无 CDN、无外链字体），直接双击 `index.html` 也能看。

## 重新生成

```powershell
cargo run -q -p rpi-cli --example glyph_capture > demo/_capture.txt
python demo/build_glyph_demo.py                          # demo/glyph-changes-demo.html
python demo/build_glyph_demo.py --out pages/index.html   # 站点副本
python demo/_verify.py pages/index.html                  # 逐格回读校验
```

## 发布方式（重要）

该 fork 的 Actions 被禁用（`workflow_dispatch` 返回
`Actions has been disabled for this repository`，push 事件也不触发任何
workflow），所以 **`.github/workflows/pages.yml` 在这台仓库上不会生效**。
页面实际通过 **legacy Pages 源**发布：

| 项 | 值 |
| --- | --- |
| 源分支 | `main` |
| 源目录 | `/docs` |
| 构建类型 | `legacy`（GitHub 直接托管，不经 Actions） |

因此更新线上页面的步骤是：

```powershell
python demo/build_glyph_demo.py --out docs/index.html
git add docs/index.html
git commit -m "docs: refresh the glyph comparison page"
git push
```

若日后仓库 Actions 恢复，把 `pages.yml` 的 `build_type` 切回 `workflow`
即可退回到“从源码重建 + 校验 + 拒绝过期副本”的那条更严格的流水线。

## 两处同一份文件

| 路径 | 用途 |
| --- | --- |
| `demo/glyph-changes-demo.html` | 评审用的本地产物 |
| `pages/index.html` | 仓库内的站点副本（与上面逐字节相同，仅行尾可能为 CRLF） |
| `docs/index.html` | **实际发布源**，内容同上 |

发布前请确认三者内容一致（Git 的 `autocrlf` 会让工作区副本带 CRLF，
比较时先归一化行尾，或直接比较 `git show HEAD:docs/index.html`）。
