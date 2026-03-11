import { cn } from "@/lib/utils";

interface FiestaLogoProps {
  size?: "sm" | "md";
  className?: string;
}

/**
 * CSS-based wordmark logo for FiestaBoard.
 *
 * "Fiesta" uses a warm multi-stop gradient that echoes the sidebar palette,
 * while "Board" stays solid in the current foreground color for contrast.
 * A small four-pointed star accent sits between the two words at the baseline
 * to give the mark a festive but professional feel.
 */
export function FiestaLogo({ size = "md", className }: FiestaLogoProps) {
  const isSm = size === "sm";

  return (
    <span
      aria-label="FiestaBoard"
      role="img"
      className={cn(
        "fiesta-logo inline-flex items-baseline select-none leading-none",
        isSm ? "text-lg" : "text-xl",
        className,
      )}
    >
      <span className="fiesta-logo-fiesta font-extrabold tracking-tight">
        Fiesta
      </span>
      <span className="fiesta-logo-star" />
      <span className="fiesta-logo-board font-medium tracking-tight">
        Board
      </span>
    </span>
  );
}
