import {useState, useEffect, type ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import {useColorMode} from '@docusaurus/theme-common';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  icon: string;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'Plugin Architecture',
    icon: '/img/features/plugin-architecture.png',
    description: (
      <>
        23 built-in plugins for weather, stocks, transit, sports scores, Disney park wait times,
        ferry schedules, and more. Create your own plugins with our developer guide.
      </>
    ),
  },
  {
    title: 'WYSIWYG Editor',
    icon: '/img/features/wysiwyg-editor.png',
    description: (
      <>
        Create pages with a visual editor that shows exactly how content will appear on your 
        board—template variables, colors, and alignment in real time.
      </>
    ),
  },
  {
    title: 'Schedule Mode',
    icon: '/img/features/schedule-mode.png',
    description: (
      <>
        Visual calendar to schedule which pages display when. Set different pages for 
        different times and days, with a default page for gaps.
      </>
    ),
  },
  {
    title: 'Docker Ready',
    icon: '/img/features/docker-ready.png',
    description: (
      <>
        One-command deployment with Docker Compose. Works on Mac, Linux, Windows, 
        and Raspberry Pi. No complex setup required.
      </>
    ),
  },
  {
    title: 'Highly Customizable',
    icon: '/img/features/customizable.png',
    description: (
      <>
        Create custom pages with multiple data sources. Configure silence schedules, 
        time zones, temperature units, and more.
      </>
    ),
  },
  {
    title: 'Open Source',
    icon: '/img/features/open-source.png',
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
  image: string;
  alt: string;
  description: string;
  link: string;
};

const FeatureShowcaseList: ShowcaseItem[] = [
  {
    title: 'Dashboard & Web UI',
    image: '/img/web-ui-home.png',
    alt: 'FiestaBoard web dashboard showing active display with stock ticker data',
    description: 'Monitor your display, manage pages, and configure plugins from a modern web interface.',
    link: '/docs/features/page-editor',
  },
  {
    title: 'WYSIWYG Page Editor',
    image: '/img/page-editor-wysiwyg.png',
    alt: 'FiestaBoard WYSIWYG page editor with visual board preview',
    description: 'Design your board layouts visually—see exactly how content will appear before sending it to your display.',
    link: '/docs/features/page-editor',
  },
  {
    title: 'Visual Scheduling',
    image: '/img/schedule-calendar.png',
    alt: 'FiestaBoard schedule calendar view with time-based page scheduling',
    description: 'Schedule different pages for different times and days with an intuitive calendar interface.',
    link: '/docs/features/schedule',
  },
];

const PluginShowcaseList: ShowcaseItem[] = [
  {
    title: 'Weather',
    image: '/img/weather-display.png',
    alt: 'Weather conditions displayed on split-flap board',
    description: 'Current conditions, UV index, high/low temps',
    link: '/docs/plugins/weather',
  },
  {
    title: 'Stocks',
    image: '/img/stocks-display.png',
    alt: 'Stock prices displayed on split-flap board',
    description: 'Real-time stock prices with color indicators',
    link: '/docs/plugins/stocks',
  },
  {
    title: 'Sports Scores',
    image: '/img/sports-scores-display.png',
    alt: 'Live sports scores displayed on split-flap board',
    description: 'NFL, Soccer, NHL, NBA live scores',
    link: '/docs/plugins/sports-scores',
  },
  {
    title: 'Sun Art',
    image: '/img/sun-art-display.png',
    alt: 'Sun art visualization on split-flap board',
    description: 'Beautiful time-of-day color patterns',
    link: '/docs/plugins/sun-art',
  },
  {
    title: 'Disney Parks',
    image: '/img/disney-parks-times-display.png',
    alt: 'Disney park wait times on split-flap board',
    description: 'Live ride wait times from Disney parks',
    link: '/docs/plugins/disney-parks',
  },
  {
    title: 'Star Trek Quotes',
    image: '/img/star-trek-quotes-display.png',
    alt: 'Star Trek quote displayed on split-flap board',
    description: 'Random quotes from TNG, Voyager, DS9',
    link: '/docs/plugins/star-trek-quotes',
  },
  {
    title: 'SF Muni',
    image: '/img/muni-display.png',
    alt: 'Muni transit arrivals on split-flap board',
    description: 'Real-time SF Muni arrival predictions',
    link: '/docs/plugins/muni',
  },
  {
    title: 'Visual Clock',
    image: '/img/visual-clock-display.png',
    alt: 'Pixel-art clock on split-flap board',
    description: 'Full-screen pixel-art clock display',
    link: '/docs/plugins/visual-clock',
  },
  {
    title: 'Nearby Aircraft',
    image: '/img/nearby-aircraft-display.png',
    alt: 'Aircraft tracking on split-flap board',
    description: 'Real-time flights near your location',
    link: '/docs/plugins/nearby-aircraft',
  },
];

function deriveThemedPath(src: string, mode: 'light' | 'dark'): string {
  const lastSlash = src.lastIndexOf('/');
  const dir = src.substring(0, lastSlash);
  const filename = src.substring(lastSlash + 1);
  return `${dir}/${mode}/${filename}`;
}

function Feature({title, icon, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        <img className={styles.featureIcon} src={icon} alt={title} loading="lazy" />
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

function ShowcaseLightbox({
  src,
  alt,
  activeMode,
  onSetMode,
  onClose,
}: {
  src: string;
  alt: string;
  activeMode: 'light' | 'dark';
  onSetMode: (mode: 'light' | 'dark') => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handler);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  return (
    <div className={styles.lightboxOverlay} onClick={onClose} role="dialog" aria-modal="true">
      <div className={styles.lightboxContent} onClick={(e) => e.stopPropagation()}>
        <button type="button" className={styles.lightboxClose} onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
        <img className={styles.lightboxImage} src={src} alt={alt} />
        <div className={styles.lightboxFooter}>
          <div className={styles.showcaseToggle}>
            <button
              type="button"
              className={clsx(styles.lightboxToggleBtn, activeMode === 'light' && styles.lightboxToggleBtnActive)}
              onClick={() => onSetMode('light')}
              aria-label="Show light mode screenshot">
              <svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor" aria-hidden="true">
                <path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" />
              </svg>
              <span>Light</span>
            </button>
            <button
              type="button"
              className={clsx(styles.lightboxToggleBtn, activeMode === 'dark' && styles.lightboxToggleBtnActive)}
              onClick={() => onSetMode('dark')}
              aria-label="Show dark mode screenshot">
              <svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor" aria-hidden="true">
                <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
              </svg>
              <span>Dark</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function FeatureShowcase({title, image, alt, description, link, reverse}: ShowcaseItem & {reverse?: boolean}) {
  const {colorMode} = useColorMode();
  const [activeMode, setActiveMode] = useState<'light' | 'dark'>(colorMode);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  useEffect(() => {
    setActiveMode(colorMode);
  }, [colorMode]);

  const activeSrc = deriveThemedPath(image, activeMode);

  return (
    <>
      <div className={clsx(styles.showcaseRow, reverse && styles.showcaseRowReverse)}>
        <div className={styles.showcaseImage}>
          <img
            src={activeSrc}
            alt={alt}
            loading="lazy"
            onClick={() => setLightboxOpen(true)}
            style={{cursor: 'zoom-in'}}
          />
          <div className={styles.showcaseToggle}>
            <button
              type="button"
              className={clsx(styles.showcaseToggleBtn, activeMode === 'light' && styles.showcaseToggleBtnActive)}
              onClick={() => setActiveMode('light')}
              aria-label="Show light mode screenshot">
              <svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor" aria-hidden="true">
                <path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" />
              </svg>
              <span>Light</span>
            </button>
            <button
              type="button"
              className={clsx(styles.showcaseToggleBtn, activeMode === 'dark' && styles.showcaseToggleBtnActive)}
              onClick={() => setActiveMode('dark')}
              aria-label="Show dark mode screenshot">
              <svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor" aria-hidden="true">
                <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
              </svg>
              <span>Dark</span>
            </button>
          </div>
        </div>
        <div className={styles.showcaseContent}>
          <Heading as="h3">{title}</Heading>
          <p>{description}</p>
          <Link className="button button--primary button--sm" to={link}>
            Learn More →
          </Link>
        </div>
      </div>
      {lightboxOpen && (
        <ShowcaseLightbox
          src={activeSrc}
          alt={alt}
          activeMode={activeMode}
          onSetMode={setActiveMode}
          onClose={() => setLightboxOpen(false)}
        />
      )}
    </>
  );
}

function PluginCard({title, image, alt, description, link}: ShowcaseItem) {
  return (
    <Link to={link} className={styles.pluginCard}>
      <div className={styles.pluginCardImage}>
        <img src={image} alt={alt} loading="lazy" />
      </div>
      <div className={styles.pluginCardBody}>
        <Heading as="h4">
          {title}
        </Heading>
        <p>{description}</p>
      </div>
    </Link>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <>
      {/* Feature cards */}
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
              23 Plugins and Counting
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
              Explore All Plugins
            </Link>
          </div>
        </div>
      </section>

      {/* Call to action */}
      <section className={styles.ctaSection}>
        <div className="container text--center">
          <Heading as="h2" className={styles.ctaTitle}>
            Ready to Get Started?
          </Heading>
          <p className={styles.ctaSubtitle}>
            FiestaBoard is free, open source, and runs anywhere Docker does.
            Get up and running in minutes.
          </p>
          <div className={styles.ctaButtons}>
            <Link
              className="button button--primary button--lg"
              to="/docs/setup/beginners-guide">
              Beginner's Guide
            </Link>
            <Link
              className="button button--outline button--primary button--lg"
              to="/docs/development/plugin-guide">
              Build a Plugin
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
