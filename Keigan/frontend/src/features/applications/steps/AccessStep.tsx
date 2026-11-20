import { CheckCircle2, CircleHelp, ShieldCheck, XCircle } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useAccessInformation, useUpdateAccess, useVerifyAccessGroups, type AccessInformation, type GroupVerificationResult } from "@/api/applicationsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CopyButton } from "@/components/ui/CopyButton";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { StepFrame } from "../components/StepFrame";
import type { StepProps } from "../stepRegistry";

function GroupCard({ title, groupName, objectId, canEditNames, canEdit, onSave }: {
  title: string;
  groupName: string;
  objectId: string | null;
  canEditNames: boolean;
  canEdit: boolean;
  onSave: (values: { name: string; objectId: string }) => void;
}) {
  const { t } = useTranslation("onboarding");
  const [name, setName] = useState(groupName);
  const [identifier, setIdentifier] = useState(objectId ?? "");
  const hasChanges = name !== groupName || identifier !== (objectId ?? "");
  return (
    <Card className="flex flex-col gap-4 p-[var(--card-padding)]">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-caption text-muted">{title}</div>
          <div className="truncate font-mono text-body font-semibold">{groupName}</div>
        </div>
        <CopyButton showLabel variant="secondary" size="md" label={t("access.copyGroup")} value={groupName} />
      </div>
      {canEdit ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label={t("access.groupName")} disabled={!canEditNames} value={name} onChange={(event) => setName(event.target.value)} />
          <Input label={t("access.objectId")} isOptional helperText={t("access.objectIdHelp")} value={identifier} onChange={(event) => setIdentifier(event.target.value)} />
          <Button className="justify-self-start sm:col-span-2" size="sm" disabled={!hasChanges} onClick={() => onSave({ name, objectId: identifier })}>{t("access.save")}</Button>
        </div>
      ) : objectId ? (
        <div className="text-body-sm text-muted">{t("access.objectId")}: <span className="font-mono">{objectId}</span></div>
      ) : null}
    </Card>
  );
}

function VerificationRow({ result }: { result: GroupVerificationResult }) {
  const { t } = useTranslation("onboarding");
  const StatusIcon = result.exists === true ? CheckCircle2 : result.exists === false ? XCircle : CircleHelp;
  const statusTone = result.exists === true ? "text-success" : result.exists === false ? "text-danger" : "text-warning";
  return (
    <li className="flex items-start gap-3 py-3">
      <StatusIcon className={`mt-0.5 shrink-0 ${statusTone}`} size={18} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-body-sm font-semibold">{result.role === "admin" ? t("access.adminGroup") : t("access.readerGroup")}</span>
          <span className="font-mono text-body-sm break-all">{result.groupName}</span>
        </div>
        <p className="text-body-sm text-muted">{result.message}</p>
        {result.sampleMemberNames.length ? (
          <p className="text-caption text-muted">{t("access.verify.members", { names: result.sampleMemberNames.join(", "), count: result.memberCount ?? result.sampleMemberNames.length })}</p>
        ) : null}
        {result.objectIdSaved ? <p className="text-caption text-success">{t("access.verify.objectIdSaved", { objectId: result.objectId })}</p> : null}
      </div>
    </li>
  );
}

/** Lets a Keigan admin confirm, before any owner signs in, that SailPoint has provisioned both groups in Entra ID. */
function GroupVerificationPanel({ applicationId, canVerify, onVerified }: { applicationId: string; canVerify: boolean; onVerified?: () => void }) {
  const { t } = useTranslation("onboarding");
  const verifyGroups = useVerifyAccessGroups(applicationId);
  const verification = verifyGroups.data;
  return (
    <Card className="flex flex-col gap-3 p-[var(--card-padding)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 font-display text-h3 font-semibold"><ShieldCheck size={18} aria-hidden="true" className="text-action" />{t("access.verify.title")}</h3>
          <p className="text-body-sm text-muted">{t("access.verify.description")}</p>
        </div>
        {canVerify ? (
          <Button size="sm" variant="secondary" isLoading={verifyGroups.isPending} onClick={() => verifyGroups.mutate(undefined, { onSuccess: onVerified })}>
            {t("access.verify.button")}
          </Button>
        ) : null}
      </div>
      {verifyGroups.isError ? <ErrorState size="sm" error={verifyGroups.error} onRetry={() => verifyGroups.mutate(undefined)} /> : null}
      {verification ? (
        <>
          <ul className="divide-y divide-hairline">{verification.results.map((result) => <VerificationRow key={result.role} result={result} />)}</ul>
          <p className="text-caption text-muted">{verification.directory === "entra" ? t("access.verify.sourceEntra") : t("access.verify.sourceLocal")}</p>
        </>
      ) : null}
    </Card>
  );
}

/** Step 10 (informational): the two AD groups, SailPoint instructions, optional group object IDs and, in Entra mode, members. */
export function AccessStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  const { t } = useTranslation("onboarding");
  const accessQuery = useAccessInformation(applicationId);
  const updateAccess = useUpdateAccess(applicationId);
  const access: AccessInformation | undefined = accessQuery.data;

  return (
    <StepFrame stepKey="access">
      {accessQuery.isError ? (
        <ErrorState error={accessQuery.error} onRetry={() => void accessQuery.refetch()} />
      ) : !access ? (
        <Skeleton className="h-48 rounded-lg" />
      ) : (
        <div className="flex flex-col gap-4">
          <Banner tone="info" title={t("access.howItWorksTitle")}>
            <p>{t("access.howItWorksBody")}</p>
            <p className="mt-2 font-semibold">{t("access.sailpointTitle")}</p>
            <p>{access.sailpointInstructions}</p>
          </Banner>
          <GroupCard
            key={`admin-${access.adminGroupName}-${access.adminGroupObjectId}`}
            title={t("access.adminGroup")}
            groupName={access.adminGroupName}
            objectId={access.adminGroupObjectId}
            canEdit={canEdit}
            canEditNames={access.canEditGroupNames}
            onSave={({ name, objectId }) => updateAccess.mutate({ ...(access.canEditGroupNames ? { adminGroupName: name } : {}), adminGroupObjectId: objectId }, { onSuccess: onStatusChange })}
          />
          <GroupCard
            key={`reader-${access.readerGroupName}-${access.readerGroupObjectId}`}
            title={t("access.readerGroup")}
            groupName={access.readerGroupName}
            objectId={access.readerGroupObjectId}
            canEdit={canEdit}
            canEditNames={access.canEditGroupNames}
            onSave={({ name, objectId }) => updateAccess.mutate({ ...(access.canEditGroupNames ? { readerGroupName: name } : {}), readerGroupObjectId: objectId }, { onSuccess: onStatusChange })}
          />
          <GroupVerificationPanel applicationId={applicationId} canVerify={canEdit} onVerified={onStatusChange} />
          <p className="text-body-sm text-muted">{access.membersAvailable ? t("access.membersEntra") : t("access.membersLocal")}</p>
        </div>
      )}
    </StepFrame>
  );
}
