import { useTranslation } from "react-i18next";
import { useSuggestedPrompts, type SuggestedPrompt } from "@/api/chatApi";
import { useApplicationScope } from "@/auth/applicationScope";

/** The questions offered in an empty chat when no single application is in scope: one for each kind of question the tools answer (spec 8.5). */
const genericPromptKeys = [["slos", "data"], ["incidents", "data"], ["changes", "data"], ["failedRequests", "data"], ["signals", "data"], ["runbook", "knowledge"]] as const;

/**
 * The six suggested questions of the empty chat. With one application in scope the server writes them about it (its name, one of its services); otherwise
 * they are generic and translated here, never about an arbitrary application.
 */
export function useChatPrompts(): SuggestedPrompt[] {
  const { t } = useTranslation("chat");
  const scope = useApplicationScope();
  const scopedApplicationId = scope.applicationIds.length === 1 ? (scope.applicationIds[0] ?? null) : null;
  const serverPrompts = useSuggestedPrompts(scopedApplicationId);
  return scopedApplicationId ? (serverPrompts.data ?? []) : genericPromptKeys.map(([promptKey, category]) => ({ promptText: t(`empty.generic.${promptKey}`), category }));
}
