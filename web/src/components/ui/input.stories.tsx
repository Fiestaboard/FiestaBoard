import type { Meta, StoryObj } from "@storybook/react";
import { Input } from "./input";
import { Label } from "./label";

const meta = {
  title: "UI/Input",
  component: Input,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    type: {
      control: "select",
      options: ["text", "password", "email", "number", "file", "search", "url", "tel"],
      description: "HTML input type",
    },
    disabled: {
      control: "boolean",
      description: "Disabled state",
    },
    placeholder: {
      control: "text",
      description: "Placeholder text",
    },
  },
} satisfies Meta<typeof Input>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    type: "text",
    placeholder: "Enter text...",
  },
};

export const Email: Story = {
  args: {
    type: "email",
    placeholder: "user@example.com",
  },
};

export const Password: Story = {
  args: {
    type: "password",
    placeholder: "Enter password...",
  },
};

export const File: Story = {
  args: {
    type: "file",
    "aria-label": "Upload file",
  },
};

export const Disabled: Story = {
  args: {
    type: "text",
    placeholder: "Disabled input",
    disabled: true,
  },
};

export const WithValue: Story = {
  args: {
    type: "text",
    defaultValue: "Pre-filled value",
    "aria-label": "Example input",
  },
};

export const WithLabel = () => (
  <div className="grid w-full max-w-sm items-center gap-1.5">
    <Label htmlFor="email">Email</Label>
    <Input type="email" id="email" placeholder="Email" />
  </div>
);

export const AllTypes = () => (
  <div className="flex flex-col gap-4 w-80">
    <Input type="text" placeholder="Text input" aria-label="Text" />
    <Input type="email" placeholder="Email input" aria-label="Email" />
    <Input type="password" placeholder="Password input" aria-label="Password" />
    <Input type="number" placeholder="Number input" aria-label="Number" />
    <Input type="search" placeholder="Search input" aria-label="Search" />
    <Input type="url" placeholder="URL input" aria-label="URL" />
    <Input type="tel" placeholder="Telephone input" aria-label="Telephone" />
    <Input type="file" aria-label="File upload" />
    <Input type="text" placeholder="Disabled input" aria-label="Disabled" disabled />
  </div>
);
