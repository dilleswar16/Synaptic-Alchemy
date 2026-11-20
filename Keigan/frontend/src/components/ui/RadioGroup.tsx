import type { ReactNode } from "react";
import { RadioGroup as RadixRadioGroup } from "radix-ui";
import { cn } from "@/utils/cn";
import { FormField, useFormFieldIds, type FieldDecorationProps } from "./FormField";

export interface RadioOption<Value extends string = string> {
  value: Value;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
}

export interface RadioGroupProps<Value extends string = string> extends FieldDecorationProps {
  options: RadioOption<Value>[];
  value?: Value;
  defaultValue?: Value;
  onValueChange?: (value: Value) => void;
  orientation?: "vertical" | "horizontal";
  /** `card` renders each option as a bordered, selectable tile. */
  variant?: "default" | "card";
  disabled?: boolean;
  name?: string;
  id?: string;
  className?: string;
  "aria-label"?: string;
}

/** Exclusive choice among a few visible options (Radix RadioGroup). */
export function RadioGroup<Value extends string = string>({
  options,
  value,
  defaultValue,
  onValueChange,
  orientation = "vertical",
  variant = "default",
  disabled,
  name,
  id,
  className,
  label,
  helperText,
  errorMessage,
  isOptional,
  labelAction,
  ...ariaProps
}: RadioGroupProps<Value>) {
  const fieldIds = useFormFieldIds(id);
  return (
    <FormField
      label={label}
      helperText={helperText}
      errorMessage={errorMessage}
      isOptional={isOptional}
      labelAction={labelAction}
      fieldIds={fieldIds}
      className={className}
      isLabelElementless
    >
      <RadixRadioGroup.Root
        id={fieldIds.controlId}
        value={value}
        defaultValue={defaultValue}
        onValueChange={(nextValue: string) => onValueChange?.(nextValue as Value)}
        orientation={orientation}
        disabled={disabled}
        name={name}
        aria-labelledby={label ? fieldIds.labelId : undefined}
        aria-label={ariaProps["aria-label"]}
        className={cn(orientation === "vertical" ? "flex flex-col gap-2.5" : "flex flex-wrap gap-x-6 gap-y-2.5", variant === "card" && "gap-2")}
      >
        {options.map((option) => {
          const optionId = `${fieldIds.controlId}-${option.value}`;
          return (
            <label
              key={option.value}
              htmlFor={optionId}
              className={cn(
                "group flex cursor-pointer items-start gap-2.5",
                variant === "card" &&
                  "rounded-md border border-hairline bg-surface p-3.5 transition-colors hover:bg-surface-hover has-[[data-state=checked]]:border-action has-[[data-state=checked]]:bg-surface-selected",
                option.disabled && "cursor-not-allowed opacity-60",
              )}
            >
              <RadixRadioGroup.Item
                id={optionId}
                value={option.value}
                disabled={option.disabled}
                className="mt-0.5 grid size-[18px] shrink-0 place-items-center rounded-full border-[1.5px] border-strong bg-surface transition-colors hover:border-action data-[state=checked]:border-action"
              >
                <RadixRadioGroup.Indicator className="size-2.5 rounded-full bg-action" />
              </RadixRadioGroup.Item>
              <span className="min-w-0">
                <span className="block text-body text-default">{option.label}</span>
                {option.description ? <span className="block text-caption text-muted">{option.description}</span> : null}
              </span>
            </label>
          );
        })}
      </RadixRadioGroup.Root>
    </FormField>
  );
}
