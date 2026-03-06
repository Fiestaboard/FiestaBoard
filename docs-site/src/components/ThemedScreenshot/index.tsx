import {useState, useEffect, useCallback, type ReactNode} from 'react';
import {useColorMode} from '@docusaurus/theme-common';
import styles from './styles.module.css';

interface ThemedScreenshotProps {
  src: string;
  alt?: string;
  light?: string;
  dark?: string;
}

function deriveThemedPaths(src: string): {light: string; dark: string} {
  const lastSlash = src.lastIndexOf('/');
  const dir = src.substring(0, lastSlash);
  const filename = src.substring(lastSlash + 1);
  return {
    light: `${dir}/light/${filename}`,
    dark: `${dir}/dark/${filename}`,
  };
}

function ThemeToggle({
  activeMode,
  onSetMode,
}: {
  activeMode: 'light' | 'dark';
  onSetMode: (mode: 'light' | 'dark') => void;
}) {
  return (
    <div className={styles.toggleBar}>
      <button
        type="button"
        className={`${styles.toggleButton} ${activeMode === 'light' ? styles.active : ''}`}
        onClick={() => onSetMode('light')}
        aria-label="Show light mode screenshot"
        title="Light mode">
        <svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor" aria-hidden="true">
          <path d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" />
        </svg>
        <span>Light</span>
      </button>
      <button
        type="button"
        className={`${styles.toggleButton} ${activeMode === 'dark' ? styles.active : ''}`}
        onClick={() => onSetMode('dark')}
        aria-label="Show dark mode screenshot"
        title="Dark mode">
        <svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor" aria-hidden="true">
          <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
        </svg>
        <span>Dark</span>
      </button>
    </div>
  );
}

function Lightbox({
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
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [handleKeyDown]);

  return (
    <div className={styles.lightboxOverlay} onClick={onClose} role="dialog" aria-modal="true">
      <div className={styles.lightboxContent} onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className={styles.lightboxClose}
          onClick={onClose}
          aria-label="Close">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>
        <img className={styles.lightboxImage} src={src} alt={alt} />
        <div className={styles.lightboxFooter}>
          <ThemeToggle activeMode={activeMode} onSetMode={onSetMode} />
        </div>
      </div>
    </div>
  );
}

export default function ThemedScreenshot({
  src,
  alt = '',
  light,
  dark,
}: ThemedScreenshotProps): ReactNode {
  const {colorMode} = useColorMode();
  const derived = deriveThemedPaths(src);
  const lightSrc = light ?? derived.light;
  const darkSrc = dark ?? derived.dark;

  const [activeMode, setActiveMode] = useState<'light' | 'dark'>(colorMode);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  useEffect(() => {
    setActiveMode(colorMode);
  }, [colorMode]);

  const activeSrc = activeMode === 'light' ? lightSrc : darkSrc;

  return (
    <>
      <figure className={styles.container}>
        <img
          className={styles.image}
          src={activeSrc}
          alt={alt}
          loading="lazy"
          onClick={() => setLightboxOpen(true)}
        />
        <figcaption className={styles.toggleBar}>
          <ThemeToggle activeMode={activeMode} onSetMode={setActiveMode} />
        </figcaption>
      </figure>
      {lightboxOpen && (
        <Lightbox
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
