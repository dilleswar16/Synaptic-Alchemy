import { useState, type FormEvent } from "react";
import { SendHorizontal } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { cn } from "@/utils/cn";

export interface ChatComposerProps {
  /** Called with the trimmed text; the composer clears itself afterwards. */
  onSend: (messageText: string) => void;
  isSending?: boolean;
  isDisabled?: boolean;
  placeholder?: string;
  className?: string;
}

/** Multi-line composer: Enter sends, Shift+Enter adds a line (max 6 lines). */
export function ChatComposer({ onSend, isSending = false, isDisabled = false, placeholder, className }: ChatComposerProps) {
  const { t } = useTranslation("chat");
  const [draft, setDraft] = useState("");
  const canSend = draft.trim().length > 0 && !isSending && !isDisabled;
  const submit = () => {
    if (!canSend) return;
    onSend(draft.trim());
    setDraft("");
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };
  return (
    <form onSubmit={onSubmit} className={cn("flex items-end gap-2", className)}>
      <Textarea
        aria-label={t("composer.label")} placeholder={placeholder ?? t("composer.placeholder")} value={draft} onChange={(event) => setDraft(event.target.value)} disabled={isDisabled}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
        rows={1} autoResize maximumRows={6} containerClassName="flex-1"
      />
      <Button type="submit" size="lg" leadingIcon={SendHorizontal} disabled={!canSend} isLoading={isSending}>{t("composer.send")}</Button>
    </form>
  );
}
