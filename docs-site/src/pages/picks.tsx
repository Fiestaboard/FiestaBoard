import {useState, type ReactNode} from 'react';
import clsx from 'clsx';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import Link from '@docusaurus/Link';
import styles from './picks.module.css';

// ---------------------------------------------------------------------------
// Pick data — mirrors staff-picks/picks.json in the main app
// ---------------------------------------------------------------------------

type RequiredPlugin = {id: string; name: string};

type Pick = {
  id: string;
  name: string;
  description: string;
  device_type: 'flagship' | 'note';
  tags: string[];
  image: string;
  required_plugins: RequiredPlugin[];
  share_string: string;
};

const PICKS: Pick[] = [
  {
    id: 'weather-dashboard',
    name: 'Weather Dashboard',
    description:
      'Full weather breakdown for your location — conditions, feel, wind, UV, and sunset.',
    device_type: 'flagship',
    tags: ['weather'],
    image: '/img/staff-picks/weather-dashboard.png',
    required_plugins: [
      {id: 'weather', name: 'Weather'},
      {id: 'date_time', name: 'Date & Time'},
    ],
    share_string:
      'eyJ2IjoxLCJwYWdlIjp7Im5hbWUiOiJXZWF0aGVyIERhc2hib2FyZCIsInR5cGUiOiJ0ZW1wbGF0ZSIsImRldmljZV90eXBlIjoiZmxhZ3NoaXAiLCJkaXNwbGF5X3R5cGUiOm51bGwsInJvd3MiOm51bGwsInRlbXBsYXRlIjpbInt7d2hpdGV9fXt7d2hpdGV9fXt7ZmlsbF9zcGFjZX19e3t3ZWF0aGVyLmxvY2F0aW9ucy4wLmxvY2F0aW9uX25hbWV9fXt7ZmlsbF9zcGFjZX19e3t3aGl0ZX19e3t3aGl0ZX19Iiwie3t3aGl0ZX19e3tmaWxsX3NwYWNlfX17e2RhdGVfdGltZS5kYXRlfX17e2ZpbGxfc3BhY2V9fXt7ZGF0ZV90aW1lLnRpbWV9fXt7ZmlsbF9zcGFjZX19e3t3aGl0ZX19IiwiTk9XICB7e3dlYXRoZXIubG9jYXRpb25zLjAudGVtcGVyYXR1cmV9fUYgUkFJTiB7e3dlYXRoZXIubG9jYXRpb25zLjAucHJlY2lwaXRhdGlvbl9jaGFuY2V9fSUiLCJMSUtFIHt7d2VhdGhlci5sb2NhdGlvbnMuMC5mZWVsc19saWtlfX1GIFdJTkQge3t3ZWF0aGVyLmxvY2F0aW9ucy4wLndpbmRfc3BlZWR9fSBNUEgiLCJISUdIIHt7d2VhdGhlci5sb2NhdGlvbnMuMC5oaWdoX3RlbXB9fUYgVVYgICB7e3dlYXRoZXIubG9jYXRpb25zLjAudXZfaW5kZXh9fXt7d2VhdGhlci51dl9pbmRleF9jb2xvcn19IiwiTE9XICB7e3dlYXRoZXIubG9jYXRpb25zLjAubG93X3RlbXB9fUYgU0VUICB7e3dlYXRoZXIubG9jYXRpb25zLjAuc3Vuc2V0fX0iXSwibGluZV9tZXRhZGF0YSI6W3siYWxpZ25tZW50IjoibGVmdCIsIndyYXAiOmZhbHNlfSx7ImFsaWdubWVudCI6ImxlZnQiLCJ3cmFwIjpmYWxzZX0seyJhbGlnbm1lbnQiOiJsZWZ0Iiwid3JhcCI6ZmFsc2V9LHsiYWxpZ25tZW50IjoibGVmdCIsIndyYXAiOmZhbHNlfSx7ImFsaWdubWVudCI6ImxlZnQiLCJ3cmFwIjpmYWxzZX0seyJhbGlnbm1lbnQiOiJsZWZ0Iiwid3JhcCI6ZmFsc2V9XSwiZHVyYXRpb25fc2Vjb25kcyI6MzAwLCJ0cmFuc2l0aW9uX3N0cmF0ZWd5IjpudWxsLCJ0cmFuc2l0aW9uX2ludGVydmFsX21zIjpudWxsLCJ0cmFuc2l0aW9uX3N0ZXBfc2l6ZSI6bnVsbH19',
  },
  {
    id: 'word-of-the-day',
    name: 'Word of the Day',
    description:
      'Daily vocabulary word with its Spanish translation, part of speech, and definition.',
    device_type: 'flagship',
    tags: ['education'],
    image: '/img/staff-picks/word-of-the-day.png',
    required_plugins: [{id: 'word_of_day', name: 'Word of the Day'}],
    share_string:
      'eyJ2IjoxLCJwYWdlIjp7Im5hbWUiOiJXb3JkIG9mIHRoZSBEYXkiLCJ0eXBlIjoidGVtcGxhdGUiLCJkZXZpY2VfdHlwZSI6ImZsYWdzaGlwIiwiZGlzcGxheV90eXBlIjpudWxsLCJyb3dzIjpudWxsLCJ0ZW1wbGF0ZSI6WyJ7e3JlZH19e3t5ZWxsb3d9fXt7cmVkfX17e2ZpbGxfc3BhY2V9fVBBTEFCUkEgREVMIERJQSB7e2ZpbGxfc3BhY2V9fXt7cmVkfX17e3llbGxvd319e3tyZWR9fSIsInt7cmVkfX17e3llbGxvd319e3tyZWR9fXt7ZmlsbF9zcGFjZX19e3t3b3JkX29mX2RheS50cmFuc2xhdGlvbl9lc319e3tmaWxsX3NwYWNlfX17e3JlZH19e3t5ZWxsb3d9fXt7cmVkfX0iLCJ7e3JlZH19e3t5ZWxsb3d9fXt7cmVkfX17e2ZpbGxfc3BhY2V9fXt7cmVkfX17e3llbGxvd319e3tyZWR9fSIsInt7d29yZF9vZl9kYXkud29yZH19ICh7e3dvcmRfb2ZfZGF5LnBhcnRfb2Zfc3BlZWNofX0pIiwie3t3b3JkX29mX2RheS5kZWZpbml0aW9ufX0iLCIiXSwibGluZV9tZXRhZGF0YSI6W3siYWxpZ25tZW50IjoibGVmdCIsIndyYXAiOmZhbHNlfSx7ImFsaWdubWVudCI6ImxlZnQiLCJ3cmFwIjpmYWxzZX0seyJhbGlnbm1lbnQiOiJsZWZ0Iiwid3JhcCI6ZmFsc2V9LHsiYWxpZ25tZW50IjoibGVmdCIsIndyYXAiOmZhbHNlfSx7ImFsaWdubWVudCI6ImxlZnQiLCJ3cmFwIjpmYWxzZX0seyJhbGlnbm1lbnQiOiJsZWZ0Iiwid3JhcCI6ZmFsc2V9XSwiZHVyYXRpb25fc2Vjb25kcyI6MzAwLCJ0cmFuc2l0aW9uX3N0cmF0ZWd5IjpudWxsLCJ0cmFuc2l0aW9uX2ludGVydmFsX21zIjpudWxsLCJ0cmFuc2l0aW9uX3N0ZXBfc2l6ZSI6bnVsbH19',
  },
];

// ---------------------------------------------------------------------------
// Copy button
// ---------------------------------------------------------------------------

function CopyButton({text}: {text: string}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const el = document.createElement('textarea');
      el.value = text;
      el.style.position = 'fixed';
      el.style.opacity = '0';
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={clsx(styles.copyButton, copied && styles.copyButtonDone)}
      aria-label="Copy import string to clipboard"
    >
      {copied ? (
        <>
          <svg viewBox="0 0 20 20" width="13" height="13" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
          Copied!
        </>
      ) : (
        <>
          <svg viewBox="0 0 20 20" width="13" height="13" fill="currentColor" aria-hidden="true">
            <path d="M8 3a1 1 0 011-1h2a1 1 0 110 2H9a1 1 0 01-1-1z" />
            <path d="M6 3a2 2 0 00-2 2v11a2 2 0 002 2h8a2 2 0 002-2V5a2 2 0 00-2-2 3 3 0 01-3 3H9a3 3 0 01-3-3z" />
          </svg>
          Copy import string
        </>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Pick card
// ---------------------------------------------------------------------------

function PickCard({pick}: {pick: Pick}) {
  return (
    <div className={styles.pickCard}>
      {/* Board preview */}
      <div className={styles.previewWell}>
        <img
          src={pick.image}
          alt={`${pick.name} displayed on a Vestaboard`}
          className={styles.previewImage}
          loading="lazy"
        />
      </div>

      {/* Body */}
      <div className={styles.cardBody}>
        <div>
          <Heading as="h3" className={styles.cardTitle}>{pick.name}</Heading>
          <p className={styles.cardDescription}>{pick.description}</p>
        </div>

        {/* Required plugins */}
        {pick.required_plugins.length > 0 && (
          <div className={styles.pluginRow}>
            <span className={styles.pluginLabel}>Requires</span>
            {pick.required_plugins.map((p) => (
              <span key={p.id} className={styles.pluginPill}>{p.name}</span>
            ))}
          </div>
        )}

        {/* Tags */}
        <div className={styles.tagRow}>
          <span className={clsx(styles.pluginPill, styles.tag)}>
            {pick.device_type === 'flagship' ? 'Flagship' : 'Note'}
          </span>
          {pick.tags.map((tag) => (
            <span key={tag} className={styles.tag}>{tag}</span>
          ))}
        </div>

        {/* Import widget */}
        <div className={styles.importWidget}>
          <div className={styles.importWidgetHeader}>
            <p className={styles.importWidgetLabel}>Import string</p>
            <CopyButton text={pick.share_string} />
          </div>
          <div className={styles.importStringBox}>
            {pick.share_string}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PicksPage(): ReactNode {
  return (
    <Layout
      title="Staff Picks"
      description="Hand-picked templates from the FiestaBoard team. Browse curated pages and import them into your board in one click."
    >
      {/* Hero */}
      <header className={styles.heroBanner}>
        <div className="container">
          <div className={styles.heroIcon} aria-hidden="true">✦</div>
          <Heading as="h1" className={styles.heroTitle}>Staff Picks</Heading>
          <p className={styles.heroSubtitle}>
            Curated templates from the FiestaBoard team
          </p>
          <p className={styles.hersByline}>
            Hand-picked by the creators of FiestaBoard
          </p>
        </div>
      </header>

      {/* Gallery */}
      <main>
        <section className={styles.picksSection}>
          <div className="container">
            <div className={styles.picksGrid}>
              {PICKS.map((pick) => (
                <PickCard key={pick.id} pick={pick} />
              ))}
            </div>
          </div>
        </section>

        {/* How to import CTA */}
        <section className={styles.ctaSection}>
          <div className="container">
            <Heading as="h2" className={styles.ctaTitle}>
              How to import a pick
            </Heading>
            <p className={styles.ctaSubtitle}>
              Copy the import string above, open FiestaBoard, go to{' '}
              <strong>Pages → Import</strong>, paste, and you're done.
              The page appears in your library ready to schedule or display.
            </p>
            <div className={styles.ctaButtons}>
              <Link
                className="button button--primary button--lg"
                to="/docs/intro">
                Get Started with FiestaBoard
              </Link>
              <Link
                className="button button--outline button--primary button--lg"
                href="https://github.com/Fiestaboard/FiestaBoard">
                View on GitHub
              </Link>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
