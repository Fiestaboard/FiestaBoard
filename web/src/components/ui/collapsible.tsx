"use client";

import { Collapsible as CollapsiblePrimitive } from "@base-ui/react/collapsible";
import * as React from "react";

const Collapsible = CollapsiblePrimitive.Root;

function CollapsibleTrigger({
  asChild = false,
  children,
  ...props
}: React.ComponentProps<typeof CollapsiblePrimitive.Trigger> & { asChild?: boolean }) {
  return (
    <CollapsiblePrimitive.Trigger
      {...(asChild ? { render: React.Children.only(children) as React.ReactElement } : { children })}
      {...props}
    />
  );
}

const CollapsibleContent = CollapsiblePrimitive.Panel;

export { Collapsible, CollapsibleContent, CollapsibleTrigger };
