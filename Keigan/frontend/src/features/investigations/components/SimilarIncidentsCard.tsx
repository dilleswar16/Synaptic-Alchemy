import { useState } from "react";
import { EyeOff, History, ThumbsDown, ThumbsUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { isApiError } from "@/api/httpClient";
import { useSetRelevance, useSimilarIncidents, type MemoryRelevanceVerdict, type SimilarIncident } from "@/api/incidentMemoryApi";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { RelativeTime } from "@/components/ui/RelativeTime";
import { StatusChip } from "@/components/ui/StatusChip";
import { useToast } from "@/components/ui/Toast";
import { HideSimilarIncidentDialog } from "./HideSimilarIncidentDialog";

/** The id the "Seen before" chip in the header scrolls to. */
export const similarIncidentsElementId = "similar-incidents";

const verdictTone = { correct: "success", partially_correct: "warning", incorrect: "danger" } as const;

function TrustChip({ verdict }: { verdict: SimilarIncident["verdict"] }) {
  const { t } = useTranslation("investigations");
  return <StatusChip size="sm" tone={verdict ? verdictTone[verdict] : "neutral"} variant="outline">{t(`similarIncidents.trust.${verdict ?? "none"}`)}</StatusChip>;
}

function MatchRow({ match, investigationId, onHide }: { match: SimilarIncident; investigationId: string; onHide: (match: SimilarIncident) => void }) {
  const { t } = useTranslation("investigations");
  const { showToast } = useToast();
  const setRelevance = useSetRelevance(investigationId);
  const answer = (verdict: MemoryRelevanceVerdict) =>
    setRelevance.mutate({ memoryEntryId: match.memoryEntryId, verdict: match.myRelevanceVerdict === verdict ? null : verdict }, {
      onError: (error) => showToast({ tone: "danger", title: t("similarIncidents.relevanceFailed"), description: isApiError(error) ? error.detail : undefined }),
    });
  const wasMarkedIncorrect = match.verdict === "incorrect" && match.causeText === null && match.causeSource === "investigation";
  return (
    <li className="flex flex-col gap-2 rounded-md border border-hairline p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link to={`/investigations/${match.investigationId}`} className="min-w-0 break-words text-body font-semibold text-action hover:underline">
          {match.incidentNumber ? <span className="mr-2 font-mono text-body-sm">{match.incidentNumber}</span> : null}
          {match.incidentTitle}
        </Link>
        {match.isSameApplication ? null : <span className="text-caption text-muted">{match.application.applicationName}</span>}
        <RelativeTime value={match.occurredAt} className="text-caption text-muted" />
        <TrustChip verdict={match.verdict} />
        {match.wasGivenToAnalysis ? <StatusChip size="sm" tone="ai" variant="outline">{t("similarIncidents.givenToAnalysis")}</StatusChip> : null}
        {match.isStale ? <StatusChip size="sm" tone="warning" variant="outline" title={match.staleReasons.map((reason) => t(`similarIncidents.stale.${reason}`)).join(" ")}>{t("similarIncidents.mayBeOutOfDate")}</StatusChip> : null}
      </div>
      {wasMarkedIncorrect ? (
        <p className="text-body-sm text-muted">{t("similarIncidents.analysisMarkedIncorrect")}</p>
      ) : match.causeText ? (
        <p className="text-body-sm text-default"><span className="font-semibold">{t("similarIncidents.cause")}</span> {match.causeText} <span className="text-muted">({t(`similarIncidents.causeSource.${match.causeSource}`)})</span></p>
      ) : null}
      {match.fixText ? <p className="text-body-sm text-default"><span className="font-semibold">{t("similarIncidents.fix")}</span> {match.fixText} <span className="text-muted">({t(`similarIncidents.fixSource.${match.fixSource}`)})</span></p> : null}
      <p className="text-caption text-muted">
        {t("similarIncidents.matchedOn")} {match.matchReasons.map((reason) => `${t(`similarIncidents.keyKind.${reason.keyKind}`)} (${reason.displayText})`).join(", ")}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-caption text-muted">{t("similarIncidents.wasThisRelevant")}</span>
        <Button size="sm" variant={match.myRelevanceVerdict === "relevant" ? "subtle" : "ghost"} leadingIcon={ThumbsUp} aria-pressed={match.myRelevanceVerdict === "relevant"} onClick={() => answer("relevant")} disabled={setRelevance.isPending}>{t("similarIncidents.relevant")}</Button>
        <Button size="sm" variant={match.myRelevanceVerdict === "not_relevant" ? "subtle" : "ghost"} leadingIcon={ThumbsDown} aria-pressed={match.myRelevanceVerdict === "not_relevant"} onClick={() => answer("not_relevant")} disabled={setRelevance.isPending}>{t("similarIncidents.notRelevant")}</Button>
        {match.canHide ? <Button size="sm" variant="ghost" leadingIcon={EyeOff} onClick={() => onHide(match)}>{t("similarIncidents.hide.action")}</Button> : null}
      </div>
    </li>
  );
}

/** "Seen before": past incidents with the same facts, each with why it matched and what fixed it. Hints for people, never evidence. Shown only when there is something to show. */
export function SimilarIncidentsCard({ investigationId }: { investigationId: string }) {
  const { t } = useTranslation("investigations");
  const similar = useSimilarIncidents(investigationId);
  const [matchToHide, setMatchToHide] = useState<SimilarIncident | null>(null);
  const items = similar.data?.items ?? [];
  if (items.length === 0) return null;
  const standing = items.filter((match) => !match.isRejected);
  const rejected = items.filter((match) => match.isRejected);
  const rows = (matches: SimilarIncident[]) => (
    <ul className="flex flex-col gap-3">
      {matches.map((match) => <MatchRow key={match.memoryEntryId} match={match} investigationId={investigationId} onHide={setMatchToHide} />)}
    </ul>
  );
  return (
    <Card id={similarIncidentsElementId}>
      <CardHeader icon={History} iconTone="info" title={t("similarIncidents.title")} description={t("similarIncidents.description")} />
      <CardBody className="flex flex-col gap-5">
        {standing.length > 0 ? rows(standing) : null}
        {rejected.length > 0 ? (
          <section aria-label={t("similarIncidents.rejectedTitle")} className="flex flex-col gap-2 border-t border-hairline pt-4">
            <h4 className="text-body-sm font-semibold text-default">{t("similarIncidents.rejectedTitle")}</h4>
            <p className="text-caption text-muted">{t("similarIncidents.rejectedDescription")}</p>
            {rows(rejected)}
          </section>
        ) : null}
      </CardBody>
      <HideSimilarIncidentDialog investigationId={investigationId} match={matchToHide} onOpenChange={(open) => (open ? undefined : setMatchToHide(null))} />
    </Card>
  );
}
