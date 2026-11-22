import { useTranslation } from "react-i18next";
import { Switch } from "@/components/ui/Switch";
import { useToolDetailsPreference } from "./useToolDetailsPreference";

/** The "Show tool details" switch of a conversation (spec 8.6); it reads and writes the preference shared by every conversation. */
export function ToolDetailsSwitch({ className }: { className?: string }) {
  const { t } = useTranslation("chat");
  const { showToolDetails, setShowToolDetails } = useToolDetailsPreference();
  return <Switch size="sm" checked={showToolDetails} onCheckedChange={setShowToolDetails} label={<span className="text-body-sm">{t("trace.showDetails")}</span>} className={className} />;
}
