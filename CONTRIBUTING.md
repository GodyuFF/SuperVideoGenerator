# 贡献指南

感谢关注 SuperVideoGenerator。欢迎通过 Issue 与 Pull Request 参与。

## 开始之前

1. 阅读根目录 [README.md](README.md) 与 [docs/getting-started.md](docs/getting-started.md)，确认能在本机跑通。
2. 自备 LLM / 生图 / TTS 等 API Key（见 `.env.example`），费用自负。
3. 搜索是否已有相同 Issue / PR，避免重复。

## 开发环境（摘要）

- Python 3.11+、Node.js 18+
- Windows 可用 `launch-desktop.vbs`；或分别启动 API + Vite（见快速开始）
- 本地数据在 `data/`，请勿提交

## 欢迎的贡献类型

- Bug 修复与复现说明
- 文档纠错、上手路径改进
- 小范围功能增强（请先开 Issue 讨论方向）
- 测试与构建稳定性改进

## 暂不优先

- 大规模无关重构
- 未讨论过的新云厂商整套接入（可先提案）
- 将本机 `data/`、真实 Key、内部设计文档（`docs/superpowers` 等）提交进仓库

## Pull Request 流程

1. Fork（或同仓分支）并基于最新 `main` 开分支。
2. 改动尽量小而完整；说明「为什么」与如何验证。
3. 若触及桌面安装包，注明是否在本地跑过 `apps/desktop/packaging` 相关脚本。
4. 提交前确认：无 `.env` / `data/` / 密钥；用户可见文案若改中文，尽量同步英文（i18n）。
5. 打开 PR，关联相关 Issue。

维护者会审阅；可能请你改小范围后再合。不保证每个 PR 都能合并，但会尽量回复。

## Issue 建议写法

- **Bug：** 期望行为、实际行为、系统/版本、复现步骤、相关日志（打码 Key）
- **功能：** 使用场景、是否接受替代方案

## 行为准则

参与时请保持礼貌、就事论事。恶意骚扰、人身攻击、垃圾广告会被关闭并视情况屏蔽。详见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 许可

贡献一经合并，按本仓库 [MIT License](LICENSE) 授权。Edit Studio 相关代码另见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
