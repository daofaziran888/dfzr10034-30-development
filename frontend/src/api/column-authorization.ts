import { request } from './client'

const BASE = '/api/column-authorization'

export type FieldVersion = {
  id: number
  字段编号: string
  所属资产: string
  字段名称: string
  字段版本: string
  字段标识: string
  字段类型: string
  业务含义: string
  发布时间: string
  status: string
}

export type ContractVersion = {
  id: number
  契约编号: string
  数据资产: string
  签署版本: string
  消费方: string
  签约字段: string[]
  负责人核验: string
  核验说明: string
  status: string
}

export type GrantRow = {
  id: number
  授权编号: string
  数据资产: string
  契约编号: string
  签署版本: string
  消费方: string
  字段名称: string
  字段标识: string
  字段版本: string
  授权依据: string
  拒绝原因: string
  冲突说明: string
  处理结论: string
  status: string
}

export type ReadableColumn = {
  字段名称: string
  字段版本: string
  字段标识: string
  契约编号: string
  签署版本: string
  授权编号: string
  授权依据: string
}

export type ClaimResult = {
  ok: boolean
  note: Record<string, unknown>
  asset_code: string
  partition_code: string
  partition_type: string
  consumer: string
  field_versions: Record<string, string>
  readable_columns: ReadableColumn[]
  owner_check: { passed: boolean; detail: string; owner: string }
}

export type DeliveryRow = {
  id: number
  清单编号: string
  数据资产: string
  分区编号: string
  分区类型: string
  分区字段版本: Record<string, string>
  消费方: string
  可读字段: string
  可读列明细: ReadableColumn[]
  核验结果: string
  核验说明: string
  负责人: string
  status: string
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await request(path, { method: 'POST', body: JSON.stringify(payload) })
  return (await response.json()) as T
}

async function getJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) throw new Error('列级授权数据读取失败')
  return (await response.json()) as T
}

// 负责人
export const assignOwner = (payload: { asset_code: string; owner: string; backup?: string }) =>
  postJson(`${BASE}/owners/assign`, payload)
export const handoverOwner = (assignmentId: number, newOwner: string) =>
  postJson(`${BASE}/owners/${assignmentId}/handover`, { new_owner: newOwner })
export const ownerCheck = (assetCode: string) =>
  getJson<{ passed: boolean; detail: string; owner: string }>(
    `${BASE}/assets/${encodeURIComponent(assetCode)}/owner-check`,
  )

// 契约签署版本
export const signContract = (payload: {
  asset_code: string
  consumer: string
  provider?: string
  signed_fields: string[]
  signed_version?: string
}) => postJson<{ contract: ContractVersion; owner_check: { passed: boolean } }>(`${BASE}/contracts/sign`, payload)
export const listContractVersions = (assetCode: string) =>
  getJson<{ items: ContractVersion[]; total: number }>(
    `${BASE}/assets/${encodeURIComponent(assetCode)}/contracts`,
  )

// 字段目录
export const publishField = (payload: {
  asset_code: string
  field_name: string
  field_type?: string
  biz_meaning?: string
}) => postJson<FieldVersion>(`${BASE}/fields`, payload)
export const listFieldVersions = (assetCode: string, fieldName: string) =>
  getJson<{ versions: FieldVersion[] }>(
    `${BASE}/assets/${encodeURIComponent(assetCode)}/field-versions?field_name=${encodeURIComponent(fieldName)}`,
  )

// 列级授权
export const grantField = (payload: {
  contract_id: number
  consumer: string
  field_name: string
  field_version?: string
}) => postJson<{ ok: boolean; reason?: string; conflict: boolean; grant: GrantRow }>(`${BASE}/grants`, payload)
export const listConflicts = (assetCode?: string) =>
  getJson<{ items: GrantRow[]; total: number }>(
    `${BASE}/grants/conflicts${assetCode ? `?asset_code=${encodeURIComponent(assetCode)}` : ''}`,
  )
export const resolveConflict = (grantId: number, resolution: string) =>
  postJson<{ ok: boolean; message: string; grant?: GrantRow }>(
    `${BASE}/grants/${grantId}/resolve`,
    { resolution },
  )
export const traceGrants = (assetCode: string, consumer?: string) =>
  getJson<{ items: GrantRow[]; total: number }>(
    `${BASE}/assets/${encodeURIComponent(assetCode)}/grants/trace${
      consumer ? `?consumer=${encodeURIComponent(consumer)}` : ''
    }`,
  )

// 交付分区
export const registerPartition = (payload: {
  asset_code: string
  partition_code: string
  field_versions: Record<string, string>
  partition_type: string
  owner?: string
}) => postJson<DeliveryRow>(`${BASE}/partitions`, payload)
export const claimPartition = (partitionCode: string, consumer: string, operator = '') =>
  postJson<ClaimResult>(`${BASE}/partitions/${encodeURIComponent(partitionCode)}/claim`, {
    consumer,
    operator,
  })
export const tracePartitions = (assetCode: string) =>
  getJson<{ items: DeliveryRow[]; total: number }>(
    `${BASE}/assets/${encodeURIComponent(assetCode)}/partitions`,
  )
