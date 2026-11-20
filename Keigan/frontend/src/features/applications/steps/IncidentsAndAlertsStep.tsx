import { ServiceNowGroupsSection } from "../components/ServiceNowGroupsSection";
import { StepFrame } from "../components/StepFrame";
import type { StepProps } from "../stepRegistry";
import { AlertSourcesSection } from "@/features/alerts/components/AlertSourcesSection";
import { IncidentCreationPolicySection } from "@/features/alerts/components/IncidentCreationPolicySection";
import { NoisePolicySection } from "@/features/alerts/components/NoisePolicySection";

/** Step 7: 7a ServiceNow groups (S1), 7b alert sources, 7c noise reduction policy, 7d incident creation from alerts (S3). */
export function IncidentsAndAlertsStep({ applicationId, canEdit, onStatusChange }: StepProps) {
  return (
    <StepFrame stepKey="incidents">
      <ServiceNowGroupsSection applicationId={applicationId} canEdit={canEdit} onChanged={onStatusChange} />
      <AlertSourcesSection applicationId={applicationId} canEdit={canEdit} onChanged={onStatusChange} />
      <NoisePolicySection applicationId={applicationId} canEdit={canEdit} onChanged={onStatusChange} />
      <IncidentCreationPolicySection applicationId={applicationId} canEdit={canEdit} onChanged={onStatusChange} />
    </StepFrame>
  );
}
