import { defineLogicFunction } from "twenty-sdk/define";
import type { LogicFunctionExecutionContext, RoutePayload } from "twenty-sdk/logic-function";
import { DECIDE_APPROVAL_FUNCTION_UNIVERSAL_IDENTIFIER } from "src/constants/universal-identifiers";
import { decideReview, readConfig } from "src/lib/review-api";

const handler = (event: RoutePayload, context: LogicFunctionExecutionContext) =>
  decideReview(readConfig(), context.workspaceMemberId, event.body);

export default defineLogicFunction({
  universalIdentifier: DECIDE_APPROVAL_FUNCTION_UNIVERSAL_IDENTIFIER,
  name: "cra-decide-review",
  description: "保存当前成员对指定审核方案的通过或拒绝决定",
  timeoutSeconds: 10,
  handler,
  httpRouteTriggerSettings: { path: "/cra-review/decision", httpMethod: "POST", isAuthRequired: true },
});
