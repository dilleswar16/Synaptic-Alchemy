import { useMemo, useState } from "react";
import { ChevronDown, Layers, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useApplicationScope } from "@/auth/applicationScope";
import { cn } from "@/utils/cn";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Input } from "@/components/ui/Input";
import { Popover } from "@/components/ui/Popover";
import { Skeleton } from "@/components/ui/Skeleton";

/** Multi-select application scope ("All my applications" or a set). Lists, counts and chat follow it. */
export function ApplicationScopeSwitcher({ className }: { className?: string }) {
  const { t } = useTranslation("navigation");
  const { availableApplications, isLoadingApplications, selectedApplicationIds, isAllSelected, setSelectedApplicationIds, clearSelection } = useApplicationScope();
  const [searchText, setSearchText] = useState("");

  const scopeLabel = isAllSelected
    ? t("applicationScope.allMyApplications")
    : selectedApplicationIds.length === 1
      ? (availableApplications.find((application) => application.applicationId === selectedApplicationIds[0])?.applicationName ?? t("applicationScope.selectedCount", { count: 1 }))
      : t("applicationScope.selectedCount", { count: selectedApplicationIds.length });

  const filteredApplications = useMemo(() => {
    const query = searchText.trim().toLowerCase();
    return query
      ? availableApplications.filter((application) => `${application.applicationName} ${application.applicationCode}`.toLowerCase().includes(query))
      : availableApplications;
  }, [availableApplications, searchText]);

  function toggleApplication(applicationId: string, isChecked: boolean): void {
    const nextSelection = isChecked ? [...selectedApplicationIds, applicationId] : selectedApplicationIds.filter((identifier) => identifier !== applicationId);
    setSelectedApplicationIds(nextSelection.length === availableApplications.length ? [] : nextSelection);
  }

  return (
    <Popover
      align="start"
      width="md"
      isFlush
      aria-label={t("applicationScope.label")}
      trigger={
        <Button variant="secondary" size="sm" leadingIcon={Layers} aria-label={t("applicationScope.triggerLabel", { scope: scopeLabel })} className={cn("min-w-0 max-w-[260px] shrink", className)}>
          <span className="min-w-0 truncate">{scopeLabel}</span>
          <ChevronDown aria-hidden="true" size={16} strokeWidth={1.75} className="shrink-0" />
        </Button>
      }
    >
      <div className="flex flex-col">
        <div className="border-b border-hairline p-3">
          <Input
            size="sm"
            leadingIcon={Search}
            value={searchText}
            onChange={(changeEvent) => setSearchText(changeEvent.target.value)}
            placeholder={t("applicationScope.searchPlaceholder")}
            aria-label={t("applicationScope.searchPlaceholder")}
          />
        </div>
        <div className="max-h-72 overflow-y-auto p-2">
          {isLoadingApplications ? (
            <div className="flex flex-col gap-2 p-2">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-5 w-1/2" />
            </div>
          ) : availableApplications.length === 0 ? (
            <p className="p-3 text-body-sm text-muted">{t("applicationScope.noApplications")}</p>
          ) : (
            <>
              <div className="rounded-sm px-2 py-1.5 hover:bg-surface-hover">
                <Checkbox checked={isAllSelected} onCheckedChange={() => clearSelection()} label={t("applicationScope.allMyApplications")} />
              </div>
              {filteredApplications.length === 0 ? (
                <p className="p-3 text-body-sm text-muted">{t("applicationScope.noMatches", { query: searchText })}</p>
              ) : (
                filteredApplications.map((application) => (
                  <div key={application.applicationId} className="flex items-center justify-between gap-2 rounded-sm px-2 py-1.5 hover:bg-surface-hover">
                    <Checkbox
                      checked={isAllSelected ? false : selectedApplicationIds.includes(application.applicationId)}
                      onCheckedChange={(checked) => toggleApplication(application.applicationId, checked === true)}
                      label={
                        <span className="flex items-baseline gap-2">
                          <span>{application.applicationName}</span>
                          <span className="font-mono text-caption text-muted">{application.applicationCode}</span>
                        </span>
                      }
                    />
                    {application.role ? <Badge tone={application.role === "admin" ? "brand" : "neutral"}>{t(application.role === "admin" ? "applicationScope.roleAdmin" : "applicationScope.roleReader")}</Badge> : null}
                  </div>
                ))
              )}
            </>
          )}
        </div>
        <p className="border-t border-hairline px-4 py-2.5 text-caption text-muted">{t("applicationScope.hint")}</p>
      </div>
    </Popover>
  );
}
