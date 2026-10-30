# glyph-changes · rpi 图标调整对照页

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
python demo/build_glyph_demo.py            # 写 demo/glyph-changes-demo.html
python demo/build_glyph_demo.py --out pages/index.html   # 写站点副本
python demo/_verify.py                     # 逐格回读校验
```

## 为什么是两处同一份文件

| 路径 | 用途 |
| --- | --- |
| `demo/glyph-changes-demo.html` | 设计评审时的本地产物，随 `demo/` 一起演进 |
| `pages/index.html` | GitHub Pages 发布的入口，内容与上面**逐字节相同** |

CI 会校验两者一致（`cmp`），避免有人只改了一处导致线上与评审版本分叉。
