import { defineCommandMenuItem, STANDARD_OBJECT } from "twenty-sdk/define";
import {
  QUOTE_ENTRY_COMMAND_UNIVERSAL_IDENTIFIER,
  QUOTE_ENTRY_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
} from "src/constants/universal-identifiers";

export default defineCommandMenuItem({
  universalIdentifier: QUOTE_ENTRY_COMMAND_UNIVERSAL_IDENTIFIER,
  label: "登记报价事实",
  shortLabel: "登记报价",
  availabilityObjectUniversalIdentifier: STANDARD_OBJECT.opportunity.universalIdentifier,
  frontComponentUniversalIdentifier: QUOTE_ENTRY_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
});
