import { defineLogicFunction } from "twenty-sdk/define";
import type { LogicFunctionExecutionContext, RoutePayload } from "twenty-sdk/logic-function";
import { LIST_APPROVALS_FUNCTION_UNIVERSAL_IDENTIFIER } from "src/constants/universal-identifiers";
import { listReviews, readConfig } from "src/lib/review-api";

const handler = (event: RoutePayload, context: LogicFunctionExecutionContext) =>
  listReviews(readConfig(), context.workspaceMemberId, event.queryStringParameters?.status ?? "pending", event.queryStringParameters?.cursor);

export default defineLogicFunction({
  universalIdentifier: LIST_APPROVALS_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: "cra-list-reviews",
  description: "读取当前授权成员可处理的审核事项",
  timeoutSeconds: 10,
  handler,
  httpRouteTriggerSettings: { path: "/cra-review/requests", httpMethod: "GET", isAuthRequired: true },
});
