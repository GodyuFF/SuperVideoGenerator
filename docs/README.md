# SuperVideoGenerator 文档

> 更新日期：2026-07-20

本目录存放**项目介绍**与详细设计。根下只保留入门文档；方案与规格在 `superpowers/`。

## 入门（本目录）

| 文档 | 说明 |
|------|------|
| [产品概览](product-overview.md) | 定位、核心能力、交互范式 |
| [快速开始](getting-started.md) | 环境、安装、启动、配置 |

仓库根目录 [README.md](../README.md) 提供对外简介与最短上手路径。

许可：[MIT](../LICENSE)；OpenCut 第三方声明见 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。

## 详细手册（`superpowers/reference/`）

| 文档 | 说明 |
|------|------|
| [产品计划手册](superpowers/reference/product-plan.md) | 领域模型、页面、编排、路线图 |
| [代码设计计划](superpowers/reference/code-design-plan.md) | 仓库结构、持久化、API |
| [提示词架构](superpowers/reference/prompt-architecture.md) | 固定区 / 动态区 |
| [工具参考](superpowers/reference/tools-reference.md) | Tool Registry |
| [Edit Studio](superpowers/reference/edit-studio-plan.md) | 多轨时间轴与导出 |
| [桌面打包](superpowers/reference/desktop-packaging.md) | 安装包与发版 |
| [前端风格](superpowers/reference/frontend-style-guide.md) | 暗房胶片设计系统 |
| [数据存储](superpowers/reference/data-storage.md) | 持久化流程 |
| [Schema](superpowers/reference/data-storage-schema.md) | 表结构 |
| [i18n](superpowers/reference/i18n.md) | 国际化 |
| [扩展开发](superpowers/reference/extensions.md) | Skill / Tool entry_points |
| [编排状态](superpowers/reference/orchestration-state.md) | 主编排状态组装 |
| [OpenCut 集成](superpowers/reference/opencut-integration.md) | 剪辑器集成 |
| [分镜结构](superpowers/reference/shot-structure-and-logic.md) | Shot / SubShot |
| [其它](superpowers/reference/) | av-sync、migration-review 等 |

## 设计规格与实施计划（`superpowers/`）

| 路径 | 说明 |
|------|------|
| [specs/](superpowers/specs/) | 功能设计规格（design） |
| [plans/](superpowers/plans/) | 分步实施计划 |
