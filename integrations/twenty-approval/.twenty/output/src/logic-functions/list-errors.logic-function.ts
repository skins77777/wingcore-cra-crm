import { defineLogicFunction } from "twenty-sdk/define";
import type { LogicFunctionExecutionContext } from "twenty-sdk/logic-function";
import { listSystemErrors, readConfig } from "src/lib/review-api";

export default defineLogicFunction({
  universalIdentifier: "9df10b18-4482-4a31-9e7e-3d87ecb7b6b4",
  name: "cra-list-review-errors",
  description: "读取当前授权成员的系统处理异常",
  timeoutSeconds: 10,
  handler: (_event: unknown, context: LogicFunctionExecutionContext) => listSystemErrors(readConfig(), context.workspaceMemberId),
  httpRouteTriggerSettings: { path: "/cra-review/errors", httpMethod: "GET", isAuthRequired: true },
});
