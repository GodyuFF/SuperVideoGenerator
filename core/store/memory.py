"""内存仓储：MVP 阶段数据存储，后续可替换为 SQLite/PostgreSQL。"""

from core.models.entities import (
    AssetReference,
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
        # script_id -> 当前 plan 存储键
        self._script_plans: dict[str, str] = {}

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
        self.text_assets[asset.id] = asset
        return asset

    def get_text_asset(self, asset_id: str) -> TextAsset | None:
        return self.text_assets.get(asset_id)

    def delete_text_asset(self, asset_id: str) -> bool:
        if asset_id in self.text_assets:
            del self.text_assets[asset_id]
            return True
        return False

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
