import { useId, type ReactNode } from "react";
import { Check, Minus } from "lucide-react";
import { Checkbox as RadixCheckbox } from "radix-ui";
import { cn } from "@/utils/cn";

export type CheckedState = boolean | "indeterminate";

export interface CheckboxProps {
  checked?: CheckedState;
  defaultChecked?: CheckedState;
  onCheckedChange?: (checked: CheckedState) => void;
  label?: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  name?: string;
  value?: string;
  id?: string;
  className?: string;
  "aria-label"?: string;
}

/** Radix checkbox (Blue 2 when checked) with optional label and description; supports "indeterminate". */
export function Checkbox({
  checked,
  defaultChecked,
  onCheckedChange,
  label,
  description,
  disabled,
  name,
  value,
  id,
  className,
  ...ariaProps
}: CheckboxProps) {
  const generatedId = useId();
  const checkboxId = id ?? `checkbox-${generatedId}`;
  const descriptionId = description ? `${checkboxId}-description` : undefined;
  return (
    <div className={cn("flex items-start gap-2.5", className)}>
      <RadixCheckbox.Root
        id={checkboxId}
        checked={checked}
        defaultChecked={defaultChecked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        name={name}
        value={value}
        aria-label={ariaProps["aria-label"]}
        aria-describedby={descriptionId}
        className={cn(
          "mt-0.5 grid size-[18px] shrink-0 place-items-center rounded-[5px] border-[1.5px] border-control bg-surface text-on-action transition-colors",
          "hover:border-action data-[state=checked]:border-action data-[state=checked]:bg-action",
          "data-[state=indeterminate]:border-action data-[state=indeterminate]:bg-action disabled:cursor-not-allowed disabled:opacity-50",
        )}
      >
        <RadixCheckbox.Indicator>
          {checked === "indeterminate" ? (
            <Minus aria-hidden="true" size={13} strokeWidth={3} />
          ) : (
            <Check aria-hidden="true" size={13} strokeWidth={3} />
          )}
        </RadixCheckbox.Indicator>
      </RadixCheckbox.Root>
      {label || description ? (
        <div className="min-w-0">
          {label ? (
            <label htmlFor={checkboxId} className={cn("block cursor-pointer text-body text-default", disabled && "cursor-not-allowed opacity-60")}>
              {label}
            </label>
          ) : null}
          {description ? (
            <p id={descriptionId} className="text-caption text-muted">
              {description}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
