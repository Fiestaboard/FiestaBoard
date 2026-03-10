import { cn } from "@/lib/utils";

interface PageToolbarProps {
  left?: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
}

export function PageToolbar({ left, right, className }: PageToolbarProps) {
  return (
    <div
      className={cn(
        "mb-4 flex items-center animate-card-fade-in",
        left && right ? "justify-between" : right ? "justify-end" : "justify-start",
        className,
      )}
      style={{ animationDelay: "50ms" }}
    >
      {left && <div className="flex items-center gap-3">{left}</div>}
      {right && <div className="flex items-center gap-3">{right}</div>}
    </div>
  );
}
