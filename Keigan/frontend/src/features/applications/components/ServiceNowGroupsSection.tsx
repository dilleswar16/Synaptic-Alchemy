import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { searchServiceNowGroups, useReplaceServiceNowGroups, useServiceNowGroups } from "@/api/applicationsApi";
import { Combobox } from "@/components/ui/Combobox";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { TokenInput } from "@/components/ui/TokenInput";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";

/** Step 7a: ServiceNow assignment groups Keigan polls. Typeahead when ServiceNow is connected, free-text tokens saved as unverified otherwise. */
export function ServiceNowGroupsSection({ applicationId, canEdit, onChanged }: { applicationId: string; canEdit: boolean; onChanged?: () => void }) {
  const { t } = useTranslation("onboarding");
  const groupsQuery = useServiceNowGroups(applicationId);
  const replaceGroups = useReplaceServiceNowGroups(applicationId);
  const [searchText, setSearchText] = useState("");
  const debouncedSearch = useDebouncedValue(searchText, 250);
  const suggestionsQuery = useQuery({ queryKey: ["servicenow-search", debouncedSearch], queryFn: () => searchServiceNowGroups(debouncedSearch), enabled: canEdit });
  const groups = groupsQuery.data ?? [];
  const groupNames = groups.map((group) => group.groupName);
  const verifiedNames = new Set(groups.filter((group) => group.verificationStatus === "verified").map((group) => group.groupName));

  const save = (names: string[]) => replaceGroups.mutate(names, { onSuccess: onChanged });

  return (
    <section className="flex flex-col gap-4">
      <SectionHeader level={3} title={t("servicenow.title")} description={t("servicenow.description")} />
      <TokenInput
        label={t("servicenow.groups")}
        helperText={t("servicenow.groupsHelp")}
        placeholder={t("servicenow.placeholder")}
        disabled={!canEdit}
        maximumTokens={20}
        value={groupNames}
        onValueChange={save}
        getTokenTone={(token) => (verifiedNames.has(token) ? "success" : "neutral")}
      />
      {canEdit ? (
        <Combobox
          aria-label={t("servicenow.search")}
          placeholder={t("servicenow.search")}
          searchPlaceholder={t("servicenow.searchPlaceholder")}
          value={null}
          onSearchChange={setSearchText}
          isLoading={suggestionsQuery.isFetching}
          options={(suggestionsQuery.data ?? []).filter((suggestion) => !groupNames.includes(suggestion.groupName)).map((suggestion) => ({ value: suggestion.groupName, label: suggestion.groupName }))}
          onValueChange={(selected) => { if (selected) save([...groupNames, selected]); }}
        />
      ) : null}
    </section>
  );
}
