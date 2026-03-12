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
        "inline-flex items-baseline select-none leading-none tracking-tight",
        isSm ? "text-lg" : "text-xl",
        className,
      )}
    >
      <span className="font-black text-brand">
        Fiesta
      </span>
      <span className="font-light text-sidebar-foreground">
        Board
      </span>
    </span>
  );
}
