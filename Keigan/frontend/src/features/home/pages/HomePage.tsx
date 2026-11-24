import { useState, type FormEvent } from "react";
import { Activity, BellRing, CalendarClock, FileText, Gauge, Moon, Radar, Search, ShieldAlert, Sparkles, Sun, Sunrise } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { useHomeDashboard, type LiveIncidentItem } from "@/api/dashboardApi";
import { useApplicationScope } from "@/auth/applicationScope";
import { useCurrentUser } from "@/auth/authContext";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Input } from "@/components/ui/Input";
import { PriorityChip } from "@/components/ui/PriorityChip";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatTile } from "@/components/ui/StatTile";
import { StatusChip } from "@/components/ui/StatusChip";
import type { StatusTone } from "@/components/ui/toneStyles";
import { formatDateTime, formatDuration, formatPercentage } from "@/utils/formatters";
import { ApplicationHealthCardView } from "@/features/home/components/ApplicationHealthCardView";

const greetingIcons = { morning: Sunrise, afternoon: Sun, evening: Moon } as const;

const severityTones: Record<string, StatusTone> = { critical: "danger", high: "alert", warning: "warning", medium: "warning", info: "info", low: "info" };

function greetingKey(date: Date): "morning" | "afternoon" | "evening" {
  const hour = date.getHours();
  return hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
}

function LiveIncidentRow({ incident }: { incident: LiveIncidentItem }) {
  const { t } = useTranslation("home");
  const isRunning = incident.investigationStatus === "running" || incident.investigationStatus === "queued";
  return (
    <li className="flex flex-col gap-2 border-t border-hairline py-3 first:border-t-0">
      <div className="flex items-start gap-3">
        {incident.priority ? <PriorityChip priority={incident.priority} size="sm" /> : null}
        <div className="min-w-0 flex-1">
          <Link to={incident.investigationId ? `/investigations/${incident.investigationId}` : "/incidents"} className="block truncate text-body-sm font-semibold text-default hover:text-action">{incident.incidentTitle}</Link>
          <p className="text-caption text-muted">{[incident.applicationName, incident.externalIncidentNumber].filter(Boolean).join(" · ")} · <RelativeTime value={incident.openedAt} /></p>
        </div>
        <StatusChip tone={isRunning ? "ai" : "info"} size="sm" pulse={isRunning}>{isRunning ? t("live.investigating") : t(`live.status.${incident.incidentStatus}`, { defaultValue: incident.incidentStatus })}</StatusChip>
      </div>
      {isRunning && incident.progressPercent !== null ? <ProgressBar value={incident.progressPercent} tone="ai" size="xs" label={incident.currentStageName ?? undefined} showValue /> : null}
    </li>
  );
}

/** The first screen everyone sees: greeting and status, KPIs, application health, live incidents and the intelligence feed (doc 04 §6.2). */
export default function HomePage() {
  const { t } = useTranslation("home");
  const { t: translateIntelligence } = useTranslation("intelligence");
  const navigate = useNavigate();
  const scope = useApplicationScope();
  const currentUser = useCurrentUser();
  const dashboard = useHomeDashboard(scope.applicationIds);
  const [question, setQuestion] = useState("");

  const askKeigan = (event: FormEvent) => {
    event.preventDefault();
    if (question.trim()) navigate("/chat", { state: { question: question.trim() } });
  };

  if (dashboard.isError) return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} isRetrying={dashboard.isFetching} />;
  const data = dashboard.data;
  const kpis = data?.kpis;
  const priorityBreakdown = kpis ? Object.entries(kpis.openIncidentsByPriority).sort(([first], [second]) => first.localeCompare(second)).map(([priority, count]) => `${count} ${priority}`).join(" · ") : "";
  const name = data?.greetingName ?? currentUser?.displayName?.split(" ")[0] ?? "";
  const GreetingIcon = greetingIcons[greetingKey(new Date())];

  return (
    <div className="flex flex-col gap-6">
      <section className="-mx-4 -mt-4 bg-gradient-brand-soft px-4 pt-8 pb-6 sm:-mx-5 sm:px-5 md:-mx-8 md:px-8" aria-labelledby="home-greeting">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-start gap-4">
            <span className="greeting-icon grid size-12 shrink-0 place-items-center rounded-xl border border-hairline bg-surface text-default shadow-xs" aria-hidden>
              <GreetingIcon size={24} strokeWidth={1.6} />
            </span>
            <div>
              <h1 id="home-greeting" className="text-h1 font-semibold text-default">{t(`greeting.${greetingKey(new Date())}`, { name })}</h1>
              {data ? <p className="mt-1 max-w-3xl text-body-lg text-muted">{data.statusSentence}</p> : <Skeleton className="mt-2 h-6 w-96 max-w-full" />}
            </div>
          </div>
          {data ? <p className="flex items-center gap-1.5 text-caption text-muted"><span className="size-1.5 rounded-full bg-success-fill" aria-hidden />{t("syncedAt", { time: formatDateTime(data.generatedAt, { timeStyle: "short" }) })}</p> : null}
        </div>
      </section>

      <Card>
        <CardHeader title={t("live.title")} description={t("live.description")} actions={<Button variant="ghost" size="sm" onClick={() => navigate("/incidents")}>{t("viewAll")}</Button>} />
        <CardBody>
          {!data ? <Skeleton className="h-24" /> : data.liveIncidents.length === 0 ? <p className="py-2 text-body-sm text-muted">{t("live.empty")}</p> : <ul>{data.liveIncidents.map((incident) => <LiveIncidentRow key={incident.incidentId} incident={incident} />)}</ul>}
        </CardBody>
      </Card>

      <section aria-label={t("kpi.sectionLabel")} className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {!kpis ? [0, 1, 2, 3].map((index) => <Skeleton key={index} className="h-28" />) : (
          <>
            <StatTile icon={ShieldAlert} iconTone={kpis.openIncidentsTotal ? "danger" : "success"} label={t("kpi.openIncidents")} value={kpis.openIncidentsTotal} secondaryText={priorityBreakdown || t("kpi.noneOpen")} to="/incidents" />
            <StatTile icon={BellRing} iconTone="alert" label={t("kpi.alertGroups")} value={kpis.activeAlertGroupCount} secondaryText={kpis.noiseReductionPercentage === null ? t("kpi.noAlerts") : t("kpi.noiseReduced", { percentage: formatPercentage(kpis.noiseReductionPercentage, { maximumFractionDigits: 0 }) })} secondaryTone={kpis.noiseReductionPercentage ? "positive" : "default"} to="/alerts" />
            <StatTile icon={Gauge} iconTone={kpis.slosAtRiskCount ? "warning" : "success"} label={t("kpi.slosAtRisk")} value={kpis.slosAtRiskCount} secondaryText={t("kpi.slosTotal", { count: kpis.sloTotalCount })} to="/slo" />
            <StatTile icon={Activity} iconTone="ai" label={t("kpi.investigations")} value={kpis.investigationsLast24Hours} secondaryText={kpis.meanMinutesToFirstUpdate === null ? t("kpi.noFirstUpdate") : t("kpi.firstUpdate", { duration: formatDuration(kpis.meanMinutesToFirstUpdate * 60_000) })} />
          </>
        )}
      </section>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-6">
          <section aria-labelledby="home-health">
            <h2 id="home-health" className="mb-3 text-h3 font-semibold text-default">{t("health.title")}</h2>
            {!data ? <div className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">{[0, 1, 2].map((index) => <Skeleton key={index} className="h-48" />)}</div> : data.applicationCards.length === 0 ? (
              <EmptyState icon={Radar} title={t("health.emptyTitle")} description={t("health.emptyDescription")} isBordered />
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">{data.applicationCards.map((card) => <ApplicationHealthCardView key={card.applicationId} card={card} />)}</div>
            )}
          </section>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <section aria-labelledby="home-ask" className="rounded-xl bg-gradient-ai p-5 text-white shadow-md">
            <h2 id="home-ask" className="flex items-center gap-2 font-display text-h3 font-semibold text-white"><Sparkles size={18} aria-hidden />{t("ask.title")}</h2>
            <p className="mt-1 text-body-sm text-white/80">{t("ask.description")}</p>
            <form onSubmit={askKeigan} className="mt-3 flex flex-col gap-2">
              <Input aria-label={t("ask.label")} placeholder={t("ask.placeholder")} leadingIcon={Search} value={question} onChange={(event) => setQuestion(event.target.value)} />
              <Button type="submit" variant="secondary" disabled={!question.trim()}>{t("ask.submit")}</Button>
            </form>
          </section>

          <Card>
            <CardHeader icon={Radar} iconTone="ai" title={t("feed.title")} description={t("feed.description")} actions={<Button variant="ghost" size="sm" onClick={() => navigate("/intelligence")}>{t("viewAll")}</Button>} />
            <CardBody>
              {!data ? <Skeleton className="h-20" /> : data.intelligenceFeed.length === 0 ? <p className="text-body-sm text-muted">{t("feed.empty")}</p> : (
                <ul className="flex flex-col gap-3">
                  {data.intelligenceFeed.map((item) => (
                    <li key={item.signalId} className="flex items-start gap-2.5">
                      <StatusChip tone={severityTones[item.signalSeverity] ?? "info"} size="sm">{translateIntelligence(`severity.${item.signalSeverity}`)}</StatusChip>
                      <div className="min-w-0">
                        <p className="text-body-sm font-medium text-default">{item.signalTitle}</p>
                        <p className="text-caption text-muted">{item.applicationName}{item.forecastBreachAt ? ` · ${t("feed.forecast", { time: formatDateTime(item.forecastBreachAt, { dateStyle: "medium", timeStyle: "short" }) })}` : ""}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader icon={CalendarClock} iconTone="info" title={t("maintenance.title")} description={t("maintenance.description")} />
            <CardBody>
              {!data ? <Skeleton className="h-16" /> : data.maintenanceWindows.length === 0 ? <p className="text-body-sm text-muted">{t("maintenance.empty")}</p> : (
                <ul className="flex flex-col gap-2.5">
                  {data.maintenanceWindows.map((window) => (
                    <li key={window.maintenanceWindowId} className="text-body-sm">
                      <p className="font-medium text-default">{window.windowName}</p>
                      <p className="text-caption text-muted">{window.applicationName} · {formatDateTime(window.startsAt, { dateStyle: "medium", timeStyle: "short" })}</p>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader icon={FileText} iconTone="neutral" title={t("postmortems.title")} />
            <CardBody>
              {!data ? <Skeleton className="h-16" /> : data.recentPostmortems.length === 0 ? <p className="text-body-sm text-muted">{t("postmortems.empty")}</p> : (
                <ul className="flex flex-col gap-2.5">
                  {data.recentPostmortems.map((postmortem) => (
                    <li key={postmortem.postmortemId} className="text-body-sm">
                      <Link to="/incidents" className="font-medium text-default hover:text-action">{postmortem.reportTitle}</Link>
                      <p className="text-caption text-muted">{postmortem.applicationName} · {t(`postmortems.status.${postmortem.reportStatus}`, { defaultValue: postmortem.reportStatus })}</p>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}
