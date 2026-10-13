export type ReviewStatus = "pending" | "approved" | "rejected" | "superseded";
export type ExecutionStatus = "not_started" | "queued" | "running" | "succeeded" | "conflict" | "failed" | "manual_required";

export interface ReviewRequest {
  id: string;
  workspaceId: string;
  planDigest: string;
  ruleId: string;
  ruleVersion: string;
  title: string;
  reason: string;
  status: ReviewStatus;
  createdAt: string;
  target: { objectLabel: string; recordLabel: string };
  changes: Array<{ fieldLabel: string; before: string; after: string }>;
  evidence: Array<{ sourceLabel: string; reference: string; excerpt: string }>;
  choices: Array<{ id: string; label: string; description: string }>;
  decision: null | { outcome: "approved" | "rejected"; actorLabel: string; decidedAt: string; note: string; selectedChoiceId: string | null };
  execution: { status: ExecutionStatus; message: string };
  // 由后台基于当前成员、规则及记录版本计算，不能相信浏览器提交的能力。
  canDecide: boolean;
}

export interface ReviewPage { values: ReviewRequest[]; nextCursor: string | null }
export interface DecisionInput {
  id: string;
  planDigest: string;
  outcome: "approved" | "rejected";
  note: string;
  selectedChoiceId: string | null;
}

export const statuses: ReviewStatus[] = ["pending", "approved", "rejected", "superseded"];
const executions: ExecutionStatus[] = ["not_started", "queued", "running", "succeeded", "conflict", "failed", "manual_required"];
export const identifier = /^[A-Za-z0-9_-]{1,200}$/;
const digest = /^[a-f0-9]{64}$/;
const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const str = (value: unknown, max = 20000): value is string => typeof value === "string" && value.length <= max;
const nonempty = (value: unknown): value is string => str(value) && value.trim().length > 0;
const time = (value: unknown): boolean => nonempty(value) && Number.isFinite(Date.parse(value));
const rows = (value: unknown, predicate: (row: Record<string, unknown>) => boolean, max = 100): boolean =>
  Array.isArray(value) && value.length <= max && value.every(row => object(row) && predicate(row));

export function parseRequest(value: unknown, workspaceId?: string): ReviewRequest {
  if (!object(value) || !nonempty(value.id) || !identifier.test(value.id) || !nonempty(value.workspaceId) ||
    (workspaceId !== undefined && value.workspaceId !== workspaceId) ||
    !nonempty(value.planDigest) || !digest.test(value.planDigest) ||
    !nonempty(value.ruleId) || !nonempty(value.ruleVersion) || !nonempty(value.title) || !nonempty(value.reason) ||
    !statuses.includes(value.status as ReviewStatus) || !time(value.createdAt) || typeof value.canDecide !== "boolean" ||
    !object(value.target) || !nonempty(value.target.objectLabel) || !nonempty(value.target.recordLabel) ||
    !rows(value.changes, row => nonempty(row.fieldLabel) && str(row.before) && str(row.after)) ||
    !rows(value.evidence, row => nonempty(row.sourceLabel) && nonempty(row.reference) && str(row.excerpt)) ||
    !rows(value.choices, row => nonempty(row.id) && identifier.test(row.id) && nonempty(row.label) && str(row.description)) ||
    !object(value.execution) || !executions.includes(value.execution.status as ExecutionStatus) || !str(value.execution.message)) {
    throw new Error("审核后台返回的数据不完整或工作区不符");
  }
  const item = value as unknown as ReviewRequest;
  if (new Set(item.choices.map(choice => choice.id)).size !== item.choices.length) throw new Error("审核选项重复");
  if (item.decision !== null) {
    const d = item.decision;
    if (!object(d) || !["approved", "rejected"].includes(d.outcome) || !nonempty(d.actorLabel) || !time(d.decidedAt) || !str(d.note, 4000) ||
      !(d.selectedChoiceId === null || (nonempty(d.selectedChoiceId) && item.choices.some(choice => choice.id === d.selectedChoiceId)))) {
      throw new Error("审核决定格式错误");
    }
    if (d.outcome === "approved" && item.choices.length > 0 && d.selectedChoiceId === null) throw new Error("审核决定缺少选择");
    if (d.outcome === "rejected" && d.selectedChoiceId !== null) throw new Error("拒绝决定不应选择候选");
  }
  if ((item.status === "pending" && item.decision !== null) ||
    (["approved", "rejected"].includes(item.status) && item.decision?.outcome !== item.status) ||
    (item.status !== "pending" && item.canDecide) ||
    (["pending", "rejected"].includes(item.status) && item.execution.status !== "not_started")) {
    throw new Error("审核状态与决定或执行状态不一致");
  }
  return item;
}

export function parsePage(value: unknown, workspaceId?: string): ReviewPage {
  if (!object(value) || !Array.isArray(value.values) || value.values.length > 100 ||
    !(value.nextCursor === null || (nonempty(value.nextCursor) && value.nextCursor.length <= 2000))) {
    throw new Error("审核列表格式错误");
  }
  const values = value.values.map(row => parseRequest(row, workspaceId));
  if (new Set(values.map(row => row.id)).size !== values.length) throw new Error("审核列表有重复记录");
  return { values, nextCursor: value.nextCursor };
}

export function parseDecision(value: unknown): DecisionInput {
  if (!object(value) || !nonempty(value.id) || !identifier.test(value.id) || !nonempty(value.planDigest) || !digest.test(value.planDigest) ||
    !["approved", "rejected"].includes(String(value.outcome)) || !str(value.note, 4000) ||
    !(value.selectedChoiceId === null || (nonempty(value.selectedChoiceId) && identifier.test(value.selectedChoiceId))) ||
    (value.outcome === "rejected" && value.selectedChoiceId !== null)) throw new Error("审核决定参数不正确");
  // 显式重建，丢弃浏览器伪造的 actor、工作区、变更内容或执行权限。
  return { id: value.id, planDigest: value.planDigest, outcome: value.outcome as DecisionInput["outcome"], note: value.note, selectedChoiceId: value.selectedChoiceId };
}
