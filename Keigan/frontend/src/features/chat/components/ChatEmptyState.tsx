import { useTranslation } from "react-i18next";
import type { SuggestedPrompt } from "@/api/chatApi";
import { KeiganLogo } from "@/components/layout/KeiganLogo";

export interface ChatEmptyStateProps {
  prompts: readonly SuggestedPrompt[];
  onAsk: (messageText: string) => void;
}

/** What an empty conversation shows: what Keigan can do, and the suggested questions as cards. */
export function ChatEmptyState({ prompts, onAsk }: ChatEmptyStateProps) {
  const { t } = useTranslation("chat");
  return (
    <div className="m-auto flex w-full max-w-3xl flex-col items-center gap-6 text-center">
      <KeiganLogo variant="mark" size={56} />
      <h2 className="text-h2 font-semibold text-default">{t("empty.title")}</h2>
      <p className="text-body text-muted">{t("empty.description")}</p>
      <ul className="grid w-full grid-cols-1 gap-3 text-left sm:grid-cols-2 lg:grid-cols-3">
        {prompts.map((prompt) => (
          <li key={prompt.promptText}>
            <button type="button" onClick={() => onAsk(prompt.promptText)} className="h-full w-full rounded-lg border border-hairline bg-surface p-3 text-body-sm text-default shadow-xs transition hover:-translate-y-px hover:bg-surface-hover hover:shadow-sm">
              <span className="mb-1 block text-caption font-medium text-muted">{t(`empty.category.${prompt.category}`)}</span>
              {prompt.promptText}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
