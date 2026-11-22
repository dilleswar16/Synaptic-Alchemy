import { useTranslation } from "react-i18next";
import { formatList } from "@/utils/formatters";
import { fieldLabel, formatFieldValue, isHiddenField, isScalar } from "./toolValues";

/** The field that titles an item of a list, in order of preference: a title, a name or a label of its own, else the first field whose name ends in one of them. */
const itemTitleFieldNames = ["title", "name", "label", "summary", "description"] as const;
const itemTitleFieldSuffixes = ["_title", "_label", "alias", "rule_name", "detector_name", "sli_name"] as const;

function itemTitleFieldName(item: Record<string, unknown>): string | undefined {
  const isText = (fieldName: string) => typeof item[fieldName] === "string" && item[fieldName] !== "";
  return itemTitleFieldNames.find(isText) ?? itemTitleFieldSuffixes.flatMap((suffix) => Object.keys(item).filter((fieldName) => fieldName.endsWith(suffix))).find(isText);
}

/** The items of a list output (or of a list inside a record): a title, then the item's other plain fields as "label: value" pairs; internal ids are left out. */
export function RecordListOutput({ items }: { items: Array<Record<string, unknown>> }) {
  const { t } = useTranslation("chat");
  return (
    <ul className="flex flex-col gap-2">
      {items.map((item, itemIndex) => {
        const titleFieldName = itemTitleFieldName(item);
        const detailFieldNames = Object.keys(item).filter((fieldName) => fieldName !== titleFieldName && !isHiddenField(fieldName, item) && isScalar(item[fieldName]) && item[fieldName] !== null && item[fieldName] !== "");
        return (
          <li key={itemIndex} className="rounded-md border border-hairline bg-surface-sunken px-3 py-2">
            {titleFieldName ? <p className="text-body-sm font-medium break-words text-default">{String(item[titleFieldName])}</p> : null}
            <p className="text-caption break-words text-muted">
              {formatList(detailFieldNames.map((fieldName) => t("tool.fieldPair", { label: fieldLabel(t, fieldName), value: formatFieldValue(t, item[fieldName]) })))}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
