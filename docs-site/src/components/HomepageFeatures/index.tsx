import BrowserOnly from "@docusaurus/BrowserOnly";
import Link from "@docusaurus/Link";
import { useColorMode } from "@docusaurus/theme-common";
import { Badge, Button, Code, ScaledBoardDisplay, TextLink } from "@fiestaboard/ui";
import { type ReactNode } from "react";

import { plugins } from "../../plugin-data";
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
      "Create pages with a visual editor that shows exactly how content will appear on your board—template variables, colors, and alignment in real time.",
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
    title: "FiestaPi — flash a Raspberry Pi, done",
    description: (
      <>
        A pre-built Raspberry Pi OS image with FiestaBoard, Docker, and the self-update sidecar all pre-installed. Flash
        a microSD card with Raspberry Pi Imager, boot your Pi, open <Code>http://fiestapi.local:4420</Code> — no Docker
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
        — no SSH, no <Code>docker compose pull</Code>. On for FiestaPi by default; opt in on Docker installs by enabling
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
      "Design your board layouts visually—see exactly how content will appear before sending it to your display.",
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
};

/** Sample board messages reused verbatim from FiestaboardSite.dc.html. */
const PluginList: PluginItem[] = [
  {
    title: "Weather",
    description: "Current conditions, UV index, high/low temps",
    link: "/docs/plugins/weather",
    message: "SAN FRANCISCO CA\n62F CLEAR SKIES\nHI 68F   LO 54F\nUV INDEX 4 MODERATE\nSUNSET 8:04 PM",
  },
  {
    title: "Stocks",
    description: "Real-time stock prices with color indicators",
    link: "/docs/plugins/stocks",
    message: "MARKETS  4:00 PM ET\nAAPL   232.10 +1.24\nMSFT   418.90 +0.62\nNVDA   121.44 -0.85\nBTC   64,880  -0.40",
  },
  {
    title: "Sports Scores",
    description: "NFL, Soccer, NHL, NBA live scores",
    link: "/docs/plugins/sports-scores",
    message: "TONIGHT\nNFL  SF 24  SEA 17 F\nNBA GSW 112 LAL 108\nNHL SJS  2  VGK   3\nMLS  SJ  1  LA    1",
  },
  {
    title: "Sun Art",
    description: "Beautiful time-of-day color patterns",
    link: "/docs/plugins/sun-art",
    message:
      "{yellow}{yellow}{orange}{orange}{red}{red}\n{orange}{orange}{red}{red}{violet}{violet}\n{red}{red}{violet}{violet}{blue}{blue}\n{violet}{violet}{blue}{blue}{blue}{blue}",
  },
  {
    title: "Disney Parks",
    description: "Live ride wait times from Disney parks",
    link: "/docs/plugins/disney-parks",
    message: "DISNEYLAND WAITS\nRISE OF RESIST 85M\nSPACE MOUNTAIN 45M\nMATTERHORN     30M\nHAUNTED MANSION 25M",
  },
  {
    title: "Star Trek Quotes",
    description: "Random quotes from TNG, Voyager, DS9",
    link: "/docs/plugins/star-trek-quotes",
    message: "THINGS ARE ONLY\nIMPOSSIBLE UNTIL\nTHEY ARE NOT\n\n- JEAN LUC PICARD",
  },
  {
    title: "SF Muni",
    description: "Real-time SF Muni arrival predictions",
    link: "/docs/plugins/muni",
    message: "MUNI  CHURCH ST\nN JUDAH OB    4 MIN\nN JUDAH IB   11 MIN\nJ CHURCH OB   7 MIN\nKT INGLESIDE 15 MIN",
  },
  {
    title: "Visual Clock",
    description: "Full-screen pixel-art clock display",
    link: "/docs/plugins/visual-clock",
    message:
      "{orange}{orange}{orange}  {orange}{orange}{orange}\n{orange}   {orange}    {orange}\n{orange}{orange}{orange}  {orange}{orange}{orange}\n{orange}       {orange}\n{orange}{orange}{orange}  {orange}{orange}{orange}",
  },
  {
    title: "Nearby Aircraft",
    description: "Real-time flights near your location",
    link: "/docs/plugins/nearby-aircraft",
    message: "OVERHEAD NOW\nUAL 1912  SFO  31K\nAAL  238  JFK  37K\nSWA  455  OAK   9K\nDAL 2201  ATL  35K",
  },
];

function deriveThemedPath(src: string, mode: "light" | "dark"): string {
  const lastSlash = src.lastIndexOf("/");
  const dir = src.substring(0, lastSlash);
  const filename = src.substring(lastSlash + 1);
  return `${dir}/${mode}/${filename}`;
}

function FeatureCard({ title, icon, description }: FeatureItem) {
  return (
    <div className={styles.featureCard}>
      <img className={styles.featureCardImage} src={icon} alt={title} loading="lazy" />
      <div className={styles.featureCardBody}>
        <h3 className={styles.featureCardTitle}>{title}</h3>
        <p className={styles.featureCardDesc}>{description}</p>
      </div>
    </div>
  );
}

function HighlightCard({ title, description, primary, secondary }: HighlightItem) {
  return (
    <div className={styles.highlightCard}>
      <Badge variant="success">New</Badge>
      <h3 className={styles.highlightTitle}>{title}</h3>
      <p className={styles.highlightBody}>{description}</p>
      <div className={styles.cardButtons}>
        <Button variant="secondary" size="sm" asChild>
          <Link to={primary.to}>{primary.label}</Link>
        </Button>
        <Button variant="ghost" size="sm" asChild>
          <Link to={secondary.to}>{secondary.label}</Link>
        </Button>
      </div>
    </div>
  );
}

function ShowcaseRow({ title, image, alt, description, link, reverse }: ShowcaseItem & { reverse?: boolean }) {
  const { colorMode } = useColorMode();
  const src = deriveThemedPath(image, colorMode);
  return (
    <div className={reverse ? styles.showcaseRowReverse : styles.showcaseRow}>
      <div className={styles.showcaseImage}>
        <img src={src} alt={alt} loading="lazy" />
      </div>
      <div className={styles.showcaseContent}>
        <h3 className={styles.showcaseTitle}>{title}</h3>
        <p className={styles.showcaseDesc}>{description}</p>
        <TextLink href={link}>Learn More →</TextLink>
      </div>
    </div>
  );
}

function PluginCard({ title, description, link, message }: PluginItem) {
  return (
    <Link to={link} className={styles.pluginCard}>
      <div className={styles.pluginCardBoard}>
        <BrowserOnly fallback={<div className={styles.pluginBoardFallback} />}>
          {() => <ScaledBoardDisplay message={message} size="sm" />}
        </BrowserOnly>
      </div>
      <div className={styles.pluginCardName}>{title}</div>
      <div className={styles.pluginCardDesc}>{description}</div>
    </Link>
  );
}

export default function HomepageFeatures(): ReactNode {
  const pluginCount = plugins.length + BUNDLED_PLUGIN_COUNT;
  return (
    <>
      {/* Feature grid */}
      <section className={styles.section}>
        <div className={styles.inner}>
          <div className={styles.featureGrid}>
            {FeatureList.map((props) => (
              <FeatureCard key={props.title} {...props} />
            ))}
          </div>
        </div>
      </section>

      {/* What's New */}
      <section className={styles.sectionMuted}>
        <div className={styles.inner}>
          <h2 className={styles.sectionTitle}>What&apos;s New</h2>
          <p className={styles.sectionSubtitle}>
            The fastest way to run FiestaBoard, and updates without ever touching a terminal
          </p>
          <div className={styles.highlightGrid}>
            {HighlightList.map((props) => (
              <HighlightCard key={props.title} {...props} />
            ))}
          </div>
        </div>
      </section>

      {/* See It in Action */}
      <section className={styles.section}>
        <div className={styles.inner}>
          <h2 className={styles.sectionTitle}>See It in Action</h2>
          <p className={styles.sectionSubtitle}>A powerful web interface to manage your split-flap display</p>
          <div className={styles.showcaseStack}>
            {FeatureShowcaseList.map((props, idx) => (
              <ShowcaseRow key={props.title} {...props} reverse={idx % 2 === 1} />
            ))}
          </div>
        </div>
      </section>

      {/* Plugin grid */}
      <section className={styles.sectionMuted}>
        <div className={styles.inner}>
          <h2 className={styles.sectionTitle}>{pluginCount}+ Plugins and Counting</h2>
          <p className={styles.sectionSubtitle}>
            From weather and stocks to Disney park wait times—there&apos;s a plugin for everything
          </p>
          <div className={styles.pluginGrid}>
            {PluginList.map((props) => (
              <PluginCard key={props.title} {...props} />
            ))}
          </div>
          <div className={styles.centerAction}>
            <Button variant="outline" size="lg" asChild>
              <Link to="/plugins">Explore All Plugins</Link>
            </Button>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className={styles.section}>
        <div className={styles.ctaInner}>
          <h2 className={styles.sectionTitle}>Ready to Get Started?</h2>
          <p className={styles.ctaSubtitle}>
            FiestaBoard is free, open source, and runs anywhere Docker does. Get up and running in minutes.
          </p>
          <div className={styles.centerAction}>
            <Button variant="brand" size="lg" asChild>
              <Link to="/docs/setup/beginners-guide">Beginner&apos;s Guide</Link>
            </Button>
            <Button variant="outline" size="lg" asChild>
              <Link to="/docs/development/plugin-guide">Build a Plugin</Link>
            </Button>
          </div>
        </div>
      </section>
    </>
  );
}
