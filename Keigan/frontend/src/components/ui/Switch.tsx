import { useId, type ReactNode } from "react";
import { Switch as RadixSwitch } from "radix-ui";
import { cn } from "@/utils/cn";

export interface SwitchProps {
  checked?: boolean;
  defaultChecked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  /** Visible label; when omitted pass `aria-label`. */
  label?: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  name?: string;
  id?: string;
  size?: "sm" | "md";
  className?: string;
  "aria-label"?: string;
}

/** On/off toggle (Radix Switch); Blue 2 when on. Label sits to the right. */
export function Switch({
  checked,
  defaultChecked,
  onCheckedChange,
  label,
  description,
  disabled,
  name,
  id,
  size = "md",
  className,
  ...ariaProps
}: SwitchProps) {
  const generatedId = useId();
  const switchId = id ?? `switch-${generatedId}`;
  const descriptionId = description ? `${switchId}-description` : undefined;
  return (
    <div className={cn("flex items-start gap-3", className)}>
      <RadixSwitch.Root
        id={switchId}
        checked={checked}
        defaultChecked={defaultChecked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        name={name}
        aria-label={ariaProps["aria-label"]}
        aria-describedby={descriptionId}
        className={cn(
          "relative mt-0.5 inline-flex shrink-0 items-center rounded-full border border-transparent bg-strong transition-colors duration-150",
          "data-[state=checked]:bg-action disabled:cursor-not-allowed disabled:opacity-50",
          size === "md" ? "h-5 w-9" : "h-4 w-7",
        )}
      >
        <RadixSwitch.Thumb
          className={cn(
            "block rounded-full bg-white shadow-sm transition-transform duration-150 ease-[var(--ease-standard)] data-[state=unchecked]:translate-x-0.5",
            size === "md" ? "size-4 data-[state=checked]:translate-x-[18px]" : "size-3 data-[state=checked]:translate-x-[14px]",
          )}
        />
      </RadixSwitch.Root>
      {label || description ? (
        <div className="min-w-0">
          {label ? (
            <label htmlFor={switchId} className={cn("block cursor-pointer text-body text-default", disabled && "cursor-not-allowed opacity-60")}>
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
