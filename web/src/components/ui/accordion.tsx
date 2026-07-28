"use client";

import { Accordion as AccordionPrimitive } from "@base-ui/react/accordion";
import { ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

type AccordionProps = Omit<
  React.ComponentProps<typeof AccordionPrimitive.Root>,
  "value" | "defaultValue" | "onValueChange" | "multiple"
> & {
  /** Radix-style API: "single" allows one open item, "multiple" allows several. */
  type?: "single" | "multiple";
  /** Radix-style flag; Base UI single-mode items are always collapsible. */
  collapsible?: boolean;
  value?: string | string[];
  defaultValue?: string | string[];
  onValueChange?: (value: string | string[]) => void;
};

function Accordion({
  type = "single",
  collapsible: _collapsible,
  value,
  defaultValue,
  onValueChange,
  ...props
}: AccordionProps) {
  const toArray = (v: string | string[] | undefined) => (v === undefined ? undefined : Array.isArray(v) ? v : [v]);
  return (
    <AccordionPrimitive.Root
      multiple={type === "multiple"}
      value={toArray(value)}
      defaultValue={toArray(defaultValue)}
      onValueChange={
        onValueChange
          ? (values: string[]) =>
              type === "multiple" ? onValueChange(values) : onValueChange(values[values.length - 1] ?? "")
          : undefined
      }
      {...props}
    />
  );
}

const AccordionItem = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Item>
>(({ className, ...props }, ref) => (
  <AccordionPrimitive.Item ref={ref} className={cn("border-b", className)} {...props} />
));
AccordionItem.displayName = "AccordionItem";

const AccordionTrigger = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Header className="flex">
    <AccordionPrimitive.Trigger
      ref={ref}
      className={cn(
        "flex flex-1 items-center justify-between py-4 font-medium transition-colors hover:underline [&[data-panel-open]>svg]:rotate-180",
        className,
      )}
      {...props}
    >
      {children}
      <ChevronDown className="h-4 w-4 shrink-0 transition-transform duration-200" />
    </AccordionPrimitive.Trigger>
  </AccordionPrimitive.Header>
));
AccordionTrigger.displayName = "AccordionTrigger";

const AccordionContent = React.forwardRef<
  React.ComponentRef<typeof AccordionPrimitive.Panel>,
  React.ComponentPropsWithoutRef<typeof AccordionPrimitive.Panel>
>(({ className, children, ...props }, ref) => (
  <AccordionPrimitive.Panel
    ref={ref}
    className="overflow-hidden text-sm data-[ending-style]:animate-accordion-up data-[open]:animate-accordion-down"
    {...props}
  >
    <div className="min-h-0 overflow-hidden">
      <div className={cn("pb-4 pt-0", className)}>{children}</div>
    </div>
  </AccordionPrimitive.Panel>
));

AccordionContent.displayName = "AccordionContent";

export { Accordion, AccordionContent, AccordionItem, AccordionTrigger };
