import { identifier, parseDecision, parsePage, parseRequest, statuses } from "./contracts.ts";
import type { ReviewPage, ReviewRequest, ReviewStatus } from "./contracts.ts";

export interface ReviewConfig { apiUrl: string; apiToken: string; workspaceId: string; reviewerIds: string[] }

export function readConfig(env: NodeJS.ProcessEnv = process.env): ReviewConfig {
  const apiUrl = env.CRA_REVIEW_API_URL?.trim() ?? "";
  const apiToken = env.CRA_REVIEW_API_TOKEN?.trim() ?? "";
  const workspaceId = env.CRA_REVIEW_WORKSPACE_ID?.trim() ?? "";
  const reviewerIds = (env.CRA_REVIEWER_MEMBER_IDS ?? "").split(",").map(id => id.trim()).filter(Boolean);
  let url: URL;
  try { url = new URL(apiUrl); } catch { throw new Error("请配置客户审核 API 地址"); }
  const localBackend = url.protocol === "http:" && url.hostname === "172.22.176.1" && url.port === "3002";
  if ((url.protocol !== "https:" && !localBackend) || url.username || url.password || url.search || url.hash) throw new Error("审核 API 地址必须是 HTTPS 或已核实的本地 WSL 后台，且不含凭据、查询或锚点");
  if (!apiToken || /[\r\n]/.test(apiToken) || !identifier.test(workspaceId) || !reviewerIds.length || reviewerIds.some(id => !identifier.test(id))) {
    throw new Error("请配置审核 Token、工作区和 Twenty 审核成员");
  }
  return { apiUrl: url.toString().replace(/\/$/, ""), apiToken, workspaceId, reviewerIds };
}

export function requireReviewer(memberId: string | null | undefined, config: ReviewConfig): string {
  if (!memberId || !config.reviewerIds.includes(memberId)) throw new Error("当前登录成员没有审核权限");
  return memberId;
}

async function call(config: ReviewConfig, actor: string, path: string, body?: unknown, endpoint: "requests" | "errors" = "requests"): Promise<unknown> {
  const response = await fetch(`${config.apiUrl}/v1/review/${endpoint}${path}`, {
    method: body === undefined ? "GET" : "POST",
    redirect: "error",
    signal: AbortSignal.timeout(8000),
    headers: {
      authorization: `Bearer ${config.apiToken}`,
      "content-type": "application/json",
      "x-cra-workspace-id": config.workspaceId,
      "x-cra-reviewer-id": actor,
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    if (response.status === 409) throw new Error("记录或审核方案已变化，请刷新后重新核对");
    if (response.status === 401 || response.status === 403) throw new Error("后台拒绝访问，请核对审核配置与成员权限");
    // 不向浏览器透传上游错误、内部地址或凭据。
    throw new Error(`审核后台请求失败（${response.status}），请稍后刷新确认结果`);
  }
  return response.json();
}

export interface SystemErrorPage {
  values: Array<{ id: string; label: string; state: string; attempts: number | null; errorCode: string; message: string }>;
  total: number; checkedAt: string; state: string;
}

export async function listSystemErrors(config: ReviewConfig, memberId: string | null | undefined): Promise<SystemErrorPage> {
  const result = await call(config, requireReviewer(memberId, config), "", undefined, "errors") as SystemErrorPage;
  if (!result || !Array.isArray(result.values) || !Number.isInteger(result.total) || result.total < 0 ||
      typeof result.checkedAt !== "string" || !Number.isFinite(Date.parse(result.checkedAt)) ||
      result.values.some(row => !row || typeof row.id !== "string" || typeof row.label !== "string" || typeof row.errorCode !== "string" || typeof row.message !== "string")) {
    throw new Error("暂时无法检查系统处理状态");
  }
  return result;
}

export async function listReviews(config: ReviewConfig, memberId: string | null | undefined, status: string = "pending", cursor?: string): Promise<ReviewPage> {
  const actor = requireReviewer(memberId, config);
  if (!statuses.includes(status as ReviewStatus) || (cursor !== undefined && (!cursor || cursor.length > 2000))) throw new Error("审核列表参数不正确");
  const query = new URLSearchParams({ status, limit: "50" });
  if (cursor) query.set("cursor", cursor);
  const result = parsePage(await call(config, actor, `?${query}`), config.workspaceId);
  if (result.values.some(row => row.status !== status)) throw new Error("审核列表状态不符");
  return result;
}

export async function decideReview(config: ReviewConfig, memberId: string | null | undefined, input: unknown): Promise<{ value: ReviewRequest }> {
  const actor = requireReviewer(memberId, config);
  const decision = parseDecision(input);
  const response = await call(config, actor, `/${encodeURIComponent(decision.id)}/decision`, decision);
  const value = parseRequest((response as { value?: unknown } | null)?.value, config.workspaceId);
  if (value.id !== decision.id || value.planDigest !== decision.planDigest || value.status !== decision.outcome ||
    value.decision?.selectedChoiceId !== decision.selectedChoiceId) throw new Error("审核返回结果与提交的决定不符，请刷新核对");
  return { value };
}
