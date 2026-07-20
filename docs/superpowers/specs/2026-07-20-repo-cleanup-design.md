# 仓库清理设计（2026-07-20）

> 状态：已确认执行  
> 范围：方案 B（安全清理 + 未引用 demo + 可重建本地大目录；保留 `data/`）

## 目标

根目录只保留桌面启动入口与源码/文档相关内容；删除测试残留媒体、多余启动脚本与可重建的本地构建产物。

## 决策

| 项 | 决定 |
|----|------|
| 根目录启动 | 仅保留 `launch-desktop.vbs` + `launch-desktop.bat` |
| 浏览器模式 | 文档说明：`uvicorn` + `apps/web` 的 `npm run dev` |
| 桌面快捷方式 | 删除 `create-desktop-shortcut.bat`；文档指向 `scripts/update_desktop_shortcut.ps1` |
| 垃圾 mp4 | 删除根目录 `fake_*.mp4`、`shot_pipeline_out.mp4` |
| demo 媒体 | 删除 `apps/web/public/demo/*.mp4`（代码无引用）及 `dist/demo` 副本 |
| 本地大目录 | 清空 `.worktrees/`、`apps/desktop/runtime/`、`.remotion/` |
| 保留 | `data/`、`.venv`、`node_modules`（不含 examples/vendor；2026-07-20 已删） |

## 文档同步

更新 README、CLAUDE.md、apps/desktop/README、code-design-plan、desktop-packaging、opencut-integration，以及 UI/i18n 中对 `dev.bat` 的引用。
