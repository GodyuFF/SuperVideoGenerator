"""内存仓储：MVP 阶段数据存储，后续可替换为 SQLite/PostgreSQL。"""

from core.models.entities import (
    AssetReference,
    AssetScope,
    MediaAsset,
    MediaAssetType,
    PlanDocument,
    Project,
    Script,
    TextAsset,
    VideoPlan,
)


class MemoryStore:
    """基于字典的内存存储，便于单元测试与快速原型。"""

    def __init__(self) -> None:
        self.projects: dict[str, Project] = {}
        self.scripts: dict[str, Script] = {}
        self.text_assets: dict[str, TextAsset] = {}
        self.references: dict[str, AssetReference] = {}
        self.plans: dict[str, PlanDocument] = {}
        self.video_plans: dict[str, VideoPlan] = {}
        self.media_assets: dict[str, MediaAsset] = {}
        # script_id -> 当前 plan 存储键
        self._script_plans: dict[str, str] = {}

    def list_projects(self) -> list[Project]:
        return sorted(
            self.projects.values(),
            key=lambda p: p.created_at or p.id,
            reverse=True,
        )

    def list_shared_assets(self, project_id: str) -> list[TextAsset]:
        return [
            a
            for a in self.text_assets.values()
            if a.project_id == project_id and a.scope == AssetScope.PROJECT_SHARED
        ]

    def add_project(self, project: Project) -> Project:
        self.projects[project.id] = project
        return project

    def get_project(self, project_id: str) -> Project | None:
        return self.projects.get(project_id)

    def add_script(self, script: Script) -> Script:
        self.scripts[script.id] = script
        return script

    def get_script(self, script_id: str) -> Script | None:
        return self.scripts.get(script_id)

    def list_scripts_for_project(self, project_id: str) -> list[Script]:
        return [s for s in self.scripts.values() if s.project_id == project_id]

    def add_text_asset(self, asset: TextAsset) -> TextAsset:
        validated = TextAsset.model_validate(asset.model_dump())
        self.text_assets[validated.id] = validated
        return validated

    def get_text_asset(self, asset_id: str) -> TextAsset | None:
        return self.text_assets.get(asset_id)

    def delete_text_asset(self, asset_id: str) -> bool:
        if asset_id in self.text_assets:
            del self.text_assets[asset_id]
            return True
        return False

    def update_text_asset(self, asset: TextAsset) -> TextAsset:
        validated = TextAsset.model_validate(asset.model_dump())
        self.text_assets[validated.id] = validated
        return validated

    def remove_reference(self, ref_id: str) -> bool:
        if ref_id in self.references:
            del self.references[ref_id]
            return True
        return False

    def list_references_from(self, source_id: str) -> list[AssetReference]:
        return [r for r in self.references.values() if r.source_id == source_id]

    def list_references_to(self, target_id: str) -> list[AssetReference]:
        return [r for r in self.references.values() if r.target_id == target_id]

    def list_assets_for_script(self, script_id: str) -> list[TextAsset]:
        """返回本片私有资产 + 同项目共享池资产。"""
        script = self.scripts.get(script_id)
        if not script:
            return []
        return [
            a
            for a in self.text_assets.values()
            if a.script_id == script_id
            or (
                a.scope.value == "project_shared"
                and a.project_id == script.project_id
            )
        ]

    def add_reference(self, ref: AssetReference) -> AssetReference:
        self.references[ref.id] = ref
        return ref

    def set_plan(self, script_id: str, plan: PlanDocument) -> PlanDocument:
        key = f"{script_id}_v{plan.version}"
        self.plans[key] = plan
        self._script_plans[script_id] = key
        return plan

    def get_plan(self, script_id: str) -> PlanDocument | None:
        key = self._script_plans.get(script_id)
        if not key:
            return None
        return self.plans.get(key)

    def set_video_plan(self, plan: VideoPlan) -> VideoPlan:
        self.video_plans[plan.id] = plan
        return plan

    def get_video_plan_for_script(self, script_id: str) -> VideoPlan | None:
        for vp in self.video_plans.values():
            if vp.script_id == script_id:
                return vp
        return None

    def add_media_asset(self, asset: MediaAsset) -> MediaAsset:
        self.media_assets[asset.id] = asset
        return asset

    def list_media_for_script(
        self,
        script_id: str,
        media_type: MediaAssetType | None = None,
    ) -> list[MediaAsset]:
        script = self.scripts.get(script_id)
        if not script:
            return []
        items = [
            m
            for m in self.media_assets.values()
            if m.script_id == script_id and m.project_id == script.project_id
        ]
        if media_type is not None:
            items = [m for m in items if m.type == media_type]
        return sorted(items, key=lambda m: m.name)

    def list_media_for_project(self, project_id: str) -> list[MediaAsset]:
        return sorted(
            [m for m in self.media_assets.values() if m.project_id == project_id],
            key=lambda m: (m.type.value, m.name),
        )

    def clear(self) -> None:
        """清空全部内存数据（保留同一实例，避免外部引用失效）。"""
        self.projects.clear()
        self.scripts.clear()
        self.text_assets.clear()
        self.references.clear()
        self.plans.clear()
        self.video_plans.clear()
        self.media_assets.clear()
        self._script_plans.clear()
