import { cn } from "@/lib/utils";

interface PageLayoutProps {
  children: React.ReactNode;
  className?: string;
  outerClassName?: string;
}

export function PageLayout({ children, className, outerClassName }: PageLayoutProps) {
  return (
    <div className={cn("min-h-screen bg-background overflow-x-hidden", outerClassName)}>
      <div className={cn(
        "container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 lg:py-3 max-w-[1920px]",
        className
      )}>
        {children}
      </div>
    </div>
  );
}
