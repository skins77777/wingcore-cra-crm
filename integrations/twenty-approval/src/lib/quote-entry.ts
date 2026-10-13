// Server-only quote gateway. Never accepts an actor or workspace from request bodies.
export interface QuoteConfig {
  apiUrl: string; apiToken: string; workspaceId: string; members: Record<string, "*" | string[]>;
}
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function readQuoteConfig(env: NodeJS.ProcessEnv = process.env): QuoteConfig {
  const apiUrl = env.CRA_REVIEW_API_URL ?? "";
  const apiToken = env.CRA_QUOTE_API_TOKEN ?? "";
  const workspaceId = env.CRA_QUOTE_WORKSPACE_ID ?? "";
  let url: URL;
  let members: QuoteConfig["members"];
  try { url = new URL(apiUrl); members = JSON.parse(env.CRA_QUOTE_MEMBER_SCOPES ?? ""); }
  catch { throw new Error("报价后台配置不完整"); }
  const local = url.protocol === "http:" && url.hostname === "172.22.176.1" && url.port === "3002";
  if ((!local && url.protocol !== "https:") || url.username || url.password || url.search || url.hash ||
      !apiToken || /[\r\n]/.test(apiToken) || !uuid.test(workspaceId) ||
      !members || typeof members !== "object" || Array.isArray(members) || !Object.keys(members).length ||
      Object.entries(members).some(([id, scope]) => !uuid.test(id) ||
        (scope !== "*" && (!Array.isArray(scope) || !scope.length || scope.some(x => typeof x !== "string" || !uuid.test(x)))))) {
    throw new Error("报价后台地址、工作区或成员范围配置无效");
  }
  return { apiUrl: url.toString().replace(/\/$/, ""), apiToken, workspaceId, members };
}

export function requireQuoteMember(config: QuoteConfig, member: string | null | undefined, opportunityId: unknown): string {
  if (typeof opportunityId !== "string" || !uuid.test(opportunityId)) throw new Error("商机编号无效");
  const scope = member ? config.members[member] : undefined;
  if (!member || !scope || (scope !== "*" && !scope.includes(opportunityId))) throw new Error("当前登录成员没有该商机的报价登记权限");
  return member;
}

export async function quoteCall(config: QuoteConfig, member: string | null | undefined, input: unknown, submit: boolean): Promise<unknown> {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("报价请求无效");
  const body = input as Record<string, unknown>;
  const actor = requireQuoteMember(config, member, body.opportunityId);
  let path = "/v1/quotes/registrations";
  if (!submit) {
    if (Object.keys(body).some(k => !["opportunityId", "submissionId"].includes(k))) throw new Error("读取参数无效");
    if (body.submissionId !== undefined && (typeof body.submissionId !== "string" || !uuid.test(body.submissionId))) throw new Error("提交编号无效");
    path = `/v1/quotes/opportunities/${encodeURIComponent(body.opportunityId as string)}` +
      (body.submissionId ? `?submissionId=${encodeURIComponent(body.submissionId as string)}` : "");
  } else if (Object.keys(body).some(k => !["submissionId", "opportunityId", "status", "expectedUpdatedAt", "quoteRound", "sentAt", "channel", "channelDetail", "evidence"].includes(k))) {
    throw new Error("报价请求字段无效");
  }
  const response = await fetch(config.apiUrl + path, {
    method: submit ? "POST" : "GET", redirect: "error", signal: AbortSignal.timeout(60000),
    headers: { authorization: `Bearer ${config.apiToken}`, "content-type": "application/json",
      "x-cra-workspace-id": config.workspaceId, "x-cra-member-id": actor },
    ...(submit ? { body: JSON.stringify(body) } : {}),
  });
  // Failed but persisted submissions must remain queryable and retryable.
  const result = await response.json() as Record<string, unknown>;
  if ([200, 409, 422, 503].includes(response.status) && result?.value && typeof result.value === "object") return result;
  if (!response.ok) throw new Error(`报价后台请求失败（${response.status}），请核对登记或用原提交编号重试`);
  return result;
}
