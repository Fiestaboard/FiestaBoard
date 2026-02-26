import type { Meta, StoryObj } from "@storybook/react";
import SpotlightCard from "./spotlight-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../card";
import { Badge } from "../badge";

const meta = {
  title: "UI/React Bits/SpotlightCard",
  component: SpotlightCard,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    spotlightColor: {
      control: "color",
      description: "Color of the spotlight effect (RGBA)",
    },
  },
} satisfies Meta<typeof SpotlightCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    spotlightColor: "rgba(255, 255, 255, 0.25)",
    children: (
      <Card className="w-80">
        <CardHeader>
          <CardTitle>Spotlight Card</CardTitle>
          <CardDescription>Hover to see the spotlight effect</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Move your mouse over this card to see the interactive spotlight effect.
          </p>
        </CardContent>
      </Card>
    ),
  },
};

export const BlueSpotlight: Story = {
  args: {
    spotlightColor: "rgba(99, 102, 241, 0.15)",
    children: (
      <Card className="w-80">
        <CardHeader>
          <CardTitle>Blue Spotlight</CardTitle>
          <CardDescription>Custom spotlight color</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            This card uses a blue spotlight effect on hover.
          </p>
        </CardContent>
      </Card>
    ),
  },
};

export const GreenSpotlight: Story = {
  args: {
    spotlightColor: "rgba(34, 197, 94, 0.2)",
    children: (
      <Card className="w-80 border-green-500/50">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Active Plugin</CardTitle>
            <Badge variant="default">Enabled</Badge>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Spotlight effect can be customized to match your theme.
          </p>
        </CardContent>
      </Card>
    ),
  },
};

export const MultipleCards = () => (
  <div className="grid grid-cols-2 gap-4 p-8">
    <SpotlightCard spotlightColor="rgba(239, 68, 68, 0.15)">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Card 1</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Red spotlight effect
          </p>
        </CardContent>
      </Card>
    </SpotlightCard>
    <SpotlightCard spotlightColor="rgba(99, 102, 241, 0.15)">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Card 2</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Blue spotlight effect
          </p>
        </CardContent>
      </Card>
    </SpotlightCard>
    <SpotlightCard spotlightColor="rgba(34, 197, 94, 0.15)">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Card 3</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Green spotlight effect
          </p>
        </CardContent>
      </Card>
    </SpotlightCard>
    <SpotlightCard spotlightColor="rgba(234, 179, 8, 0.15)">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Card 4</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Yellow spotlight effect
          </p>
        </CardContent>
      </Card>
    </SpotlightCard>
  </div>
);
