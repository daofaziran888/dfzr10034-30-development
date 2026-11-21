"""领域服务注册表：通用资源路由按模块 key 分派到独立业务服务。"""
from __future__ import annotations

from app.services.base import BaseModuleService
from app.services.asset_registry import AssetRegistryService
from app.services.metadata_index import MetadataIndexService
from app.services.quality_rule import QualityRuleService
from app.services.profile_stats import ProfileStatsService
from app.services.classification import ClassificationService
from app.services.lifecycle_policy import LifecyclePolicyService
from app.services.cold_archive import ColdArchiveService
from app.services.retention_job import RetentionJobService
from app.services.data_anonym import DataAnonymService
from app.services.operation_log import OperationLogService
from app.services.change_capture import ChangeCaptureService
from app.services.lineage_track import LineageTrackService
from app.services.impact_analysis import ImpactAnalysisService
from app.services.tag_registry import TagRegistryService
from app.services.govern_score import GovernScoreService
from app.services.data_contract import DataContractService
from app.services.compliance_scan import ComplianceScanService
from app.services.issue_track import IssueTrackService
from app.services.version_history import VersionHistoryService
from app.services.schedule_job import ScheduleJobService
from app.services.diff_report import DiffReportService
from app.services.owner_mgr import OwnerMgrService
from app.services.field_catalog import FieldCatalogService
from app.services.contract_grant import ContractGrantService
from app.services.delivery_note import DeliveryNoteService

# 服务模块别名，供跨模块调用
QUALITY_SERVICE = QualityRuleService()
COMPLIANCE_SERVICE = ComplianceScanService()
LIFECYCLE_SERVICE = LifecyclePolicyService()

SERVICES: dict[str, BaseModuleService] = {
    "asset_registry": AssetRegistryService(),
    "metadata_index": MetadataIndexService(),
    "quality_rule": QUALITY_SERVICE,
    "profile_stats": ProfileStatsService(),
    "classification": ClassificationService(),
    "lifecycle_policy": LIFECYCLE_SERVICE,
    "cold_archive": ColdArchiveService(),
    "retention_job": RetentionJobService(),
    "data_anonym": DataAnonymService(),
    "operation_log": OperationLogService(),
    "change_capture": ChangeCaptureService(),
    "lineage_track": LineageTrackService(),
    "impact_analysis": ImpactAnalysisService(),
    "tag_registry": TagRegistryService(),
    "govern_score": GovernScoreService(),
    "data_contract": DataContractService(),
    "compliance_scan": COMPLIANCE_SERVICE,
    "issue_track": IssueTrackService(),
    "version_history": VersionHistoryService(),
    "schedule_job": ScheduleJobService(),
    "diff_report": DiffReportService(),
    "owner_mgr": OwnerMgrService(),
    "field_catalog": FieldCatalogService(),
    "contract_grant": ContractGrantService(),
    "delivery_note": DeliveryNoteService(),
}


def service_for(module: str) -> BaseModuleService | None:
    return SERVICES.get(module)