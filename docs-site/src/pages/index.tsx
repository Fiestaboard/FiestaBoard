import BrowserOnly from "@docusaurus/BrowserOnly";
import Link from "@docusaurus/Link";
import { Button } from "@fiestaboard/ui";
import HeroBoard from "@site/src/components/HeroBoard";
import HomepageFeatures from "@site/src/components/HomepageFeatures";
import Layout from "@theme/Layout";
import type { ReactNode } from "react";

import styles from "./index.module.css";

function Hero() {
  return (
    <section className={styles.section}>
      <div className={styles.heroInner}>
        <div className={styles.heroCopy}>
          <h1 className={styles.heroTitle}>Turn your split-flap display into a living dashboard</h1>
          <p className={styles.heroBody}>
            Transform your Vestaboard into a real-time information hub—track your morning commute, monitor the markets,
            check surf conditions, or display Star Trek wisdom. Compatible with Vestaboard Flagship and Note. All
            beautifully formatted, endlessly customizable, and running in Docker with zero hassle.
          </p>
          <p className={styles.heroSubline}>
            Weather, stocks, sports &amp; more — flash a Raspberry Pi or run with Docker
          </p>
          <div className={styles.heroButtons}>
            <Button variant="brand" size="lg" asChild>
              <Link to="/docs/intro">Get Started</Link>
            </Button>
            <Button variant="outline" size="lg" asChild>
              <Link href="https://github.com/Fiestaboard/FiestaBoard">View on GitHub</Link>
            </Button>
          </div>
        </div>
        <div className={styles.heroBoard}>
          <BrowserOnly fallback={<div className={styles.heroBoardFallback} />}>{() => <HeroBoard />}</BrowserOnly>
        </div>
      </div>
    </section>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout
      title="Transform Your Split-Flap Display"
      description="FiestaBoard is free, open-source software for Vestaboard and split-flap displays. 26 plugins for weather, stocks, sports, transit, and more. Compatible with Vestaboard Flagship and Note."
    >
      <Hero />
      <main>
        <HomepageFeatures />
      </main>
    </Layout>
  );
}
