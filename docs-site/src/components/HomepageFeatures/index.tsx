import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  emoji: string;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'Plugin Architecture',
    emoji: '🔌',
    description: (
      <>
        18 built-in plugins for weather, stocks, transit, sports scores, Disney park wait times,
        ferry schedules, and more. Create your own plugins with our developer guide.
      </>
    ),
  },
  {
    title: 'WYSIWYG Editor',
    emoji: '✏️',
    description: (
      <>
        Create pages with a visual editor that shows exactly how content will appear on your 
        board—template variables, colors, and alignment in real time.
      </>
    ),
  },
  {
    title: 'Schedule Mode',
    emoji: '📅',
    description: (
      <>
        Visual calendar to schedule which pages display when. Set different pages for 
        different times and days, with a default page for gaps.
      </>
    ),
  },
  {
    title: 'Docker Ready',
    emoji: '🐳',
    description: (
      <>
        One-command deployment with Docker Compose. Works on Mac, Linux, Windows, 
        and Raspberry Pi. No complex setup required.
      </>
    ),
  },
  {
    title: 'Highly Customizable',
    emoji: '🎨',
    description: (
      <>
        Create custom pages with multiple data sources. Configure silence schedules, 
        time zones, temperature units, and more.
      </>
    ),
  },
  {
    title: 'Open Source',
    emoji: '💚',
    description: (
      <>
        MIT licensed and community-driven. Contribute plugins, report issues, 
        or customize it for your needs. Built with love in San Francisco.
      </>
    ),
  },
];

type ShowcaseItem = {
  title: string;
  emoji: string;
  image: string;
  alt: string;
  description: string;
  link: string;
};

const FeatureShowcaseList: ShowcaseItem[] = [
  {
    title: 'Dashboard & Web UI',
    emoji: '🖥️',
    image: '/img/web-ui-home.png',
    alt: 'FiestaBoard web dashboard showing active display with stock ticker data',
    description: 'Monitor your display, manage pages, and configure plugins from a modern web interface.',
    link: '/docs/features/page-editor',
  },
  {
    title: 'WYSIWYG Page Editor',
    emoji: '✏️',
    image: '/img/page-editor-wysiwyg.png',
    alt: 'FiestaBoard WYSIWYG page editor with visual board preview',
    description: 'Design your board layouts visually—see exactly how content will appear before sending it to your display.',
    link: '/docs/features/page-editor',
  },
  {
    title: 'Visual Scheduling',
    emoji: '📅',
    image: '/img/schedule-calendar.png',
    alt: 'FiestaBoard schedule calendar view with time-based page scheduling',
    description: 'Schedule different pages for different times and days with an intuitive calendar interface.',
    link: '/docs/features/schedule',
  },
];

const PluginShowcaseList: ShowcaseItem[] = [
  {
    title: 'Weather',
    emoji: '🌤️',
    image: '/img/weather-display.png',
    alt: 'Weather conditions displayed on split-flap board',
    description: 'Current conditions, UV index, high/low temps',
    link: '/docs/plugins/weather',
  },
  {
    title: 'Stocks',
    emoji: '📈',
    image: '/img/stocks-display.png',
    alt: 'Stock prices displayed on split-flap board',
    description: 'Real-time stock prices with color indicators',
    link: '/docs/plugins/overview',
  },
  {
    title: 'Sports Scores',
    emoji: '🏆',
    image: '/img/sports-scores-display.png',
    alt: 'Live sports scores displayed on split-flap board',
    description: 'NFL, Soccer, NHL, NBA live scores',
    link: '/docs/plugins/sports-scores',
  },
  {
    title: 'Sun Art',
    emoji: '🌅',
    image: '/img/sun-art-sunset.png',
    alt: 'Sun art sunset visualization on split-flap board',
    description: 'Beautiful time-of-day visualizations',
    link: '/docs/plugins/overview',
  },
  {
    title: 'Disney Parks',
    emoji: '🏰',
    image: '/img/disney-parks-times-display.png',
    alt: 'Disney park wait times on split-flap board',
    description: 'Live ride wait times from Disney parks',
    link: '/docs/plugins/overview',
  },
  {
    title: 'Star Trek Quotes',
    emoji: '🖖',
    image: '/img/star-trek-quotes-display.png',
    alt: 'Star Trek quote displayed on split-flap board',
    description: 'Random quotes from TNG, Voyager, DS9',
    link: '/docs/plugins/overview',
  },
  {
    title: 'Air Quality & Fog',
    emoji: '💨',
    image: '/img/air-fog-display.png',
    alt: 'Air quality and fog conditions displayed on split-flap board',
    description: 'AQI monitoring, fog detection, dew point',
    link: '/docs/plugins/overview',
  },
];

function Feature({title, emoji, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        <span className={styles.featureEmoji}>{emoji}</span>
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

function FeatureShowcase({title, emoji, image, alt, description, link, reverse}: ShowcaseItem & {reverse?: boolean}) {
  return (
    <div className={clsx(styles.showcaseRow, reverse && styles.showcaseRowReverse)}>
      <div className={styles.showcaseImage}>
        <img src={image} alt={alt} loading="lazy" />
      </div>
      <div className={styles.showcaseContent}>
        <Heading as="h3">
          <span className={styles.showcaseEmoji}>{emoji}</span> {title}
        </Heading>
        <p>{description}</p>
        <Link className="button button--primary button--sm" to={link}>
          Learn More →
        </Link>
      </div>
    </div>
  );
}

function PluginCard({title, emoji, image, alt, description, link}: ShowcaseItem) {
  return (
    <Link to={link} className={styles.pluginCard}>
      <div className={styles.pluginCardImage}>
        <img src={image} alt={alt} loading="lazy" />
      </div>
      <div className={styles.pluginCardBody}>
        <Heading as="h4">
          <span>{emoji}</span> {title}
        </Heading>
        <p>{description}</p>
      </div>
    </Link>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <>
      {/* Feature cards with emojis */}
      <section className={styles.features}>
        <div className="container">
          <div className="row">
            {FeatureList.map((props, idx) => (
              <Feature key={idx} {...props} />
            ))}
          </div>
        </div>
      </section>

      {/* Feature showcase with screenshots */}
      <section className={styles.showcase}>
        <div className="container">
          <div className="text--center margin-bottom--lg">
            <Heading as="h2" className={styles.sectionTitle}>
              See It in Action
            </Heading>
            <p className={styles.sectionSubtitle}>
              A powerful web interface to manage your split-flap display
            </p>
          </div>
          {FeatureShowcaseList.map((props, idx) => (
            <FeatureShowcase key={props.title} {...props} reverse={idx % 2 === 1} />
          ))}
        </div>
      </section>

      {/* Plugin showcase gallery */}
      <section className={styles.pluginShowcase}>
        <div className="container">
          <div className="text--center margin-bottom--lg">
            <Heading as="h2" className={styles.sectionTitle}>
              🎉 18 Plugins and Counting
            </Heading>
            <p className={styles.sectionSubtitle}>
              From weather and stocks to Disney park wait times—there's a plugin for everything
            </p>
          </div>
          <div className={styles.pluginGrid}>
            {PluginShowcaseList.map((props) => (
              <PluginCard key={props.title} {...props} />
            ))}
          </div>
          <div className="text--center margin-top--lg">
            <Link
              className="button button--primary button--lg"
              to="/docs/plugins/overview">
              🔌 Explore All Plugins
            </Link>
          </div>
        </div>
      </section>

      {/* Call to action */}
      <section className={styles.ctaSection}>
        <div className="container text--center">
          <Heading as="h2" className={styles.ctaTitle}>
            Ready to Get Started? 🚀
          </Heading>
          <p className={styles.ctaSubtitle}>
            FiestaBoard is free, open source, and runs anywhere Docker does.
            Get up and running in minutes.
          </p>
          <div className={styles.ctaButtons}>
            <Link
              className="button button--primary button--lg"
              to="/docs/setup/beginners-guide">
              📖 Beginner's Guide
            </Link>
            <Link
              className="button button--outline button--primary button--lg"
              to="/docs/development/plugin-guide">
              🛠️ Build a Plugin
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
