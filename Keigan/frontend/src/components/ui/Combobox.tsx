import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Check, ChevronsUpDown, Search, X } from "lucide-react";
import { Popover as RadixPopover } from "radix-ui";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { controlBoxClassName, describedByIds, FormField, useFormFieldIds, type FieldDecorationProps } from "./FormField";
import { Spinner } from "./Spinner";

export interface ComboboxOption {
  value: string;
  label: string;
  description?: string;
  /** Extra words that should match the search (codes, aliases). */
  keywords?: string[];
  disabled?: boolean;
}

export interface ComboboxProps extends FieldDecorationProps {
  options: ComboboxOption[];
  value: string | null;
  onValueChange: (value: string | null) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: ReactNode;
  /**
   * Called with the search text. When provided, filtering is the caller's job (server-side typeahead):
   * pass the matching `options` and `isLoading`.
   */
  onSearchChange?: (searchText: string) => void;
  isLoading?: boolean;
  /** Show a clear button when a value is selected. */
  isClearable?: boolean;
  disabled?: boolean;
  id?: string;
  size?: "sm" | "md";
  className?: string;
  "aria-label"?: string;
}

function optionMatches(option: ComboboxOption, normalisedSearchText: string): boolean {
  if (!normalisedSearchText) {
    return true;
  }
  const searchableText = [option.label, option.description ?? "", ...(option.keywords ?? [])].join(" ").toLowerCase();
  return normalisedSearchText.split(/\s+/).every((searchWord) => searchableText.includes(searchWord));
}

/** Searchable single select (popover with a filter box and a keyboard-navigable listbox). */
export function Combobox({
  options,
  value,
  onValueChange,
  placeholder,
  searchPlaceholder,
  emptyText,
  onSearchChange,
  isLoading = false,
  isClearable = false,
  disabled,
  id,
  size = "md",
  className,
  label,
  helperText,
  errorMessage,
  isOptional,
  labelAction,
  ...ariaProps
}: ComboboxProps) {
  const { t } = useTranslation("common");
  const fieldIds = useFormFieldIds(id);
  const listboxId = `${fieldIds.controlId}-listbox`;
  const optionIdPrefix = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const listboxRef = useRef<HTMLUListElement>(null);
  const hasError = Boolean(errorMessage);

  const selectedOption = options.find((option) => option.value === value) ?? null;
  const visibleOptions = useMemo(
    () => (onSearchChange ? options : options.filter((option) => optionMatches(option, searchText.trim().toLowerCase()))),
    [options, onSearchChange, searchText],
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [searchText, isOpen]);

  useEffect(() => {
    listboxRef.current?.querySelector(`[data-option-index="${activeIndex}"]`)?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  const selectOption = (option: ComboboxOption) => {
    if (option.disabled) {
      return;
    }
    onValueChange(option.value);
    setIsOpen(false);
    setSearchText("");
  };

  const handleSearchKeyDown = (keyboardEvent: KeyboardEvent<HTMLInputElement>) => {
    if (keyboardEvent.key === "ArrowDown") {
      keyboardEvent.preventDefault();
      setActiveIndex((currentIndex) => Math.min(currentIndex + 1, visibleOptions.length - 1));
    } else if (keyboardEvent.key === "ArrowUp") {
      keyboardEvent.preventDefault();
      setActiveIndex((currentIndex) => Math.max(currentIndex - 1, 0));
    } else if (keyboardEvent.key === "Enter") {
      keyboardEvent.preventDefault();
      const activeOption = visibleOptions[activeIndex];
      if (activeOption) {
        selectOption(activeOption);
      }
    }
  };

  const activeOptionId = visibleOptions[activeIndex] ? `${optionIdPrefix}-option-${activeIndex}` : undefined;

  return (
    <FormField
      label={label}
      helperText={helperText}
      errorMessage={errorMessage}
      isOptional={isOptional}
      labelAction={labelAction}
      fieldIds={fieldIds}
      className={className}
    >
      <RadixPopover.Root
        open={isOpen}
        onOpenChange={(nextOpen: boolean) => {
          setIsOpen(nextOpen);
          if (!nextOpen) {
            setSearchText("");
            onSearchChange?.("");
          }
        }}
      >
        <div className="relative">
          <RadixPopover.Trigger asChild disabled={disabled}>
            <button
              type="button"
              id={fieldIds.controlId}
              role="combobox"
              aria-expanded={isOpen}
              aria-controls={listboxId}
              aria-haspopup="listbox"
              aria-label={ariaProps["aria-label"]}
              aria-invalid={hasError || undefined}
              aria-describedby={describedByIds(fieldIds, Boolean(helperText), hasError)}
              className={cn(
                controlBoxClassName(size),
                "inline-flex items-center justify-between gap-2 text-left",
                !selectedOption && "text-subtle",
                isClearable && selectedOption && "pr-16",
              )}
            >
              <span className="min-w-0 truncate">{selectedOption?.label ?? placeholder ?? t("combobox.placeholder")}</span>
              <ChevronsUpDown aria-hidden="true" size={16} strokeWidth={1.75} className="shrink-0 text-muted" />
            </button>
          </RadixPopover.Trigger>
          {isClearable && selectedOption && !disabled ? (
            <button
              type="button"
              aria-label={t("combobox.clearSelection")}
              onClick={() => onValueChange(null)}
              className="absolute top-1/2 right-8 grid size-6 -translate-y-1/2 place-items-center rounded-xs text-muted hover:bg-surface-hover hover:text-default"
            >
              <X aria-hidden="true" size={14} />
            </button>
          ) : null}
        </div>
        <RadixPopover.Portal>
          <RadixPopover.Content
            align="start"
            sideOffset={6}
            collisionPadding={8}
            className={cn(
              "z-[60] w-[var(--radix-popover-trigger-width)] min-w-64 overflow-hidden rounded-md border border-hairline bg-surface shadow-lg",
              "data-[state=closed]:animate-pop-out data-[state=open]:animate-pop-in",
            )}
          >
            <div className="flex items-center gap-2 border-b border-hairline px-3">
              <Search aria-hidden="true" size={16} className="shrink-0 text-subtle" />
              <input
                autoFocus
                value={searchText}
                onChange={(changeEvent) => {
                  setSearchText(changeEvent.target.value);
                  onSearchChange?.(changeEvent.target.value);
                }}
                onKeyDown={handleSearchKeyDown}
                placeholder={searchPlaceholder ?? t("combobox.searchPlaceholder")}
                aria-controls={listboxId}
                aria-activedescendant={activeOptionId}
                aria-autocomplete="list"
                className="h-10 w-full bg-transparent text-body text-default outline-none placeholder:text-subtle focus-visible:outline-none"
              />
              {isLoading ? <Spinner size="sm" className="text-muted" /> : null}
            </div>
            <ul ref={listboxRef} id={listboxId} role="listbox" aria-labelledby={label ? fieldIds.labelId : undefined} className="max-h-72 overflow-y-auto p-1">
              {visibleOptions.length === 0 && !isLoading ? (
                <li className="px-3 py-6 text-center text-body-sm text-muted">{emptyText ?? t("combobox.noMatches")}</li>
              ) : null}
              {visibleOptions.map((option, optionIndex) => {
                const isSelected = option.value === value;
                return (
                  <li
                    key={option.value}
                    id={`${optionIdPrefix}-option-${optionIndex}`}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={option.disabled || undefined}
                    data-option-index={optionIndex}
                    onMouseMove={() => setActiveIndex(optionIndex)}
                    onClick={() => selectOption(option)}
                    className={cn(
                      "relative flex cursor-pointer items-start gap-2 rounded-sm py-2 pr-9 pl-2.5 text-body text-default",
                      optionIndex === activeIndex && "bg-surface-hover",
                      option.disabled && "pointer-events-none opacity-50",
                    )}
                  >
                    <span className="min-w-0">
                      <span className={cn("block truncate", isSelected && "font-medium")}>{option.label}</span>
                      {option.description ? <span className="block text-caption text-muted">{option.description}</span> : null}
                    </span>
                    {isSelected ? <Check aria-hidden="true" size={16} strokeWidth={2.25} className="absolute top-2.5 right-2.5 text-action" /> : null}
                  </li>
                );
              })}
            </ul>
          </RadixPopover.Content>
        </RadixPopover.Portal>
      </RadixPopover.Root>
    </FormField>
  );
}
