import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
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
    <Card
      className={cn("mb-6 animate-card-fade-in gap-0 px-5 py-4", className)}
      style={{ animationDelay }}
    >
      <div className="min-w-0">
        <h1 className="page-title flex items-center gap-3">
          <Icon className="h-7 w-7 text-brand-emphasis flex-shrink-0" />
          {title}
        </h1>
        <p className="page-description">{description}</p>
      </div>
      {children}
    </Card>
  );
}
