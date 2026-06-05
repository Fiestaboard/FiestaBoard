import type { Meta, StoryObj } from "@storybook/react";
import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "./alert";

const meta = {
  title: "UI/Alert",
  component: Alert,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["default", "destructive"],
      description: "Visual style variant",
    },
  },
} satisfies Meta<typeof Alert>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    className: "w-[450px]",
    children: (
      <>
        <AlertTitle>Heads up!</AlertTitle>
        <AlertDescription>You can add components to your app using the CLI.</AlertDescription>
      </>
    ),
  },
};

export const Destructive: Story = {
  args: {
    variant: "destructive",
    className: "w-[450px]",
    children: (
      <>
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Error</AlertTitle>
        <AlertDescription>Your session has expired. Please log in again.</AlertDescription>
      </>
    ),
  },
};

export const WithIcon = () => (
  <Alert className="w-[450px]">
    <Info className="h-4 w-4" />
    <AlertTitle>Information</AlertTitle>
    <AlertDescription>This is an informational alert with an icon.</AlertDescription>
  </Alert>
);

export const Success = () => (
  <Alert className="w-[450px]">
    <CheckCircle2 className="h-4 w-4" />
    <AlertTitle>Success</AlertTitle>
    <AlertDescription>Your changes have been saved successfully.</AlertDescription>
  </Alert>
);

export const Warning = () => (
  <Alert className="w-[450px]">
    <TriangleAlert className="h-4 w-4" />
    <AlertTitle>Warning</AlertTitle>
    <AlertDescription>Your account is about to reach its usage limit.</AlertDescription>
  </Alert>
);

export const AllVariants = () => (
  <div className="flex flex-col gap-4 w-[450px]">
    <Alert>
      <Info className="h-4 w-4" />
      <AlertTitle>Default Alert</AlertTitle>
      <AlertDescription>This is the default variant.</AlertDescription>
    </Alert>
    <Alert variant="destructive">
      <AlertCircle className="h-4 w-4" />
      <AlertTitle>Destructive Alert</AlertTitle>
      <AlertDescription>This is the destructive variant.</AlertDescription>
    </Alert>
  </div>
);
