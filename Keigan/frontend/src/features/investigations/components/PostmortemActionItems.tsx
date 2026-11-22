import { ListChecks } from "lucide-react";
import { useTranslation } from "react-i18next";
import { usePostmortemActionItems } from "@/api/actionItemsApi";
import { Banner } from "@/components/ui/Banner";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ActionItemList } from "@/features/action-items/components/ActionItemList";

/** The postmortem's follow-ups as tracked rows. Suggestions wait here until a person accepts or discards each; finalising needs none left. */
export function PostmortemActionItems({ postmortemId, isFinal }: { postmortemId: string; isFinal: boolean }) {
  const { t } = useTranslation("actionItems");
  const { data: items, isLoading } = usePostmortemActionItems(postmortemId);
  const suggestedCount = (items ?? []).filter((item) => item.itemStatus === "proposed").length;
  if (isLoading) return <Skeleton className="h-24 w-full" />;
  if (!items || items.length === 0) return null;
  return (
    <Card radius="lg">
      <CardHeader title={t("panel.title")} description={isFinal ? t("panel.finalDescription") : t("panel.description")} actions={<ListChecks size={18} aria-hidden className="text-muted" />} />
      <CardBody className="flex flex-col gap-4">
        {suggestedCount > 0 && !isFinal ? <Banner tone="info" title={t("panel.suggestedTitle", { count: suggestedCount })}>{t("panel.suggestedBody")}</Banner> : null}
        <ActionItemList items={items} />
      </CardBody>
    </Card>
  );
}
