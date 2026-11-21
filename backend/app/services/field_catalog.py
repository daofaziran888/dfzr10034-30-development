"""字段目录领域服务：资产的列级字段登记与字段版本管理。

数据契约的列级授权需要落到「资产 + 字段名 + 字段版本」三元组上。
资产交接后允许重新发布同名字段，发布动作产生新的字段版本（v1、v2 ……），
旧版本保留可追溯，发数人员据此区分同一名称在不同时期指向的不同字段。
"""
from __future__ import annotations

import time as _time
from typing import Any

from app.services.base import BaseModuleService
from app.store import store


class FieldCatalogService(BaseModuleService):
    MODULE = "field_catalog"
    ENTITY = "字段版本"
    OPERATION_TERM = "发布"
    LIST_FIELDS = [
        "字段编号", "所属资产", "字段名称", "字段版本", "字段标识",
        "字段类型", "业务含义", "发布时间",
    ]
    REQUIRED_FIELDS = ["字段编号", "所属资产", "字段名称"]
    STATUS_ORDER = ["草稿", "已发布", "已停用"]
    ACTION_RULES = {"发布字段": "已发布", "停用字段": "已停用"}
    NEGATIVE_ACTIONS = ["停用字段"]

    # ── 发布与版本管理 ────────────────────────────────────────

    def publish_field(
        self,
        asset_code: str,
        field_name: str,
        field_type: str = "string",
        biz_meaning: str = "",
    ) -> dict[str, Any]:
        """发布资产字段；同名字段重复发布时自动递增字段版本。

        同名不同版本会得到不同的字段标识（``资产.字段名@vN``），
        列级授权绑定字段标识，因此重新发布同名新列不会静默覆盖旧列授权。
        """
        version = self._next_field_version(asset_code, field_name)
        field_id = store.next_id(self.MODULE)
        field_key = f"{asset_code}.{field_name}@v{version}"
        entry = {
            "id": field_id,
            "字段编号": f"FCOL-{field_id:04d}",
            "所属资产": asset_code,
            "字段名称": field_name,
            "字段版本": f"v{version}",
            "字段标识": field_key,
            "字段类型": field_type,
            "业务含义": biz_meaning,
            "发布时间": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "已发布",
            "pending": False,
            "abnormal": False,
            "created_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        store.rows(self.MODULE).append(entry)

        store.log_change(
            self.MODULE, field_id, "发布字段版本",
            before=None, after=field_key,
            source="field_catalog", scope="field_catalog"
        )
        self.emit_event("field_published", {
            "field_id": field_id,
            "asset_code": asset_code,
            "field_name": field_name,
            "field_version": f"v{version}",
            "field_key": field_key,
        })
        return entry

    def _next_field_version(self, asset_code: str, field_name: str) -> int:
        versions = [
            self._version_number(row.get("字段版本", "v0"))
            for row in store.rows(self.MODULE)
            if row.get("所属资产") == asset_code and row.get("字段名称") == field_name
        ]
        return max(versions, default=0) + 1

    @staticmethod
    def _version_number(version_label: str) -> int:
        try:
            return int(str(version_label).lstrip("vV"))
        except ValueError:
            return 0

    # ── 查询 ──────────────────────────────────────────────────

    def list_fields(self, asset_code: str) -> list[dict[str, Any]]:
        """列出资产已发布的全部字段版本。"""
        return store.find_by_field(self.MODULE, "所属资产", asset_code)

    def list_field_versions(self, asset_code: str, field_name: str) -> list[dict[str, Any]]:
        """列出资产下某同名字段的全部版本（按版本号升序）。"""
        rows = [
            row for row in store.rows(self.MODULE)
            if row.get("所属资产") == asset_code and row.get("字段名称") == field_name
        ]
        return sorted(rows, key=lambda row: self._version_number(row.get("字段版本", "v0")))

    def get_field(self, field_key: str) -> dict[str, Any] | None:
        """按字段标识（资产.字段名@vN）取字段版本。"""
        rows = store.find_by_field(self.MODULE, "字段标识", field_key)
        return rows[0] if rows else None

    def latest_field(self, asset_code: str, field_name: str) -> dict[str, Any] | None:
        """取资产下同名字段的最新版本。"""
        versions = self.list_field_versions(asset_code, field_name)
        return versions[-1] if versions else None

    def resolve_field_key(
        self, asset_code: str, field_name: str, field_version: str | None = None
    ) -> str | None:
        """把字段名（+可选版本）解析为字段标识；不传版本时取最新版本。"""
        if field_version:
            label = field_version if str(field_version).startswith("v") else f"v{field_version}"
            field = self.get_field(f"{asset_code}.{field_name}@{label}")
            return field["字段标识"] if field else None
        field = self.latest_field(asset_code, field_name)
        return field["字段标识"] if field else None
