/** Classic 编辑器 React 错误边界：渲染失败时显示重试而非白屏。 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface ClassicEditorErrorBoundaryProps {
  children: ReactNode;
  onRetry?: () => void;
}

interface ClassicEditorErrorBoundaryState {
  error: Error | null;
}

/** 捕获 OpenCut Classic 子树运行时错误。 */
export class ClassicEditorErrorBoundary extends Component<
  ClassicEditorErrorBoundaryProps,
  ClassicEditorErrorBoundaryState
> {
  state: ClassicEditorErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ClassicEditorErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ClassicEditorErrorBoundary:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="classic-load-error">
          <p className="board-error">剪辑器加载失败：{this.state.error.message}</p>
          <p className="muted text-sm">请重试；若持续失败请刷新页面并确认浏览器支持 WebAssembly。</p>
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={() => {
              this.setState({ error: null });
              this.props.onRetry?.();
            }}
          >
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
