import { createContext, useContext, useId, useState, type ComponentProps, type ReactNode } from "react";
import { motion } from "motion/react";
import { Tabs as RadixTabs } from "radix-ui";
import { cn } from "@/utils/cn";
import { Badge } from "./Badge";

interface TabsContextValue {
  activeValue: string | undefined;
  indicatorLayoutId: string;
}

const TabsContext = createContext<TabsContextValue | null>(null);

export interface TabsProps extends Omit<ComponentProps<typeof RadixTabs.Root>, "value" | "defaultValue" | "onValueChange"> {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
}

/**
 * Underline tabs with a sliding 2 px Blue 2 indicator (doc 04 §5). Compose:
 * `<Tabs defaultValue="rca"><TabsList><TabsTrigger value="rca">RCA</TabsTrigger></TabsList><TabsContent value="rca">…</TabsContent></Tabs>`.
 * Controlled (`value` + `onValueChange`) or uncontrolled (`defaultValue`).
 */
export function Tabs({ value, defaultValue, onValueChange, className, children, ...rootProps }: TabsProps) {
  const [uncontrolledValue, setUncontrolledValue] = useState(defaultValue);
  const activeValue = value ?? uncontrolledValue;
  const indicatorLayoutId = `tabs-indicator-${useId()}`;

  const handleValueChange = (nextValue: string) => {
    if (value === undefined) {
      setUncontrolledValue(nextValue);
    }
    onValueChange?.(nextValue);
  };

  return (
    <TabsContext.Provider value={{ activeValue, indicatorLayoutId }}>
      <RadixTabs.Root value={activeValue} onValueChange={handleValueChange} className={cn("min-w-0", className)} {...rootProps}>
        {children}
      </RadixTabs.Root>
    </TabsContext.Provider>
  );
}

export function TabsList({ className, ...listProps }: ComponentProps<typeof RadixTabs.List>) {
  return (
    <RadixTabs.List
      className={cn("scrollbar-none flex min-w-0 items-end gap-6 overflow-x-auto border-b border-hairline", className)}
      {...listProps}
    />
  );
}

export interface TabsTriggerProps extends ComponentProps<typeof RadixTabs.Trigger> {
  /** Optional count shown as a micro badge. */
  count?: ReactNode;
}

export function TabsTrigger({ value, count, className, children, ...triggerProps }: TabsTriggerProps) {
  const tabsContext = useContext(TabsContext);
  const isActive = tabsContext?.activeValue === value;
  return (
    <RadixTabs.Trigger
      value={value}
      className={cn(
        "group relative -mb-px inline-flex h-11 shrink-0 items-center gap-2 px-0.5 text-body font-medium text-muted transition-colors",
        "hover:text-default data-[state=active]:text-default disabled:pointer-events-none disabled:opacity-50",
        className,
      )}
      {...triggerProps}
    >
      {children}
      {count !== undefined && count !== null ? (
        <Badge tone={isActive ? "info" : "neutral"} className="transition-colors">
          {count}
        </Badge>
      ) : null}
      {isActive && tabsContext ? (
        <motion.span
          layoutId={tabsContext.indicatorLayoutId}
          aria-hidden="true"
          className="absolute inset-x-0 bottom-0 h-0.5 rounded-full bg-action"
          transition={{ type: "spring", stiffness: 520, damping: 42 }}
        />
      ) : null}
    </RadixTabs.Trigger>
  );
}

export function TabsContent({ className, ...contentProps }: ComponentProps<typeof RadixTabs.Content>) {
  return <RadixTabs.Content className={cn("pt-6 focus-visible:outline-none", className)} {...contentProps} />;
}
