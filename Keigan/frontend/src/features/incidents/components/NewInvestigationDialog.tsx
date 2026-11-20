import { useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useServices } from "@/api/applicationsApi";
import { isApiError } from "@/api/httpClient";
import { useStartInvestigation } from "@/api/investigationsApi";
import { useApplicationScope } from "@/auth/applicationScope";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Dialog } from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Skeleton } from "@/components/ui/Skeleton";
import { Textarea } from "@/components/ui/Textarea";
import { useToast } from "@/components/ui/Toast";

interface NewInvestigationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultApplicationId?: string;
}

function ServicePicker({ applicationId, selectedServiceIds, onChange }: { applicationId: string; selectedServiceIds: string[]; onChange: (serviceIds: string[]) => void }) {
  const { t } = useTranslation("incidents");
  const { data: services, isLoading } = useServices(applicationId);
  if (isLoading) return <Skeleton className="h-16 w-full" />;
  const monitoredServices = (services ?? []).filter((service) => service.isMonitoringEnabled);
  if (monitoredServices.length === 0) return null;
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-body-sm font-semibold text-default">{t("newInvestigation.services")}</legend>
      <p className="text-caption text-muted">{t("newInvestigation.servicesHelp")}</p>
      <div className="grid max-h-40 gap-1.5 overflow-y-auto sm:grid-cols-2">
        {monitoredServices.map((service) => (
          <Checkbox
            key={service.serviceId}
            label={service.serviceName}
            checked={selectedServiceIds.includes(service.serviceId)}
            onCheckedChange={(checked) => onChange(checked === true ? [...selectedServiceIds, service.serviceId] : selectedServiceIds.filter((serviceId) => serviceId !== service.serviceId))}
          />
        ))}
      </div>
    </fieldset>
  );
}

/** "New investigation": application, optional services and time window, and a description of what is wrong. */
export function NewInvestigationDialog({ open, onOpenChange, defaultApplicationId }: NewInvestigationDialogProps) {
  const { t } = useTranslation("incidents");
  const navigate = useNavigate();
  const { showToast } = useToast();
  const { availableApplications } = useApplicationScope();
  const startInvestigation = useStartInvestigation();
  const [applicationId, setApplicationId] = useState<string>(defaultApplicationId ?? "");
  const [serviceIds, setServiceIds] = useState<string[]>([]);
  const [description, setDescription] = useState("");
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const effectiveApplicationId = applicationId || availableApplications[0]?.applicationId || "";
  const canSubmit = Boolean(effectiveApplicationId) && description.trim().length >= 5;

  const submit = () => {
    startInvestigation.mutate(
      {
        applicationId: effectiveApplicationId,
        serviceIds,
        description: description.trim(),
        windowStart: windowStart ? new Date(windowStart).toISOString() : undefined,
        windowEnd: windowEnd ? new Date(windowEnd).toISOString() : undefined,
      },
      {
        onSuccess: (job) => {
          showToast({ tone: "ai", title: t("newInvestigation.startedTitle"), description: t("newInvestigation.startedDescription") });
          onOpenChange(false);
          setDescription("");
          setServiceIds([]);
          void navigate(`/investigations/${job.jobId}`);
        },
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={t("newInvestigation.title")}
      description={t("newInvestigation.description")}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("newInvestigation.cancel")}</Button>
          <Button onClick={submit} isLoading={startInvestigation.isPending} disabled={!canSubmit}>{t("newInvestigation.start")}</Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Select
          label={t("newInvestigation.application")}
          value={effectiveApplicationId}
          onValueChange={(value) => {
            setApplicationId(value);
            setServiceIds([]);
          }}
          options={availableApplications.map((application) => ({ value: application.applicationId, label: `${application.applicationName} (${application.applicationCode})` }))}
        />
        {effectiveApplicationId ? <ServicePicker applicationId={effectiveApplicationId} selectedServiceIds={serviceIds} onChange={setServiceIds} /> : null}
        <Textarea
          label={t("newInvestigation.descriptionLabel")}
          helperText={t("newInvestigation.descriptionHelp")}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={4}
          maxLength={8000}
          errorMessage={isApiError(startInvestigation.error) ? (startInvestigation.error.fieldErrorFor("description") ?? startInvestigation.error.detail) : undefined}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input type="datetime-local" label={t("newInvestigation.windowStart")} isOptional value={windowStart} onChange={(event) => setWindowStart(event.target.value)} />
          <Input type="datetime-local" label={t("newInvestigation.windowEnd")} isOptional value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)} />
        </div>
      </div>
    </Dialog>
  );
}
