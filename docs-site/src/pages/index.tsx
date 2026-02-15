import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import HomepageFeatures from '@site/src/components/HomepageFeatures';
import Heading from '@theme/Heading';

import styles from './index.module.css';

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className={clsx('hero hero--primary', styles.heroBanner)}>
      <div className="container">
        <img 
          src="/img/logo.png" 
          alt="FiestaBoard" 
          className={styles.heroLogo}
        />
        <Heading as="h1" className="hero__title">
          {siteConfig.title}
        </Heading>
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <p className={styles.heroDescription}>
          Transform your iconic split-flap display into a real-time information hub—track your morning commute, 
          monitor the markets, check surf conditions, or display Star Trek wisdom. All beautifully formatted, 
          endlessly customizable, and running in Docker with zero hassle.
        </p>
        <div className={styles.buttons}>
          <Link
            className="button button--secondary button--lg"
            to="/docs/intro">
            🚀 Get Started
          </Link>
          <Link
            className={clsx('button button--outline button--lg', styles.githubButton)}
            href="https://github.com/roblesi/FiestaBoard">
            ⭐ View on GitHub
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title="Transform Your Split-Flap Display"
      description="FiestaBoard transforms your split-flap display into a living dashboard. Track weather, transit, stocks, and more with a beautiful web UI and Docker deployment.">
      <HomepageHeader />
      <main>
        <HomepageFeatures />
      </main>
    </Layout>
  );
}
