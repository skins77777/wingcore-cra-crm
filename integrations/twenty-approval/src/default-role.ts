import { defineApplicationRole } from "twenty-sdk/define";
import { DEFAULT_ROLE_UNIVERSAL_IDENTIFIER } from "src/constants/universal-identifiers";

// 本应用只代理审核请求，业务写入由客户后台的既有执行器负责。
export default defineApplicationRole({
  universalIdentifier: DEFAULT_ROLE_UNIVERSAL_IDENTIFIER,
  label: "待审核服务角色",
  description: "提供审核入口，不直接读写 CRM 业务对象",
  canReadAllObjectRecords: false,
  canUpdateAllObjectRecords: false,
  canSoftDeleteAllObjectRecords: false,
  canDestroyAllObjectRecords: false,
  objectPermissions: [],
});
