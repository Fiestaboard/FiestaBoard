import { cn } from "@/lib/utils";

interface PageLayoutProps {
  children: React.ReactNode;
  className?: string;
  outerClassName?: string;
  /** When true, the layout fills the viewport height and hides overflow so
   *  inner content (e.g. the schedule calendar) can scroll independently. */
  fillHeight?: boolean;
}

export function PageLayout({ children, className, outerClassName, fillHeight }: PageLayoutProps) {
  return (
    <div className={cn(
      "bg-background overflow-x-hidden",
      fillHeight ? "flex-1 min-h-0 flex flex-col overflow-hidden" : "min-h-full",
      outerClassName
    )}>
      <div className={cn(
        "container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 lg:py-3 max-w-full",
        fillHeight && "flex-1 min-h-0 flex flex-col overflow-hidden",
        className
      )}>
        {children}
      </div>
    </div>
  );
}
