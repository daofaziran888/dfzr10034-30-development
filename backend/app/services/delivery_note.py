"""交付清单领域服务：资产交接、分区领取与列级交付核验。

负责人交接当日登记交付分区，办单人员领取旧分区/新分区时，服务按
``contract_grant`` 的列级授权和分区内的字段版本，计算每个消费方实际能
读取的列，并把每一列的契约签署依据回写到交付清单。
"""
from __future__ import annotations

import time as _time
from typing import Any

from app.services.base import BaseModuleService
from app.services.contract_grant import ContractGrantService
from app.store import store


class DeliveryNoteService(BaseModuleService):
    MODULE = "delivery_note"
    ENTITY = "交付清单"
    OPERATION_TERM = "核验"
    LIST_FIELDS = [
        "清单编号", "数据资产", "分区编号", "分区类型", "消费方",
        "可读字段", "核验结果", "负责人", "交付时间",
    ]
    REQUIRED_FIELDS = ["清单编号", "数据资产", "分区编号"]
    STATUS_ORDER = ["待领取", "已领取", "核验未过"]
    ACTION_RULES = {"确认领取": "已领取", "核验退回": "核验未过"}
    NEGATIVE_ACTIONS = ["核验退回"]

    def __init__(self) -> None:
        self.grant_service = ContractGrantService()

    # ── 分区登记 ──────────────────────────────────────────────

    def register_partition(
        self,
        asset_code: str,
        partition_code: str,
        field_versions: dict[str, str],
        partition_type: str = "旧分区",
        owner: str = "",
    ) -> dict[str, Any]:
        """登记一个待交付分区，并记录分区内每个字段的字段版本。

        旧分区保留交接前的字段版本，新分区承载重新发布后的同名字段新版本，
        字段版本快照在登记时固化，后续同名再发布不影响已登记分区。
        """
        note_id = store.next_id(self.MODULE)
        note = {
            "id": note_id,
            "清单编号": f"DELI-{note_id:04d}",
            "数据资产": asset_code,
            "分区编号": partition_code,
            "分区类型": partition_type,
            "分区字段版本": dict(field_versions),
            "消费方": "",
            "可读字段": "",
            "可读列明细": [],
            "核验结果": "待核验",
            "核验说明": "",
            "负责人": owner,
            "交付时间": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "待领取",
            "pending": True,
            "abnormal": False,
            "created_at": _time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        store.rows(self.MODULE).append(note)

        store.log_change(
            self.MODULE, note_id, "登记交付分区",
            before=None, after=f"{partition_code}({partition_type})",
            source="delivery", scope=f"asset:{asset_code}"
        )
        self.emit_event("partition_registered", {
            "note_id": note_id,
            "asset_code": asset_code,
            "partition_code": partition_code,
            "partition_type": partition_type,
        })
        return note

    # ── 领取与核验回写 ────────────────────────────────────────

    def claim_partition(
        self,
        partition_code: str,
        consumer: str,
        operator: str = "",
    ) -> dict[str, Any]:
        """办单人员为某消费方领取分区，核验列级授权并回写交付清单。

        返回内容包含消费方实际可读的列及每列的契约签署依据；
        未获授权或字段版本不匹配的列不会进入清单。
        """
        note = self._find_partition(partition_code)
        if note is None:
            return {"ok": False, "message": f"分区{partition_code}未登记，无法领取"}

        asset_code = str(note["数据资产"])
        field_versions: dict[str, str] = dict(note.get("分区字段版本", {}))
        columns = self.grant_service.readable_columns(
            asset_code, consumer, field_versions
        )

        # 负责人资产指派核验结果一并回写。
        owner_check = self._owner_verification(asset_code)
        passed = bool(columns) and owner_check["passed"]

        note["消费方"] = consumer
        note["可读字段"] = ",".join(col["字段名称"] for col in columns)
        note["可读列明细"] = columns
        note["核验结果"] = "核验通过" if passed else "核验未过"
        note["核验说明"] = (
            f"消费方{consumer}在分区{partition_code}可读{len(columns)}列；"
            f"负责人指派核验：{owner_check['detail']}"
        )
        note["负责人"] = owner_check.get("owner", note.get("负责人", ""))
        note["交付时间"] = _time.strftime("%Y-%m-%d %H:%M:%S")
        note["status"] = "已领取" if passed else "核验未过"
        note["pending"] = not passed
        note["abnormal"] = not passed
        note["领取人"] = operator

        store.log_change(
            self.MODULE, note["id"], "领取分区并回写交付清单",
            before=None, after=note["核验结果"],
            source="delivery",
            scope=f"asset:{asset_code};consumer:{consumer};columns:{len(columns)}",
        )
        self.emit_event("partition_claimed", {
            "note_id": note["id"],
            "partition_code": partition_code,
            "consumer": consumer,
            "readable_count": len(columns),
            "passed": passed,
        })
        return {
            "ok": passed,
            "note": note,
            "asset_code": asset_code,
            "partition_code": partition_code,
            "partition_type": note.get("分区类型", ""),
            "consumer": consumer,
            "field_versions": field_versions,
            "readable_columns": columns,
            "owner_check": owner_check,
        }

    @staticmethod
    def _owner_verification(asset_code: str) -> dict[str, Any]:
        """复用负责人管理的资产指派核验。"""
        from app.services.owner_mgr import OwnerMgrService

        return OwnerMgrService().verify_asset_assignment(asset_code)

    def _find_partition(self, partition_code: str) -> dict[str, Any] | None:
        rows = store.find_by_field(self.MODULE, "分区编号", partition_code)
        return rows[0] if rows else None

    # ── 追溯 ──────────────────────────────────────────────────

    def trace_partitions(self, asset_code: str) -> list[dict[str, Any]]:
        """追溯资产已经交付/登记的全部分区（含旧版分区）。"""
        return store.find_by_field(self.MODULE, "数据资产", asset_code)

    def get_partition(self, partition_code: str) -> dict[str, Any] | None:
        return self._find_partition(partition_code)
