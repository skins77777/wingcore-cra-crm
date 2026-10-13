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

// src/lib/contracts.ts
var identifier = /^[A-Za-z0-9_-]{1,200}$/;

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
async function listSystemErrors(config, memberId) {
  const result = await call(config, requireReviewer(memberId, config), "", void 0, "errors");
  if (!result || !Array.isArray(result.values) || !Number.isInteger(result.total) || result.total < 0 || typeof result.checkedAt !== "string" || !Number.isFinite(Date.parse(result.checkedAt)) || result.values.some((row) => !row || typeof row.id !== "string" || typeof row.label !== "string" || typeof row.errorCode !== "string" || typeof row.message !== "string")) {
    throw new Error("\u6682\u65F6\u65E0\u6CD5\u68C0\u67E5\u7CFB\u7EDF\u5904\u7406\u72B6\u6001");
  }
  return result;
}

// src/logic-functions/list-errors.logic-function.ts
var list_errors_logic_function_default = defineLogicFunction({
  universalIdentifier: "9df10b18-4482-4a31-9e7e-3d87ecb7b6b4",
  name: "cra-list-review-errors",
  description: "\u8BFB\u53D6\u5F53\u524D\u6388\u6743\u6210\u5458\u7684\u7CFB\u7EDF\u5904\u7406\u5F02\u5E38",
  timeoutSeconds: 10,
  handler: (_event, context) => listSystemErrors(readConfig(), context.workspaceMemberId),
  httpRouteTriggerSettings: { path: "/cra-review/errors", httpMethod: "GET", isAuthRequired: true }
});
export {
  list_errors_logic_function_default as default
};
//# sourceMappingURL=list-errors.logic-function.mjs.map
