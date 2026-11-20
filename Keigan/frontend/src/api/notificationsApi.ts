import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/api/httpClient";
import type { Identifier, IsoDateTimeString, Priority } from "@/api/types/common";

/* ── Types (doc 05 §10) ────────────────────────────────────────────── */
export type RecipientType = "person" | "teams_channel" | "distribution_list";
export type StakeholderRole = "sre" | "developer" | "manager" | "executive" | "business_owner" | "vendor_contact";
export type NotificationChannel = "email" | "teams_incident_chat" | "teams_channel";
export type NotificationType = "incident_detected" | "preliminary_report" | "progress_update" | "postmortem" | "intelligence_report" | "slo_burn_alert" | "alert_group";

export const notificationChannels: NotificationChannel[] = ["email", "teams_incident_chat", "teams_channel"];
export const notificationTypes: NotificationType[] = ["incident_detected", "preliminary_report", "progress_update", "postmortem", "intelligence_report", "slo_burn_alert", "alert_group"];
export const stakeholderRoles: StakeholderRole[] = ["sre", "developer", "manager", "executive", "business_owner", "vendor_contact"];

export interface Stakeholder {
  stakeholderId: Identifier;
  applicationId: Identifier;
  recipientType: RecipientType;
  displayName: string;
  emailAddress: string | null;
  userPrincipalName: string | null;
  entraObjectId: string | null;
  teamsTeamId: string | null;
  teamsChannelId: string | null;
  stakeholderRole: StakeholderRole;
  subscribedServiceIds: string[];
  notificationChannels: NotificationChannel[];
  minimumPriority: Priority;
  subscribedNotificationTypes: NotificationType[];
  preferredLanguageCode: string;
  isActive: boolean;
}
export type StakeholderBody = Partial<Omit<Stakeholder, "stakeholderId" | "applicationId">>;

export interface DirectoryUser {
  displayName: string;
  emailAddress: string | null;
  userPrincipalName: string | null;
  entraObjectId: string | null;
  jobTitle: string | null;
  source: string;
}
export interface StakeholderTestResult {
  deliveriesQueued: number;
  deliveryIds: string[];
  message: string;
}

export interface TeamsChatParticipant {
  displayName: string;
  userPrincipalName: string | null;
  role: "member" | "bot";
}
export interface TeamsChatMessage {
  messageId: Identifier;
  authorRole: "assistant" | "teams_participant" | "user" | "system_notice";
  authorDisplayName: string | null;
  authorUserPrincipalName: string | null;
  messageText: string;
  adaptiveCard: Record<string, unknown> | null;
  createdAt: IsoDateTimeString;
}
export interface TeamsChatFact {
  timelineEventId: Identifier;
  eventTitle: string;
  eventDetailsMarkdown: string | null;
  eventOccurredAt: IsoDateTimeString;
  actorDisplayName: string | null;
}
export interface TeamsChat {
  incidentId: Identifier;
  chatExists: boolean;
  isSimulated: boolean;
  chatTopic: string | null;
  chatWebUrl: string | null;
  chatStatus: string | null;
  participants: TeamsChatParticipant[];
  messages: TeamsChatMessage[];
  facts: TeamsChatFact[];
  canPost: boolean;
}

export const notificationQueryKeys = {
  stakeholders: (applicationId: string) => ["stakeholders", applicationId] as const,
  directory: (query: string) => ["directory-users", query] as const,
  teamsChat: (incidentId: string) => ["teams-chat", incidentId] as const,
};

/* ── Hooks ─────────────────────────────────────────────────────────── */
export const useStakeholders = (applicationId: string) =>
  useQuery({ queryKey: notificationQueryKeys.stakeholders(applicationId), queryFn: () => apiGet<Stakeholder[]>(`/applications/${applicationId}/stakeholders`) });

function useStakeholderMutation<Variables, Result>(applicationId: string, mutationFunction: (variables: Variables) => Promise<Result>) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: mutationFunction, onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationQueryKeys.stakeholders(applicationId) }) });
}
export const useCreateStakeholder = (applicationId: string) =>
  useStakeholderMutation(applicationId, (body: StakeholderBody) => apiPost<Stakeholder, StakeholderBody>(`/applications/${applicationId}/stakeholders`, body));
export const useUpdateStakeholder = (applicationId: string) =>
  useStakeholderMutation(applicationId, (variables: { stakeholderId: string; body: StakeholderBody }) =>
    apiPatch<Stakeholder, StakeholderBody>(`/applications/${applicationId}/stakeholders/${variables.stakeholderId}`, variables.body),
  );
export const useDeleteStakeholder = (applicationId: string) =>
  useStakeholderMutation(applicationId, (stakeholderId: string) => apiDelete(`/applications/${applicationId}/stakeholders/${stakeholderId}`));
export const useSendStakeholderTest = (applicationId: string) =>
  useMutation({ mutationFn: (stakeholderId: string) => apiPost<StakeholderTestResult>(`/applications/${applicationId}/stakeholders/${stakeholderId}/test`) });

export const useDirectorySearch = (query: string) =>
  useQuery({
    queryKey: notificationQueryKeys.directory(query),
    enabled: query.trim().length >= 2,
    queryFn: () => apiGet<DirectoryUser[]>("/directory/users/search", { query: { query } }),
    staleTime: 30_000,
  });

export const useTeamsChat = (incidentId: string) =>
  useQuery({ queryKey: notificationQueryKeys.teamsChat(incidentId), queryFn: () => apiGet<TeamsChat>(`/incidents/${incidentId}/teams-chat`), refetchInterval: 10_000 });
export const usePostTeamsChatMessage = (incidentId: string) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageText: string) => apiPost<TeamsChat, { messageText: string }>(`/incidents/${incidentId}/teams-chat/messages`, { messageText }),
    onSuccess: (chat) => queryClient.setQueryData(notificationQueryKeys.teamsChat(incidentId), chat),
  });
};
