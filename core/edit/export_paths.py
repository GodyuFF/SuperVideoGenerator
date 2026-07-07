"""剪辑成片导出路径辅助。"""

from __future__ import annotations

from pathlib import Path

from core.store.project_paths import script_exports_dir


def export_filename_for_asset(asset_id: str) -> str:
    return f"final_{asset_id}.mp4"


def prepare_export_output_path(
    project_id: str,
    script_id: str,
    asset_id: str,
) -> Path:
    return script_exports_dir(project_id, script_id) / export_filename_for_asset(asset_id)
