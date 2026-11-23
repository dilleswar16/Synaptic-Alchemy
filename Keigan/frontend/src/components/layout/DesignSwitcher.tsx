import { Palette } from "lucide-react";
import { useTranslation } from "react-i18next";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import { IconButton } from "@/components/ui/IconButton";
import { designOptions, useDesign, type DesignId } from "@/hooks/useDesign";

/** Design system choice in the top bar, next to the light / dark toggle. */
export function DesignSwitcher() {
  const { t } = useTranslation("common");
  const { designId, setDesign } = useDesign();
  return (
    <DropdownMenu
      trigger={<IconButton icon={Palette} label={t("design.change")} />}
      entries={[
        {
          type: "radioGroup",
          key: "design",
          value: designId,
          onValueChange: (value) => setDesign(value as DesignId),
          options: designOptions.map((option) => ({ value: option.id, label: option.name })),
        },
      ]}
    />
  );
}
