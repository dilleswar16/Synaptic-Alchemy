import { useRef, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { isApiError } from "@/api/httpClient";
import { useCreateApplication, type Application, type CriticalityTier } from "@/api/applicationsApi";
import { stakeholderRoles, type StakeholderRole } from "@/api/notificationsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { CopyButton } from "@/components/ui/CopyButton";
import { Dialog } from "@/components/ui/Dialog";
import { IconButton } from "@/components/ui/IconButton";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { isValidEmailAddress } from "@/utils/emailAddress";

const regionOptions = ["JP", "AU", "US", "NL", "FR", "ES", "MX", "CN"];
const defaultLocaleByRegion: Record<string, string> = { JP: "ja", CN: "zh-CN", ES: "es", MX: "es-MX", NL: "nl", FR: "fr" };
const localeOptions = ["en", "ja", "zh-CN", "es", "es-MX", "nl", "fr"];

interface TeamRow {
  rowId: number;
  displayName: string;
  emailAddress: string;
  stakeholderRole: StakeholderRole;
}

const isBlankRow = (row: TeamRow) => row.displayName.trim() === "" && row.emailAddress.trim() === "";

interface CreateApplicationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Keigan admins onboard directly; everyone else files a request that Keigan admins accept. */
  isRequest: boolean;
}

/** Spec 6.1: name, code (2 to 10 upper-case letters or digits), business unit, region, locale, tier, description. Shows the two AD groups afterwards. */
export function CreateApplicationDialog({ open, onOpenChange, isRequest }: CreateApplicationDialogProps) {
  const { t } = useTranslation("applications");
  const navigate = useNavigate();
  const createApplication = useCreateApplication();
  const [created, setCreated] = useState<Application | null>(null);
  const { t: tNotifications } = useTranslation("notifications");
  const [team, setTeam] = useState<TeamRow[]>([]);
  const [submittedTeamCount, setSubmittedTeamCount] = useState(0);
  const nextRowId = useRef(1);
  const [form, setForm] = useState({ applicationName: "", applicationCode: "", businessUnitName: "", regionCode: "", primaryLocale: "en", criticalityTier: "tier_2" as CriticalityTier, applicationDescription: "" });
  const update = (changes: Partial<typeof form>) => setForm((previous) => ({ ...previous, ...changes }));
  const codeIsValid = /^[A-Z0-9]{2,10}$/.test(form.applicationCode);
  const filledRows = team.filter((row) => !isBlankRow(row));
  const addressCounts = new Map<string, number>();
  filledRows.forEach((row) => addressCounts.set(row.emailAddress.trim().toLowerCase(), (addressCounts.get(row.emailAddress.trim().toLowerCase()) ?? 0) + 1));
  /** The message beside a row's email field: invalid, listed twice, or the server's own (for example "already on this team"). */
  const rowEmailError = (row: TeamRow) => {
    const typedAddress = row.emailAddress.trim();
    if (typedAddress === "") return isBlankRow(row) ? undefined : t("create.team.emailRequired");
    if (!isValidEmailAddress(typedAddress)) return t("create.team.emailInvalid");
    if ((addressCounts.get(typedAddress.toLowerCase()) ?? 0) > 1) return t("create.team.emailDuplicate");
    return undefined;
  };
  const rowNameError = (row: TeamRow) => (row.displayName.trim() === "" && !isBlankRow(row) ? t("create.team.nameRequired") : undefined);
  const teamIsValid = filledRows.every((row) => rowNameError(row) === undefined && rowEmailError(row) === undefined);
  const canSubmit = form.applicationName.trim().length >= 2 && codeIsValid && teamIsValid;
  const addRow = () => {
    const defaultRole: StakeholderRole = team.length === 0 ? "lead" : "developer"; // the first person entered is usually the team lead
    setTeam((previous) => [...previous, { rowId: nextRowId.current++, displayName: "", emailAddress: "", stakeholderRole: defaultRole }]);
  };
  const updateRow = (rowId: number, changes: Partial<TeamRow>) => setTeam((previous) => previous.map((row) => (row.rowId === rowId ? { ...row, ...changes } : row)));
  const fieldError = (field: string) => (isApiError(createApplication.error) ? createApplication.error.fieldErrorFor(field) : undefined);

  const close = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen) {
      setCreated(null);
      setTeam([]);
      createApplication.reset();
    }
  };

  const submit = () =>
    createApplication.mutate(
      {
        ...form,
        applicationDescription: form.applicationDescription || undefined,
        businessUnitName: form.businessUnitName || undefined,
        regionCode: form.regionCode || undefined,
        teamMembers: filledRows.map((row) => ({ displayName: row.displayName.trim(), emailAddress: row.emailAddress.trim(), stakeholderRole: row.stakeholderRole })),
      },
      { onSuccess: (application) => { setSubmittedTeamCount(filledRows.length); setCreated(application); } },
    );

  if (created) {
    return (
      <Dialog
        open={open}
        onOpenChange={close}
        title={isRequest ? t("create.requestedTitle") : t("create.createdTitle", { name: created.applicationName })}
        description={t("create.groupsIntro")}
        footer={
          <>
            <Button variant="secondary" onClick={() => close(false)}>{t("create.close")}</Button>
            {!isRequest ? <Button onClick={() => navigate(`/applications/${created.applicationId}/components`)}>{t("create.openWorkspace")}</Button> : null}
          </>
        }
      >
        <div className="flex flex-col gap-3">
          {[created.adminGroupName, created.readerGroupName].map((groupName, index) => (
            <div key={groupName} className="flex items-center justify-between gap-3 rounded-lg border border-hairline bg-sunken px-4 py-3">
              <div className="min-w-0">
                <div className="text-caption text-muted">{index === 0 ? t("create.adminGroup") : t("create.readerGroup")}</div>
                <div className="truncate font-mono text-body-sm">{groupName}</div>
              </div>
              <CopyButton value={groupName} label={t("create.copyGroup")} />
            </div>
          ))}
          <p className="text-body-sm text-muted">{t("create.sailpointHint")}</p>
          {submittedTeamCount > 0 ? <Banner tone="info">{t(isRequest ? "create.team.addedListedOnly" : "create.team.addedInvited", { count: submittedTeamCount })}</Banner> : null}
        </div>
      </Dialog>
    );
  }

  return (
    <Dialog
      open={open}
      onOpenChange={close}
      size="lg"
      title={isRequest ? t("create.requestTitle") : t("create.title")}
      description={isRequest ? t("create.requestDescription") : t("create.description")}
      footer={
        <>
          <Button variant="secondary" onClick={() => close(false)}>{t("create.cancel")}</Button>
          <Button onClick={submit} disabled={!canSubmit} isLoading={createApplication.isPending}>{isRequest ? t("create.requestSubmit") : t("create.submit")}</Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Input label={t("create.name")} value={form.applicationName} onChange={(event) => update({ applicationName: event.target.value })} errorMessage={fieldError("applicationName")} />
        <Input
          label={t("create.code")}
          helperText={t("create.codeHelp")}
          value={form.applicationCode}
          maxLength={10}
          onChange={(event) => update({ applicationCode: event.target.value.toUpperCase() })}
          errorMessage={fieldError("applicationCode") ?? (form.applicationCode && !codeIsValid ? t("create.codeInvalid") : undefined)}
        />
        <Input label={t("create.businessUnit")} isOptional value={form.businessUnitName} onChange={(event) => update({ businessUnitName: event.target.value })} />
        <Select
          label={t("create.region")}
          isOptional
          value={form.regionCode || undefined}
          options={regionOptions.map((region) => ({ value: region, label: t(`regions.${region}`) }))}
          onValueChange={(region) => update({ regionCode: region, primaryLocale: defaultLocaleByRegion[region] ?? "en" })}
        />
        <Select label={t("create.locale")} value={form.primaryLocale} options={localeOptions.map((locale) => ({ value: locale, label: t(`locales.${locale}`) }))} onValueChange={(locale) => update({ primaryLocale: locale })} />
        <Select
          label={t("create.tier")}
          value={form.criticalityTier}
          options={(["tier_1", "tier_2", "tier_3"] as const).map((tier) => ({ value: tier, label: t(`tiers.${tier}`) }))}
          onValueChange={(tier) => update({ criticalityTier: tier })}
        />
        <Textarea className="sm:col-span-2" containerClassName="sm:col-span-2" label={t("create.descriptionLabel")} isOptional rows={3} value={form.applicationDescription} onChange={(event) => update({ applicationDescription: event.target.value })} />
      </div>
      <section className="mt-6 flex flex-col gap-3 border-t border-hairline pt-5" aria-labelledby="create-team-heading">
        <div>
          <h3 id="create-team-heading" className="text-body font-semibold">{t("create.team.title")}</h3>
          <p className="text-body-sm text-muted">{t(isRequest ? "create.team.descriptionRequest" : "create.team.description")}</p>
        </div>
        {team.map((row, rowIndex) => (
          <div key={row.rowId} className="grid items-start gap-3 sm:grid-cols-[1fr_1fr_11rem_auto]" role="group" aria-label={t("create.team.rowLabel", { number: rowIndex + 1 })}>
            <Input label={t("create.team.name")} value={row.displayName} onChange={(event) => updateRow(row.rowId, { displayName: event.target.value })} errorMessage={rowNameError(row)} />
            <Input
              label={t("create.team.email")}
              type="email"
              value={row.emailAddress}
              onChange={(event) => updateRow(row.rowId, { emailAddress: event.target.value })}
              errorMessage={rowEmailError(row)}
            />
            <Select label={t("create.team.role")} value={row.stakeholderRole} options={stakeholderRoles.map((role) => ({ value: role, label: tNotifications(`roles.${role}`) }))} onValueChange={(role) => updateRow(row.rowId, { stakeholderRole: role })} />
            <IconButton icon={Trash2} label={t("create.team.remove", { number: rowIndex + 1 })} variant="ghost" className="sm:mt-7" onClick={() => setTeam((previous) => previous.filter((candidate) => candidate.rowId !== row.rowId))} />
          </div>
        ))}
        <Button variant="secondary" size="sm" leadingIcon={Plus} className="self-start" onClick={addRow}>{t(team.length === 0 ? "create.team.addFirst" : "create.team.addAnother")}</Button>
      </section>
      {createApplication.isError && !fieldError("applicationCode") ? (
        <Banner tone="danger" className="mt-4">
          {isApiError(createApplication.error) ? createApplication.error.detail : t("create.failed")}
          {isApiError(createApplication.error) && createApplication.error.fieldErrors.length > 0 ? (
            <ul className="mt-1 list-disc ps-5">{createApplication.error.fieldErrors.map((fieldError) => <li key={`${fieldError.field}-${fieldError.message}`}>{fieldError.message}</li>)}</ul>
          ) : null}
        </Banner>
      ) : null}
    </Dialog>
  );
}
