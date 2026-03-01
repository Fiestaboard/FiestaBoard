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

export const AllVariations = () => (
  <div className="space-y-8 w-[500px]">
    <div>
      <h3 className="text-sm font-medium mb-3">Two Tabs</h3>
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1" className="pt-3">
          Content for tab 1
        </TabsContent>
        <TabsContent value="tab2" className="pt-3">
          Content for tab 2
        </TabsContent>
      </Tabs>
    </div>
    <div>
      <h3 className="text-sm font-medium mb-3">Many Tabs</h3>
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">One</TabsTrigger>
          <TabsTrigger value="tab2">Two</TabsTrigger>
          <TabsTrigger value="tab3">Three</TabsTrigger>
          <TabsTrigger value="tab4">Four</TabsTrigger>
          <TabsTrigger value="tab5">Five</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1" className="pt-3">Tab 1 content</TabsContent>
        <TabsContent value="tab2" className="pt-3">Tab 2 content</TabsContent>
        <TabsContent value="tab3" className="pt-3">Tab 3 content</TabsContent>
        <TabsContent value="tab4" className="pt-3">Tab 4 content</TabsContent>
        <TabsContent value="tab5" className="pt-3">Tab 5 content</TabsContent>
      </Tabs>
    </div>
    <div>
      <h3 className="text-sm font-medium mb-3">With Disabled Tab</h3>
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Active</TabsTrigger>
          <TabsTrigger value="tab2" disabled>Disabled</TabsTrigger>
          <TabsTrigger value="tab3">Available</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1" className="pt-3">Active tab content</TabsContent>
        <TabsContent value="tab3" className="pt-3">Available tab content</TabsContent>
      </Tabs>
    </div>
  </div>
);
