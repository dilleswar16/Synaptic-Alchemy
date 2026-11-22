import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/api/httpClient";
import type { Identifier, IsoDateTimeString } from "@/api/types/common";

/* ── Types (doc 05 §7) ─────────────────────────────────────────────── */
/** The kinds of answer the old chat router stored (history before Ask Keigan); answers of Ask Keigan carry a run instead (`answerRunId`). */
export type ChatAnswerKind ="text" | "number" | "chart" | "table" | "clarification";
export type ChartType = "line" | "area" | "bar" | "stacked_bar" | "pie" | "table";

export interface ChartSeriesSpecification {
  field: string;
  label: string;
  colorToken?: string;
}

export interface ChartSpecification {
  chartType: ChartType;
  title: string;
  xField: string;
  xFieldKind: "time" | "category";
  series: ChartSeriesSpecification[];
  unit?: string;
  rows: Array<Record<string, string | number | null>>;
}

export interface ChatQueryDetails {
  serviceName: string;
  sourceKind: string;
  queryLanguage: string;
  queryText: string;
  timeRange?: { start: IsoDateTimeString; end: IsoDateTimeString };
  rowCount: number;
  isSimulated?: boolean;
}

export interface ChatCitation {
  kind: string;
  title: string;
  reference: string;
}

export interface ChatMessagePayload {
  answerKind: ChatAnswerKind;
  numberValue?: number;
  chartSpecification?: ChartSpecification;
  tableRows?: Array<Record<string, unknown>>;
  queryDetails?: ChatQueryDetails;
  citations?: ChatCitation[];
  failed?: boolean;
  /** Set on the answers of Ask Keigan and on their questions (spec 7.1): the stored run with the steps behind the answer. */
  answerRunId?: Identifier;
}

export interface ChatMessage {
  messageId: Identifier;
  conversationId: Identifier;
  authorRole: "user" | "assistant";
  authorDisplayName: string | null;
  messageText: string;
  messagePayload: ChatMessagePayload | null;
  createdAt: IsoDateTimeString;
}

export interface Conversation {
  conversationId: Identifier;
  conversationScope: "keigan_ai_chat" | "investigation";
  applicationIds: Identifier[];
  investigationId: Identifier | null;
  conversationTitle: string;
  messageCount: number;
  createdAt: IsoDateTimeString;
  updatedAt: IsoDateTimeString;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}

export interface SuggestedPrompt {
  promptText: string;
  category: "data" | "knowledge";
}

export const chatQueryKeys = {
  conversations: ["chat", "conversations"] as const,
  conversation: (conversationId: string) => ["chat", "conversation", conversationId] as const,
  suggestedPrompts: (applicationId: string | null) => ["chat", "suggested-prompts", applicationId] as const,
  investigationConversation: (investigationId: string) => ["chat", "investigation-conversation", investigationId] as const,
};

/* ── Hooks ─────────────────────────────────────────────────────────── */
export function useConversations() {
  return useQuery({ queryKey: chatQueryKeys.conversations, queryFn: () => apiGet<Conversation[]>("/chat/conversations", { query: { scope: "keigan_ai_chat" } }) });
}

export function useConversation(conversationId: string | undefined) {
  return useQuery({
    queryKey: chatQueryKeys.conversation(conversationId ?? ""),
    queryFn: () => apiGet<ConversationDetail>(`/chat/conversations/${conversationId}`),
    enabled: Boolean(conversationId),
  });
}

export function useSuggestedPrompts(applicationId: string | null) {
  return useQuery({ queryKey: chatQueryKeys.suggestedPrompts(applicationId), queryFn: () => apiGet<SuggestedPrompt[]>("/chat/suggested-prompts", { query: { applicationId: applicationId ?? undefined } }), staleTime: 5 * 60_000 });
}

export function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (applicationIds: string[]) => apiPost<ConversationDetail, { conversationScope: string; applicationIds: string[] }>("/chat/conversations", { conversationScope: "keigan_ai_chat", applicationIds }),
    onSuccess: (created) => {
      // The new conversation is already what the server would send when asked for it: the screen that opens it does not ask again (and cannot catch the first question half stored).
      queryClient.setQueryData(chatQueryKeys.conversation(created.conversationId), created);
      void queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversations });
    },
  });
}

export function useRenameConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ conversationId, conversationTitle }: { conversationId: string; conversationTitle: string }) => apiPatch<Conversation, { conversationTitle: string }>(`/chat/conversations/${conversationId}`, { conversationTitle }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversations }),
  });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => apiDelete<void>(`/chat/conversations/${conversationId}`),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: chatQueryKeys.conversations }),
  });
}

/** The conversation of one investigation; the server returns the existing one, so asking again after a reload finds the earlier exchange. */
export function useInvestigationConversation(investigationId: string, enabled: boolean) {
  return useQuery({
    queryKey: chatQueryKeys.investigationConversation(investigationId),
    queryFn: () => apiPost<ConversationDetail, { conversationScope: "investigation"; investigationId: string }>("/chat/conversations", { conversationScope: "investigation", investigationId }),
    enabled,
    staleTime: Infinity,
  });
}
