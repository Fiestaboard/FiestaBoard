import { useColorMode } from "@docusaurus/theme-common";
import { Box, Button } from "@fiestaboard/ui";
import clsx from "clsx";
import { X } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import styles from "./styles.module.css";

interface BoardScreenshotProps {
  src: string;
  alt?: string;
  black?: string;
  white?: string;
}

function deriveBoardPaths(src: string): { black: string; white: string } {
  const lastSlash = src.lastIndexOf("/");
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
  activeStyle: "black" | "white";
  onSetStyle: (style: "black" | "white") => void;
}) {
  return (
    <Box className={styles.toggleBar}>
      {(["black", "white"] as const).map((style) => (
        <Button
          key={style}
          type="button"
          variant="ghost"
          aria-pressed={activeStyle === style}
          className={clsx(styles.toggleButton, activeStyle === style && styles.active)}
          onClick={() => onSetStyle(style)}
          aria-label={`Show ${style} board screenshot`}
          title={`${style === "black" ? "Black" : "White"} board`}
        >
          {style === "black" ? "Black" : "White"}
        </Button>
      ))}
    </Box>
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
  activeStyle: "black" | "white";
  onSetStyle: (style: "black" | "white") => void;
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
          <BoardToggle activeStyle={activeStyle} onSetStyle={onSetStyle} />
        </Box>
      </Box>
    </Box>
  );
}

export default function BoardScreenshot({ src, alt = "", black, white }: BoardScreenshotProps): ReactNode {
  const { colorMode } = useColorMode();
  const derived = deriveBoardPaths(src);
  const blackSrc = black ?? derived.black;
  const whiteSrc = white ?? derived.white;

  const defaultStyle = colorMode === "light" ? "white" : "black";
  const [activeStyle, setActiveStyle] = useState<"black" | "white">(defaultStyle);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  useEffect(() => {
    setActiveStyle(colorMode === "light" ? "white" : "black");
  }, [colorMode]);

  const activeSrc = activeStyle === "black" ? blackSrc : whiteSrc;

  return (
    <>
      <figure className={styles.container}>
        <img className={styles.image} src={activeSrc} alt={alt} loading="lazy" onClick={() => setLightboxOpen(true)} />
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
