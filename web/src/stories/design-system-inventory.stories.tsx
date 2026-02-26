import type { Meta } from "@storybook/react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { 
  Select, 
  SelectTrigger, 
  SelectValue, 
  SelectContent, 
  SelectItem 
} from "@/components/ui/select";
import { 
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent
} from "@/components/ui/accordion";
import { Plus, Mail, Trash2, CheckCircle2, AlertCircle, Info } from "lucide-react";

const meta = {
  title: "Design System/Inventory",
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;

export const AllComponents = () => (
  <div className="min-h-screen bg-background p-8">
    <div className="max-w-7xl mx-auto space-y-12">
      {/* Header */}
      <div className="border-b pb-6">
        <h1 className="text-4xl font-bold mb-2">Design System Inventory</h1>
        <p className="text-muted-foreground">
          Complete overview of all UI components and their variants for token testing
        </p>
      </div>

      {/* Buttons */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Buttons</h2>
        <div className="space-y-6">
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3">All Variants</h3>
            <div className="flex flex-wrap gap-3">
              <Button variant="default">Default</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="destructive">Destructive</Button>
              <Button variant="outline">Outline</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="link">Link</Button>
            </div>
          </div>
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3">All Sizes</h3>
            <div className="flex flex-wrap items-center gap-3">
              <Button size="sm">Small</Button>
              <Button size="default">Default</Button>
              <Button size="lg">Large</Button>
              <Button size="icon" aria-label="Add"><Plus className="h-4 w-4" /></Button>
              <Button size="icon-sm" aria-label="Add"><Plus className="h-4 w-4" /></Button>
              <Button size="icon-lg" aria-label="Add"><Plus className="h-4 w-4" /></Button>
            </div>
          </div>
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3">With Icons</h3>
            <div className="flex flex-wrap gap-3">
              <Button><Mail className="h-4 w-4 mr-2" />With Icon</Button>
              <Button variant="destructive"><Trash2 className="h-4 w-4 mr-2" />Delete</Button>
              <Button variant="outline" size="icon" aria-label="Add"><Plus className="h-4 w-4" /></Button>
            </div>
          </div>
          <div>
            <h3 className="text-sm font-medium text-muted-foreground mb-3">States</h3>
            <div className="flex flex-wrap gap-3">
              <Button disabled>Disabled</Button>
              <Button variant="outline" disabled>Disabled Outline</Button>
              <Button variant="ghost" disabled>Disabled Ghost</Button>
            </div>
          </div>
        </div>
      </section>

      {/* Badges */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Badges</h2>
        <div className="flex flex-wrap gap-3">
          <Badge variant="default">Default</Badge>
          <Badge variant="secondary">Secondary</Badge>
          <Badge variant="destructive">Destructive</Badge>
          <Badge variant="outline">Outline</Badge>
        </div>
      </section>

      {/* Alerts */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Alerts</h2>
        <div className="space-y-4 max-w-2xl">
          <Alert>
            <Info className="h-4 w-4" />
            <AlertTitle>Default Alert</AlertTitle>
            <AlertDescription>This is a default informational alert.</AlertDescription>
          </Alert>
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error Alert</AlertTitle>
            <AlertDescription>This is a destructive/error alert.</AlertDescription>
          </Alert>
          <Alert>
            <CheckCircle2 className="h-4 w-4" />
            <AlertTitle>Success</AlertTitle>
            <AlertDescription>Operation completed successfully.</AlertDescription>
          </Alert>
        </div>
      </section>

      {/* Cards */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Cards</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Basic Card</CardTitle>
              <CardDescription>A simple card with header</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">Card content goes here</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>With Footer</CardTitle>
              <CardDescription>Card with footer actions</CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm">Content section</p>
            </CardContent>
            <CardFooter>
              <Button size="sm" className="w-full">Action</Button>
            </CardFooter>
          </Card>
          <Card className="border-primary">
            <CardHeader>
              <CardTitle>Highlighted Card</CardTitle>
              <CardDescription>With custom border</CardDescription>
            </CardHeader>
            <CardContent>
              <Badge variant="default">Featured</Badge>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Form Inputs */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Form Inputs</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl">
          <div className="space-y-2">
            <Label htmlFor="text">Text Input</Label>
            <Input id="text" type="text" placeholder="Enter text..." />
          </div>
          <div className="space-y-2">
            <Label htmlFor="email">Email Input</Label>
            <Input id="email" type="email" placeholder="user@example.com" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">Password Input</Label>
            <Input id="password" type="password" placeholder="••••••••" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="disabled">Disabled Input</Label>
            <Input id="disabled" type="text" placeholder="Disabled" disabled />
          </div>
        </div>
      </section>

      {/* Switches */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Switches</h2>
        <div className="flex flex-wrap gap-6">
          <div className="flex items-center gap-2">
            <Switch id="switch-1" />
            <Label htmlFor="switch-1">Default</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch id="switch-2" defaultChecked />
            <Label htmlFor="switch-2">Checked</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch id="switch-3" disabled />
            <Label htmlFor="switch-3">Disabled</Label>
          </div>
          <div className="flex items-center gap-2">
            <Switch id="switch-4" defaultChecked disabled />
            <Label htmlFor="switch-4">Disabled Checked</Label>
          </div>
        </div>
      </section>

      {/* Select */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Select</h2>
        <div className="max-w-xs space-y-2">
          <Label>Choose an option</Label>
          <Select defaultValue="option1">
            <SelectTrigger>
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="option1">Option 1</SelectItem>
              <SelectItem value="option2">Option 2</SelectItem>
              <SelectItem value="option3">Option 3</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </section>

      {/* Tabs */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Tabs</h2>
        <Tabs defaultValue="tab1" className="max-w-2xl">
          <TabsList>
            <TabsTrigger value="tab1">Tab 1</TabsTrigger>
            <TabsTrigger value="tab2">Tab 2</TabsTrigger>
            <TabsTrigger value="tab3">Tab 3</TabsTrigger>
          </TabsList>
          <TabsContent value="tab1" className="mt-4">
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">Content for Tab 1</p>
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="tab2" className="mt-4">
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">Content for Tab 2</p>
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="tab3" className="mt-4">
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground">Content for Tab 3</p>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </section>

      {/* Accordion */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Accordion</h2>
        <Accordion type="single" collapsible className="max-w-2xl">
          <AccordionItem value="item-1">
            <AccordionTrigger>Section 1</AccordionTrigger>
            <AccordionContent>
              Content for the first accordion section
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="item-2">
            <AccordionTrigger>Section 2</AccordionTrigger>
            <AccordionContent>
              Content for the second accordion section
            </AccordionContent>
          </AccordionItem>
          <AccordionItem value="item-3">
            <AccordionTrigger>Section 3</AccordionTrigger>
            <AccordionContent>
              Content for the third accordion section
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </section>

      {/* Skeletons */}
      <section className="space-y-4">
        <h2 className="text-2xl font-semibold">Skeleton Loaders</h2>
        <div className="space-y-4 max-w-2xl">
          <div className="space-y-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-3/4" />
          </div>
          <div className="flex items-center gap-4">
            <Skeleton className="h-12 w-12 rounded-full" />
            <div className="space-y-2 flex-1">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-3 w-3/4" />
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
);

export const ColorTokens = () => (
  <div className="min-h-screen bg-background p-8">
    <div className="max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Color Token Inventory</h1>
        <p className="text-muted-foreground">
          Test how color token changes affect all components
        </p>
      </div>

      {/* Color Swatches */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Primary Colors</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="space-y-2">
            <div className="h-20 rounded-lg bg-primary border" />
            <div className="text-xs">
              <div className="font-medium">primary</div>
              <div className="text-muted-foreground">Primary brand color</div>
            </div>
          </div>
          <div className="space-y-2">
            <div className="h-20 rounded-lg bg-primary-foreground border" />
            <div className="text-xs">
              <div className="font-medium">primary-foreground</div>
              <div className="text-muted-foreground">Text on primary</div>
            </div>
          </div>
          <div className="space-y-2">
            <div className="h-20 rounded-lg bg-secondary border" />
            <div className="text-xs">
              <div className="font-medium">secondary</div>
              <div className="text-muted-foreground">Secondary color</div>
            </div>
          </div>
          <div className="space-y-2">
            <div className="h-20 rounded-lg bg-secondary-foreground border" />
            <div className="text-xs">
              <div className="font-medium">secondary-foreground</div>
              <div className="text-muted-foreground">Text on secondary</div>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Semantic Colors</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="space-y-2">
            <div className="h-20 rounded-lg bg-destructive border" />
            <div className="text-xs">
              <div className="font-medium">destructive</div>
              <div className="text-muted-foreground">Error/danger</div>
            </div>
          </div>
          <div className="space-y-2">
            <div className="h-20 rounded-lg bg-muted border" />
            <div className="text-xs">
              <div className="font-medium">muted</div>
              <div className="text-muted-foreground">Subdued background</div>
            </div>
          </div>
          <div className="space-y-2">
            <div className="h-20 rounded-lg bg-accent border" />
            <div className="text-xs">
              <div className="font-medium">accent</div>
              <div className="text-muted-foreground">Hover/focus state</div>
            </div>
          </div>
          <div className="space-y-2">
            <div className="h-20 rounded-lg bg-card border" />
            <div className="text-xs">
              <div className="font-medium">card</div>
              <div className="text-muted-foreground">Card background</div>
            </div>
          </div>
        </div>
      </section>

      {/* Typography */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Typography</h2>
        <div className="space-y-3">
          <div className="text-4xl font-bold">Heading 1</div>
          <div className="text-3xl font-bold">Heading 2</div>
          <div className="text-2xl font-semibold">Heading 3</div>
          <div className="text-xl font-semibold">Heading 4</div>
          <div className="text-base">Body text (base)</div>
          <div className="text-sm">Small text</div>
          <div className="text-xs">Extra small text</div>
          <div className="text-sm text-muted-foreground">Muted text</div>
          <div className="text-sm text-primary">Primary text</div>
          <div className="text-sm text-destructive">Destructive text</div>
        </div>
      </section>

      {/* Borders & Spacing */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Borders & Radius</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="border rounded-lg p-4 text-center text-sm">
            <div className="font-medium mb-1">default</div>
            <div className="text-xs text-muted-foreground">var(--radius)</div>
          </div>
          <div className="border rounded-md p-4 text-center text-sm">
            <div className="font-medium mb-1">md</div>
            <div className="text-xs text-muted-foreground">calc(var(--radius) - 2px)</div>
          </div>
          <div className="border rounded-sm p-4 text-center text-sm">
            <div className="font-medium mb-1">sm</div>
            <div className="text-xs text-muted-foreground">calc(var(--radius) - 4px)</div>
          </div>
          <div className="border rounded-full p-4 text-center text-sm">
            <div className="font-medium mb-1">full</div>
            <div className="text-xs text-muted-foreground">9999px</div>
          </div>
        </div>
      </section>
    </div>
  </div>
);

export const InteractiveComponents = () => (
  <div className="min-h-screen bg-background p-8">
    <div className="max-w-4xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold mb-2">Interactive Components</h1>
        <p className="text-muted-foreground">
          All interactive states and hover effects in one view
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Button States</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>All variants hover states</Label>
            <div className="flex flex-wrap gap-2">
              <Button>Default</Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="destructive">Destructive</Button>
              <Button variant="outline">Outline</Button>
              <Button variant="ghost">Ghost</Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Form Controls</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="test-input">Input with focus</Label>
            <Input id="test-input" placeholder="Focus to see ring..." />
          </div>
          <div className="flex items-center gap-2">
            <Switch id="test-switch" />
            <Label htmlFor="test-switch">Toggle this switch</Label>
          </div>
          <div className="space-y-2">
            <Label>Select dropdown</Label>
            <Select>
              <SelectTrigger>
                <SelectValue placeholder="Choose..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Option 1</SelectItem>
                <SelectItem value="2">Option 2</SelectItem>
                <SelectItem value="3">Option 3</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Collapsible Content</CardTitle>
        </CardHeader>
        <CardContent>
          <Accordion type="single" collapsible>
            <AccordionItem value="item-1">
              <AccordionTrigger>Expand to see content</AccordionTrigger>
              <AccordionContent>
                This content can be expanded and collapsed. Notice the animation
                and focus states.
              </AccordionContent>
            </AccordionItem>
            <AccordionItem value="item-2">
              <AccordionTrigger>Another section</AccordionTrigger>
              <AccordionContent>
                Multiple accordion items can be configured with different behaviors.
              </AccordionContent>
            </AccordionItem>
          </Accordion>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Tabbed Content</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="details">Details</TabsTrigger>
              <TabsTrigger value="settings">Settings</TabsTrigger>
            </TabsList>
            <TabsContent value="overview" className="mt-4">
              <p className="text-sm text-muted-foreground">Overview content with all token colors applied.</p>
            </TabsContent>
            <TabsContent value="details" className="mt-4">
              <p className="text-sm text-muted-foreground">Details section content.</p>
            </TabsContent>
            <TabsContent value="settings" className="mt-4">
              <p className="text-sm text-muted-foreground">Settings configuration area.</p>
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  </div>
);

export const CompactShowcase = () => (
  <div className="p-8 bg-background space-y-6">
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 max-w-6xl mx-auto">
      {/* Buttons */}
      <Card>
        <CardHeader>
          <CardTitle>Buttons</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Button size="sm">Default</Button>
            <Button size="sm" variant="secondary">Secondary</Button>
            <Button size="sm" variant="destructive">Destructive</Button>
            <Button size="sm" variant="outline">Outline</Button>
            <Button size="sm" variant="ghost">Ghost</Button>
          </div>
        </CardContent>
      </Card>

      {/* Badges */}
      <Card>
        <CardHeader>
          <CardTitle>Badges</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <Badge>Default</Badge>
            <Badge variant="secondary">Secondary</Badge>
            <Badge variant="destructive">Destructive</Badge>
            <Badge variant="outline">Outline</Badge>
          </div>
        </CardContent>
      </Card>

      {/* Inputs */}
      <Card>
        <CardHeader>
          <CardTitle>Form Inputs</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Input placeholder="Text input" />
          <Input placeholder="Disabled" disabled />
          <div className="flex items-center gap-2">
            <Switch id="compact-switch" />
            <Label htmlFor="compact-switch">Switch control</Label>
          </div>
        </CardContent>
      </Card>

      {/* Alerts */}
      <Card>
        <CardHeader>
          <CardTitle>Alerts</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>Default alert</AlertDescription>
          </Alert>
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>Error alert</AlertDescription>
          </Alert>
        </CardContent>
      </Card>

      {/* Typography */}
      <Card>
        <CardHeader>
          <CardTitle>Typography</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="text-2xl font-bold">Heading</div>
          <div className="text-base">Body text</div>
          <div className="text-sm text-muted-foreground">Muted text</div>
          <div className="text-xs">Small text</div>
        </CardContent>
      </Card>

      {/* Loading States */}
      <Card>
        <CardHeader>
          <CardTitle>Loading States</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </CardContent>
      </Card>
    </div>
  </div>
);
