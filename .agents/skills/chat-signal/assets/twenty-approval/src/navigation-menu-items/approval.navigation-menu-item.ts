import { defineNavigationMenuItem, NavigationMenuItemType } from "twenty-sdk/define";

import {
  APPROVAL_NAVIGATION_UNIVERSAL_IDENTIFIER,
  APPROVAL_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
} from "src/constants/universal-identifiers";

export default defineNavigationMenuItem({
  universalIdentifier: APPROVAL_NAVIGATION_UNIVERSAL_IDENTIFIER,
  name: "待审核",
  icon: "IconShieldCheck",
  color: "orange",
  position: 1,
  type: NavigationMenuItemType.PAGE_LAYOUT,
  pageLayoutUniversalIdentifier: APPROVAL_PAGE_LAYOUT_UNIVERSAL_IDENTIFIER,
});
