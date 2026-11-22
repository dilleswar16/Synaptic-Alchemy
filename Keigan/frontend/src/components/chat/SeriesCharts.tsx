import { useTranslation } from "react-i18next";
import { SeriesChart } from "./SeriesChart";
import type { SeriesModel } from "./toolSeriesModels";

export interface SeriesChartsProps {
  models: readonly SeriesModel[];
  /** What the numbers are (the tool's own summary); each chart is named with it, and with its unit when the output has more than one chart. */
  title: string | undefined;
}

/** The charts of one tool output: one per unit of number (percentages, values, counts), never two units on one axis. */
export function SeriesCharts({ models, title }: SeriesChartsProps) {
  const { t } = useTranslation("chat");
  return (
    <>
      {models.map((model) => (
        <SeriesChart
          key={model.fieldKind}
          model={model}
          title={models.length > 1 && title !== undefined ? t("tool.fieldPair", { label: t(`tool.series.groups.${model.fieldKind}`), value: title }) : title}
        />
      ))}
    </>
  );
}
