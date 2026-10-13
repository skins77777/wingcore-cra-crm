import { defineApplication } from "twenty-sdk/define";
import {
  APP_DESCRIPTION, APP_DISPLAY_NAME, APPLICATION_UNIVERSAL_IDENTIFIER,
  API_URL_VARIABLE_UNIVERSAL_IDENTIFIER, API_TOKEN_VARIABLE_UNIVERSAL_IDENTIFIER,
  REVIEWERS_VARIABLE_UNIVERSAL_IDENTIFIER, WORKSPACE_VARIABLE_UNIVERSAL_IDENTIFIER,
} from "src/constants/universal-identifiers";

export default defineApplication({
  universalIdentifier: APPLICATION_UNIVERSAL_IDENTIFIER,
  displayName: APP_DISPLAY_NAME,
  description: APP_DESCRIPTION,
  applicationVariables: {
    CRA_REVIEW_API_URL: {
      universalIdentifier: API_URL_VARIABLE_UNIVERSAL_IDENTIFIER,
      description: "客户审核后台的 HTTPS 地址；不含查询参数或凭据",
      isSecret: true,
    },
    CRA_REVIEW_API_TOKEN: {
      universalIdentifier: API_TOKEN_VARIABLE_UNIVERSAL_IDENTIFIER,
      description: "仅供服务端使用、绑定客户工作区的审核 API Token",
      isSecret: true,
    },
    CRA_REVIEW_WORKSPACE_ID: {
      universalIdentifier: WORKSPACE_VARIABLE_UNIVERSAL_IDENTIFIER,
      description: "客户后台的实际工作区标识，无作者测试前缀限制",
      isSecret: true,
    },
    CRA_REVIEWER_MEMBER_IDS: {
      universalIdentifier: REVIEWERS_VARIABLE_UNIVERSAL_IDENTIFIER,
      description: "允许处理审核的 Twenty workspaceMemberId，逗号分隔；后台仍校验逐项权限",
      isSecret: true,
    },
  },
});
