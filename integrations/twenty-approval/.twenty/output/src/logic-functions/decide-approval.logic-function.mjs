import { createRequire as __createRequire } from 'module';
const require = __createRequire(import.meta.url);

// twenty-sdk-define-stub:__twenty-sdk-define-stub__
var __defineFactoryStub = (config) => ({
  success: true,
  config,
  errors: []
});
var __anyHandler = {
  get(_target, prop) {
    if (prop === "__esModule") return true;
    if (prop === Symbol.toPrimitive) return () => "";
    if (typeof prop === "symbol") return void 0;
    return new Proxy(() => void 0, __anyHandler);
  },
  apply() {
    return new Proxy(() => void 0, __anyHandler);
  }
};
var __anyStub = new Proxy(() => void 0, __anyHandler);
var defineLogicFunction = __defineFactoryStub;

// src/constants/universal-identifiers.ts
var DECIDE_APPROVAL_FUNCTION_UNIVERSAL_IDENTIFIER = "7725f688-d5d4-4957-a544-dc15727e54d0";

// src/lib/contracts.ts
var statuses = ["pending", "approved", "rejected", "superseded"];
var executions = ["not_started", "queued", "running", "succeeded", "conflict", "failed", "manual_required"];
var identifier = /^[A-Za-z0-9_-]{1,200}$/;
var digest = /^[a-f0-9]{64}$/;
var object = (value) => typeof value === "object" && value !== null && !Array.isArray(value);
var str = (value, max = 2e4) => typeof value === "string" && value.length <= max;
var nonempty = (value) => str(value) && value.trim().length > 0;
var time = (value) => nonempty(value) && Number.isFinite(Date.parse(value));
var rows = (value, predicate, max = 100) => Array.isArray(value) && value.length <= max && value.every((row) => object(row) && predicate(row));
function parseRequest(value, workspaceId) {
  if (!object(value) || !nonempty(value.id) || !identifier.test(value.id) || !nonempty(value.workspaceId) || workspaceId !== void 0 && value.workspaceId !== workspaceId || !nonempty(value.planDigest) || !digest.test(value.planDigest) || !nonempty(value.ruleId) || !nonempty(value.ruleVersion) || !nonempty(value.title) || !nonempty(value.reason) || !statuses.includes(value.status) || !time(value.createdAt) || typeof value.canDecide !== "boolean" || !object(value.target) || !nonempty(value.target.objectLabel) || !nonempty(value.target.recordLabel) || !rows(value.changes, (row) => nonempty(row.fieldLabel) && str(row.before) && str(row.after)) || !rows(value.evidence, (row) => nonempty(row.sourceLabel) && nonempty(row.reference) && str(row.excerpt)) || !rows(value.choices, (row) => nonempty(row.id) && identifier.test(row.id) && nonempty(row.label) && str(row.description)) || !object(value.execution) || !executions.includes(value.execution.status) || !str(value.execution.message)) {
    throw new Error("\u5BA1\u6838\u540E\u53F0\u8FD4\u56DE\u7684\u6570\u636E\u4E0D\u5B8C\u6574\u6216\u5DE5\u4F5C\u533A\u4E0D\u7B26");
  }
  const item = value;
  if (new Set(item.choices.map((choice) => choice.id)).size !== item.choices.length) throw new Error("\u5BA1\u6838\u9009\u9879\u91CD\u590D");
  if (item.decision !== null) {
    const d = item.decision;
    if (!object(d) || !["approved", "rejected"].includes(d.outcome) || !nonempty(d.actorLabel) || !time(d.decidedAt) || !str(d.note, 4e3) || !(d.selectedChoiceId === null || nonempty(d.selectedChoiceId) && item.choices.some((choice) => choice.id === d.selectedChoiceId))) {
      throw new Error("\u5BA1\u6838\u51B3\u5B9A\u683C\u5F0F\u9519\u8BEF");
    }
    if (d.outcome === "approved" && item.choices.length > 0 && d.selectedChoiceId === null) throw new Error("\u5BA1\u6838\u51B3\u5B9A\u7F3A\u5C11\u9009\u62E9");
    if (d.outcome === "rejected" && d.selectedChoiceId !== null) throw new Error("\u62D2\u7EDD\u51B3\u5B9A\u4E0D\u5E94\u9009\u62E9\u5019\u9009");
  }
  if (item.status === "pending" && item.decision !== null || ["approved", "rejected"].includes(item.status) && item.decision?.outcome !== item.status || item.status !== "pending" && item.canDecide || ["pending", "rejected"].includes(item.status) && item.execution.status !== "not_started") {
    throw new Error("\u5BA1\u6838\u72B6\u6001\u4E0E\u51B3\u5B9A\u6216\u6267\u884C\u72B6\u6001\u4E0D\u4E00\u81F4");
  }
  return item;
}
function parseDecision(value) {
  if (!object(value) || !nonempty(value.id) || !identifier.test(value.id) || !nonempty(value.planDigest) || !digest.test(value.planDigest) || !["approved", "rejected"].includes(String(value.outcome)) || !str(value.note, 4e3) || !(value.selectedChoiceId === null || nonempty(value.selectedChoiceId) && identifier.test(value.selectedChoiceId)) || value.outcome === "rejected" && value.selectedChoiceId !== null) throw new Error("\u5BA1\u6838\u51B3\u5B9A\u53C2\u6570\u4E0D\u6B63\u786E");
  return { id: value.id, planDigest: value.planDigest, outcome: value.outcome, note: value.note, selectedChoiceId: value.selectedChoiceId };
}

// src/lib/review-api.ts
function readConfig(env = process.env) {
  const apiUrl = env.CRA_REVIEW_API_URL?.trim() ?? "";
  const apiToken = env.CRA_REVIEW_API_TOKEN?.trim() ?? "";
  const workspaceId = env.CRA_REVIEW_WORKSPACE_ID?.trim() ?? "";
  const reviewerIds = (env.CRA_REVIEWER_MEMBER_IDS ?? "").split(",").map((id) => id.trim()).filter(Boolean);
  let url;
  try {
    url = new URL(apiUrl);
  } catch {
    throw new Error("\u8BF7\u914D\u7F6E\u5BA2\u6237\u5BA1\u6838 API \u5730\u5740");
  }
  const localBackend = url.protocol === "http:" && url.hostname === "172.22.176.1" && url.port === "3002";
  if (url.protocol !== "https:" && !localBackend || url.username || url.password || url.search || url.hash) throw new Error("\u5BA1\u6838 API \u5730\u5740\u5FC5\u987B\u662F HTTPS \u6216\u5DF2\u6838\u5B9E\u7684\u672C\u5730 WSL \u540E\u53F0\uFF0C\u4E14\u4E0D\u542B\u51ED\u636E\u3001\u67E5\u8BE2\u6216\u951A\u70B9");
  if (!apiToken || /[\r\n]/.test(apiToken) || !identifier.test(workspaceId) || !reviewerIds.length || reviewerIds.some((id) => !identifier.test(id))) {
    throw new Error("\u8BF7\u914D\u7F6E\u5BA1\u6838 Token\u3001\u5DE5\u4F5C\u533A\u548C Twenty \u5BA1\u6838\u6210\u5458");
  }
  return { apiUrl: url.toString().replace(/\/$/, ""), apiToken, workspaceId, reviewerIds };
}
function requireReviewer(memberId, config) {
  if (!memberId || !config.reviewerIds.includes(memberId)) throw new Error("\u5F53\u524D\u767B\u5F55\u6210\u5458\u6CA1\u6709\u5BA1\u6838\u6743\u9650");
  return memberId;
}
async function call(config, actor, path, body, endpoint = "requests") {
  const response = await fetch(`${config.apiUrl}/v1/review/${endpoint}${path}`, {
    method: body === void 0 ? "GET" : "POST",
    redirect: "error",
    signal: AbortSignal.timeout(8e3),
    headers: {
      authorization: `Bearer ${config.apiToken}`,
      "content-type": "application/json",
      "x-cra-workspace-id": config.workspaceId,
      "x-cra-reviewer-id": actor
    },
    ...body === void 0 ? {} : { body: JSON.stringify(body) }
  });
  if (!response.ok) {
    if (response.status === 409) throw new Error("\u8BB0\u5F55\u6216\u5BA1\u6838\u65B9\u6848\u5DF2\u53D8\u5316\uFF0C\u8BF7\u5237\u65B0\u540E\u91CD\u65B0\u6838\u5BF9");
    if (response.status === 401 || response.status === 403) throw new Error("\u540E\u53F0\u62D2\u7EDD\u8BBF\u95EE\uFF0C\u8BF7\u6838\u5BF9\u5BA1\u6838\u914D\u7F6E\u4E0E\u6210\u5458\u6743\u9650");
    throw new Error(`\u5BA1\u6838\u540E\u53F0\u8BF7\u6C42\u5931\u8D25\uFF08${response.status}\uFF09\uFF0C\u8BF7\u7A0D\u540E\u5237\u65B0\u786E\u8BA4\u7ED3\u679C`);
  }
  return response.json();
}
async function decideReview(config, memberId, input) {
  const actor = requireReviewer(memberId, config);
  const decision = parseDecision(input);
  const response = await call(config, actor, `/${encodeURIComponent(decision.id)}/decision`, decision);
  const value = parseRequest(response?.value, config.workspaceId);
  if (value.id !== decision.id || value.planDigest !== decision.planDigest || value.status !== decision.outcome || value.decision?.selectedChoiceId !== decision.selectedChoiceId) throw new Error("\u5BA1\u6838\u8FD4\u56DE\u7ED3\u679C\u4E0E\u63D0\u4EA4\u7684\u51B3\u5B9A\u4E0D\u7B26\uFF0C\u8BF7\u5237\u65B0\u6838\u5BF9");
  return { value };
}

// src/logic-functions/decide-approval.logic-function.ts
var handler = (event, context) => decideReview(readConfig(), context.workspaceMemberId, event.body);
var decide_approval_logic_function_default = defineLogicFunction({
  universalIdentifier: DECIDE_APPROVAL_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: "cra-decide-review",
  description: "\u4FDD\u5B58\u5F53\u524D\u6210\u5458\u5BF9\u6307\u5B9A\u5BA1\u6838\u65B9\u6848\u7684\u901A\u8FC7\u6216\u62D2\u7EDD\u51B3\u5B9A",
  timeoutSeconds: 10,
  handler,
  httpRouteTriggerSettings: { path: "/cra-review/decision", httpMethod: "POST", isAuthRequired: true }
});
export {
  decide_approval_logic_function_default as default
};
//# sourceMappingURL=decide-approval.logic-function.mjs.map
