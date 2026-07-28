"use client";

import { Select as SelectPrimitive } from "@base-ui/react/select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Base UI renders the raw value in the trigger unless given an `items`
 * map. Radix rendered the selected item's content, and every call site
 * relies on that, so derive the map from the SelectItem children.
 */
function collectSelectItems(children: React.ReactNode): Array<{ value: unknown; label: React.ReactNode }> {
  const items: Array<{ value: unknown; label: React.ReactNode }> = [];
  const walk = (node: React.ReactNode) => {
    React.Children.forEach(node, (child) => {
      if (!React.isValidElement(child)) return;
      const childProps = child.props as { value?: unknown; children?: React.ReactNode };
      if (child.type === SelectItem && childProps.value !== undefined) {
        items.push({ value: childProps.value, label: childProps.children });
      } else if (childProps.children) {
        walk(childProps.children);
      }
    });
  };
  walk(children);
  return items;
}

type SelectProps = Omit<
  React.ComponentProps<typeof SelectPrimitive.Root>,
  "value" | "defaultValue" | "onValueChange" | "items"
> & {
  // Radix-style string typing; Base UI's generic Root types these as unknown.
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
};

function Select({ children, onValueChange, ...props }: SelectProps) {
  const items = collectSelectItems(children);
  return (
    <SelectPrimitive.Root
      items={items.length > 0 ? items : undefined}
      onValueChange={onValueChange as ((value: unknown) => void) | undefined}
      {...props}
    >
      {children}
    </SelectPrimitive.Root>
  );
}

const SelectGroup = SelectPrimitive.Group;

const SelectValue = SelectPrimitive.Value;

const SelectTrigger = React.forwardRef<
  React.ComponentRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50 [&>span]:line-clamp-1",
      className,
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon className="flex">
      <ChevronDown className="h-4 w-4 text-muted-foreground" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = "SelectTrigger";

const SelectScrollUpButton = React.forwardRef<
  React.ComponentRef<typeof SelectPrimitive.ScrollUpArrow>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollUpArrow>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollUpArrow
    ref={ref}
    className={cn(
      "sticky top-0 z-10 flex w-full cursor-default items-center justify-center bg-popover py-1",
      className,
    )}
    {...props}
  >
    <ChevronUp className="h-4 w-4" />
  </SelectPrimitive.ScrollUpArrow>
));
SelectScrollUpButton.displayName = "SelectScrollUpButton";

const SelectScrollDownButton = React.forwardRef<
  React.ComponentRef<typeof SelectPrimitive.ScrollDownArrow>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.ScrollDownArrow>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.ScrollDownArrow
    ref={ref}
    className={cn(
      "sticky bottom-0 z-10 flex w-full cursor-default items-center justify-center bg-popover py-1",
      className,
    )}
    {...props}
  >
    <ChevronDown className="h-4 w-4" />
  </SelectPrimitive.ScrollDownArrow>
));
SelectScrollDownButton.displayName = "SelectScrollDownButton";

const SelectContent = React.forwardRef<
  React.ComponentRef<typeof SelectPrimitive.Popup>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Popup> & {
    side?: "top" | "right" | "bottom" | "left";
    align?: "start" | "center" | "end";
    sideOffset?: number;
    position?: "popper" | "item-aligned";
    disableHeightConstraint?: boolean;
  }
>(({ className, children, side, align, sideOffset = 4, disableHeightConstraint = false, ...props }, ref) => {
  // `position` was a Radix concept; Base UI always positions popper-style
  // here (alignItemWithTrigger is disabled to match).
  delete (props as Record<string, unknown>).position;
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Positioner
        side={side}
        align={align}
        sideOffset={sideOffset}
        alignItemWithTrigger={false}
        className="z-[120]"
      >
        <SelectPrimitive.Popup
          ref={ref}
          className={cn(
            // max-w: content sized by a long item (e.g. page names) would run
            // off narrow viewports. Clamping here makes long item text wrap
            // instead.
            "relative min-w-[max(8rem,var(--anchor-width))] max-w-[calc(100vw-16px)] overflow-y-auto rounded-md border bg-popover text-popover-foreground shadow-md",
            !disableHeightConstraint && "max-h-[min(24rem,var(--available-height))]",
            // When height constraint is disabled, use a fixed height that fits
            // multiple items. Each SelectItem is typically ~36-40px, so 90px
            // should comfortably fit 2 items.
            disableHeightConstraint && "!h-[90px] !min-h-[90px] !max-h-[90px]",
            className,
          )}
          {...props}
        >
          <SelectScrollUpButton />
          <SelectPrimitive.List className="w-full p-1">{children}</SelectPrimitive.List>
          <SelectScrollDownButton />
        </SelectPrimitive.Popup>
      </SelectPrimitive.Positioner>
    </SelectPrimitive.Portal>
  );
});
SelectContent.displayName = "SelectContent";

const SelectLabel = React.forwardRef<
  React.ComponentRef<typeof SelectPrimitive.GroupLabel>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.GroupLabel>
>(({ className, ...props }, ref) => (
  <SelectPrimitive.GroupLabel
    ref={ref}
    className={cn("py-1.5 pl-8 pr-2 text-sm font-semibold", className)}
    {...props}
  />
));
SelectLabel.displayName = "SelectLabel";

const SelectItem = React.forwardRef<
  React.ComponentRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[highlighted]:bg-accent data-[highlighted]:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      className,
    )}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="h-4 w-4" />
      </SelectPrimitive.ItemIndicator>
    </span>

    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = "SelectItem";

const SelectSeparator = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      role="separator"
      aria-orientation="horizontal"
      className={cn("-mx-1 my-1 h-px bg-muted", className)}
      {...props}
    />
  ),
);
SelectSeparator.displayName = "SelectSeparator";

export {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectScrollDownButton,
  SelectScrollUpButton,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
};
