# 文档目录整理设计（2026-07-20）

> 状态：已执行

## 目标

- 删除 `vendor/`、`examples/`
- `docs/` 根仅保留介绍（README、product-overview、getting-started）
- 方案细节在 `docs/superpowers/reference|specs|plans`（无顶层 `docs/plans/`）
- 外层 README 不迁入 docs；抽出手册细节到 `docs/LOCAL-README-EXTRA.md`（gitignore）

## 结构

```
docs/
  README.md
  product-overview.md
  getting-started.md
  LOCAL-README-EXTRA.md   # gitignore
  superpowers/
    reference/   # 原 docs 根长文
    specs/
    plans/
```
