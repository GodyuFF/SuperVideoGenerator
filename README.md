# SuperVideoGenerator

AI 视频生成 Agent：ReAct 主编排、A2UI 用户确认、自动生成/费用确认模式。

## 快速开始

```bash
pip install -r requirements.txt
pytest tests/ -v
uvicorn apps.api.main:app --reload --port 8000
```

前端：

```bash
cd apps/web && npm install && npm run dev
```

## 文档

- [产品计划手册](docs/product-plan.md)
- [代码设计计划](docs/code-design-plan.md)

## 生成模式

- `auto`：视频生成步骤不等待用户确认
- `cost_confirm`：视频生成前通过 A2UI 展示预估费用，用户确认后执行

用户通过 **左侧对话** 描述创意，**超级视频大师** 自动完成 Plan 并调度子 Agent 执行，无需手动点击按钮。

在项目配置中设置 `generation.mode`。
