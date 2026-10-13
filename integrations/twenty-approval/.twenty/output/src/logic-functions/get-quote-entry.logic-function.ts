import { defineLogicFunction } from "twenty-sdk/define";
import type { LogicFunctionExecutionContext, RoutePayload } from "twenty-sdk/logic-function";
import { quoteCall, readQuoteConfig } from "src/lib/quote-entry";

const handler = (event: RoutePayload, context: LogicFunctionExecutionContext) =>
  quoteCall(readQuoteConfig(), context.workspaceMemberId, event.body, false);

export default defineLogicFunction({
  universalIdentifier: "d3b424a0-764b-41c7-81b7-e5e6eb2e8c01",
  name: "cra-get-quote-entry", description: "读取当前成员授权商机的报价登记和提交处理结果",
  timeoutSeconds: 70, handler,
  httpRouteTriggerSettings: { path: "/cra-quotes/read", httpMethod: "POST", isAuthRequired: true },
});
