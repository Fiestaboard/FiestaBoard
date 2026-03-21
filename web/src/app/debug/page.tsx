"use client";

import { Activity } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Card, CardContent } from "@/components/ui/card";

export default function DebugMonitorPage() {
  return (
    <PageLayout title="Monitor" icon={Activity}>
        <Card>
          <CardContent className="py-12 text-center">
            <Activity className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h2 className="text-lg font-semibold mb-2">Monitoring Removed</h2>
            <p className="text-sm text-muted-foreground max-w-lg mx-auto">
              In-container monitoring (Prometheus &amp; Grafana) has been removed
              to reduce image size and speed up container startup.
              Use Docker&apos;s built-in logging instead:{" "}
              <code className="px-1.5 py-0.5 rounded bg-muted font-mono text-xs">docker logs fiestaboard</code>
            </p>
          </CardContent>
        </Card>
    </PageLayout>
  );
}
