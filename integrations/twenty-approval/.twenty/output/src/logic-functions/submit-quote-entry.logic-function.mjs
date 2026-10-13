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

// src/lib/quote-entry.ts
var uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function readQuoteConfig(env = process.env) {
  const apiUrl = env.CRA_REVIEW_API_URL ?? "";
  const apiToken = env.CRA_QUOTE_API_TOKEN ?? "";
  const workspaceId = env.CRA_QUOTE_WORKSPACE_ID ?? "";
  let url;
  let members;
  try {
    url = new URL(apiUrl);
    members = JSON.parse(env.CRA_QUOTE_MEMBER_SCOPES ?? "");
  } catch {
    throw new Error("\u62A5\u4EF7\u540E\u53F0\u914D\u7F6E\u4E0D\u5B8C\u6574");
  }
  const local = url.protocol === "http:" && url.hostname === "172.22.176.1" && url.port === "3002";
  if (!local && url.protocol !== "https:" || url.username || url.password || url.search || url.hash || !apiToken || /[\r\n]/.test(apiToken) || !uuid.test(workspaceId) || !members || typeof members !== "object" || Array.isArray(members) || !Object.keys(members).length || Object.entries(members).some(([id, scope]) => !uuid.test(id) || scope !== "*" && (!Array.isArray(scope) || !scope.length || scope.some((x) => typeof x !== "string" || !uuid.test(x))))) {
    throw new Error("\u62A5\u4EF7\u540E\u53F0\u5730\u5740\u3001\u5DE5\u4F5C\u533A\u6216\u6210\u5458\u8303\u56F4\u914D\u7F6E\u65E0\u6548");
  }
  return { apiUrl: url.toString().replace(/\/$/, ""), apiToken, workspaceId, members };
}
function requireQuoteMember(config, member, opportunityId) {
  if (typeof opportunityId !== "string" || !uuid.test(opportunityId)) throw new Error("\u5546\u673A\u7F16\u53F7\u65E0\u6548");
  const scope = member ? config.members[member] : void 0;
  if (!member || !scope || scope !== "*" && !scope.includes(opportunityId)) throw new Error("\u5F53\u524D\u767B\u5F55\u6210\u5458\u6CA1\u6709\u8BE5\u5546\u673A\u7684\u62A5\u4EF7\u767B\u8BB0\u6743\u9650");
  return member;
}
async function quoteCall(config, member, input, submit) {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("\u62A5\u4EF7\u8BF7\u6C42\u65E0\u6548");
  const body = input;
  const actor = requireQuoteMember(config, member, body.opportunityId);
  let path = "/v1/quotes/registrations";
  if (!submit) {
    if (Object.keys(body).some((k) => !["opportunityId", "submissionId"].includes(k))) throw new Error("\u8BFB\u53D6\u53C2\u6570\u65E0\u6548");
    if (body.submissionId !== void 0 && (typeof body.submissionId !== "string" || !uuid.test(body.submissionId))) throw new Error("\u63D0\u4EA4\u7F16\u53F7\u65E0\u6548");
    path = `/v1/quotes/opportunities/${encodeURIComponent(body.opportunityId)}` + (body.submissionId ? `?submissionId=${encodeURIComponent(body.submissionId)}` : "");
  } else if (Object.keys(body).some((k) => !["submissionId", "opportunityId", "status", "expectedUpdatedAt", "quoteRound", "sentAt", "channel", "channelDetail", "evidence"].includes(k))) {
    throw new Error("\u62A5\u4EF7\u8BF7\u6C42\u5B57\u6BB5\u65E0\u6548");
  }
  const response = await fetch(config.apiUrl + path, {
    method: submit ? "POST" : "GET",
    redirect: "error",
    signal: AbortSignal.timeout(6e4),
    headers: {
      authorization: `Bearer ${config.apiToken}`,
      "content-type": "application/json",
      "x-cra-workspace-id": config.workspaceId,
      "x-cra-member-id": actor
    },
    ...submit ? { body: JSON.stringify(body) } : {}
  });
  const result = await response.json();
  if ([200, 409, 422, 503].includes(response.status) && result?.value && typeof result.value === "object") return result;
  if (!response.ok) throw new Error(`\u62A5\u4EF7\u540E\u53F0\u8BF7\u6C42\u5931\u8D25\uFF08${response.status}\uFF09\uFF0C\u8BF7\u6838\u5BF9\u767B\u8BB0\u6216\u7528\u539F\u63D0\u4EA4\u7F16\u53F7\u91CD\u8BD5`);
  return result;
}

// src/logic-functions/submit-quote-entry.logic-function.ts
var handler = (event, context) => quoteCall(readQuoteConfig(), context.workspaceMemberId, event.body, true);
var submit_quote_entry_logic_function_default = defineLogicFunction({
  universalIdentifier: "d3b424a0-764b-41c7-81b7-e5e6eb2e8c02",
  name: "cra-submit-quote-entry",
  description: "\u767B\u8BB0\u4EBA\u5DE5\u62A5\u4EF7\u4E8B\u5B9E\uFF0C\u6821\u9A8C\u5E76\u56DE\u8BFB\u4E09\u4E2AT1\u62A5\u4EF7\u5B57\u6BB5",
  timeoutSeconds: 70,
  handler,
  httpRouteTriggerSettings: { path: "/cra-quotes/register", httpMethod: "POST", isAuthRequired: true }
});
export {
  submit_quote_entry_logic_function_default as default
};
//# sourceMappingURL=submit-quote-entry.logic-function.mjs.map
