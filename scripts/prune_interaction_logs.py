#!/usr/bin/env python3
"""交互日志维护 CLI：按天数与 kind 清理 SQLite，可选 VACUUM。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.interaction_log.maintenance import prune_and_vacuum
from core.interaction_log.store import InteractionLogStore, DEFAULT_DB_PATH


def main() -> int:
    """解析参数并执行 prune。"""
    parser = argparse.ArgumentParser(description="清理 interaction_logs.db 过期记录")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="删除早于 N 天的记录（默认 30）",
    )
    parser.add_argument(
        "--kinds",
        type=str,
        default="api_request",
        help="逗号分隔的 kind 列表（默认 api_request）",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help="SQLite 路径（默认 data/interaction_logs.db）",
    )
    parser.add_argument(
        "--vacuum",
        action="store_true",
        help="清理后执行 VACUUM 回收磁盘空间",
    )
    args = parser.parse_args()
    kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
    store = InteractionLogStore(args.db)
    result = prune_and_vacuum(store, days=args.days, kinds=kinds, vacuum=args.vacuum)
    before_mb = int(result["size_before_bytes"]) / (1024 * 1024)
    after_mb = int(result["size_after_bytes"]) / (1024 * 1024)
    print(
        f"deleted={result['deleted']} kinds={list(kinds)} days={args.days} "
        f"size_before={before_mb:.2f}MB size_after={after_mb:.2f}MB vacuum={result['vacuum']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
