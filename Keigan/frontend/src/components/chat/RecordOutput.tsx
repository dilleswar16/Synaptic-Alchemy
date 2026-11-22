import { useTranslation } from "react-i18next";
import { KeyValueList, type KeyValueItem } from "@/components/ui/KeyValueList";
import { RecordListOutput } from "./RecordListOutput";
import { asRecordArray, fieldLabel, formatFieldValue, isHiddenField } from "./toolValues";

/** Fields every tool output carries for the engine and the card header; the result view does not repeat them. */
const envelopeFieldNames: ReadonlySet<string> = new Set(["summary", "records", "item_count", "total_count", "is_truncated", "is_simulated"]);

/**
 * One record, or the fields of any output that has no view of its own: a label and a value for each plain field, then each list of records inside it
 * (hypotheses, evidence, alerts, decisions, steps) as a titled list. The envelope and internal ids are left out.
 */
export function RecordOutput({ record, isCompact }: { record: Record<string, unknown>; isCompact: boolean }) {
  const { t } = useTranslation("chat");
  const entries = Object.entries(record).filter(([fieldName, value]) => !envelopeFieldNames.has(fieldName) && !isHiddenField(fieldName, record) && !(Array.isArray(value) && value.length === 0));
  const lists = entries.flatMap(([fieldName, value]) => {
    const items = asRecordArray(value);
    return Array.isArray(value) && items.length === value.length ? [{ fieldName, items }] : [];
  });
  const listFieldNames = new Set(lists.map((list) => list.fieldName));
  const items: KeyValueItem[] = entries
    .filter(([fieldName]) => !listFieldNames.has(fieldName))
    .map(([fieldName, value]) => ({ key: fieldName, label: fieldLabel(t, fieldName), value: <span className="whitespace-pre-wrap">{formatFieldValue(t, value)}</span> }));
  if (items.length === 0 && lists.length === 0) {
    return null;
  }
  return (
    <div className="flex flex-col gap-3">
      {items.length > 0 ? <KeyValueList items={items} dense layout={isCompact ? "stacked" : "columns"} /> : null}
      {lists.map(({ fieldName, items: listItems }) => (
        <section key={fieldName} className="flex flex-col gap-2">
          <h5 className="text-caption font-semibold text-muted">{fieldLabel(t, fieldName)}</h5>
          <RecordListOutput items={listItems} />
        </section>
      ))}
    </div>
  );
}
