import { defineRole } from "twenty-sdk/define";
export default defineRole({
  universalIdentifier: "510eea4e-a8f1-4d8d-a89d-ff572d858cc8",
  label: "CRA 聊天客户与商机写入",
  description: "只读写客户和商机；无删除、订单、公司、任务或设置权限",
  canBeAssignedToApiKeys: true,
  canBeAssignedToUsers: false,
  canBeAssignedToAgents: false,
  canUpdateAllSettings: false,
  canAccessAllTools: false,
  canReadAllObjectRecords: false,
  canUpdateAllObjectRecords: false,
  canSoftDeleteAllObjectRecords: false,
  canDestroyAllObjectRecords: false,
  objectPermissions: [
    { objectUniversalIdentifier: "20202020-e674-48e5-a542-72570eee7213", canReadObjectRecords: true, canUpdateObjectRecords: true, canSoftDeleteObjectRecords: false, canDestroyObjectRecords: false },
    { objectUniversalIdentifier: "20202020-9549-49dd-b2b2-883999db8938", canReadObjectRecords: true, canUpdateObjectRecords: true, canSoftDeleteObjectRecords: false, canDestroyObjectRecords: false },
  ],
});
