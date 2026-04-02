"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Edit, Trash2, Calendar, GalleryHorizontalEnd } from "lucide-react";
import type { ScheduleEntry, Page, Carousel } from "@/lib/api";
import { isCarouselId } from "@/lib/api";

interface ScheduleListViewProps {
  schedules: ScheduleEntry[];
  pages: Page[];
  carousels?: Carousel[];
  onEdit: (schedule: ScheduleEntry) => void;
  onDelete: (id: string) => void;
}

function formatDays(schedule: ScheduleEntry): string {
  if (schedule.day_pattern === "all") return "All days";
  if (schedule.day_pattern === "weekdays") return "Mon-Fri";
  if (schedule.day_pattern === "weekends") return "Sat-Sun";
  if (schedule.day_pattern === "custom" && schedule.custom_days) {
    return schedule.custom_days
      .map((d) => d.slice(0, 3).charAt(0).toUpperCase() + d.slice(1, 3))
      .join(", ");
  }
  return "";
}

export function ScheduleListView({
  schedules,
  pages,
  carousels = [],
  onEdit,
  onDelete,
}: ScheduleListViewProps) {
  const getPageName = (pageId: string): string => {
    if (isCarouselId(pageId)) {
      const carousel = carousels.find((c) => c.id === pageId);
      return carousel?.name || pageId;
    }
    return pages.find((p) => p.id === pageId)?.name || pageId;
  };

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="text-lg">Schedule Entries</CardTitle>
      </CardHeader>
      <CardContent>
        {schedules.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <Calendar className="h-12 w-12 mx-auto mb-4" />
            <p>No schedules created yet</p>
            <p className="text-sm mt-1">Use the toolbar above to add your first schedule</p>
          </div>
        ) : (
          <div className="space-y-3">
            {schedules.map((schedule) => {
              const pageName = getPageName(schedule.page_id);
              return (
                <div
                  key={schedule.id}
                  className="flex items-center justify-between p-4 border rounded-lg"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      {isCarouselId(schedule.page_id) && (
                        <GalleryHorizontalEnd className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                      )}
                      <span className="font-medium">{pageName}</span>
                      {!schedule.enabled && (
                        <Badge variant="secondary">Disabled</Badge>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {schedule.start_time} - {schedule.end_time || "open"} • {formatDays(schedule)}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onEdit(schedule)}
                      aria-label="Edit"
                    >
                      <Edit className="h-4 w-4" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onDelete(schedule.id)}
                      aria-label="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
