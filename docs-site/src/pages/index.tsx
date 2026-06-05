import Link from "@docusaurus/Link";
import { useColorMode } from "@docusaurus/theme-common";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import HomepageFeatures from "@site/src/components/HomepageFeatures";
import Layout from "@theme/Layout";
import clsx from "clsx";
import type { ReactNode } from "react";

import styles from "./index.module.css";

function HomepageHeader() {
  const { siteConfig } = useDocusaurusContext();
  const { colorMode } = useColorMode();
  // Dark mode: deep gradient needs the light logo; light mode: pastel gradient needs the dark logo
  const logoSrc = colorMode === "dark" ? "/img/branding/logo-lockup-dark.png" : "/img/branding/logo-lockup-light.png";
  return (
    <header className={clsx("hero hero--primary", styles.heroBanner)}>
      <div className="container">
        <img src={logoSrc} alt="FiestaBoard" className={styles.heroLockup} />
        <p className="hero__subtitle">{siteConfig.tagline}</p>
        <p className={styles.heroDescription}>
          Transform your Vestaboard into a real-time information hub—track your morning commute, monitor the markets,
          check surf conditions, or display Star Trek wisdom. Compatible with Vestaboard Flagship and Note. All
          beautifully formatted, endlessly customizable, and running in Docker with zero hassle.
        </p>
        <p className={styles.heroDescriptionShort}>
          Weather, stocks, sports & more — flash a Raspberry Pi or run with Docker
        </p>
        <div className={styles.buttons}>
          <Link className="button button--secondary button--lg" to="/docs/intro">
            Get Started
          </Link>
          <Link
            className={clsx("button button--outline button--lg", styles.githubButton)}
            href="https://github.com/Fiestaboard/FiestaBoard"
          >
            View on GitHub
          </Link>
        </div>
      </div>
    </header>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout
      title="Transform Your Split-Flap Display"
      description="FiestaBoard is free, open-source software for Vestaboard and split-flap displays. 26 plugins for weather, stocks, sports, transit, and more. Compatible with Vestaboard Flagship and Note."
    >
      <HomepageHeader />
      <main>
        <HomepageFeatures />
      </main>
    </Layout>
  );
}
