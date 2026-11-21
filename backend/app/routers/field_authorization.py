"""契约列级授权专用接口：字段发布、列级授权、冲突处理与分区交付。

通用资源路由（resource.py）只承载列表/登记/动作，发数人员实际使用的
授权工作流通过本路由落到 field_catalog / contract_grant / delivery_note
三个领域服务，路由层不做业务判断，全部规则在服务内执行。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.contract_grant import ContractGrantService
from app.services.data_contract import DataContractService
from app.services.delivery_note import DeliveryNoteService
from app.services.field_catalog import FieldCatalogService
from app.services.owner_mgr import OwnerMgrService

router = APIRouter(prefix="/api/column-authorization", tags=["契约列级授权"])

catalog_service = FieldCatalogService()
grant_service = ContractGrantService()
delivery_service = DeliveryNoteService()
contract_service = DataContractService()
owner_service = OwnerMgrService()


class SignContractPayload(BaseModel):
    asset_code: str
    consumer: str
    provider: str = ""
    signed_fields: list[str] = Field(default_factory=list)
    signed_version: str | None = None
    sla: str = "99.9%可用性"
    frequency: str = "每日更新"


class AssignOwnerPayload(BaseModel):
    asset_code: str
    role: str = "数据负责人"
    owner: str
    backup: str = ""


class HandoverPayload(BaseModel):
    new_owner: str


@router.post("/contracts/sign")
def sign_contract(payload: SignContractPayload) -> dict[str, Any]:
    """签署契约并生成签署版本，同时回写负责人资产指派核验结果。"""
    return contract_service.define_contract(
        payload.asset_code,
        {"summary": ",".join(payload.signed_fields)},
        payload.sla, payload.frequency, payload.provider, payload.consumer,
        signed_fields=payload.signed_fields,
        signed_version=payload.signed_version,
    )


@router.get("/assets/{asset_code}/contracts")
def list_contract_versions(asset_code: str) -> dict[str, Any]:
    rows = contract_service.get_signed_versions(asset_code)
    return {"items": rows, "total": len(rows)}


@router.post("/owners/assign")
def assign_owner(payload: AssignOwnerPayload) -> dict[str, Any]:
    return owner_service.assign_owner(
        payload.asset_code, payload.role, payload.owner, payload.backup
    )


@router.post("/owners/{assignment_id}/handover")
def handover_owner(assignment_id: int, payload: HandoverPayload) -> dict[str, Any]:
    result = owner_service.handover(assignment_id, payload.new_owner)
    return result or {"ok": False, "message": f"指派 {assignment_id} 不存在"}


@router.get("/assets/{asset_code}/owner-check")
def owner_check(asset_code: str) -> dict[str, Any]:
    return owner_service.verify_asset_assignment(asset_code)


class PublishFieldPayload(BaseModel):
    asset_code: str
    field_name: str
    field_type: str = "string"
    biz_meaning: str = ""


class GrantFieldPayload(BaseModel):
    contract_id: int
    consumer: str
    field_name: str
    field_version: str | None = None


class ResolveConflictPayload(BaseModel):
    resolution: str
    target_field_key: str | None = None


class RegisterPartitionPayload(BaseModel):
    asset_code: str
    partition_code: str
    field_versions: dict[str, str] = Field(default_factory=dict)
    partition_type: str = "旧分区"
    owner: str = ""


class ClaimPartitionPayload(BaseModel):
    consumer: str
    operator: str = ""


@router.post("/fields")
def publish_field(payload: PublishFieldPayload) -> dict[str, Any]:
    """发布资产字段；同名再发布自动生成新字段版本。"""
    return catalog_service.publish_field(
        payload.asset_code, payload.field_name,
        payload.field_type, payload.biz_meaning,
    )


@router.get("/assets/{asset_code}/field-versions")
def list_field_versions(asset_code: str, field_name: str) -> dict[str, Any]:
    return {
        "asset_code": asset_code,
        "field_name": field_name,
        "versions": catalog_service.list_field_versions(asset_code, field_name),
    }


@router.post("/grants")
def grant_field(payload: GrantFieldPayload) -> dict[str, Any]:
    """按契约签署版本申请列级授权（越权返回 ok=false 并留痕）。"""
    return grant_service.grant_field(
        payload.contract_id, payload.consumer,
        payload.field_name, payload.field_version,
    )


@router.get("/grants/conflicts")
def list_conflicts(asset_code: str | None = None) -> dict[str, Any]:
    conflicts = grant_service.detect_conflicts(asset_code)
    return {"items": conflicts, "total": len(conflicts)}


@router.post("/grants/{grant_id}/resolve")
def resolve_conflict(grant_id: int, payload: ResolveConflictPayload) -> dict[str, Any]:
    return grant_service.resolve_conflict(
        grant_id, payload.resolution, payload.target_field_key
    )


@router.get("/assets/{asset_code}/grants/trace")
def trace_grants(asset_code: str, consumer: str | None = None) -> dict[str, Any]:
    rows = grant_service.trace_grants(asset_code, consumer)
    return {"items": rows, "total": len(rows)}


@router.post("/partitions")
def register_partition(payload: RegisterPartitionPayload) -> dict[str, Any]:
    return delivery_service.register_partition(
        payload.asset_code, payload.partition_code,
        payload.field_versions, payload.partition_type, payload.owner,
    )


@router.post("/partitions/{partition_code}/claim")
def claim_partition(partition_code: str, payload: ClaimPartitionPayload) -> dict[str, Any]:
    """领取分区并回写消费方实际可读列与签署依据。"""
    return delivery_service.claim_partition(
        partition_code, payload.consumer, payload.operator
    )


@router.get("/assets/{asset_code}/partitions")
def trace_partitions(asset_code: str) -> dict[str, Any]:
    rows = delivery_service.trace_partitions(asset_code)
    return {"items": rows, "total": len(rows)}
