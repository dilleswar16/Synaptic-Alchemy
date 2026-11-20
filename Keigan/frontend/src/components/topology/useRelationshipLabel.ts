import { useTranslation } from "react-i18next";

/** Translates a service relationship such as `writes_to`; an unknown future value is shown with its underscores removed. */
export function useRelationshipLabel(): (relationship: string) => string {
  const { t } = useTranslation("common");
  return (relationship) => t(`topology.relationships.${relationship}`, { defaultValue: relationship.replaceAll("_", " ") });
}
