import type { Meta, StoryObj } from "@storybook/react";
import { ScrollArea, ScrollBar } from "./scroll-area";

const meta = {
  title: "UI/ScrollArea",
  component: ScrollArea,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ScrollArea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Vertical: Story = {
  args: {
    className: "h-72 w-48 rounded-md border",
    children: (
      <div className="p-4">
        <h4 className="mb-4 text-sm font-medium leading-none">Tags</h4>
        {Array.from({ length: 50 }).map((_, i) => (
          <div key={i} className="text-sm py-1">
            Tag {i + 1}
          </div>
        ))}
      </div>
    ),
  },
};

export const Horizontal = () => (
  <ScrollArea className="w-96 whitespace-nowrap rounded-md border">
    <div className="flex w-max space-x-4 p-4">
      {Array.from({ length: 20 }).map((_, i) => (
        <div
          key={i}
          className="shrink-0 rounded-md border p-4 w-[150px] text-center"
        >
          Item {i + 1}
        </div>
      ))}
    </div>
    <ScrollBar orientation="horizontal" />
  </ScrollArea>
);

export const LongContent = () => (
  <ScrollArea className="h-[200px] w-[350px] rounded-md border p-4">
    <div className="space-y-4">
      <h4 className="text-sm font-medium">Long Form Content</h4>
      {Array.from({ length: 10 }).map((_, i) => (
        <p key={i} className="text-sm text-muted-foreground">
          Paragraph {i + 1}: Lorem ipsum dolor sit amet, consectetur adipiscing
          elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
        </p>
      ))}
    </div>
  </ScrollArea>
);
