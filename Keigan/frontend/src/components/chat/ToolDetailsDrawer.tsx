import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/Badge";
import { Drawer } from "@/components/ui/Drawer";
import { EvidenceChip } from "@/components/ui/EvidenceChip";
import { ToolCardBody, type ToolCardBodyProps } from "./ToolCardBody";
import { toolTargetLabel } from "./toolCardState";

export interface ToolDetailsDrawerProps extends ToolCardBodyProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Tool label, for the title. */
  title: string;
}

/** The details of one tool call in a side sheet: where the container is too narrow to open them inside the card (the investigation panel, spec 8.2). */
export function ToolDetailsDrawer({ open, onOpenChange, title, ...bodyProps }: ToolDetailsDrawerProps) {
  const { t } = useTranslation("chat");
  const { tool } = bodyProps;
  const targetLabel = toolTargetLabel(tool);
  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      size="md"
      title={title}
      description={t("drawer.detailsDescription")}
      headerContent={
        targetLabel || tool.citationCode ? (
          <div className="flex flex-wrap items-center gap-2">
            {targetLabel ? <Badge tone="brand" className="max-w-full"><span className="min-w-0 truncate">{targetLabel}</span></Badge> : null}
            {tool.citationCode ? <EvidenceChip code={tool.citationCode} /> : null}
          </div>
        ) : null
      }
    >
      <ToolCardBody {...bodyProps} />
    </Drawer>
  );
}
