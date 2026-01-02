"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Progress } from "@/components/ui/progress";
import { 
  Activity, 
  Play, 
  CheckCircle,
  AlertCircle,
  Clock,
  Loader2,
  FileText,
  RefreshCw,
  Unlock,
} from "lucide-react";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ProcessingJob {
  id: string;
  job_type: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;
  message: string | null;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
  filename?: string;
  pages?: number;
  chunks?: number;
}

interface RagProcessingTabProps {
  ragId: string;
  accessToken: string;
  onProcessingComplete?: () => void;
}

export function RagProcessingTab({ ragId, accessToken, onProcessingComplete }: RagProcessingTabProps) {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);
  const [isClearingLocks, setIsClearingLocks] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);
  const [lastTriggeredAt, setLastTriggeredAt] = useState<Date | null>(null);

  // Calculate stats
  const queuedCount = jobs.filter(j => j.status === "queued").length;
  const processingCount = jobs.filter(j => j.status === "processing").length;
  const completedCount = jobs.filter(j => j.status === "completed").length;
  const failedCount = jobs.filter(j => j.status === "failed").length;

  // Fetch jobs
  const refreshJobs = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/jobs`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error("Failed to fetch jobs");
      const data = await response.json();
      setJobs(data.jobs || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch jobs");
    } finally {
      setIsRefreshing(false);
    }
  }, [ragId, accessToken]);

  // Initial load
  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    const interval = setInterval(refreshJobs, 5000);
    return () => clearInterval(interval);
  }, [refreshJobs]);

  // Trigger processing
  const triggerProcessing = async () => {
    setIsTriggering(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/process`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error("Failed to trigger processing");
      const data = await response.json();
      setTriggerMessage(data.message || "Processing triggered");
      setLastTriggeredAt(new Date());
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger processing");
    } finally {
      setIsTriggering(false);
    }
  };

  // Clear locks
  const clearLocks = async () => {
    setIsClearingLocks(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/locks`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error("Failed to clear locks");
      const data = await response.json();
      setTriggerMessage(data.message || "Locks cleared");
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear locks");
    } finally {
      setIsClearingLocks(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "queued": return <Clock className="h-4 w-4 text-muted-foreground" />;
      case "processing": return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
      case "completed": return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed": return <AlertCircle className="h-4 w-4 text-red-500" />;
      default: return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "queued": return <Badge variant="secondary">Queued</Badge>;
      case "processing": return <Badge className="bg-blue-500">Processing</Badge>;
      case "completed": return <Badge className="bg-green-500">Completed</Badge>;
      case "failed": return <Badge variant="destructive">Failed</Badge>;
      default: return <Badge variant="secondary">{status}</Badge>;
    }
  };

  const formatDuration = (start?: string, end?: string) => {
    if (!start) return "-";
    const startDate = new Date(start);
    const endDate = end ? new Date(end) : new Date();
    const seconds = Math.floor((endDate.getTime() - startDate.getTime()) / 1000);
    
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="space-y-6">
      {/* Error Banner */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 text-destructive px-4 py-3 rounded-lg flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          <span>{error}</span>
          <Button variant="ghost" size="sm" onClick={() => setError(null)} className="ml-auto">
            Dismiss
          </Button>
        </div>
      )}
      
      {/* Success Message */}
      {triggerMessage && (
        <div className="bg-green-500/10 border border-green-500/20 text-green-700 dark:text-green-400 px-4 py-3 rounded-lg flex items-center gap-2">
          <CheckCircle className="h-4 w-4" />
          <span>{triggerMessage}</span>
          <Button variant="ghost" size="sm" onClick={() => setTriggerMessage(null)} className="ml-auto">
            Dismiss
          </Button>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Queued</p>
                <p className="text-2xl font-bold">{queuedCount}</p>
              </div>
              <Clock className="h-8 w-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Processing</p>
                <p className="text-2xl font-bold">{processingCount}</p>
              </div>
              {processingCount > 0 ? (
                <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
              ) : (
                <Activity className="h-8 w-8 text-muted-foreground" />
              )}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Completed</p>
                <p className="text-2xl font-bold">{completedCount}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Failed</p>
                <p className="text-2xl font-bold">{failedCount}</p>
              </div>
              <AlertCircle className="h-8 w-8 text-red-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Processing Queue */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Activity className="h-5 w-5" />
                Processing Queue
              </CardTitle>
              <CardDescription>
                {lastTriggeredAt && (
                  <>Last triggered: {lastTriggeredAt.toLocaleTimeString()}. </>
                )}
                Click &quot;Process Pending&quot; to start processing queued documents.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={clearLocks}
                disabled={isClearingLocks}
                title="Clear stale processing locks"
              >
                {isClearingLocks ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Unlock className="h-4 w-4 mr-1" />
                    Clear Locks
                  </>
                )}
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={refreshJobs}
                disabled={isRefreshing}
              >
                <RefreshCw className={`h-4 w-4 mr-1 ${isRefreshing ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              <Button
                size="sm"
                onClick={triggerProcessing}
                disabled={isTriggering || queuedCount === 0}
              >
                {isTriggering ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-1" />
                )}
                Process Pending ({queuedCount})
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {jobs.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Activity className="h-10 w-10 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No processing jobs</p>
              <p className="text-xs mt-1">Upload documents to start processing</p>
            </div>
          ) : (
            <ScrollArea className="h-[400px]">
              <div className="space-y-3">
                {jobs.map(job => (
                  <div
                    key={job.id}
                    className={`flex items-center gap-4 p-4 rounded-lg border ${
                      job.status === "queued" 
                        ? "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800"
                        : job.status === "processing"
                        ? "bg-blue-50 dark:bg-blue-950/30 border-blue-300 dark:border-blue-700"
                        : job.status === "completed"
                        ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800"
                        : "bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800"
                    }`}
                  >
                    {getStatusIcon(job.status)}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium truncate">
                          {job.filename || job.job_type}
                        </span>
                        {getStatusBadge(job.status)}
                      </div>
                      {job.status === "processing" && job.progress > 0 && (
                        <Progress value={job.progress} className="h-1 mt-2" />
                      )}
                      {job.message && (
                        <p className="text-xs text-muted-foreground mt-1 truncate">
                          {job.message}
                        </p>
                      )}
                      {job.error && (
                        <p className="text-xs text-red-600 dark:text-red-400 mt-1 truncate">
                          {job.error}
                        </p>
                      )}
                    </div>
                    <div className="text-right text-xs text-muted-foreground">
                      {job.pages && <div>{job.pages} pages</div>}
                      {job.chunks && <div>{job.chunks} chunks</div>}
                      <div>{formatDate(job.created_at)}</div>
                      {(job.status === "processing" || job.status === "completed") && job.started_at && (
                        <div>{formatDuration(job.started_at, job.completed_at)}</div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
