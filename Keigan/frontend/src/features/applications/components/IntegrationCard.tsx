import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useSaveIntegration, type Integration, type IntegrationField } from "@/api/applicationsApi";
import { isApiError } from "@/api/httpClient";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { StatusChip } from "@/components/ui/StatusChip";
import { Textarea } from "@/components/ui/Textarea";

const keyValueToText = (value: unknown): string =>
  value && typeof value === "object" ? Object.entries(value as Record<string, unknown>).map(([key, entry]) => `${key}=${String(entry)}`).join("\n") : "";
const textToKeyValue = (text: string): Record<string, string> =>
  Object.fromEntries(text.split("\n").map((line) => line.trim()).filter((line) => line.includes("=")).map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1).trim()]));

function initialValues(integration: Integration): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of integration.fields) {
    const stored = integration.integrationConfiguration[field.key];
    values[field.key] =
      field.fieldType === "secret" ? "" // write-only: a stored credential is never sent back, so the box starts empty
        : field.fieldType === "key_value_list" ? keyValueToText(stored)
          : stored !== undefined ? String(stored) : (field.defaultValue ?? "");
  }
  return values;
}

/** One integration (CMDB, EI portal, knowledge API) rendered from its JSON field schema, so fields can change without UI changes. */
export function IntegrationCard({ applicationId, integration, canEdit }: { applicationId: string; integration: Integration; canEdit: boolean }) {
  const { t } = useTranslation("knowledge");
  const saveIntegration = useSaveIntegration(applicationId);
  const [isOpen, setIsOpen] = useState(false);
  const [values, setValues] = useState<Record<string, string>>(() => initialValues(integration));
  const [notes, setNotes] = useState(integration.integrationNotes ?? "");
  const isSaved = integration.integrationStatus !== "not_set_up";

  const secretFieldKey = integration.fields.find((field) => field.fieldType === "secret")?.key;

  const save = () =>
    saveIntegration.mutate(
      {
        integrationKind: integration.integrationKind,
        integrationConfiguration: Object.fromEntries(
          integration.fields
            .filter((field) => field.fieldType !== "secret")
            .map((field) => [field, (values[field.key] ?? "").trim()] as const)
            .filter(([, text]) => text)
            .map(([field, text]) => [field.key, field.fieldType === "key_value_list" ? textToKeyValue(text) : text]),
        ),
        // Sent only when the user typed one; leaving the box empty keeps the saved credential.
        credentialValue: secretFieldKey ? (values[secretFieldKey] ?? "").trim() || undefined : undefined,
        integrationNotes: notes || undefined,
      },
      { onSuccess: () => secretFieldKey && setValues((previous) => ({ ...previous, [secretFieldKey]: "" })) },
    );

  const renderField = (field: IntegrationField) => {
    const label = t(`integrations.fields.${field.key}`, { defaultValue: field.label });
    const common = { label, isOptional: !field.required, helperText: field.helpText } as const;
    if (field.fieldType === "select") {
      return <Select key={field.key} {...common} disabled={!canEdit} value={values[field.key] || undefined} options={(field.options ?? []).map(([value, optionLabel]) => ({ value, label: optionLabel }))} onValueChange={(next) => setValues({ ...values, [field.key]: next })} />;
    }
    if (field.fieldType === "textarea" || field.fieldType === "key_value_list") {
      return <Textarea key={field.key} {...common} disabled={!canEdit} isMonospace={field.fieldType === "key_value_list"} rows={3} placeholder={field.fieldType === "key_value_list" ? "key=value" : field.placeholder} value={values[field.key] ?? ""} onChange={(event) => setValues({ ...values, [field.key]: event.target.value })} />;
    }
    if (field.fieldType === "secret") {
      return (
        <Input
          key={field.key}
          {...common}
          helperText={integration.hasCredential ? t("integrations.credentialSaved") : field.helpText}
          disabled={!canEdit}
          type="password"
          autoComplete="new-password"
          placeholder={integration.hasCredential ? t("integrations.credentialSavedPlaceholder") : field.placeholder}
          value={values[field.key] ?? ""}
          onChange={(event) => setValues({ ...values, [field.key]: event.target.value })}
        />
      );
    }
    return (
      <Input
        key={field.key}
        {...common}
        disabled={!canEdit}
        type={field.fieldType === "url" ? "url" : "text"}
        placeholder={field.placeholder}
        value={values[field.key] ?? ""}
        onChange={(event) => setValues({ ...values, [field.key]: event.target.value })}
        errorMessage={isApiError(saveIntegration.error) ? saveIntegration.error.fieldErrorFor(`integrationConfiguration.${field.key}`) : undefined}
      />
    );
  };

  return (
    <Card dense className="flex flex-col gap-3 p-[var(--card-padding)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-body font-semibold">{integration.displayName}</h4>
            <StatusChip size="sm" tone={isSaved ? "ai" : "neutral"} icon={false}>
              {isSaved && !integration.readerAvailable ? t("integrations.savedReaderNotAvailable") : isSaved ? t("integrations.configured") : t("integrations.notSetUp")}
            </StatusChip>
          </div>
          <p className="mt-1 text-body-sm text-muted">{integration.purpose}</p>
        </div>
        <Button size="sm" variant="secondary" trailingIcon={isOpen ? ChevronUp : ChevronDown} onClick={() => setIsOpen((previous) => !previous)}>
          {isSaved ? t("integrations.viewDetails") : t("integrations.setUp")}
        </Button>
      </div>
      {isOpen ? (
        <div className="flex flex-col gap-4 border-t border-hairline pt-4">
          {integration.fields.map(renderField)}
          <Textarea label={t("integrations.notes")} isOptional rows={2} disabled={!canEdit} value={notes} onChange={(event) => setNotes(event.target.value)} />
          {saveIntegration.isError && !isApiError(saveIntegration.error) ? <Banner tone="danger">{t("integrations.saveFailed")}</Banner> : null}
          {canEdit ? <Button className="self-start" isLoading={saveIntegration.isPending} onClick={save}>{t("integrations.save")}</Button> : null}
        </div>
      ) : null}
    </Card>
  );
}
