import type { Meta, StoryObj } from "@storybook/react";
import { useEffect, useState } from "react";

import { BoardDisplay } from "./board-display";

const meta = {
  title: "Components/BoardDisplay",
  component: BoardDisplay,
  parameters: {
    layout: "centered",
  },
  tags: ["autodocs"],
  argTypes: {
    size: {
      control: "select",
      options: ["sm", "md", "lg"],
      description: "Size variant of the display",
    },
    isLoading: {
      control: "boolean",
      description: "Loading state of the display",
    },
    boardType: {
      control: "select",
      options: ["black", "white"],
      description: "Type of board (black or white)",
    },
  },
} satisfies Meta<typeof BoardDisplay>;

export default meta;
type Story = StoryObj<typeof meta>;

// Sample messages for different scenarios
const simpleMessage = "HELLO WORLD\nWELCOME TO\nFIESTABOARD";

const coloredMessage = `{red}BRUSH YOUR TEETH!{/red}
{blue}SPENCER{/blue}
{green}ROBBIE{/green}
{orange}ELI{/orange}
{yellow}FLOSS TOO!{/yellow}`;

const weatherMessage = `MONDAY DEC 30
SAN FRANCISCO
{blue}52{/blue}°F {yellow}62{/yellow}°F CLOUDY
MUNI 33 - 12 MIN
NEXT MEETING 2PM`;

const transitMessage = `{67}{67}{67} TRANSIT {67}{67}{67}
MUNI 1 - 5 MIN
MUNI 33 - 12 MIN
{64}{64} TRAFFIC {64}{64}
HOME TO WORK 25M`;

const multiColorBar = `{63}{63}{64}{64}{65}{65}{66}{66}{67}{67}{68}{68}
{red}RED{/red} {orange}ORANGE{/orange} {yellow}YELLOW{/yellow}
{green}GREEN{/green} {blue}BLUE{/blue} {violet}VIOLET{/violet}
COLOR PALETTE TEST`;

export const Default: Story = {
  args: {
    message: simpleMessage,
    size: "md",
    isLoading: false,
  },
};

export const Loading: Story = {
  args: {
    message: null,
    size: "md",
    isLoading: true,
  },
};

export const WithColors: Story = {
  args: {
    message: coloredMessage,
    size: "md",
    isLoading: false,
  },
};

export const WeatherDisplay: Story = {
  args: {
    message: weatherMessage,
    size: "md",
    isLoading: false,
  },
};

export const TransitDisplay: Story = {
  args: {
    message: transitMessage,
    size: "md",
    isLoading: false,
  },
};

export const ColorPalette: Story = {
  args: {
    message: multiColorBar,
    size: "md",
    isLoading: false,
  },
};

export const SmallSize: Story = {
  args: {
    message: simpleMessage,
    size: "sm",
    isLoading: false,
  },
};

export const LargeSize: Story = {
  args: {
    message: simpleMessage,
    size: "lg",
    isLoading: false,
  },
};

export const WhiteBoard: Story = {
  args: {
    message: simpleMessage,
    size: "md",
    isLoading: false,
    boardType: "white",
  },
};

export const WhiteBoardWithColors: Story = {
  args: {
    message: coloredMessage,
    size: "md",
    isLoading: false,
    boardType: "white",
  },
};

export const EmptyMessage: Story = {
  args: {
    message: "",
    size: "md",
    isLoading: false,
  },
};

export const NullMessage: Story = {
  args: {
    message: null,
    size: "md",
    isLoading: false,
  },
};

export const LongText: Story = {
  args: {
    message: "THIS IS A VERY LONG LINE THAT WILL BE TRUNCATED\nSECOND LINE HERE\nTHIRD LINE\nFOURTH\nFIFTH\nSIXTH LINE",
    size: "md",
    isLoading: false,
  },
};

// Interactive story to test loading-to-display transition
export const LoadingTransition = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  const testMessage = `{red}HELLO WORLD{/red}
WELCOME TO
FIESTABOARD
{blue}52{/blue}°F {yellow}62{/yellow}°F CLOUDY
{63}{64}{65}{66}{67}{68} SPLIT FLAP {63}{64}{65}{66}{67}{68}`;

  useEffect(() => {
    // Start with loading, then show message after 3 seconds
    const timer = setTimeout(() => {
      setMessage(testMessage);
      setIsLoading(false);
    }, 3000);

    return () => clearTimeout(timer);
  }, []);

  const handleReset = () => {
    setIsLoading(true);
    setMessage(null);

    // After 3 seconds of loading, show the message again
    setTimeout(() => {
      setMessage(testMessage);
      setIsLoading(false);
    }, 3000);
  };

  return (
    <div className="flex flex-col items-center gap-6">
      <BoardDisplay message={message} isLoading={isLoading} size="md" boardType="black" />

      <button
        onClick={handleReset}
        disabled={isLoading}
        className={`px-6 py-3 rounded-lg font-semibold transition-colors ${
          isLoading
            ? "bg-muted text-muted-foreground cursor-not-allowed"
            : "bg-primary text-primary-foreground hover:bg-primary/90"
        }`}
      >
        {isLoading ? "Loading..." : "Reset"}
      </button>

      <div className="text-sm text-muted-foreground text-center max-w-md">
        <p className="font-semibold mb-2">Loading Transition Demo</p>
        <p>Watch the tiles flip continuously in loading state, then continue cycling until each lands on its target.</p>
        <p className="mt-2 text-info">Click &quot;Reset&quot; to replay the animation</p>
      </div>
    </div>
  );
};

// Interactive story to test message changes with real tile cycling
// Uses actual CharTiles cycling during loading (not legacy FlipTiles)
export const MessageTransition = () => {
  const [message, setMessage] = useState(coloredMessage);
  const [isLoading, setIsLoading] = useState(false);

  const _message1 = coloredMessage; // "BRUSH YOUR TEETH!" with colors
  const message2 = `GOOD MORNING!
{blue}SPENCER{/blue}
{green}ROBBIE{/green}
{orange}ELI{/orange}
HAVE A GREAT DAY!`;

  const handleTransition = () => {
    // Put into loading state
    // Keep the current message visible so we see actual CharTiles cycling (not FlipTiles)
    setIsLoading(true);

    // After 6 seconds, set new message and turn off loading
    // Tiles will continue rotating until they reach their target characters
    setTimeout(() => {
      setMessage(message2);
      setIsLoading(false);
    }, 6000);
  };

  return (
    <div className="flex flex-col items-center gap-6">
      <BoardDisplay message={message} isLoading={isLoading} size="md" boardType="black" />

      <button
        onClick={handleTransition}
        disabled={isLoading}
        className={`px-6 py-3 rounded-lg font-semibold transition-colors ${
          isLoading
            ? "bg-muted text-muted-foreground cursor-not-allowed"
            : "bg-primary text-primary-foreground hover:bg-primary/90"
        }`}
      >
        {isLoading ? "Loading..." : "Change Message"}
      </button>

      <div className="text-sm text-muted-foreground text-center max-w-md">
        <p className="font-semibold mb-2">Message Transition Demo</p>
        <p>
          Click the button to start loading. During loading, actual tiles cycle through characters (like real
          FiestaBoard).
        </p>
        <p className="mt-2">
          After 6 seconds, the message changes and tiles continue rotating until each reaches its target character.
        </p>
        <p className="mt-2 text-info">Uses real CharTiles, not legacy FlipTiles</p>
      </div>
    </div>
  );
};

// Story to test loading -> loaded transition with visible individual stopping
export const LoadingToLoadedTransition = () => {
  const [isLoading, setIsLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);

  const testMessage = `{red}BRUSH YOUR TEETH!{/red}
{blue}SPENCER{/blue}
{green}ROBBIE{/green}
{orange}ELI{/orange}
{yellow}FLOSS TOO!{/yellow}`;

  useEffect(() => {
    // Start with loading for 3 seconds, then show message
    const timer = setTimeout(() => {
      setMessage(testMessage);
      setIsLoading(false);
    }, 3000);

    return () => clearTimeout(timer);
  }, []);

  const handleReset = () => {
    setIsLoading(true);
    setMessage(null);

    setTimeout(() => {
      setMessage(testMessage);
      setIsLoading(false);
    }, 3000);
  };

  return (
    <div className="flex flex-col items-center gap-6">
      <BoardDisplay message={message} isLoading={isLoading} size="md" boardType="black" />

      <button
        onClick={handleReset}
        disabled={isLoading}
        className={`px-6 py-3 rounded-lg font-semibold transition-colors ${
          isLoading
            ? "bg-muted text-muted-foreground cursor-not-allowed"
            : "bg-primary text-primary-foreground hover:bg-primary/90"
        }`}
      >
        {isLoading ? "Loading..." : "Reset"}
      </button>

      <div className="text-sm text-muted-foreground text-center max-w-md">
        <p className="font-semibold mb-2">Loading → Loaded Transition</p>
        <p>Watch tiles cycle during loading, then continue cycling until each individually reaches its target.</p>
        <p className="mt-2 text-info">Tiles should stop one by one, not all at once</p>
      </div>
    </div>
  );
};

// Dedicated story to showcase the 3D split-flap animation.
// Cycles between two messages so you can watch the flap mechanics at full board size.
export const SplitFlapAnimation = () => {
  const [message, setMessage] = useState("HELLO WORLD");
  const [isLoading, setIsLoading] = useState(false);
  const [boardType, setBoardType] = useState<"black" | "white">("black");

  const messages = [
    "HELLO WORLD",
    `{red}SPLIT{/red} {blue}FLAP{/blue} DEMO
{63}{64}{65}{66}{67}{68}{63}{64}{65}{66}{67}
ABCDEFGHIJKLMNOPQRSTUV
1234567890!@#$$()`,
    `GOOD MORNING
THE TIME IS 9:45 AM
{blue}52{/blue}°F PARTLY CLOUDY
{yellow}HAVE A GREAT DAY!{/yellow}`,
  ];

  const [msgIdx, setMsgIdx] = useState(0);

  const handleFlip = () => {
    setIsLoading(true);
    setTimeout(() => {
      const next = (msgIdx + 1) % messages.length;
      setMsgIdx(next);
      setMessage(messages[next]);
      setIsLoading(false);
    }, 4000);
  };

  return (
    <div className="flex flex-col items-center gap-6">
      <BoardDisplay message={message} isLoading={isLoading} size="lg" boardType={boardType} />

      <div className="flex gap-3">
        <button
          onClick={handleFlip}
          disabled={isLoading}
          className={`px-6 py-3 rounded-lg font-semibold transition-colors ${
            isLoading
              ? "bg-muted text-muted-foreground cursor-not-allowed"
              : "bg-primary text-primary-foreground hover:bg-primary/90"
          }`}
        >
          {isLoading ? "Flipping..." : "Flip to Next Message"}
        </button>
        <button
          onClick={() => setBoardType(boardType === "black" ? "white" : "black")}
          className="px-6 py-3 rounded-lg font-semibold border border-border hover:bg-accent transition-colors"
        >
          {boardType === "black" ? "Switch to White" : "Switch to Black"}
        </button>
      </div>

      <div className="text-sm text-muted-foreground text-center max-w-lg">
        <p className="font-semibold mb-2">Split-Flap Animation Demo</p>
        <p>
          Each tile uses a 4-layer 3D structure: the old character&apos;s top half folds down past the midpoint while
          the new character&apos;s bottom half unfolds into place — just like a real Solari board.
        </p>
        <p className="mt-2">
          During loading, all tiles cycle through the full character set. When the new message arrives, each tile
          continues flipping until it reaches its target character and stops.
        </p>
      </div>
    </div>
  );
};
