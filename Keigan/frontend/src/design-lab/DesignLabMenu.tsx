import { Brush } from "lucide-react";
import { isDeveloperEnvironment, useRuntimeConfiguration } from "@/config/runtimeConfiguration";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import { IconButton } from "@/components/ui/IconButton";
import { useDesign, type DesignId, designOptions } from "@/design/useDesign";
import { useTheme, type ThemePreference } from "@/hooks/useTheme";
import { labThemes, type LabId } from "./themes";
import { useDesignLab } from "./useDesignLab";

/** Top-bar shortcut for the design lab: company and light / dark from any page. Developer environments only, English-only. */
export function DesignLabMenu() {
  const runtimeConfiguration = useRuntimeConfiguration();
  const { labId, setLab } = useDesignLab();
  const { designId, setDesign } = useDesign();
  const { preference, setPreference } = useTheme();
  if (!isDeveloperEnvironment(runtimeConfiguration)) {
    return null;
  }
  return (
    <DropdownMenu
      trigger={<IconButton icon={Brush} label="Design lab" />}
      entries={[
        { type: "label", key: "design-label", label: "Keigan design" },
        {
          type: "radioGroup",
          key: "design",
          value: designId,
          onValueChange: (value) => setDesign(value as DesignId),
          options: designOptions.map((option) => ({ value: option.id, label: option.name })),
        },
        { type: "separator", key: "design-separator" },
        { type: "label", key: "company-label", label: "Company (design lab)" },
        {
          type: "radioGroup",
          key: "company",
          value: labId ?? "off",
          onValueChange: (value) => setLab(value === "off" ? null : (value as LabId)),
          options: [{ value: "off", label: "Keigan (lab off)" }, ...labThemes.map((theme) => ({ value: theme.id, label: theme.company }))],
        },
        { type: "separator", key: "mode-separator" },
        {
          type: "radioGroup",
          key: "mode",
          value: preference,
          onValueChange: (value) => setPreference(value as ThemePreference),
          options: [
            { value: "light", label: "Light" },
            { value: "dark", label: "Dark" },
          ],
        },
      ]}
    />
  );
}
