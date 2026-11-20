import { LayoutGrid, Rows3, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Input } from "@/components/ui/Input";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Switch } from "@/components/ui/Switch";
import { cn } from "@/utils/cn";
import { incidentPriorities, incidentSources, incidentStatusOrder } from "./incidentPresentation";

export type IncidentView = "table" | "board";

export interface IncidentFilterState {
  search: string;
  priorities: string[];
  statuses: string[];
  sources: string[];
  onlyMine: boolean;
  view: IncidentView;
}

interface FilterToggleGroupProps {
  label: string;
  values: readonly string[];
  selected: string[];
  getLabel: (value: string) => string;
  onChange: (selected: string[]) => void;
}

function FilterToggleGroup({ label, values, selected, getLabel, onChange }: FilterToggleGroupProps) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap items-center gap-1.5">
      <span className="text-caption font-semibold text-muted">{label}</span>
      {values.map((value) => {
        const isSelected = selected.includes(value);
        return (
          <button
            key={value}
            type="button"
            aria-pressed={isSelected}
            onClick={() => onChange(isSelected ? selected.filter((item) => item !== value) : [...selected, value])}
            className={cn(
              "h-7 rounded-full border px-3 text-caption font-medium transition-colors",
              isSelected ? "border-transparent bg-action-subtle text-action-subtle-text" : "border-strong bg-surface text-muted hover:bg-surface-hover",
            )}
          >
            {getLabel(value)}
          </button>
        );
      })}
    </div>
  );
}

interface IncidentFilterBarProps {
  filters: IncidentFilterState;
  onChange: (changes: Partial<IncidentFilterState>) => void;
}

/** Search, priority / status / source toggles, "only mine" and the table / board switch. All state lives in the URL. */
export function IncidentFilterBar({ filters, onChange }: IncidentFilterBarProps) {
  const { t } = useTranslation("incidents");
  return (
    <div className="mb-5 flex flex-col gap-3 rounded-lg border border-hairline bg-surface p-4 shadow-xs">
      <div className="flex flex-wrap items-center gap-3">
        <Input
          aria-label={t("filters.searchLabel")}
          placeholder={t("filters.searchPlaceholder")}
          leadingIcon={Search}
          value={filters.search}
          onChange={(event) => onChange({ search: event.target.value })}
          containerClassName="min-w-64 flex-1"
        />
        <Switch size="sm" checked={filters.onlyMine} onCheckedChange={(onlyMine) => onChange({ onlyMine })} label={t("filters.onlyMine")} />
        <SegmentedControl<IncidentView>
          aria-label={t("filters.viewLabel")}
          value={filters.view}
          onValueChange={(view) => onChange({ view })}
          options={[
            { value: "table", label: t("filters.viewTable"), icon: Rows3 },
            { value: "board", label: t("filters.viewBoard"), icon: LayoutGrid },
          ]}
        />
      </div>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <FilterToggleGroup label={t("filters.priority")} values={incidentPriorities} selected={filters.priorities} getLabel={(value) => value} onChange={(priorities) => onChange({ priorities })} />
        <FilterToggleGroup label={t("filters.status")} values={incidentStatusOrder} selected={filters.statuses} getLabel={(value) => t(`status.${value}`)} onChange={(statuses) => onChange({ statuses })} />
        <FilterToggleGroup label={t("filters.source")} values={incidentSources} selected={filters.sources} getLabel={(value) => t(`source.${value}`)} onChange={(sources) => onChange({ sources })} />
      </div>
    </div>
  );
}
