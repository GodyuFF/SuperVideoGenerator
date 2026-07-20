# opencut-classic（Vendor 参考源码）

本目录用于存放 [opencut-app/opencut-classic](https://github.com/opencut-app/opencut-classic) 完整源码，作为 SuperVideoGenerator 编辑器 UI 移植的参考基线。

## 添加 Submodule（网络可用时）

```bash
git submodule add https://github.com/opencut-app/opencut-classic.git vendor/opencut-classic
git submodule update --init --recursive
```

若 submodule 尚未克隆，融合实现已将在 `apps/web/src/editor/classic/` 中逐步移植的核心模块（EditorCore、Timeline、Preview），并参见 [PORTING.md](./PORTING.md)。

## 许可

opencut-classic 采用 MIT License，移植代码保留原许可声明。
