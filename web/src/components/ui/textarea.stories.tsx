import type { Meta, StoryObj } from "@storybook/react";
import { Textarea } from "./textarea";
import { Label } from "./label";

const meta = {
  title: "UI/Textarea",
  component: Textarea,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    disabled: {
      control: "boolean",
      description: "Disabled state",
    },
    placeholder: {
      control: "text",
      description: "Placeholder text",
    },
    rows: {
      control: "number",
      description: "Number of visible text rows",
    },
  },
} satisfies Meta<typeof Textarea>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    placeholder: "Type something...",
    "aria-label": "Default textarea",
  },
};

export const WithLabel = () => (
  <div className="grid w-full max-w-sm items-center gap-1.5">
    <Label htmlFor="message">Message</Label>
    <Textarea id="message" placeholder="Enter your message..." />
  </div>
);

export const Disabled: Story = {
  args: {
    placeholder: "This textarea is disabled",
    disabled: true,
    "aria-label": "Disabled textarea",
  },
};

export const WithPlaceholder: Story = {
  args: {
    placeholder: "Tell us about your project...",
    "aria-label": "Project description",
  },
};

export const AllStates = () => (
  <div className="flex flex-col gap-4 w-80">
    <div className="grid gap-1.5">
      <Label htmlFor="empty">Empty</Label>
      <Textarea id="empty" placeholder="Empty textarea" />
    </div>
    <div className="grid gap-1.5">
      <Label htmlFor="prefilled">Pre-filled</Label>
      <Textarea id="prefilled" defaultValue="This textarea has content already." />
    </div>
    <div className="grid gap-1.5">
      <Label htmlFor="long">Long content</Label>
      <Textarea
        id="long"
        rows={5}
        defaultValue={
          "Line one\nLine two\nLine three\nLine four\nLine five\nLine six"
        }
      />
    </div>
    <div className="grid gap-1.5">
      <Label htmlFor="disabled-filled">Disabled with content</Label>
      <Textarea id="disabled-filled" defaultValue="Read-only content" disabled />
    </div>
    <div className="grid gap-1.5">
      <Label htmlFor="disabled-empty">Disabled empty</Label>
      <Textarea id="disabled-empty" placeholder="Cannot type here" disabled />
    </div>
  </div>
);
