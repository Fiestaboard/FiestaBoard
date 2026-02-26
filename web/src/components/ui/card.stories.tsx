import type { Meta, StoryObj } from "@storybook/react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  CardAction,
} from "./card";
import { Button } from "./button";
import { Input } from "./input";
import { Label } from "./label";

const meta = {
  title: "UI/Card",
  component: Card,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    className: "w-[350px]",
    children: (
      <>
        <CardHeader>
          <CardTitle>Card Title</CardTitle>
          <CardDescription>Card description goes here.</CardDescription>
        </CardHeader>
        <CardContent>
          <p>Card content area.</p>
        </CardContent>
        <CardFooter>
          <p className="text-sm text-muted-foreground">Card footer</p>
        </CardFooter>
      </>
    ),
  },
};

export const WithForm = () => (
  <Card className="w-[350px]">
    <CardHeader>
      <CardTitle>Create project</CardTitle>
      <CardDescription>Deploy your new project in one-click.</CardDescription>
    </CardHeader>
    <CardContent>
      <form>
        <div className="grid w-full items-center gap-4">
          <div className="flex flex-col space-y-1.5">
            <Label htmlFor="name">Name</Label>
            <Input id="name" placeholder="Name of your project" />
          </div>
        </div>
      </form>
    </CardContent>
    <CardFooter className="flex justify-between">
      <Button variant="outline">Cancel</Button>
      <Button>Deploy</Button>
    </CardFooter>
  </Card>
);

export const WithAction = () => (
  <Card className="w-[350px]">
    <CardHeader>
      <CardTitle>Notifications</CardTitle>
      <CardDescription>You have 3 unread messages.</CardDescription>
      <CardAction>
        <Button variant="outline" size="sm">
          View all
        </Button>
      </CardAction>
    </CardHeader>
    <CardContent>
      <p className="text-sm">Check your inbox for new updates.</p>
    </CardContent>
  </Card>
);

export const Simple = () => (
  <Card className="w-[350px]">
    <CardContent>
      <p>A simple card with only content.</p>
    </CardContent>
  </Card>
);

export const MultipleCards = () => (
  <div className="grid grid-cols-2 gap-4 w-[700px]">
    <Card>
      <CardHeader>
        <CardTitle>Today</CardTitle>
        <CardDescription>Overview of today&apos;s activity</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold">12</p>
        <p className="text-sm text-muted-foreground">Tasks completed</p>
      </CardContent>
    </Card>
    <Card>
      <CardHeader>
        <CardTitle>This Week</CardTitle>
        <CardDescription>Weekly summary</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold">48</p>
        <p className="text-sm text-muted-foreground">Tasks completed</p>
      </CardContent>
    </Card>
  </div>
);
