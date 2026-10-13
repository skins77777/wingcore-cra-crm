import { defineLogicFunction } from "twenty-sdk/define";
import type { LogicFunctionExecutionContext, RoutePayload } from "twenty-sdk/logic-function";
import { quoteCall, readQuoteConfig } from "src/lib/quote-entry";

const handler = (event: RoutePayload, context: LogicFunctionExecutionContext) =>
  quoteCall(readQuoteConfig(), context.workspaceMemberId, event.body, true);

export default defineLogicFunction({
  universalIdentifier: "d3b424a0-764b-41c7-81b7-e5e6eb2e8c02",
  name: "cra-submit-quote-entry", description: "登记人工报价事实，校验并回读三个T1报价字段",
  timeoutSeconds: 70, handler,
  httpRouteTriggerSettings: { path: "/cra-quotes/register", httpMethod: "POST", isAuthRequired: true },
});
