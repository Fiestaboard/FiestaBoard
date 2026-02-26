import type { Meta, StoryObj } from "@storybook/react";
import FadeContent from "./fade-content";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../card";
import { Button } from "../button";

const meta = {
  title: "UI/React Bits/FadeContent",
  component: FadeContent,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
  argTypes: {
    blur: {
      control: "boolean",
      description: "Add blur effect during fade-in",
    },
    duration: {
      control: { type: "number", min: 0.2, max: 3, step: 0.1 },
      description: "Animation duration in seconds",
    },
    delay: {
      control: { type: "number", min: 0, max: 5, step: 0.5 },
      description: "Delay before animation starts in seconds",
    },
    translateY: {
      control: { type: "number", min: 0, max: 100, step: 10 },
      description: "Vertical translation distance in pixels",
    },
    threshold: {
      control: { type: "number", min: 0, max: 1, step: 0.1 },
      description: "Intersection observer threshold (0-1)",
    },
  },
} satisfies Meta<typeof FadeContent>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: (
      <Card className="w-80">
        <CardHeader>
          <CardTitle>Fade In Content</CardTitle>
          <CardDescription>Appears when scrolled into view</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This content fades in with a smooth slide-up animation.
          </p>
        </CardContent>
      </Card>
    ),
    blur: false,
    duration: 0.6,
    translateY: 20,
  },
};

export const WithBlur: Story = {
  args: {
    children: (
      <Card className="w-80">
        <CardHeader>
          <CardTitle>Blur + Fade Effect</CardTitle>
          <CardDescription>Fades in from blur</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This content combines fade-in with a blur effect for a more dramatic entrance.
          </p>
        </CardContent>
      </Card>
    ),
    blur: true,
    duration: 0.8,
    translateY: 30,
  },
};

export const FastAnimation: Story = {
  args: {
    children: (
      <div className="p-6 rounded-lg border bg-card text-card-foreground">
        <h3 className="text-lg font-semibold mb-2">Quick Fade</h3>
        <p className="text-sm text-muted-foreground">Fast animation speed</p>
      </div>
    ),
    duration: 0.3,
  },
};

export const SlowAnimation: Story = {
  args: {
    children: (
      <div className="p-6 rounded-lg border bg-card text-card-foreground">
        <h3 className="text-lg font-semibold mb-2">Slow Fade</h3>
        <p className="text-sm text-muted-foreground">Smooth, slow animation</p>
      </div>
    ),
    duration: 2,
  },
};

export const WithDelay: Story = {
  args: {
    children: (
      <div className="p-6 rounded-lg border bg-card text-card-foreground">
        <h3 className="text-lg font-semibold mb-2">Delayed Fade</h3>
        <p className="text-sm text-muted-foreground">Waits 1 second before animating</p>
      </div>
    ),
    delay: 1,
    duration: 0.6,
  },
};

export const LargeTranslation: Story = {
  args: {
    children: (
      <Card className="w-80">
        <CardHeader>
          <CardTitle>Large Slide Distance</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Slides up from 80px below
          </p>
        </CardContent>
      </Card>
    ),
    translateY: 80,
    duration: 1,
  },
};

export const MultipleElements = () => (
  <div className="space-y-4 max-w-2xl">
    <FadeContent duration={0.6} translateY={20}>
      <Card>
        <CardHeader>
          <CardTitle>First Card</CardTitle>
          <CardDescription>No delay</CardDescription>
        </CardHeader>
      </Card>
    </FadeContent>
    <FadeContent duration={0.6} delay={0.2} translateY={20}>
      <Card>
        <CardHeader>
          <CardTitle>Second Card</CardTitle>
          <CardDescription>0.2s delay</CardDescription>
        </CardHeader>
      </Card>
    </FadeContent>
    <FadeContent duration={0.6} delay={0.4} translateY={20}>
      <Card>
        <CardHeader>
          <CardTitle>Third Card</CardTitle>
          <CardDescription>0.4s delay</CardDescription>
        </CardHeader>
      </Card>
    </FadeContent>
    <FadeContent duration={0.6} delay={0.6} blur={true} translateY={30}>
      <Button className="w-full">Call to Action</Button>
    </FadeContent>
  </div>
);
