"use client";

import { useStatus } from "@/hooks/use-board";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

export function ServiceControls() {
  const { data: status, isLoading } = useStatus();

  const isRunning = status?.running ?? false;

  if (isLoading) {
    return (
      <Card>
        <CardHeader className="px-4 sm:px-6">
          <CardTitle className="text-base sm:text-lg">Service Control</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 px-4 sm:px-6">
          <Skeleton className="h-5 w-full max-w-[200px]" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="px-4 sm:px-6">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base sm:text-lg">Service Control</CardTitle>
          <Badge variant={isRunning ? "default" : "secondary"} className={`text-xs ${isRunning ? "bg-brand/15 text-brand border-brand/25 hover:bg-brand/20" : ""}`}>
            {isRunning ? "● Running" : "○ Stopped"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 px-4 sm:px-6">
        <p className="text-[10px] text-muted-foreground">
          Content is automatically sent to the physical board
        </p>
      </CardContent>
    </Card>
  );
}
