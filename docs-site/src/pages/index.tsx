import BrowserOnly from "@docusaurus/BrowserOnly";
import Link from "@docusaurus/Link";
import { Box, Button, Flex, Text } from "@fiestaboard/ui";
import HeroBoard from "@site/src/components/HeroBoard";
import HomepageFeatures from "@site/src/components/HomepageFeatures";
import Layout from "@theme/Layout";
import type { ReactNode } from "react";

import styles from "./index.module.css";

function Hero() {
  return (
    <Box as="section" className={styles.section}>
      <Box className={styles.heroInner}>
        <Box className={styles.heroCopy}>
          {/* The page's sole h1. FiestaUI's `Heading` covers h2-h4 only (h1 is
              reserved for the app's `PageHeader`), so the hero title keeps its
              own element and takes its type scale from `index.module.css`. */}
          <h1 className={styles.heroTitle}>Turn your split-flap display into a living dashboard</h1>
          <Text className={styles.heroBody}>
            Transform your Vestaboard into a real-time information hub - track your morning commute, monitor the
            markets, check surf conditions, or display Star Trek wisdom. Compatible with Vestaboard Flagship and Note.
            All beautifully formatted, endlessly customizable, and running in Docker with zero hassle.
          </Text>
          <Text className={styles.heroSubline}>
            Weather, stocks, sports &amp; more - flash a Raspberry Pi or run with Docker
          </Text>
          <Flex gap="3" wrap className={styles.heroButtons}>
            <Button variant="brand" size="lg" asChild>
              <Link to="/docs/intro">Get Started</Link>
            </Button>
            <Button variant="outline" size="lg" asChild>
              <Link href="https://github.com/Fiestaboard/FiestaBoard">View on GitHub</Link>
            </Button>
          </Flex>
        </Box>
        <Box className={styles.heroBoard}>
          <BrowserOnly fallback={<Box className={styles.heroBoardFallback} />}>{() => <HeroBoard />}</BrowserOnly>
        </Box>
      </Box>
    </Box>
  );
}

export default function Home(): ReactNode {
  return (
    <Layout
      title="Transform Your Split-Flap Display"
      description="FiestaBoard is free, open-source software for Vestaboard and split-flap displays. 26 plugins for weather, stocks, sports, transit, and more. Compatible with Vestaboard Flagship and Note."
    >
      <Hero />
      <Box as="main">
        <HomepageFeatures />
      </Box>
    </Layout>
  );
}
