import { useMemo, useState } from "react";
import { ChevronDown, Mail, Pencil, Plus, Send, Trash2, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useServices } from "@/api/applicationsApi";
import {
  notificationChannels,
  notificationTypes,
  stakeholderRoles,
  useCreateStakeholder,
  useDeleteStakeholder,
  useDirectorySearch,
  useSendStakeholderTest,
  useSendTeamInvitation,
  useStakeholders,
  useUpdateStakeholder,
  type NotificationChannel,
  type NotificationType,
  type RecipientType,
  type Stakeholder,
  type StakeholderBody,
  type StakeholderRole,
  type TeamMemberStatus,
} from "@/api/notificationsApi";
import type { Priority } from "@/api/types/common";
import { isApiError } from "@/api/httpClient";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Checkbox } from "@/components/ui/Checkbox";
import { Combobox } from "@/components/ui/Combobox";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { DataTable, type DataTableColumn } from "@/components/ui/DataTable";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { IconButton } from "@/components/ui/IconButton";
import { Input } from "@/components/ui/Input";
import { Popover } from "@/components/ui/Popover";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { Select } from "@/components/ui/Select";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import { useToast } from "@/components/ui/Toast";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { useFeatureFlag } from "@/config/runtimeConfiguration";
import { isValidEmailAddress } from "@/utils/emailAddress";
import { formatTime } from "@/utils/formatters";
import { StepFrame } from "../components/StepFrame";
import type { StepProps } from "../stepRegistry";

interface StakeholderDraft {
  recipientType: RecipientType;
  displayName: string;
  emailAddress: string;
  userPrincipalName: string | null;
  entraObjectId: string | null;
  teamsTeamId: string;
  teamsChannelId: string;
  stakeholderRole: StakeholderRole;
  subscribedServiceIds: string[];
  notificationChannels: NotificationChannel[];
  minimumPriority: Priority;
  subscribedNotificationTypes: NotificationType[];
  preferredLanguageCode: string;
  /** Only used when adding a person: email them an invitation as they are saved. */
  sendInvitation: boolean;
}

const statusTones: Record<TeamMemberStatus, StatusTone> = { listed: "neutral", invited: "info", active: "success", inactive: "warning" };

const emptyDraft: StakeholderDraft = {
  recipientType: "person",
  displayName: "",
  emailAddress: "",
  userPrincipalName: null,
  entraObjectId: null,
  teamsTeamId: "",
  teamsChannelId: "",
  stakeholderRole: "sre",
  subscribedServiceIds: [],
  notificationChannels: ["email"],
  minimumPriority: "P2",
  subscribedNotificationTypes: ["incident_detected", "preliminary_report", "progress_update", "postmortem"],
  preferredLanguageCode: "en",
  sendInvitation: true,
};

function draftFromStakeholder(stakeholder: Stakeholder): StakeholderDraft {
  return {
    recipientType: stakeholder.recipientType,
    displayName: stakeholder.displayName,
    emailAddress: stakeholder.emailAddress ?? "",
    userPrincipalName: stakeholder.userPrincipalName,
    entraObjectId: stakeholder.entraObjectId,
    teamsTeamId: stakeholder.teamsTeamId ?? "",
    teamsChannelId: stakeholder.teamsChannelId ?? "",
    stakeholderRole: stakeholder.stakeholderRole,
    subscribedServiceIds: stakeholder.subscribedServiceIds,
    notificationChannels: stakeholder.notificationChannels,
    minimumPriority: stakeholder.minimumPriority,
    subscribedNotificationTypes: stakeholder.subscribedNotificationTypes,
    preferredLanguageCode: stakeholder.preferredLanguageCode,
    sendInvitation: false,
  };
}

/** Where a person stands (listed, invited, signed in, paused) and when; channels and lists have no sign-in, so they show a dash. */
function MemberStatusCell({ row }: { row: Stakeholder }) {
  const { t } = useTranslation("notifications");
  if (row.recipientType !== "person") return <span className="text-muted" aria-label={t("stakeholders.status.notApplicable")}>–</span>;
  return (
    <div className="flex flex-col items-start gap-0.5">
      <StatusChip size="sm" tone={row.invitationIsStale ? "warning" : statusTones[row.teamMemberStatus]} icon={false}>{t(`stakeholders.status.${row.teamMemberStatus}`)}</StatusChip>
      {row.teamMemberStatus === "invited" && row.invitedAt ? (
        <span className="text-caption text-muted">{row.invitationIsStale ? t("stakeholders.status.staleSince") : t("stakeholders.status.invitedAgo")} <RelativeTime value={row.invitedAt} /></span>
      ) : null}
      {row.teamMemberStatus === "active" && row.joinedAt ? <span className="text-caption text-muted">{t("stakeholders.status.signedInAgo")} <RelativeTime value={row.joinedAt} /></span> : null}
    </div>
  );
}

function toggled<Value>(values: Value[], value: Value, isChecked: boolean): Value[] {
  return isChecked ? (values.includes(value) ? values : [...values, value]) : values.filter((candidate) => candidate !== value);
}

/** Step 9: who is told about incidents, reports and SLO burn, in which channel, language and from which priority. */
export function NotificationsStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  const { t } = useTranslation("notifications");
  const { showToast } = useToast();
  const isEmailSimulated = useFeatureFlag("emailSimulated");
  const stakeholdersQuery = useStakeholders(applicationId);
  const servicesQuery = useServices(applicationId);
  const createStakeholder = useCreateStakeholder(applicationId);
  const updateStakeholder = useUpdateStakeholder(applicationId);
  const deleteStakeholder = useDeleteStakeholder(applicationId);
  const sendTest = useSendStakeholderTest(applicationId);
  const sendInvitation = useSendTeamInvitation(applicationId);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<StakeholderDraft>(emptyDraft);
  const [pendingDelete, setPendingDelete] = useState<Stakeholder | null>(null);
  const serviceNames = useMemo(() => new Map((servicesQuery.data ?? []).map((service) => [service.serviceId, service.serviceName])), [servicesQuery.data]);
  const stakeholders = stakeholdersQuery.data ?? [];

  const openEditor = (stakeholder?: Stakeholder) => {
    setEditingId(stakeholder?.stakeholderId ?? null);
    setDraft(stakeholder ? draftFromStakeholder(stakeholder) : emptyDraft);
    setEditorOpen(true);
  };
  const reportError = (title: string, error: unknown) => showToast({ tone: "danger", title, description: isApiError(error) ? error.detail ?? error.title : undefined });

  const saveDraft = () => {
    const body: StakeholderBody = {
      recipientType: draft.recipientType,
      displayName: draft.displayName.trim(),
      emailAddress: draft.emailAddress.trim() || null,
      userPrincipalName: draft.userPrincipalName ?? (draft.emailAddress.trim() || null),
      entraObjectId: draft.entraObjectId,
      teamsTeamId: draft.recipientType === "teams_channel" ? draft.teamsTeamId.trim() || null : null,
      teamsChannelId: draft.recipientType === "teams_channel" ? draft.teamsChannelId.trim() || null : null,
      stakeholderRole: draft.stakeholderRole,
      subscribedServiceIds: draft.subscribedServiceIds,
      notificationChannels: draft.notificationChannels,
      minimumPriority: draft.minimumPriority,
      subscribedNotificationTypes: draft.subscribedNotificationTypes,
      preferredLanguageCode: draft.preferredLanguageCode,
      ...(editingId ? {} : { sendInvitation: draft.recipientType === "person" && draft.sendInvitation }),
    };
    const onSuccess = () => {
      showToast({ tone: "success", title: t("stakeholders.saved") });
      setEditorOpen(false);
      onStatusChange?.();
    };
    const onError = (error: unknown) => reportError(t("stakeholders.saveFailed"), error);
    if (editingId) updateStakeholder.mutate({ stakeholderId: editingId, body }, { onSuccess, onError });
    else createStakeholder.mutate(body, { onSuccess, onError });
  };

  const columns: DataTableColumn<Stakeholder>[] = [
    {
      key: "name",
      header: t("stakeholders.columns.name"),
      isSortable: true,
      sortValue: (row) => row.displayName,
      cell: (row) => (
        <div className="flex flex-col">
          <span className="font-semibold">{row.displayName}</span>
          <span className="text-caption text-muted">{row.emailAddress ?? (row.teamsChannelId ? t("recipientTypes.teams_channel") : "")}</span>
        </div>
      ),
    },
    { key: "role", header: t("stakeholders.columns.role"), cell: (row) => t(`roles.${row.stakeholderRole}`) },
    { key: "status", header: t("stakeholders.columns.status"), cell: (row) => <MemberStatusCell row={row} /> },
    {
      key: "services",
      header: t("stakeholders.columns.services"),
      cell: (row) =>
        row.subscribedServiceIds.length === 0 ? (
          <StatusChip size="sm" tone="neutral" icon={false}>{t("stakeholders.allServices")}</StatusChip>
        ) : (
          <span title={row.subscribedServiceIds.map((serviceId) => serviceNames.get(serviceId) ?? serviceId).join(", ")}>{t("stakeholders.serviceCount", { count: row.subscribedServiceIds.length })}</span>
        ),
    },
    {
      key: "channels",
      header: t("stakeholders.columns.channels"),
      cell: (row) => (
        <div className="flex flex-wrap gap-1">
          {row.notificationChannels.map((channel) => (
            <StatusChip key={channel} size="sm" tone={channel === "email" ? "info" : "brand"} icon={false}>{t(`channels.${channel}`)}</StatusChip>
          ))}
        </div>
      ),
    },
    { key: "priority", header: t("stakeholders.columns.priority"), cell: (row) => row.minimumPriority },
    { key: "language", header: t("stakeholders.columns.language"), cell: (row) => t(`languages.${row.preferredLanguageCode.split("-")[0]}`, { defaultValue: row.preferredLanguageCode }) },
    {
      key: "actions",
      header: <span className="sr-only">{t("stakeholders.columns.actions")}</span>,
      align: "end",
      cell: (row) => (
        <div className="flex items-center justify-end gap-1">
          {canEdit ? (
            <>
              {row.recipientType === "person" && (row.teamMemberStatus === "listed" || row.teamMemberStatus === "invited") ? (
                <IconButton
                  icon={Mail}
                  label={
                    row.canSendInvitation
                      ? t(row.teamMemberStatus === "invited" ? "stakeholders.resendInvitation" : "stakeholders.invite")
                      : row.nextInvitationAllowedAt
                        ? t("stakeholders.inviteWaitUntil", { time: formatTime(row.nextInvitationAllowedAt) })
                        : t("stakeholders.inviteNeedsEmail")
                  }
                  variant="ghost"
                  size="sm"
                  disabled={!row.canSendInvitation || sendInvitation.isPending}
                  onClick={() =>
                    sendInvitation.mutate(row.stakeholderId, {
                      onSuccess: (result) => showToast({ tone: "success", title: t("stakeholders.inviteQueued"), description: result.message }),
                      onError: (error) => reportError(t("stakeholders.inviteFailed"), error),
                    })
                  }
                />
              ) : null}
              <IconButton
                icon={Send}
                label={t("stakeholders.sendTest")}
                variant="ghost"
                size="sm"
                disabled={sendTest.isPending}
                onClick={() =>
                  sendTest.mutate(row.stakeholderId, {
                    onSuccess: (result) => showToast({ tone: result.deliveriesQueued > 0 ? "success" : "warning", title: result.deliveriesQueued > 0 ? t("stakeholders.testQueued") : t("stakeholders.testNotSent"), description: result.message }),
                    onError: (error) => reportError(t("stakeholders.testNotSent"), error),
                  })
                }
              />
              <IconButton icon={Pencil} label={t("stakeholders.edit")} variant="ghost" size="sm" onClick={() => openEditor(row)} />
              <IconButton icon={Trash2} label={t("stakeholders.delete")} variant="ghost" size="sm" onClick={() => setPendingDelete(row)} />
            </>
          ) : null}
        </div>
      ),
    },
  ];

  const hasChatChannel = draft.notificationChannels.includes("teams_incident_chat");
  const isSaving = createStakeholder.isPending || updateStakeholder.isPending;
  const emailIsInvalid = draft.recipientType !== "teams_channel" && draft.emailAddress.trim().length > 0 && !isValidEmailAddress(draft.emailAddress);
  const isDraftValid = draft.displayName.trim().length > 0 && (draft.recipientType === "teams_channel" ? draft.teamsTeamId.trim() && draft.teamsChannelId.trim() : draft.emailAddress.trim().length > 0 && !emailIsInvalid);
  const saveError = editingId ? updateStakeholder.error : createStakeholder.error;
  const serverEmailError = isApiError(saveError) ? saveError.fieldErrorFor("emailAddress") : undefined;

  return (
    <StepFrame
      stepKey="notifications"
      actions={canEdit && !editorOpen ? <Button leadingIcon={UserPlus} onClick={() => openEditor()}>{t("stakeholders.addButton")}</Button> : undefined}
    >
      <Banner tone="info">{t("stakeholders.intro")}</Banner>
      <Banner tone="neutral">{t("stakeholders.accessNote")}</Banner>
      {isEmailSimulated ? <Banner tone="warning">{t("stakeholders.emailSimulated")}</Banner> : null}
      {!canEdit ? <Banner tone="neutral">{t("stakeholders.readOnly")}</Banner> : null}

      {editorOpen ? (
        <Card>
          <CardHeader title={editingId ? t("stakeholders.edit") : t("stakeholders.addTitle")} icon={Plus} />
          <CardBody>
            <StakeholderEditor
              draft={draft}
              onChange={setDraft}
              services={(servicesQuery.data ?? []).map((service) => ({ id: service.serviceId, name: service.serviceName }))}
              hasChatChannel={hasChatChannel}
              isNew={editingId === null}
              emailError={serverEmailError ?? (emailIsInvalid ? t("stakeholders.emailInvalid") : undefined)}
            />
            <div className="mt-6 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditorOpen(false)}>{t("stakeholders.cancel")}</Button>
              <Button isLoading={isSaving} disabled={!isDraftValid} onClick={saveDraft}>{t("stakeholders.save")}</Button>
            </div>
          </CardBody>
        </Card>
      ) : null}

      {stakeholdersQuery.isError ? <ErrorState error={stakeholdersQuery.error} onRetry={() => stakeholdersQuery.refetch()} /> : null}
      {stakeholdersQuery.isSuccess && stakeholders.length === 0 && !editorOpen ? (
        <EmptyState
          isBordered
          icon={UserPlus}
          title={t("stakeholders.emptyTitle")}
          description={t("stakeholders.emptyDescription")}
          action={canEdit ? <Button leadingIcon={UserPlus} onClick={() => openEditor()}>{t("stakeholders.addButton")}</Button> : undefined}
        />
      ) : null}
      {stakeholdersQuery.isLoading || stakeholders.length > 0 ? (
        <DataTable columns={columns} rows={stakeholders} getRowId={(row) => row.stakeholderId} caption={t("stakeholders.tableCaption")} isLoading={stakeholdersQuery.isLoading} defaultSort={{ columnKey: "name", direction: "ascending" }} />
      ) : null}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(isOpen) => !isOpen && setPendingDelete(null)}
        title={t("stakeholders.deleteTitle")}
        description={t("stakeholders.deleteDescription", { name: pendingDelete?.displayName ?? "" })}
        confirmLabel={t("stakeholders.delete")}
        tone="danger"
        onConfirm={() => {
          if (!pendingDelete) return;
          deleteStakeholder.mutate(pendingDelete.stakeholderId, {
            onSuccess: () => {
              showToast({ tone: "success", title: t("stakeholders.removed") });
              setPendingDelete(null);
              onStatusChange?.();
            },
            onError: (error) => reportError(t("stakeholders.saveFailed"), error),
          });
        }}
      />
    </StepFrame>
  );
}

function StakeholderEditor({
  draft,
  onChange,
  services,
  hasChatChannel,
  isNew,
  emailError,
}: {
  draft: StakeholderDraft;
  onChange: (draft: StakeholderDraft) => void;
  services: Array<{ id: string; name: string }>;
  hasChatChannel: boolean;
  isNew: boolean;
  emailError: string | undefined;
}) {
  const { t } = useTranslation("notifications");
  const [searchText, setSearchText] = useState("");
  const debouncedSearch = useDebouncedValue(searchText, 250);
  const directoryQuery = useDirectorySearch(debouncedSearch);
  const directoryUsers = directoryQuery.data ?? [];
  const patch = (changes: Partial<StakeholderDraft>) => onChange({ ...draft, ...changes });
  const serviceSummary = draft.subscribedServiceIds.length === 0 ? t("stakeholders.allServices") : t("stakeholders.serviceCount", { count: draft.subscribedServiceIds.length });

  return (
    <div className="grid gap-5 md:grid-cols-2">
      {draft.recipientType === "person" ? (
        <div className="md:col-span-2">
          <Combobox
            label={t("stakeholders.searchLabel")}
            helperText={t("stakeholders.searchHelper")}
            placeholder={t("stakeholders.searchPlaceholder")}
            searchPlaceholder={t("stakeholders.searchPlaceholder")}
            emptyText={t("stakeholders.searchEmpty")}
            value={null}
            isLoading={directoryQuery.isFetching}
            onSearchChange={setSearchText}
            options={directoryUsers.map((user) => ({ value: user.userPrincipalName ?? user.emailAddress ?? user.displayName, label: user.displayName, description: user.emailAddress ?? user.jobTitle ?? undefined }))}
            onValueChange={(value) => {
              const picked = directoryUsers.find((user) => (user.userPrincipalName ?? user.emailAddress ?? user.displayName) === value);
              if (picked) patch({ displayName: picked.displayName, emailAddress: picked.emailAddress ?? "", userPrincipalName: picked.userPrincipalName, entraObjectId: picked.entraObjectId });
            }}
          />
        </div>
      ) : null}
      <Select<RecipientType>
        label={t("stakeholders.recipientType")}
        value={draft.recipientType}
        onValueChange={(recipientType) => patch({ recipientType, notificationChannels: recipientType === "teams_channel" ? ["teams_channel"] : draft.notificationChannels.filter((channel) => channel !== "teams_channel") })}
        options={(["person", "distribution_list", "teams_channel"] as RecipientType[]).map((value) => ({ value, label: t(`recipientTypes.${value}`) }))}
      />
      <Input label={t("stakeholders.displayName")} value={draft.displayName} onChange={(event) => patch({ displayName: event.target.value })} />
      {draft.recipientType === "teams_channel" ? (
        <>
          <Input label={t("stakeholders.teamsTeamId")} value={draft.teamsTeamId} onChange={(event) => patch({ teamsTeamId: event.target.value })} />
          <Input label={t("stakeholders.teamsChannelId")} value={draft.teamsChannelId} onChange={(event) => patch({ teamsChannelId: event.target.value })} />
        </>
      ) : (
        <Input label={t("stakeholders.emailAddress")} type="email" value={draft.emailAddress} onChange={(event) => patch({ emailAddress: event.target.value })} errorMessage={emailError} />
      )}
      <Select<StakeholderRole>
        label={t("stakeholders.role")}
        value={draft.stakeholderRole}
        onValueChange={(stakeholderRole) => patch({ stakeholderRole })}
        options={stakeholderRoles.map((value) => ({ value, label: t(`roles.${value}`) }))}
      />
      {isNew && draft.recipientType === "person" ? (
        <Checkbox
          className="md:col-span-2"
          label={t("stakeholders.sendInvitation")}
          description={t("stakeholders.sendInvitationHelp")}
          checked={draft.sendInvitation}
          onCheckedChange={(checked) => patch({ sendInvitation: checked === true })}
        />
      ) : null}
      <Select<string>
        label={t("stakeholders.language")}
        value={draft.preferredLanguageCode.split("-")[0]}
        onValueChange={(preferredLanguageCode) => patch({ preferredLanguageCode })}
        options={[{ value: "en", label: t("languages.en") }, { value: "ja", label: t("languages.ja") }]}
      />
      <Select<Priority>
        label={t("stakeholders.minimumPriority")}
        helperText={t("stakeholders.minimumPriorityHelper")}
        value={draft.minimumPriority}
        onValueChange={(minimumPriority) => patch({ minimumPriority })}
        options={(["P1", "P2", "P3", "P4"] as Priority[]).map((value) => ({ value, label: t(`priorities.${value}`) }))}
      />
      <div className="flex flex-col gap-1.5">
        <span className="text-body-sm font-semibold">{t("stakeholders.services")}</span>
        <Popover
          width="md"
          align="start"
          trigger={<Button variant="secondary" trailingIcon={ChevronDown} className="justify-between">{serviceSummary}</Button>}
        >
          <div className="flex max-h-64 flex-col gap-2 overflow-y-auto">
            <p className="text-caption text-muted">{t("stakeholders.serviceHint")}</p>
            {services.length === 0 ? <p className="text-body-sm">{t("stakeholders.noServices")}</p> : null}
            {services.map((service) => (
              <Checkbox
                key={service.id}
                label={service.name}
                checked={draft.subscribedServiceIds.includes(service.id)}
                onCheckedChange={(checked) => patch({ subscribedServiceIds: toggled(draft.subscribedServiceIds, service.id, checked === true) })}
              />
            ))}
          </div>
        </Popover>
      </div>
      <fieldset className="flex flex-col gap-2 md:col-span-1">
        <legend className="mb-1 text-body-sm font-semibold">{t("stakeholders.channels")}</legend>
        {notificationChannels
          .filter((channel) => (draft.recipientType === "teams_channel" ? channel === "teams_channel" : channel !== "teams_channel"))
          .map((channel) => (
            <Checkbox
              key={channel}
              label={t(`channels.${channel}`)}
              description={t(`channels.${channel}Help`)}
              checked={draft.notificationChannels.includes(channel)}
              onCheckedChange={(checked) => patch({ notificationChannels: toggled(draft.notificationChannels, channel, checked === true) })}
            />
          ))}
      </fieldset>
      <fieldset className="flex flex-col gap-2 md:col-span-1">
        <legend className="mb-1 text-body-sm font-semibold">{t("stakeholders.notificationTypes")}</legend>
        {notificationTypes.map((type) => (
          <Checkbox
            key={type}
            label={t(`types.${type}`)}
            description={type === "incident_detected" && hasChatChannel ? `${t("types.incident_detectedHelp")} ${t("channels.teams_incident_chatHelp")}` : t(`types.${type}Help`)}
            checked={draft.subscribedNotificationTypes.includes(type)}
            onCheckedChange={(checked) => patch({ subscribedNotificationTypes: toggled(draft.subscribedNotificationTypes, type, checked === true) })}
          />
        ))}
      </fieldset>
    </div>
  );
}
