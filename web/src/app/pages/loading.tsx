import { Skeleton } from "@/components/ui/skeleton";
import { FileText } from "lucide-react";

export default function PagesLoading() {
  return (
    <div className="min-h-screen bg-background overflow-x-hidden">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
        <div className="mb-6 animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="page-title flex items-center gap-3">
                <FileText className="h-7 w-7 text-brand-emphasis" />
                Pages
              </h1>
              <p className="page-description">
                Create and manage content for your board
              </p>
            </div>
            <div className="flex items-center gap-3 pt-1">
              <Skeleton className="h-8 w-[68px] rounded-md" />
              <Skeleton className="h-9 sm:h-8 w-[68px] rounded-md" />
            </div>
          </div>
        </div>

        <div className="animate-card-fade-in" style={{ animationDelay: "150ms" }}>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 sm:gap-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="aspect-[9/16] w-full rounded-lg" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
