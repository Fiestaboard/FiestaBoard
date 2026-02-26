import type { Meta, StoryObj } from "@storybook/react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  SheetFooter,
  SheetClose,
} from "./sheet";
import { Button } from "./button";
import { Input } from "./input";
import { Label } from "./label";

const meta = {
  title: "UI/Sheet",
  component: Sheet,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Sheet>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: (
      <>
        <SheetTrigger asChild>
          <Button variant="outline">Open Sheet</Button>
        </SheetTrigger>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Edit Profile</SheetTitle>
            <SheetDescription>
              Make changes to your profile here. Click save when you&apos;re done.
            </SheetDescription>
          </SheetHeader>
          <div className="grid gap-4 py-4">
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="name" className="text-right">
                Name
              </Label>
              <Input id="name" defaultValue="John Doe" className="col-span-3" />
            </div>
            <div className="grid grid-cols-4 items-center gap-4">
              <Label htmlFor="username" className="text-right">
                Username
              </Label>
              <Input id="username" defaultValue="@johndoe" className="col-span-3" />
            </div>
          </div>
          <SheetFooter>
            <SheetClose asChild>
              <Button type="submit">Save changes</Button>
            </SheetClose>
          </SheetFooter>
        </SheetContent>
      </>
    ),
  },
};

export const LeftSide = () => (
  <Sheet>
    <SheetTrigger asChild>
      <Button variant="outline">Open Left</Button>
    </SheetTrigger>
    <SheetContent side="left">
      <SheetHeader>
        <SheetTitle>Navigation</SheetTitle>
        <SheetDescription>Browse your boards and settings.</SheetDescription>
      </SheetHeader>
      <div className="py-4">
        <nav className="space-y-2">
          <Button variant="ghost" className="w-full justify-start">Dashboard</Button>
          <Button variant="ghost" className="w-full justify-start">My Boards</Button>
          <Button variant="ghost" className="w-full justify-start">Settings</Button>
        </nav>
      </div>
    </SheetContent>
  </Sheet>
);

export const TopSide = () => (
  <Sheet>
    <SheetTrigger asChild>
      <Button variant="outline">Open Top</Button>
    </SheetTrigger>
    <SheetContent side="top">
      <SheetHeader>
        <SheetTitle>Notification Banner</SheetTitle>
        <SheetDescription>Important system message.</SheetDescription>
      </SheetHeader>
    </SheetContent>
  </Sheet>
);

export const BottomSide = () => (
  <Sheet>
    <SheetTrigger asChild>
      <Button variant="outline">Open Bottom</Button>
    </SheetTrigger>
    <SheetContent side="bottom">
      <SheetHeader>
        <SheetTitle>Quick Actions</SheetTitle>
        <SheetDescription>Select an action to perform.</SheetDescription>
      </SheetHeader>
    </SheetContent>
  </Sheet>
);

export const AllSides = () => (
  <div className="flex gap-4">
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline">Right</Button>
      </SheetTrigger>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Right Sheet</SheetTitle>
          <SheetDescription>This opens from the right.</SheetDescription>
        </SheetHeader>
      </SheetContent>
    </Sheet>
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline">Left</Button>
      </SheetTrigger>
      <SheetContent side="left">
        <SheetHeader>
          <SheetTitle>Left Sheet</SheetTitle>
          <SheetDescription>This opens from the left.</SheetDescription>
        </SheetHeader>
      </SheetContent>
    </Sheet>
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline">Top</Button>
      </SheetTrigger>
      <SheetContent side="top">
        <SheetHeader>
          <SheetTitle>Top Sheet</SheetTitle>
          <SheetDescription>This opens from the top.</SheetDescription>
        </SheetHeader>
      </SheetContent>
    </Sheet>
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline">Bottom</Button>
      </SheetTrigger>
      <SheetContent side="bottom">
        <SheetHeader>
          <SheetTitle>Bottom Sheet</SheetTitle>
          <SheetDescription>This opens from the bottom.</SheetDescription>
        </SheetHeader>
      </SheetContent>
    </Sheet>
  </div>
);
