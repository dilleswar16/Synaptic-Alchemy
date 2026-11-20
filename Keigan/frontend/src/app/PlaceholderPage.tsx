import { Hammer } from "lucide-react";
import { useTranslation } from "react-i18next";
import { PageHeader } from "@/components/layout/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";

/** Stub body for feature pages that are still being built. `titleKey` is a `navigation` key such as `items.alerts`. */
export function PlaceholderPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation("navigation");
  const { t: translateCommon } = useTranslation("common");
  return (
    <>
      <PageHeader title={t(titleKey)} />
      <EmptyState
        icon={Hammer}
        isBordered
        title={translateCommon("states.underConstructionTitle")}
        description={translateCommon("states.underConstructionDescription")}
      />
    </>
  );
}
