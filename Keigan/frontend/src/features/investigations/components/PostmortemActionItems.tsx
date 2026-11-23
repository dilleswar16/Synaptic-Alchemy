import { Check, ListChecks } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { type AcceptAllResult, useAcceptAllActionItems, usePostmortemActionItems } from "@/api/actionItemsApi";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ActionItemList } from "@/features/action-items/components/ActionItemList";

/** The postmortem's follow-ups as tracked rows. Suggestions wait here until a person accepts or discards each (or accepts them all); finalising needs none left. */
export function PostmortemActionItems({ postmortemId, isFinal }: { postmortemId: string; isFinal: boolean }) {
  const { t } = useTranslation("actionItems");
  const { data: items, isLoading } = usePostmortemActionItems(postmortemId);
  const acceptAll = useAcceptAllActionItems();
  const [result, setResult] = useState<AcceptAllResult | null>(null);
  const suggested = (items ?? []).filter((item) => item.itemStatus === "proposed");
  const mayAcceptAll = suggested.some((item) => item.canEdit);
  if (isLoading) return <Skeleton className="h-24 w-full" />;
  if (!items || items.length === 0) return null;
  const skipped = result?.skipped ?? [];
  return (
    <Card radius="lg">
      <CardHeader title={t("panel.title")} description={isFinal ? t("panel.finalDescription") : t("panel.description")} actions={<ListChecks size={18} aria-hidden className="text-muted" />} />
      <CardBody className="flex flex-col gap-4">
        {suggested.length > 0 && !isFinal ? (
          <Banner tone="info" title={t("panel.suggestedTitle", { count: suggested.length })}>
            <p>{t("panel.suggestedBody")}</p>
            {mayAcceptAll ? (
              <Button className="mt-2" size="sm" variant="secondary" leadingIcon={Check} isLoading={acceptAll.isPending} onClick={() => acceptAll.mutate(postmortemId, { onSuccess: setResult })}>
                {t("panel.acceptAll", { count: suggested.length })}
              </Button>
            ) : null}
          </Banner>
        ) : null}
        {skipped.length > 0 ? (
          <Banner tone="warning" title={t("panel.skippedTitle", { count: skipped.length })}>
            <ul className="list-disc space-y-0.5 pl-5">
              {skipped.map((entry) => <li key={entry.actionItemId}><span className="font-semibold">{entry.itemTitle}</span> {t(`panel.skipReason.${entry.reason}`)}</li>)}
            </ul>
          </Banner>
        ) : null}
        <ActionItemList items={items} />
      </CardBody>
    </Card>
  );
}
