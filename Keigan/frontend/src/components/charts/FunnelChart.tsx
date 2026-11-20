import { useTranslation } from "react-i18next";
import { formatNumber, formatPercentage } from "@/utils/formatters";
import { ChartFrame } from "./ChartFrame";
import { chartColorForIndex } from "./chartTheme";

export interface FunnelStage {
  key: string;
  label: string;
  count: number;
  color?: string;
}

export interface FunnelChartProps {
  stages: FunnelStage[];
  ariaLabel: string;
  className?: string;
}

/** Horizontal funnel (alerts → groups → incidents): bar width follows the count; shows count and share of stage 1. */
export function FunnelChart({ stages, ariaLabel, className }: FunnelChartProps) {
  const { t } = useTranslation("common");
  const firstCount = stages[0]?.count ?? 0;
  if (stages.length === 0 || firstCount <= 0) {
    return <p className="py-10 text-center text-body-sm text-muted">{t("chart.noData")}</p>;
  }
  return (
    <ChartFrame
      ariaLabel={ariaLabel}
      className={className}
      tableData={{
        columns: [
          { key: "stage", header: t("chart.stage") },
          { key: "count", header: t("chart.count"), align: "end" },
          { key: "share", header: t("chart.share"), align: "end" },
        ],
        rows: stages.map((stage) => ({
          __rowKey: stage.key,
          stage: stage.label,
          count: formatNumber(stage.count),
          share: formatPercentage((stage.count / firstCount) * 100),
        })),
      }}
    >
      <ol className="flex flex-col gap-2">
        {stages.map((stage, stageIndex) => {
          const widthPercentage = Math.max((stage.count / firstCount) * 100, 2);
          return (
            <li key={stage.key} className="grid grid-cols-[minmax(96px,160px)_1fr] items-center gap-3 sm:grid-cols-[minmax(120px,200px)_1fr]">
              <span className="text-body-sm text-default">{stage.label}</span>
              <div className="flex items-center gap-3">
                <div className="h-8 min-w-0 flex-1 rounded-xs bg-surface-sunken">
                  <div
                    className="h-full rounded-xs transition-[width] duration-300"
                    style={{ width: `${widthPercentage}%`, backgroundColor: stage.color ?? chartColorForIndex(stageIndex === 0 ? 0 : 4), opacity: 1 - stageIndex * 0.08 }}
                  />
                </div>
                <span className="w-28 shrink-0 text-body-sm tabular-numbers text-default">
                  <strong className="font-semibold">{formatNumber(stage.count)}</strong>
                  {stageIndex > 0 ? <span className="ml-1.5 text-caption text-muted">{formatPercentage((stage.count / firstCount) * 100)}</span> : null}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </ChartFrame>
  );
}
