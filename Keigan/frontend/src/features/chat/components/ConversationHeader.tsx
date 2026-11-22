import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/Badge";

export interface ConversationHeaderProps {
  /** Null while an existing conversation is loading. */
  title: string | null;
  /** The applications the conversation looks at; empty means all of the person's applications. Null while an existing conversation is loading. */
  applicationNames: readonly string[] | null;
}

/** The title of the conversation and the applications it looks at. */
export function ConversationHeader({ title, applicationNames }: ConversationHeaderProps) {
  const { t } = useTranslation("chat");
  return (
    <header className="flex flex-wrap items-center gap-2 border-b border-hairline px-5 py-3">
      <h2 className="mr-2 min-w-0 truncate text-body font-semibold text-default">{title ?? t("conversation.newTitle")}</h2>
      {applicationNames === null ? null : (
        <>
          <span className="text-caption text-muted">{t("conversation.scope")}</span>
          {applicationNames.length === 0 ? <Badge tone="neutral">{t("conversation.allApplications")}</Badge> : applicationNames.map((name) => <Badge key={name} tone="brand">{name}</Badge>)}
        </>
      )}
    </header>
  );
}
