import { useRef, useState, type ClipboardEvent, type KeyboardEvent } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { describedByIds, FormField, useFormFieldIds, type FieldDecorationProps } from "./FormField";
import { toneSoftClasses, type StatusTone } from "./toneStyles";

export interface TokenInputProps extends FieldDecorationProps {
  value: string[];
  onValueChange: (tokens: string[]) => void;
  placeholder?: string;
  /** Return an error message to reject a token, or null to accept it. */
  validateToken?: (token: string) => string | null;
  /** Normalise before validation, e.g. trim + upper-case codes. Defaults to trim. */
  normaliseToken?: (token: string) => string;
  /** Tone per token, e.g. neutral for "unverified", success for verified. Defaults to info. */
  getTokenTone?: (token: string) => StatusTone;
  maximumTokens?: number;
  disabled?: boolean;
  id?: string;
  className?: string;
}

const tokenSeparatorPattern = /[\n,;]+/;

/**
 * Free-text chips (assignment groups, tags, EAI codes). Enter, comma or Tab adds; Backspace on an empty box removes
 * the last chip; pasted lists split on new lines, commas and semicolons.
 */
export function TokenInput({
  value,
  onValueChange,
  placeholder,
  validateToken,
  normaliseToken = (token) => token.trim(),
  getTokenTone,
  maximumTokens,
  disabled,
  id,
  className,
  label,
  helperText,
  errorMessage,
  isOptional,
  labelAction,
}: TokenInputProps) {
  const { t } = useTranslation("common");
  const fieldIds = useFormFieldIds(id);
  const inputRef = useRef<HTMLInputElement>(null);
  const [draftText, setDraftText] = useState("");
  const [rejectionMessage, setRejectionMessage] = useState<string | null>(null);
  const shownError = errorMessage ?? rejectionMessage;
  const hasError = Boolean(shownError);

  const addTokens = (rawTokens: string[]): boolean => {
    const acceptedTokens = [...value];
    let lastRejection: string | null = null;
    for (const rawToken of rawTokens) {
      const token = normaliseToken(rawToken);
      if (!token) {
        continue;
      }
      if (maximumTokens !== undefined && acceptedTokens.length >= maximumTokens) {
        break;
      }
      if (acceptedTokens.includes(token)) {
        lastRejection = t("tokenInput.duplicateToken", { token });
        continue;
      }
      const validationMessage = validateToken?.(token) ?? null;
      if (validationMessage) {
        lastRejection = validationMessage;
        continue;
      }
      acceptedTokens.push(token);
    }
    setRejectionMessage(lastRejection);
    if (acceptedTokens.length !== value.length) {
      onValueChange(acceptedTokens);
    }
    return lastRejection === null;
  };

  const commitDraft = (): boolean => {
    if (!draftText.trim()) {
      return true;
    }
    const isAccepted = addTokens([draftText]);
    if (isAccepted) {
      setDraftText("");
    }
    return isAccepted;
  };

  const handleKeyDown = (keyboardEvent: KeyboardEvent<HTMLInputElement>) => {
    if (keyboardEvent.key === "Enter" || keyboardEvent.key === ",") {
      keyboardEvent.preventDefault();
      commitDraft();
    } else if (keyboardEvent.key === "Tab" && draftText.trim()) {
      keyboardEvent.preventDefault();
      commitDraft();
    } else if (keyboardEvent.key === "Backspace" && !draftText && value.length > 0) {
      onValueChange(value.slice(0, -1));
    }
  };

  const handlePaste = (clipboardEvent: ClipboardEvent<HTMLInputElement>) => {
    const pastedText = clipboardEvent.clipboardData.getData("text");
    if (tokenSeparatorPattern.test(pastedText)) {
      clipboardEvent.preventDefault();
      addTokens(pastedText.split(tokenSeparatorPattern));
    }
  };

  return (
    <FormField
      label={label}
      helperText={helperText}
      errorMessage={shownError}
      isOptional={isOptional}
      labelAction={labelAction}
      fieldIds={fieldIds}
      className={className}
    >
      <div
        onClick={() => inputRef.current?.focus()}
        aria-disabled={disabled || undefined}
        className={cn(
          "flex min-h-10 w-full flex-wrap items-center gap-1.5 rounded-sm border border-control bg-surface px-2 py-1.5 shadow-xs transition-[border-color,box-shadow]",
          "cursor-text hover:border-subtle focus-within:border-action focus-within:outline-3 focus-within:outline-focus focus-within:outline-offset-1",
          hasError && "border-danger-fill",
          disabled && "pointer-events-none bg-surface-sunken opacity-70",
        )}
      >
        {value.map((token) => (
          <span
            key={token}
            className={cn(
              "inline-flex h-7 max-w-full items-center gap-1 rounded-xs pr-1 pl-2 text-body-sm font-medium",
              toneSoftClasses[getTokenTone?.(token) ?? "info"],
            )}
          >
            <span className="truncate">{token}</span>
            <button
              type="button"
              aria-label={t("tokenInput.removeToken", { token })}
              onClick={(clickEvent) => {
                clickEvent.stopPropagation();
                onValueChange(value.filter((existingToken) => existingToken !== token));
              }}
              className="grid size-5 place-items-center rounded-[4px] opacity-70 hover:bg-black/10 hover:opacity-100"
            >
              <X aria-hidden="true" size={13} strokeWidth={2.25} />
            </button>
          </span>
        ))}
        <input
          ref={inputRef}
          id={fieldIds.controlId}
          value={draftText}
          disabled={disabled}
          onChange={(changeEvent) => {
            setDraftText(changeEvent.target.value);
            setRejectionMessage(null);
          }}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          onBlur={commitDraft}
          placeholder={value.length === 0 ? (placeholder ?? t("tokenInput.placeholder")) : undefined}
          aria-invalid={hasError || undefined}
          aria-describedby={describedByIds(fieldIds, Boolean(helperText), hasError)}
          className="h-7 min-w-32 flex-1 bg-transparent px-1 text-body text-default outline-none placeholder:text-subtle focus-visible:outline-none"
        />
      </div>
    </FormField>
  );
}
