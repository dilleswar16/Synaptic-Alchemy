import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/api/httpClient";
import type { Identifier, IsoDateTimeString, PagedResult } from "@/api/types/common";
import { incidentQueryKeys } from "./incidentsApi";

/* ── Types (spec 29, 4.5) ──────────────────────────────────────────── */
export type ActionItemStatus = "proposed" | "open" | "in_progress" | "blocked" | "done" | "wont_do";
export type ActionItemType = "prevent" | "detect" | "mitigate";
export type ActionItemPriority = "top" | "high" | "normal" | "low";

export const actionItemStatuses: ActionItemStatus[] = ["proposed", "open", "in_progress", "blocked", "done", "wont_do"];
export const actionItemTypes: ActionItemType[] = ["prevent", "detect", "mitigate"];
export const actionItemPriorities: ActionItemPriority[] = ["top", "high", "normal", "low"];

export interface ActionItemOwner {
  stakeholderId: Identifier;
  displayName: string;
  stakeholderRole: string;
}

export interface ActionItem {
  actionItemId: Identifier;
  applicationId: Identifier;
  applicationName: string;
  incidentId: Identifier | null;
  incidentReference: string | null;
  postmortemId: Identifier | null;
  sourceKind: string;
  itemTitle: string;
  itemDetailsMarkdown: string | null;
  actionType: ActionItemType;
  actionPriority: ActionItemPriority;
  itemStatus: ActionItemStatus;
  suggestedOwnerRoleText: string | null;
  owner: ActionItemOwner | null;
  /** A calendar date (YYYY-MM-DD) in the application's time zone. */
  dueOn: string | null;
  originalDueOn: string | null;
  dueOnChangeCount: number;
  isOverdue: boolean;
  daysOverdue: number;
  statusReasonText: string | null;
  completionNoteText: string | null;
  completedAt: IsoDateTimeString | null;
  completedBy: string | null;
  acceptedAt: IsoDateTimeString | null;
  externalReferenceText: string | null;
  /** What the caller may do, worked out by the server so the screen never offers a refused action. */
  canEdit: boolean;
  canChangeStatus: boolean;
  allowedStatuses: ActionItemStatus[];
  createdAt: IsoDateTimeString;
  updatedAt: IsoDateTimeString;
}

export interface ActionItemFilters {
  applicationIds: string[];
  statuses: ActionItemStatus[];
  owner: "me" | "unassigned" | null;
  overdueOnly: boolean;
  page: number;
}

export interface ActionItemFields {
  itemTitle?: string;
  itemDetailsMarkdown?: string | null;
  actionType?: ActionItemType;
  actionPriority?: ActionItemPriority;
  ownerStakeholderId?: Identifier | null;
  dueOn?: string;
  externalReferenceText?: string | null;
}

export interface ActionItemCreateBody extends ActionItemFields {
  itemTitle: string;
  actionType: ActionItemType;
  dueOn: string;
  incidentId?: Identifier;
  postmortemId?: Identifier;
}

export interface ActionItemStatusBody {
  status: ActionItemStatus;
  reasonText?: string;
  completionNoteText?: string;
}

export const actionItemQueryKeys = {
  all: ["action-items"] as const,
  list: (filters: ActionItemFilters) => ["action-items", "list", filters] as const,
  forPostmortem: (postmortemId: string) => ["action-items", "postmortem", postmortemId] as const,
};

/* ── Hooks ─────────────────────────────────────────────────────────── */
const pageSize = 50;

export const useActionItems = (filters: ActionItemFilters) =>
  useQuery({
    queryKey: actionItemQueryKeys.list(filters),
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) =>
      apiGet<PagedResult<ActionItem>>("/action-items", {
        signal,
        query: {
          applicationIds: filters.applicationIds.join(",") || undefined,
          statuses: filters.statuses.join(",") || undefined,
          owner: filters.owner ?? undefined,
          overdueOnly: filters.overdueOnly || undefined,
          page: filters.page,
          pageSize,
        },
      }),
  });

export const usePostmortemActionItems = (postmortemId: string | undefined) =>
  useQuery({
    queryKey: actionItemQueryKeys.forPostmortem(postmortemId ?? ""),
    enabled: Boolean(postmortemId),
    queryFn: ({ signal }) => apiGet<ActionItem[]>(`/postmortems/${postmortemId}/action-items`, { signal }),
  });

/** Every change refetches the lists and the postmortem (finalising renders the table from the rows). */
function useActionItemMutation<Variables, Result>(mutationFunction: (variables: Variables) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: mutationFunction,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: actionItemQueryKeys.all });
      await queryClient.invalidateQueries({ queryKey: incidentQueryKeys.all });
    },
  });
}

export const useCreateActionItem = () =>
  useActionItemMutation((variables: { applicationId: string; body: ActionItemCreateBody }) => apiPost<ActionItem, ActionItemCreateBody>(`/applications/${variables.applicationId}/action-items`, variables.body));
export const useUpdateActionItem = () =>
  useActionItemMutation((variables: { actionItemId: string; body: ActionItemFields }) => apiPatch<ActionItem, ActionItemFields>(`/action-items/${variables.actionItemId}`, variables.body));
export const useAcceptActionItem = () =>
  useActionItemMutation((variables: { actionItemId: string; body?: ActionItemFields }) => apiPost<ActionItem, ActionItemFields | undefined>(`/action-items/${variables.actionItemId}/accept`, variables.body));
export const useChangeActionItemStatus = () =>
  useActionItemMutation((variables: { actionItemId: string; body: ActionItemStatusBody }) => apiPost<ActionItem, ActionItemStatusBody>(`/action-items/${variables.actionItemId}/status`, variables.body));
export const useDiscardActionItem = () => useActionItemMutation((actionItemId: string) => apiDelete(`/action-items/${actionItemId}`));

/* ── Overview (spec 29, 4.4): counts per application, never a ranking of people ──────────── */
export type AttentionKind = "overdue_item" | "top_priority_unowned" | "policy_breach_open" | "postmortem_missing" | "proposed_waiting";
export type RepeatOutcome = "no_postmortem" | "no_prevent_item" | "repeated_while_open" | "repeated_after_done";
export type PreventItemStateAtRepeat = "done" | "not_done" | "wont_do";

export interface CompletionFigures {
  acceptedCount: number;
  doneCount: number;
  wontDoCount: number;
  openCount: number;
  overdueCount: number;
  /** Percent, or null while there is nothing to divide. */
  completionRate: number | null;
  completionRateSampleCount: number;
  medianDaysToComplete: number | null;
  medianSampleCount: number;
  onTimeShare: number | null;
  onTimeSampleCount: number;
}

export interface ApplicationCompletion extends CompletionFigures {
  applicationId: Identifier;
  applicationName: string;
}

export interface AttentionEntry {
  kind: AttentionKind;
  applicationId: Identifier;
  applicationName: string;
  recordKind: string;
  recordId: Identifier;
  title: string;
  /** Per kind: daysOverdue, priority, breachKind, sharePercent, incidentPriority, proposedCount, daysWaiting, incidentId, incidentReference. */
  parameters: Record<string, string | number | null>;
}

export interface EarlierPreventItem {
  actionItemId: Identifier;
  itemTitle: string;
  statusAtRepeat: PreventItemStateAtRepeat;
}

export interface RepeatIncident {
  incidentId: Identifier;
  incidentReference: string;
  openedAt: IsoDateTimeString;
  /** Absent for the first incident of the group. */
  outcome: RepeatOutcome | null;
  earlierPreventItems: EarlierPreventItem[];
}

export interface RepeatGroup {
  applicationId: Identifier;
  applicationName: string;
  recurrenceCategory: string;
  serviceId: Identifier;
  serviceName: string;
  incidents: RepeatIncident[];
}

export interface ActionItemOverview {
  periodStart: IsoDateTimeString;
  periodEnd: IsoDateTimeString;
  periodDays: number;
  completion: CompletionFigures;
  byApplication: ApplicationCompletion[];
  needsAttention: AttentionEntry[];
  repeats: RepeatGroup[];
}

export const useActionItemsOverview = (applicationIds: string[], days: number) =>
  useQuery({
    queryKey: [...actionItemQueryKeys.all, "overview", applicationIds, days] as const,
    placeholderData: keepPreviousData,
    queryFn: ({ signal }) => apiGet<ActionItemOverview>("/action-items/overview", { signal, query: { applicationIds: applicationIds.join(",") || undefined, days } }),
  });
