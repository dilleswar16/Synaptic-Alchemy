import { useState, type FormEvent } from "react";
import { SendHorizontal, Square } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { cn } from "@/utils/cn";

export interface ChatComposerProps {
  /** Called with the trimmed text; the composer clears itself afterwards. */
  onSend: (messageText: string) => void;
  isSending?: boolean;
  /** Called by the Stop button and the Esc key while `isSending`; without it the button stays Send and shows a spinner. */
  onStop?: () => void;
  isDisabled?: boolean;
  placeholder?: string;
  className?: string;
}

/** On a phone the button is a 44 px square with the icon alone; its word stays in the accessible name (spec 8.2). */
const phoneIconButtonClassName = "max-sm:size-11 max-sm:gap-0 max-sm:px-0";

/** Multi-line composer: Enter sends, Shift+Enter adds a line (max 6 lines). */
export function ChatComposer({ onSend, isSending = false, onStop, isDisabled = false, placeholder, className }: ChatComposerProps) {
  const { t } = useTranslation("chat");
  const [draft, setDraft] = useState("");
  const canSend = draft.trim().length > 0 && !isSending && !isDisabled;
  const isStoppable = isSending && onStop !== undefined;
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
          if (event.key === "Escape" && isStoppable) {
            event.preventDefault();
            onStop();
          } else if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
        rows={1} autoResize maximumRows={6} containerClassName="flex-1"
      />
      {isStoppable ? (
        <Button type="button" variant="secondary" size="lg" leadingIcon={Square} onClick={onStop} className={phoneIconButtonClassName}><span className="max-sm:sr-only">{t("composer.stop")}</span></Button>
      ) : (
        <Button type="submit" size="lg" leadingIcon={SendHorizontal} disabled={!canSend} isLoading={isSending} className={phoneIconButtonClassName}><span className="max-sm:sr-only">{t("composer.send")}</span></Button>
      )}
    </form>
  );
}
