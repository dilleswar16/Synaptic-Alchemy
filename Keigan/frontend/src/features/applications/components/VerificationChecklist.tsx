import { CheckCircle2, CircleDashed, Clock, XCircle } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ApplicationComponent } from "@/api/applicationsApi";
import { Banner } from "@/components/ui/Banner";
import { cn } from "@/utils/cn";

const checkNames = ["list_resources", "read_activity_log", "read_metrics", "query_workspace"] as const;

/** Spec 6.3 sub-step 3: live checklist per read-only role. Missing roles show "Azure can take a few minutes" while the card keeps polling. */
export function VerificationChecklist({ component }: { component: ApplicationComponent }) {
  const { t } = useTranslation("onboarding");
  const isChecking = component.accessVerificationStatus === "checking";
  const details = component.accessVerificationDetails ?? [];
  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2" aria-label={t("verify.checklistLabel")}>
        {checkNames.map((checkName) => {
          const result = details.find((detail) => detail.checkName === checkName);
          const Icon = isChecking ? Clock : !result ? CircleDashed : result.passed ? CheckCircle2 : XCircle;
          return (
            <li key={checkName} className="flex items-start gap-2.5 text-body-sm">
              <Icon
                size={18}
                aria-hidden="true"
                className={cn("mt-0.5 shrink-0", result?.passed ? "text-success" : result ? "text-danger" : "text-muted", isChecking && "animate-pulse")}
              />
              <div>
                <div className="font-medium">{t(`verify.checks.${checkName}`)}</div>
                {result && !result.passed ? (
                  <div className="text-caption text-muted">{result.missingRoleName ? t("verify.missingRole", { role: result.missingRoleName }) : result.message}</div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
      {component.accessVerificationStatus === "missing_roles" || isChecking ? <Banner tone="info">{t("verify.rolesCanTakeAWhile")}</Banner> : null}
      {component.accessVerificationStatus === "failed" ? <Banner tone="danger">{details[0]?.message ?? t("verify.failed")}</Banner> : null}
    </div>
  );
}
