import type { Meta, StoryObj } from "@storybook/react";
import { ChevronsUpDown } from "lucide-react";
import { useState } from "react";

import { Button } from "./button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "./collapsible";

const meta = {
  title: "UI/Collapsible",
  component: Collapsible,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Collapsible>;

export default meta;
type _Story = StoryObj<typeof meta>;

export const Default = () => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="w-[350px] space-y-2">
      <div className="flex items-center justify-between space-x-4 px-4">
        <h4 className="text-sm font-semibold">3 items starred</h4>
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="sm" className="w-9 p-0">
            <ChevronsUpDown className="h-4 w-4" />
            <span className="sr-only">Toggle</span>
          </Button>
        </CollapsibleTrigger>
      </div>
      <div className="rounded-md border px-4 py-3 font-mono text-sm">@base-ui/react</div>
      <CollapsibleContent className="space-y-2">
        <div className="rounded-md border px-4 py-3 font-mono text-sm">@base-ui/react/menu</div>
        <div className="rounded-md border px-4 py-3 font-mono text-sm">@base-ui/react/dialog</div>
      </CollapsibleContent>
    </Collapsible>
  );
};

export const DefaultOpen = () => (
  <Collapsible defaultOpen className="w-[350px] space-y-2">
    <div className="flex items-center justify-between space-x-4 px-4">
      <h4 className="text-sm font-semibold">Settings</h4>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" size="sm" className="w-9 p-0">
          <ChevronsUpDown className="h-4 w-4" />
          <span className="sr-only">Toggle</span>
        </Button>
      </CollapsibleTrigger>
    </div>
    <CollapsibleContent className="space-y-2">
      <div className="rounded-md border px-4 py-3 text-sm">Enable notifications</div>
      <div className="rounded-md border px-4 py-3 text-sm">Dark mode</div>
      <div className="rounded-md border px-4 py-3 text-sm">Auto-refresh</div>
    </CollapsibleContent>
  </Collapsible>
);
