"use client";

import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Cloud, CloudOff, AlertCircle, CheckCircle } from "lucide-react";
import { api } from "@/lib/api";

interface SyncHealthData {
  total_appointments: number;
  synced: number;
  pending: number;
  failed: number;
  conflict: number;
  sync_rate: number;
  recent_failures: Array<{
    id: number;
    scheduled_at: string;
    sync_error: string | null;
    external_calendar_id: string | null;
  }>;
}

export function CalendarSyncHealthWidget() {
  const { data: healthData, isLoading } = useQuery<SyncHealthData>({
    queryKey: ["appointment-sync-health"],
    queryFn: async () => {
      const response = await api.get("/api/v1/crm/appointments/sync-health");
      return response.data;
    },
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  if (isLoading || !healthData) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Calendar Sync Health</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-4">
            <Cloud className="h-8 w-8 animate-pulse text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    );
  }

  const getSyncStatusColor = () => {
    if (healthData.sync_rate >= 90) return "text-green-600";
    if (healthData.sync_rate >= 70) return "text-yellow-600";
    return "text-red-600";
  };

  const getSyncStatusIcon = () => {
    if (healthData.sync_rate >= 90) return <CheckCircle className="h-5 w-5 text-green-600" />;
    if (healthData.sync_rate >= 70) return <AlertCircle className="h-5 w-5 text-yellow-600" />;
    return <CloudOff className="h-5 w-5 text-red-600" />;
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between text-sm font-medium">
          <span>Calendar Sync Health</span>
          {getSyncStatusIcon()}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Sync Rate */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Sync Rate</span>
          <span className={`text-2xl font-bold ${getSyncStatusColor()}`}>
            {healthData.sync_rate}%
          </span>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg bg-green-50 p-2 text-center dark:bg-green-950/30">
            <div className="font-semibold text-green-700 dark:text-green-400">
              {healthData.synced}
            </div>
            <div className="text-green-600/80 dark:text-green-500/80">Synced</div>
          </div>

          <div className="rounded-lg bg-yellow-50 p-2 text-center dark:bg-yellow-950/30">
            <div className="font-semibold text-yellow-700 dark:text-yellow-400">
              {healthData.pending}
            </div>
            <div className="text-yellow-600/80 dark:text-yellow-500/80">Pending</div>
          </div>

          <div className="rounded-lg bg-red-50 p-2 text-center dark:bg-red-950/30">
            <div className="font-semibold text-red-700 dark:text-red-400">{healthData.failed}</div>
            <div className="text-red-600/80 dark:text-red-500/80">Failed</div>
          </div>

          <div className="rounded-lg bg-orange-50 p-2 text-center dark:bg-orange-950/30">
            <div className="font-semibold text-orange-700 dark:text-orange-400">
              {healthData.conflict}
            </div>
            <div className="text-orange-600/80 dark:text-orange-500/80">Conflicts</div>
          </div>
        </div>

        {/* Recent Failures */}
        {healthData.recent_failures.length > 0 && (
          <div className="space-y-1 border-t pt-3">
            <div className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <AlertCircle className="h-3 w-3" />
              <span>Recent Failures</span>
            </div>
            <div className="space-y-1">
              {healthData.recent_failures.slice(0, 3).map((failure) => (
                <div
                  key={failure.id}
                  className="rounded-md bg-red-50 p-2 text-[10px] text-red-800 dark:bg-red-950/30 dark:text-red-400"
                >
                  <div className="flex items-center justify-between gap-1">
                    <span className="truncate">
                      {failure.external_calendar_id ?? "Unknown calendar"}
                    </span>
                    <span className="shrink-0 text-muted-foreground">
                      {new Date(failure.scheduled_at).toLocaleDateString()}
                    </span>
                  </div>
                  {failure.sync_error && (
                    <div className="mt-0.5 truncate opacity-70">{failure.sync_error}</div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Total Appointments */}
        <div className="border-t pt-2 text-center text-xs text-muted-foreground">
          {healthData.total_appointments} total appointments
        </div>
      </CardContent>
    </Card>
  );
}
