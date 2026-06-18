import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

interface PageHeaderProps {
  icon: LucideIcon;
  title: string;
  description: string | React.ReactNode;
  children?: React.ReactNode;
  className?: string;
  animationDelay?: string;
}

export function PageHeader({
  icon: Icon,
  title,
  description,
  children,
  className,
  animationDelay = "0ms",
}: PageHeaderProps) {
  return (
    <div
      className={cn("mb-5 rounded-xl border bg-card text-card-foreground px-6 py-4 animate-card-fade-in", className)}
      style={{ animationDelay }}
    >
      <div className="min-w-0">
        <h1 className="page-title flex items-center gap-3">
          <Icon className="h-5 w-5 flex-shrink-0" style={{ stroke: "url(#page-icon-gradient)" }} aria-hidden="true" />
          {title}
        </h1>
        <p className="page-description">{description}</p>
      </div>
      {children}
    </div>
  );
}
