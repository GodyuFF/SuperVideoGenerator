"""NLE 工程 ZIP 打包与 README 生成。"""

from __future__ import annotations

import zipfile
from pathlib import Path


def build_readme_text(*, sequence_name: str) -> str:
    """生成 PR 导入说明文本。"""
    title = sequence_name or "SVF 剪辑工程"
    return f"""SuperVideoGenerator — Premiere Pro 工程包
序列名称：{title}

【导入步骤】
1. 将本 ZIP 解压到任意目录（保持 project.xml 与 media/ 文件夹同级）
2. 打开 Adobe Premiere Pro
3. 选择 File → Import（文件 → 导入）
4. 选中解压目录中的 project.xml
5. 若提示离线媒体，确认 media/ 文件夹与 project.xml 位于同一目录

【能力说明】
- 已导出：多视频图层、音频轨、字幕 SRT（subtitles.srt）、片段入出点
- 未完整迁移：Ken Burns 运镜、复杂转场/Classic 特效需在 PR 中手动重做
- 多层叠加的 composite 效果可能与 SVF 预览略有差异

【字幕】
可将 subtitles.srt 拖入 PR 时间轴，或使用「文件 → 导入」导入字幕轨。
"""


def create_zip(
    *,
    staging_dir: Path,
    output_path: Path,
    project_xml: str,
    srt_content: str,
    sequence_name: str,
) -> Path:
    """将 staging 目录内容与工程文件打包为 ZIP。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    readme = build_readme_text(sequence_name=sequence_name)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.xml", project_xml.encode("utf-8"))
        zf.writestr("README.txt", readme.encode("utf-8"))
        if srt_content.strip():
            zf.writestr("subtitles.srt", srt_content.encode("utf-8"))

        media_dir = staging_dir / "media"
        if media_dir.is_dir():
            for file_path in sorted(media_dir.iterdir()):
                if file_path.is_file():
                    arcname = f"media/{file_path.name}"
                    zf.write(file_path, arcname=arcname)

    return output_path
