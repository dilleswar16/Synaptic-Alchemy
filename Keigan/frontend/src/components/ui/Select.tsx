import type { ReactNode } from "react";
import { Check, ChevronDown } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Select as RadixSelect } from "radix-ui";
import { useTranslation } from "react-i18next";
import { cn } from "@/utils/cn";
import { controlBoxClassName, describedByIds, FormField, useFormFieldIds, type FieldDecorationProps } from "./FormField";

export interface SelectOption<Value extends string = string> {
  /** Must be a non-empty string (Radix reserves "" for "no value"). */
  value: Value;
  label: ReactNode;
  description?: ReactNode;
  icon?: LucideIcon;
  disabled?: boolean;
}

export interface SelectProps<Value extends string = string> extends FieldDecorationProps {
  options: SelectOption<Value>[];
  value?: Value;
  defaultValue?: Value;
  onValueChange?: (value: Value) => void;
  placeholder?: ReactNode;
  disabled?: boolean;
  name?: string;
  id?: string;
  size?: "sm" | "md";
  className?: string;
  /** Accessible name when there is no visible label. */
  "aria-label"?: string;
}

/** Single-choice dropdown (Radix Select) styled like an input. Use `Combobox` when the list needs search. */
export function Select<Value extends string = string>({
  options,
  value,
  defaultValue,
  onValueChange,
  placeholder,
  disabled,
  name,
  id,
  size = "md",
  className,
  label,
  helperText,
  errorMessage,
  isOptional,
  labelAction,
  ...ariaProps
}: SelectProps<Value>) {
  const { t } = useTranslation("common");
  const fieldIds = useFormFieldIds(id);
  const hasError = Boolean(errorMessage);
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
      <RadixSelect.Root
        value={value}
        defaultValue={defaultValue}
        onValueChange={(nextValue: string) => onValueChange?.(nextValue as Value)}
        disabled={disabled}
        name={name}
      >
        <RadixSelect.Trigger
          id={fieldIds.controlId}
          aria-label={ariaProps["aria-label"]}
          aria-invalid={hasError || undefined}
          aria-describedby={describedByIds(fieldIds, Boolean(helperText), hasError)}
          className={cn(
            controlBoxClassName(size),
            "inline-flex items-center justify-between gap-2 text-left data-[placeholder]:text-subtle",
          )}
        >
          <span className="min-w-0 truncate">
            <RadixSelect.Value placeholder={placeholder ?? t("select.placeholder")} />
          </span>
          <RadixSelect.Icon className="shrink-0 text-muted">
            <ChevronDown aria-hidden="true" size={18} strokeWidth={1.75} />
          </RadixSelect.Icon>
        </RadixSelect.Trigger>
        <RadixSelect.Portal>
          <RadixSelect.Content
            position="popper"
            sideOffset={6}
            collisionPadding={8}
            className={cn(
              "z-[60] max-h-[min(var(--radix-select-content-available-height),360px)] min-w-[var(--radix-select-trigger-width)] overflow-hidden",
              "rounded-md border border-hairline bg-surface shadow-lg data-[state=closed]:animate-pop-out data-[state=open]:animate-pop-in",
            )}
          >
            <RadixSelect.Viewport className="p-1">
              {options.map((option) => {
                const OptionIcon = option.icon;
                return (
                  <RadixSelect.Item
                    key={option.value}
                    value={option.value}
                    disabled={option.disabled}
                    className={cn(
                      "relative flex cursor-pointer select-none items-start gap-2.5 rounded-sm py-2 pr-9 pl-2.5 text-body text-default outline-none",
                      "data-[highlighted]:bg-surface-hover data-[disabled]:pointer-events-none data-[disabled]:opacity-50 data-[state=checked]:font-medium",
                    )}
                  >
                    {OptionIcon ? <OptionIcon aria-hidden="true" size={18} strokeWidth={1.75} className="mt-0.5 shrink-0 text-muted" /> : null}
                    <span className="min-w-0">
                      <RadixSelect.ItemText>{option.label}</RadixSelect.ItemText>
                      {option.description ? <span className="block text-caption font-normal text-muted">{option.description}</span> : null}
                    </span>
                    <RadixSelect.ItemIndicator className="absolute top-2.5 right-2.5 text-action">
                      <Check aria-hidden="true" size={16} strokeWidth={2.25} />
                    </RadixSelect.ItemIndicator>
                  </RadixSelect.Item>
                );
              })}
            </RadixSelect.Viewport>
          </RadixSelect.Content>
        </RadixSelect.Portal>
      </RadixSelect.Root>
    </FormField>
  );
}
