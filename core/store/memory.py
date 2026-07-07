"""内存仓储：MVP 阶段数据存储，后续可替换为 SQLite/PostgreSQL。"""

from core.models.entities import (
    AssetReference,
    AssetScope,
    EditTimeline,
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
        self.edit_timelines: dict[str, EditTimeline] = {}
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

    def set_edit_timeline(self, timeline: EditTimeline) -> EditTimeline:
        self.edit_timelines[timeline.id] = timeline
        return timeline

    def get_edit_timeline_for_script(self, script_id: str) -> EditTimeline | None:
        for etl in self.edit_timelines.values():
            if etl.script_id == script_id:
                return etl
        return None

    def get_edit_timeline(self, timeline_id: str) -> EditTimeline | None:
        return self.edit_timelines.get(timeline_id)

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
        self.edit_timelines.clear()
        self.media_assets.clear()
        self._script_plans.clear()

    def delete_script(self, script_id: str) -> bool:
        """级联删除剧本及其关联资产、计划与媒体。"""
        script = self.scripts.get(script_id)
        if script is None:
            return False

        asset_ids = {
            a.id for a in self.text_assets.values() if a.script_id == script_id
        }
        media_ids = {
            m.id for m in self.media_assets.values() if m.script_id == script_id
        }
        entity_ids = asset_ids | media_ids

        ref_ids = [
            rid
            for rid, ref in self.references.items()
            if ref.script_id == script_id
            or ref.source_id in entity_ids
            or ref.target_id in entity_ids
        ]
        for rid in ref_ids:
            del self.references[rid]

        for aid in asset_ids:
            del self.text_assets[aid]
        for mid in media_ids:
            del self.media_assets[mid]

        plan_prefix = f"{script_id}_"
        for key in [k for k in self.plans if k.startswith(plan_prefix)]:
            del self.plans[key]
        self._script_plans.pop(script_id, None)

        for vp in [v for v in self.video_plans.values() if v.script_id == script_id]:
            del self.video_plans[vp.id]

        for et in [e for e in self.edit_timelines.values() if e.script_id == script_id]:
            del self.edit_timelines[et.id]

        del self.scripts[script_id]
        return True

    def delete_project(self, project_id: str) -> bool:
        """级联删除项目、其下全部剧本与项目级共享资产。"""
        if project_id not in self.projects:
            return False

        for script in list(self.list_scripts_for_project(project_id)):
            self.delete_script(script.id)

        shared_ids = [
            a.id
            for a in self.text_assets.values()
            if a.project_id == project_id and a.scope == AssetScope.PROJECT_SHARED
        ]
        for aid in shared_ids:
            ref_ids = [
                rid
                for rid, ref in self.references.items()
                if ref.source_id == aid or ref.target_id == aid
            ]
            for rid in ref_ids:
                del self.references[rid]
            del self.text_assets[aid]

        leftover_media = [
            m.id for m in self.media_assets.values() if m.project_id == project_id
        ]
        for mid in leftover_media:
            del self.media_assets[mid]

        del self.projects[project_id]
        return True
