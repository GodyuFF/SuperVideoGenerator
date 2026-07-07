"""引用守卫与剧本编辑守卫：删除约束、未执行态可编辑判断。"""

from core.models.entities import AssetReference, AssetStatus, RelationType, Script, ScriptStatus, TextAsset
from core.store.memory import MemoryStore


class ReferenceGuardError(Exception):
    """资产被引用时禁止删除。"""

    def __init__(self, asset_id: str, references: list[AssetReference]) -> None:
        self.asset_id = asset_id
        self.references = references
        super().__init__(f"资产 {asset_id} 被 {len(references)} 处引用，无法删除")


class ReferenceGuard:
    """检查资产引用关系，支撑删除 API 与 UI 提示。"""

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def get_references_to(self, target_id: str) -> list[AssetReference]:
        """查询所有指向 target_id 的引用边。"""
        return [r for r in self._store.references.values() if r.target_id == target_id]

    def can_delete(self, asset_id: str) -> tuple[bool, list[AssetReference]]:
        """返回是否可删及引用列表。"""
        refs = self.get_references_to(asset_id)
        return len(refs) == 0, refs

    def assert_can_delete(self, asset_id: str) -> None:
        """不可删时抛出 ReferenceGuardError。"""
        ok, refs = self.can_delete(asset_id)
        if not ok:
            raise ReferenceGuardError(asset_id, refs)


class ScriptEditGuardError(Exception):
    """剧本或资产处于不可编辑状态。"""


class ScriptEditGuard:
    """AI 执行中（executing）禁止人工 CRUD；其余态（含执行完成/失败）允许。"""

    EDITABLE_STATUSES = {
        ScriptStatus.DRAFT,
        ScriptStatus.PLANNED,
        ScriptStatus.COMPLETED,
        ScriptStatus.FAILED,
    }

    @staticmethod
    def is_editable(script: Script) -> bool:
        """剧本是否处于可编辑状态。"""
        return script.status in ScriptEditGuard.EDITABLE_STATUSES

    @staticmethod
    def assert_editable(script: Script, asset_status: AssetStatus | None = None) -> None:
        """断言剧本可编辑；资产 locked 时也不可改。"""
        if script.status not in ScriptEditGuard.EDITABLE_STATUSES:
            raise ScriptEditGuardError(
                f"剧本 {script.id} 状态为 {script.status}，不可编辑"
            )
        if asset_status == AssetStatus.LOCKED:
            raise ScriptEditGuardError("资产已锁定")

    @staticmethod
    def assert_asset_editable(script: Script, asset: TextAsset) -> None:
        """断言指定文字资产可编辑。"""
        ScriptEditGuard.assert_editable(script, asset.status)
