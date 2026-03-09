import {useState, useEffect, useCallback, type ReactNode} from 'react';
import styles from './styles.module.css';

interface BoardScreenshotProps {
  src: string;
  alt?: string;
  black?: string;
  white?: string;
}

function deriveBoardPaths(src: string): {black: string; white: string} {
  const lastSlash = src.lastIndexOf('/');
  const dir = src.substring(0, lastSlash);
  const filename = src.substring(lastSlash + 1);
  return {
    black: `${dir}/black/${filename}`,
    white: `${dir}/white/${filename}`,
  };
}

function BoardToggle({
  activeStyle,
  onSetStyle,
}: {
  activeStyle: 'black' | 'white';
  onSetStyle: (style: 'black' | 'white') => void;
}) {
  return (
    <div className={styles.toggleBar}>
      <button
        type="button"
        className={`${styles.toggleButton} ${activeStyle === 'black' ? styles.active : ''}`}
        onClick={() => onSetStyle('black')}
        aria-label="Show black board screenshot"
        title="Black board">
        Black
      </button>
      <button
        type="button"
        className={`${styles.toggleButton} ${activeStyle === 'white' ? styles.active : ''}`}
        onClick={() => onSetStyle('white')}
        aria-label="Show white board screenshot"
        title="White board">
        White
      </button>
    </div>
  );
}

function Lightbox({
  src,
  alt,
  activeStyle,
  onSetStyle,
  onClose,
}: {
  src: string;
  alt: string;
  activeStyle: 'black' | 'white';
  onSetStyle: (style: 'black' | 'white') => void;
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
          <BoardToggle activeStyle={activeStyle} onSetStyle={onSetStyle} />
        </div>
      </div>
    </div>
  );
}

export default function BoardScreenshot({
  src,
  alt = '',
  black,
  white,
}: BoardScreenshotProps): ReactNode {
  const derived = deriveBoardPaths(src);
  const blackSrc = black ?? derived.black;
  const whiteSrc = white ?? derived.white;

  const [activeStyle, setActiveStyle] = useState<'black' | 'white'>('black');
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const activeSrc = activeStyle === 'black' ? blackSrc : whiteSrc;

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
        <figcaption className={styles.caption}>
          <BoardToggle activeStyle={activeStyle} onSetStyle={setActiveStyle} />
        </figcaption>
      </figure>
      {lightboxOpen && (
        <Lightbox
          src={activeSrc}
          alt={alt}
          activeStyle={activeStyle}
          onSetStyle={setActiveStyle}
          onClose={() => setLightboxOpen(false)}
        />
      )}
    </>
  );
}
