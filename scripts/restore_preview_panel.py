"""从 git 恢复 PreviewPanel 并应用可选导出补丁。"""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "apps/web/src/editor/svf/PreviewPanel.tsx"

content = subprocess.check_output(
    ["git", "show", "HEAD:apps/web/src/edit/PreviewPanel.tsx"],
    cwd=ROOT,
).decode("utf-8")

content = content.replace(
    "  exporting: boolean;\n  onExport: () => void;",
    "  exporting?: boolean;\n  onExport?: () => void;",
)
content = content.replace(
    "  scriptId?: string | null;\n}",
    "  scriptId?: string | null;\n  /** 隐藏预览区底部控制条 */\n  hideControls?: boolean;\n}",
)
content = content.replace(
    "  scriptId,\n}: PreviewPanelProps) {",
    "  scriptId,\n  hideControls = false,\n}: PreviewPanelProps) {",
)
content = content.replace(
    '      </div>\n      <div className="edit-studio-preview-controls">',
    '      </div>\n      {!hideControls && (\n      <div className="edit-studio-preview-controls">',
)
content = content.replace(
    '        </span>\n        <button\n          type="button"\n          className="btn-primary btn-sm"\n          disabled={exporting || !ffmpegAvailable}\n          onClick={() => void onExport()}',
    '        </span>\n        {onExport && (\n        <button\n          type="button"\n          className="btn-primary btn-sm"\n          disabled={exporting || !ffmpegAvailable}\n          onClick={() => void onExport()}',
)
content = content.replace(
    '          {exporting ? "导出中…" : "导出成片"}\n        </button>\n        {onExportNoSubtitles && (',
    '          {exporting ? "导出中…" : "导出成片"}\n        </button>\n        )}\n        {onExportNoSubtitles && (',
)
content = content.replace(
    '      </div>\n    </div>\n  );\n}\n',
    '      </div>\n      )}\n    </div>\n  );\n}\n',
)

OUT.write_text(content, encoding="utf-8", newline="\n")
print(f"wrote {OUT} ({len(content)} bytes)")
