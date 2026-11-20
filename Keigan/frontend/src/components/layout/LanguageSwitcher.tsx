import { Languages } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useRuntimeConfiguration } from "@/config/runtimeConfiguration";
import { changeApplicationLanguage, currentSupportedLocale, isSupportedLocale, localeDisplayNames, supportedLocales, type SupportedLocale } from "@/i18n";
import { DropdownMenu } from "@/components/ui/DropdownMenu";
import { IconButton } from "@/components/ui/IconButton";

/** Language menu (autonyms). Saves the choice on the user profile when signed in. */
export function LanguageSwitcher() {
  const { t, i18n } = useTranslation("common");
  const { supportedLocales: enabledLocales } = useRuntimeConfiguration();
  const offeredLocales = supportedLocales.filter((locale) => enabledLocales.includes(locale));
  const activeLocale = currentSupportedLocale();
  return (
    <DropdownMenu
      trigger={<IconButton icon={Languages} label={t("language.change")} />}
      entries={[
        {
          type: "radioGroup",
          key: "language",
          value: activeLocale,
          onValueChange: (value) => {
            if (isSupportedLocale(value)) {
              void changeApplicationLanguage(value as SupportedLocale);
            }
          },
          options: (offeredLocales.length > 0 ? offeredLocales : supportedLocales).map((locale) => ({
            value: locale,
            label: localeDisplayNames[locale],
            lang: locale,
          })),
        },
      ]}
      key={i18n.language}
    />
  );
}
