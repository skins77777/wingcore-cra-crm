import { definePageLayout, PageLayoutTabLayoutMode } from "twenty-sdk/define";

import {
  APPROVAL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
  APPROVAL_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
  APPROVAL_PAGE_TAB_UNIVERSAL_IDENTIFIER,
  APPROVAL_PAGE_WIDGET_UNIVERSAL_IDENTIFIER,
} from "src/constants/universal-identifiers";

export default definePageLayout({
  universalIdentifier: APPROVAL_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
  name: "待审核",
  type: "STANDALONE_PAGE",
  tabs: [{
    universalIdentifier: APPROVAL_PAGE_TAB_UNIVERSAL_IDENTIFIER,
    title: "审批中心",
    position: 0,
    icon: "IconShieldCheck",
    layoutMode: PageLayoutTabLayoutMode.VERTICAL_LIST,
    widgets: [{
      universalIdentifier: APPROVAL_PAGE_WIDGET_UNIVERSAL_IDENTIFIER,
      title: " ",
      type: "FRONT_COMPONENT",
      configuration: {
        configurationType: "FRONT_COMPONENT",
        frontComponentUniversalIdentifier: APPROVAL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
      },
    }],
  }],
});
