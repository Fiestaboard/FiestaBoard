import { cn } from "@/lib/utils";

interface FiestaLogoProps {
  size?: "sm" | "md";
  className?: string;
}

export function FiestaLogo({ size = "md", className }: FiestaLogoProps) {
  const isSm = size === "sm";

  return (
    <span
      className={cn(
        "inline-flex items-baseline select-none leading-none",
        isSm ? "text-lg" : "text-xl",
        className,
      )}
    >
      <span className="font-bold tracking-tight text-brand">
        Fiesta
      </span>
      <span
        className={cn(
          "mx-[0.1em] inline-block rounded-full bg-brand/40",
          isSm ? "h-[0.2em] w-[0.2em]" : "h-[0.22em] w-[0.22em]",
        )}
        style={{ alignSelf: "center" }}
      />
      <span className="font-medium tracking-tight text-sidebar-foreground/80">
        Board
      </span>
    </span>
  );
}
