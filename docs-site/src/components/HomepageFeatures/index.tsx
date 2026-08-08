import BrowserOnly from "@docusaurus/BrowserOnly";
import Link from "@docusaurus/Link";
import { useColorMode } from "@docusaurus/theme-common";
import { Badge, Box, Button, Code, Heading, ScaledBoardDisplay, Text, TextLink } from "@fiestaboard/ui";
import { type ReactNode } from "react";

import { pluginPreviews, plugins, previewMessage } from "../../plugin-data";
import styles from "./styles.module.css";

/** Plugins that ship inside the container (countdown, date_time). */
const BUNDLED_PLUGIN_COUNT = 2;

type FeatureItem = {
  title: string;
  icon: string;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: "Plugin Architecture",
    icon: "/img/features/plugin-architecture.png",
    description:
      "26 built-in plugins for weather, stocks, transit, sports scores, Disney park wait times, ferry schedules, and more. Create your own plugins with our developer guide.",
  },
  {
    title: "WYSIWYG Editor",
    icon: "/img/features/wysiwyg-editor.png",
    description:
      "Create pages with a visual editor that shows exactly how content will appear on your board - template variables, colors, and alignment in real time.",
  },
  {
    title: "Schedule Mode",
    icon: "/img/features/schedule-mode.png",
    description:
      "Visual calendar to schedule which pages display when. Set different pages for different times and days, with a default page for gaps.",
  },
  {
    title: "Docker Ready",
    icon: "/img/features/docker-ready.png",
    description:
      "One-command deployment with Docker Compose. Works on Mac, Linux, Windows, and Raspberry Pi. No complex setup required.",
  },
  {
    title: "Highly Customizable",
    icon: "/img/features/customizable.png",
    description:
      "Create custom pages with multiple data sources. Configure silence schedules, time zones, temperature units, and more.",
  },
  {
    title: "Open Source",
    icon: "/img/features/open-source.png",
    description:
      "MIT licensed and community-driven. Contribute plugins, report issues, or customize it for your needs. Built with love in San Francisco.",
  },
];

type HighlightItem = {
  title: string;
  description: ReactNode;
  primary: { label: string; to: string };
  secondary: { label: string; to: string };
};

const HighlightList: HighlightItem[] = [
  {
    title: "FiestaPi - flash a Raspberry Pi, done",
    description: (
      <>
        A pre-built Raspberry Pi OS image with FiestaBoard, Docker, and the self-update sidecar all pre-installed. Flash
        a microSD card with Raspberry Pi Imager, boot your Pi, open <Code>http://fiestapi.local:4420</Code> - no Docker
        setup, no terminal, no config files. Works on Pi 3B, Pi 4, Pi 5, and Pi Zero 2 W.
      </>
    ),
    primary: { label: "FiestaPi Quick Start →", to: "/docs/setup/raspberry-pi" },
    secondary: { label: "Download image", to: "https://github.com/Fiestaboard/FiestaBoard/releases/latest" },
  },
  {
    title: "One-click in-app updates",
    description: (
      <>
        When a new version ships, a banner appears in Settings → System. Click Update Now and FiestaBoard updates itself
        - no SSH, no <Code>docker compose pull</Code>. On for FiestaPi by default; opt in on Docker installs by enabling
        the <Code>fiestaupdater</Code> sidecar.
      </>
    ),
    primary: { label: "How updates work →", to: "/docs/features/updating" },
    secondary: { label: "FiestaUpdater reference", to: "/docs/deployment/fiestaupdater" },
  },
];

type ShowcaseItem = {
  title: string;
  image: string;
  alt: string;
  description: string;
  link: string;
};

const FeatureShowcaseList: ShowcaseItem[] = [
  {
    title: "Dashboard & Web UI",
    image: "/img/web-ui-home.png",
    alt: "FiestaBoard web dashboard showing active display with stock ticker data",
    description: "Monitor your display, manage pages, and configure plugins from a modern web interface.",
    link: "/docs/features/page-editor",
  },
  {
    title: "WYSIWYG Page Editor",
    image: "/img/page-editor-wysiwyg.png",
    alt: "FiestaBoard WYSIWYG page editor with visual board preview",
    description:
      "Design your board layouts visually - see exactly how content will appear before sending it to your display.",
    link: "/docs/features/page-editor",
  },
  {
    title: "Visual Scheduling",
    image: "/img/schedule-calendar.png",
    alt: "FiestaBoard schedule calendar view with time-based page scheduling",
    description: "Schedule different pages for different times and days with an intuitive calendar interface.",
    link: "/docs/features/schedule",
  },
];

type PluginItem = {
  title: string;
  description: string;
  link: string;
  message: string;
  deviceType: "flagship" | "note" | "note_array";
  notesWide: number;
  notesTall: number;
};

/**
 * Featured plugins: a curated blurb per id; the board content comes from
 * plugin-previews.json (the same data the detail page renders), so the
 * homepage can never drift from the real preview data again. `device`
 * picks which declared shape to showcase - a deliberate mix of flagship
 * dashboards, Note boards, art, quotes, and transit for variety.
 */
const FEATURED_PLUGINS: { id: string; description: string; device?: string }[] = [
  { id: "weather", description: "Current conditions, UV index, high/low temps" },
  { id: "stocks", description: "Real-time stock prices with color indicators" },
  { id: "sun_art", description: "Beautiful time-of-day color patterns" },
  { id: "dad_jokes", description: "A fresh dad joke every refresh", device: "note" },
  { id: "disney_parks_times", description: "Live ride wait times from Disney parks" },
  { id: "moon_phase", description: "Tonight's moon phase and illumination" },
  { id: "visual_clock", description: "Full-screen pixel-art clock display" },
  { id: "star_trek_quotes", description: "Random quotes from TNG, Voyager, DS9" },
  { id: "muni", description: "Real-time SF Muni arrival predictions", device: "note" },
];

const PluginList: PluginItem[] = FEATURED_PLUGINS.flatMap(({ id, description, device }) => {
  const registryEntry = plugins.find((plugin) => plugin.id === id);
  const previews = pluginPreviews[id]?.previews ?? [];
  const board = (device && previews.find((entry) => entry.device_type === device)) || previews[0];
  // Backwards compat: skip quietly if the id ever leaves the registry or seed.
  if (!registryEntry || !board) return [];
  return [
    {
      title: registryEntry.name,
      description,
      link: `/plugins/detail?id=${id}`,
      message: previewMessage(board),
      deviceType: board.device_type ?? "flagship",
      notesWide: board.notes_wide ?? 1,
      notesTall: board.notes_tall ?? 1,
    },
  ];
});

function deriveThemedPath(src: string, mode: "light" | "dark"): string {
  const lastSlash = src.lastIndexOf("/");
  const dir = src.substring(0, lastSlash);
  const filename = src.substring(lastSlash + 1);
  return `${dir}/${mode}/${filename}`;
}

function FeatureCard({ title, icon, description }: FeatureItem) {
  return (
    <Box className={styles.featureCard}>
      <img className={styles.featureCardImage} src={icon} alt={title} loading="lazy" />
      <Box className={styles.featureCardBody}>
        <Heading level={3} className={styles.featureCardTitle}>
          {title}
        </Heading>
        <Text className={styles.featureCardDesc}>{description}</Text>
      </Box>
    </Box>
  );
}

function HighlightCard({ title, description, primary, secondary }: HighlightItem) {
  return (
    <Box className={styles.highlightCard}>
      <Badge variant="success" className={styles.newBadge}>
        New
      </Badge>
      <Heading level={3} className={styles.highlightTitle}>
        {title}
      </Heading>
      <Text className={styles.highlightBody}>{description}</Text>
      <Box className={styles.cardButtons}>
        <Button variant="secondary" size="sm" asChild>
          <Link to={primary.to}>{primary.label}</Link>
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <Link to={secondary.to}>{secondary.label}</Link>
        </Button>
      </Box>
    </Box>
  );
}

function ShowcaseRow({ title, image, alt, description, link, reverse }: ShowcaseItem & { reverse?: boolean }) {
  const { colorMode } = useColorMode();
  const src = deriveThemedPath(image, colorMode);
  return (
    <Box className={reverse ? styles.showcaseRowReverse : styles.showcaseRow}>
      <Box className={styles.showcaseImage}>
        <img src={src} alt={alt} loading="lazy" />
      </Box>
      <Box className={styles.showcaseContent}>
        <Heading level={3} className={styles.showcaseTitle}>
          {title}
        </Heading>
        <Text className={styles.showcaseDesc}>{description}</Text>
        <TextLink href={link}>Learn More →</TextLink>
      </Box>
    </Box>
  );
}

function PluginCard({ title, description, link, message, deviceType, notesWide, notesTall }: PluginItem) {
  return (
    <Link to={link} className={styles.pluginCard}>
      <Box className={styles.pluginCardBoard}>
        <BrowserOnly fallback={<Box className={styles.pluginBoardFallback} />}>
          {() => (
            <ScaledBoardDisplay
              message={message}
              size="sm"
              deviceType={deviceType}
              notesWide={notesWide}
              notesTall={notesTall}
            />
          )}
        </BrowserOnly>
      </Box>
      <Text className={styles.pluginCardName}>{title}</Text>
      <Text className={styles.pluginCardDesc}>{description}</Text>
    </Link>
  );
}

export default function HomepageFeatures(): ReactNode {
  const pluginCount = plugins.length + BUNDLED_PLUGIN_COUNT;
  return (
    <>
      {/* Feature grid */}
      <Box as="section" className={styles.section}>
        <Box className={styles.inner}>
          <Box className={styles.featureGrid}>
            {FeatureList.map((props) => (
              <FeatureCard key={props.title} {...props} />
            ))}
          </Box>
        </Box>
      </Box>

      {/* What's New */}
      <Box as="section" className={styles.sectionMuted}>
        <Box className={styles.inner}>
          <Heading level={2} className={styles.sectionTitle}>
            What&apos;s New
          </Heading>
          <Text className={styles.sectionSubtitle}>
            The fastest way to run FiestaBoard, and updates without ever touching a terminal
          </Text>
          <Box className={styles.highlightGrid}>
            {HighlightList.map((props) => (
              <HighlightCard key={props.title} {...props} />
            ))}
          </Box>
        </Box>
      </Box>

      {/* See It in Action */}
      <Box as="section" className={styles.section}>
        <Box className={styles.inner}>
          <Heading level={2} className={styles.sectionTitle}>
            See It in Action
          </Heading>
          <Text className={styles.sectionSubtitle}>A powerful web interface to manage your split-flap display</Text>
          <Box className={styles.showcaseStack}>
            {FeatureShowcaseList.map((props, idx) => (
              <ShowcaseRow key={props.title} {...props} reverse={idx % 2 === 1} />
            ))}
          </Box>
        </Box>
      </Box>

      {/* Plugin grid */}
      <Box as="section" className={styles.sectionMuted}>
        <Box className={styles.inner}>
          <Heading level={2} className={styles.sectionTitle}>
            {pluginCount}+ Plugins and Counting
          </Heading>
          <Text className={styles.sectionSubtitle}>
            From weather and stocks to Disney park wait times - there&apos;s a plugin for everything
          </Text>
          <Box className={styles.pluginGrid}>
            {PluginList.map((props) => (
              <PluginCard key={props.title} {...props} />
            ))}
          </Box>
          <Box className={styles.centerAction}>
            <Button variant="outline" size="lg" asChild>
              <Link to="/plugins">Explore All Plugins</Link>
            </Button>
          </Box>
        </Box>
      </Box>

      {/* CTA */}
      <Box as="section" className={styles.section}>
        <Box className={styles.ctaInner}>
          <Heading level={2} className={styles.sectionTitle}>
            Ready to Get Started?
          </Heading>
          <Text className={styles.ctaSubtitle}>
            FiestaBoard is free, open source, and runs anywhere Docker does. Get up and running in minutes.
          </Text>
          <Box className={styles.centerAction}>
            <Button variant="brand" size="lg" asChild>
              <Link to="/docs/setup/beginners-guide">Beginner&apos;s Guide</Link>
            </Button>
            <Button variant="outline" size="lg" asChild>
              <Link to="/docs/development/plugin-guide">Build a Plugin</Link>
            </Button>
          </Box>
        </Box>
      </Box>
    </>
  );
}
