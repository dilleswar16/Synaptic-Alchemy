import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { StatusChip } from "@/components/ui/StatusChip";
import { SectionHeader } from "@/components/ui/SectionHeader";
import type { StepKey } from "@/api/applicationsApi";
import { stepDefinitions } from "../stepRegistry";

/** Common title block of every workspace step: heading, one-sentence purpose and the Required / Recommended / Optional chip. */
export function StepFrame({ stepKey, actions, children }: { stepKey: StepKey; actions?: ReactNode; children: ReactNode }) {
  const { t } = useTranslation("applications");
  const definition = stepDefinitions.find((candidate) => candidate.key === stepKey);
  return (
    <div className="flex flex-col gap-6">
      <SectionHeader
        title={
          <span className="flex flex-wrap items-center gap-3">
            {t(`steps.${stepKey}.label`)}
            {definition ? (
              <StatusChip size="sm" tone={definition.requirement === "required" ? "brand" : "neutral"} icon={false}>
                {t(`requirement.${definition.requirement}`)}
              </StatusChip>
            ) : null}
          </span>
        }
        description={t(`steps.${stepKey}.description`)}
        actions={actions}
      />
      {children}
    </div>
  );
}
