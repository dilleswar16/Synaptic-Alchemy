import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { isApiError } from "@/api/httpClient";
import { useCreateApplication, type Application, type CriticalityTier } from "@/api/applicationsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { CopyButton } from "@/components/ui/CopyButton";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";

const regionOptions = ["JP", "AU", "US", "NL", "FR", "ES", "MX", "CN"];
const defaultLocaleByRegion: Record<string, string> = { JP: "ja", CN: "zh-CN", ES: "es", MX: "es-MX", NL: "nl", FR: "fr" };
const localeOptions = ["en", "ja", "zh-CN", "es", "es-MX", "nl", "fr"];

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
  const [form, setForm] = useState({ applicationName: "", applicationCode: "", businessUnitName: "", regionCode: "", primaryLocale: "en", criticalityTier: "tier_2" as CriticalityTier, applicationDescription: "" });
  const update = (changes: Partial<typeof form>) => setForm((previous) => ({ ...previous, ...changes }));
  const codeIsValid = /^[A-Z0-9]{2,10}$/.test(form.applicationCode);
  const canSubmit = form.applicationName.trim().length >= 2 && codeIsValid;
  const fieldError = (field: string) => (isApiError(createApplication.error) ? createApplication.error.fieldErrorFor(field) : undefined);

  const close = (nextOpen: boolean) => {
    onOpenChange(nextOpen);
    if (!nextOpen) {
      setCreated(null);
      createApplication.reset();
    }
  };

  const submit = () =>
    createApplication.mutate(
      { ...form, applicationDescription: form.applicationDescription || undefined, businessUnitName: form.businessUnitName || undefined, regionCode: form.regionCode || undefined },
      { onSuccess: (application) => setCreated(application) },
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
      {createApplication.isError && !fieldError("applicationCode") ? (
        <Banner tone="danger" className="mt-4">{isApiError(createApplication.error) ? createApplication.error.detail : t("create.failed")}</Banner>
      ) : null}
    </Dialog>
  );
}
