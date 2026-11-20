import { Monitor, Moon, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useTheme, type ThemePreference } from "@/hooks/useTheme";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import { IconButton } from "@/components/ui/IconButton";

/** Light / dark / system choice in the top bar. */
export function ThemeToggle() {
  const { t } = useTranslation("common");
  const { preference, resolvedTheme, setPreference } = useTheme();
  return (
    <DropdownMenu
      trigger={<IconButton icon={resolvedTheme === "dark" ? Moon : Sun} label={t("theme.change")} />}
      entries={[
        {
          type: "radioGroup",
          key: "theme",
          value: preference,
          onValueChange: (value) => setPreference(value as ThemePreference),
          options: [
            { value: "light", label: t("theme.light"), icon: Sun },
            { value: "dark", label: t("theme.dark"), icon: Moon },
            { value: "system", label: t("theme.system"), icon: Monitor },
          ],
        },
      ]}
    />
  );
}
