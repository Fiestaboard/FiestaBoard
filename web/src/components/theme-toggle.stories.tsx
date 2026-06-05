import type { Meta, StoryObj } from "@storybook/react";
import { ThemeProvider } from "next-themes";

import { ThemeToggle } from "./theme-toggle";

const meta = {
  title: "Layout/ThemeToggle",
  component: ThemeToggle,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <ThemeProvider attribute="class" defaultTheme="light">
        <Story />
      </ThemeProvider>
    ),
  ],
} satisfies Meta<typeof ThemeToggle>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const InDarkMode: Story = {
  decorators: [
    (Story) => (
      <ThemeProvider attribute="class" defaultTheme="dark">
        <div className="dark bg-background p-4 rounded-lg">
          <Story />
        </div>
      </ThemeProvider>
    ),
  ],
};

export const InToolbar = () => (
  <ThemeProvider attribute="class" defaultTheme="light">
    <div className="flex items-center justify-between border rounded-lg p-4 bg-card">
      <div className="text-sm font-medium">Appearance</div>
      <ThemeToggle />
    </div>
  </ThemeProvider>
);
