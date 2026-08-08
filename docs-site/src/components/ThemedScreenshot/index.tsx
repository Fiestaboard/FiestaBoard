import { useColorMode } from "@docusaurus/theme-common";
import { Box, Button, Text } from "@fiestaboard/ui";
import clsx from "clsx";
import { Moon, Sun, X } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import styles from "./styles.module.css";

interface ThemedScreenshotProps {
  src: string;
  alt?: string;
  light?: string;
  dark?: string;
}

function deriveThemedPaths(src: string): { light: string; dark: string } {
  const lastSlash = src.lastIndexOf("/");
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
  activeMode: "light" | "dark";
  onSetMode: (mode: "light" | "dark") => void;
}) {
  const MODES = [
    { mode: "light", label: "Light", Icon: Sun },
    { mode: "dark", label: "Dark", Icon: Moon },
  ] as const;

  return (
    <Box className={styles.toggleBar}>
      {MODES.map(({ mode, label, Icon }) => (
        <Button
          key={mode}
          type="button"
          variant="ghost"
          aria-pressed={activeMode === mode}
          className={clsx(styles.toggleButton, activeMode === mode && styles.active)}
          onClick={() => onSetMode(mode)}
          aria-label={`Show ${mode} mode screenshot`}
          title={`${label} mode`}
        >
          <Icon aria-hidden="true" />
          <Text as="span">{label}</Text>
        </Button>
      ))}
    </Box>
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
  activeMode: "light" | "dark";
  onSetMode: (mode: "light" | "dark") => void;
  onClose: () => void;
}) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = "";
    };
  }, [handleKeyDown]);

  return (
    <Box className={styles.lightboxOverlay} onClick={onClose} role="dialog" aria-modal="true">
      <Box className={styles.lightboxContent} onClick={(e) => e.stopPropagation()}>
        <Button type="button" variant="ghost" className={styles.lightboxClose} onClick={onClose} aria-label="Close">
          <X aria-hidden="true" />
        </Button>
        <img className={styles.lightboxImage} src={src} alt={alt} />
        <Box className={styles.lightboxFooter}>
          <ThemeToggle activeMode={activeMode} onSetMode={onSetMode} />
        </Box>
      </Box>
    </Box>
  );
}

export default function ThemedScreenshot({ src, alt = "", light, dark }: ThemedScreenshotProps): ReactNode {
  const { colorMode } = useColorMode();
  const derived = deriveThemedPaths(src);
  const lightSrc = light ?? derived.light;
  const darkSrc = dark ?? derived.dark;

  const [activeMode, setActiveMode] = useState<"light" | "dark">(colorMode);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  useEffect(() => {
    setActiveMode(colorMode);
  }, [colorMode]);

  const activeSrc = activeMode === "light" ? lightSrc : darkSrc;

  return (
    <>
      <figure className={styles.container}>
        <img className={styles.image} src={activeSrc} alt={alt} loading="lazy" onClick={() => setLightboxOpen(true)} />
        <figcaption className={styles.caption}>
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
