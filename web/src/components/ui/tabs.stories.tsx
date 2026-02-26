import type { Meta, StoryObj } from "@storybook/react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./tabs";

const meta = {
  title: "UI/Tabs",
  component: Tabs,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Tabs>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    defaultValue: "account",
    className: "w-[400px]",
    children: (
      <>
        <TabsList>
          <TabsTrigger value="account">Account</TabsTrigger>
          <TabsTrigger value="password">Password</TabsTrigger>
        </TabsList>
        <TabsContent value="account">
          <p className="text-sm text-muted-foreground">
            Make changes to your account settings here.
          </p>
        </TabsContent>
        <TabsContent value="password">
          <p className="text-sm text-muted-foreground">
            Change your password here.
          </p>
        </TabsContent>
      </>
    ),
  },
};

export const ThreeTabs = () => (
  <Tabs defaultValue="overview" className="w-[400px]">
    <TabsList>
      <TabsTrigger value="overview">Overview</TabsTrigger>
      <TabsTrigger value="analytics">Analytics</TabsTrigger>
      <TabsTrigger value="reports">Reports</TabsTrigger>
    </TabsList>
    <TabsContent value="overview">
      <p className="text-sm text-muted-foreground pt-2">
        Your project overview and summary information.
      </p>
    </TabsContent>
    <TabsContent value="analytics">
      <p className="text-sm text-muted-foreground pt-2">
        View detailed analytics and insights.
      </p>
    </TabsContent>
    <TabsContent value="reports">
      <p className="text-sm text-muted-foreground pt-2">
        Download and view your reports.
      </p>
    </TabsContent>
  </Tabs>
);

export const DisabledTab = () => (
  <Tabs defaultValue="active" className="w-[400px]">
    <TabsList>
      <TabsTrigger value="active">Active</TabsTrigger>
      <TabsTrigger value="disabled" disabled>
        Disabled
      </TabsTrigger>
      <TabsTrigger value="other">Other</TabsTrigger>
    </TabsList>
    <TabsContent value="active">
      <p className="text-sm text-muted-foreground pt-2">This tab is active.</p>
    </TabsContent>
    <TabsContent value="other">
      <p className="text-sm text-muted-foreground pt-2">Another tab content.</p>
    </TabsContent>
  </Tabs>
);
