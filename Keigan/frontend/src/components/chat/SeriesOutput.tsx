import { RecordOutput } from "./RecordOutput";
import { SeriesCharts } from "./SeriesCharts";
import { withoutSeries, type SeriesModel } from "./toolSeriesModels";
import { asText } from "./toolValues";

/** The result of a series tool: the charts with their numbers in words, then the output's other fields (what it is a series of, its target). */
export function SeriesOutput({ record, models, isCompact }: { record: Record<string, unknown>; models: readonly SeriesModel[]; isCompact: boolean }) {
  return (
    <div className="flex flex-col gap-3">
      <SeriesCharts models={models} title={asText(record.summary)} />
      <RecordOutput record={withoutSeries(record, models)} isCompact={isCompact} />
    </div>
  );
}
