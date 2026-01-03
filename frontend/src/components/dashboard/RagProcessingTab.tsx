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
  RotateCcw,
  Wifi,
  WifiOff,
} from "lucide-react";
import { useProcessingRealtime, type ProcessingJob as RealtimeJob } from "@/hooks/useProcessingRealtime";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Document {
  id: string;
  filename: string;
  original_filename: string;
  status: "pending" | "processing" | "completed" | "failed";
  error_message: string | null;
  chunk_count: number;
  created_at: string;
  processed_at: string | null;
}

interface ProcessingJob {
  id: string;
  job_type: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  message: string | null;
  error_message?: string | null;
  created_at: string;
}

interface RagProcessingTabProps {
  ragId: string;
  accessToken: string;
  onProcessingComplete?: () => void;
}

export function RagProcessingTab({ ragId, accessToken, onProcessingComplete }: RagProcessingTabProps) {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [activeJob, setActiveJob] = useState<ProcessingJob | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);
  const [isClearingLocks, setIsClearingLocks] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);
  const [lastTriggeredAt, setLastTriggeredAt] = useState<Date | null>(null);

  // Fetch documents (for realtime refresh callback)
  const refreshDocuments = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/documents`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error("Failed to fetch documents");
      const data = await response.json();
      setDocuments(data.documents || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch documents");
    } finally {
      setIsRefreshing(false);
    }
  }, [ragId, accessToken]);

  // Real-time updates via Supabase Realtime
  const { 
    activeJob: realtimeJob, 
    isConnected: realtimeConnected,
    connectionError: realtimeError,
  } = useProcessingRealtime({
    ragId,
    onJobUpdate: (job) => {
      // Convert realtime job to local ProcessingJob type
      // progress is already a percentage (0-100) from the database
      setActiveJob({
        id: job.id,
        job_type: job.job_type,
        status: job.status === "processing" ? "running" : job.status,
        progress: job.progress,
        message: job.message,
        error_message: job.error_message,
        created_at: job.created_at,
      });
    },
    onDocumentUpdate: () => {
      // Refresh document list when any document status changes
      refreshDocuments();
    },
    onProcessingComplete: () => {
      refreshDocuments();
      onProcessingComplete?.();
    },
  });

  // Calculate stats from documents
  const pendingCount = documents.filter(d => d.status === "pending").length;
  const processingCount = documents.filter(d => d.status === "processing").length;
  const completedCount = documents.filter(d => d.status === "completed").length;
  const failedCount = documents.filter(d => d.status === "failed").length;

  // Fetch processing jobs (fallback when realtime not available)
  const fetchJobs = useCallback(async () => {
    // Skip polling if realtime is connected
    if (realtimeConnected) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/jobs`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (response.ok) {
        const data = await response.json();
        // Find the most recent running job
        const jobs: ProcessingJob[] = data.jobs || [];
        const runningJob = jobs.find(j => j.status === "running");
        const recentJob = jobs[0]; // Most recent
        
        // If there's a running job, or a recently completed one (within 10s), show it
        if (runningJob) {
          setActiveJob(runningJob);
        } else if (recentJob && (Date.now() - new Date(recentJob.created_at).getTime()) < 60000) {
          setActiveJob(recentJob);
        } else {
          setActiveJob(null);
        }
      }
    } catch (err) {
      console.error("Failed to fetch jobs:", err);
    }
  }, [ragId, accessToken, realtimeConnected]);

  // Initial load
  useEffect(() => {
    refreshDocuments();
    fetchJobs();
  }, [refreshDocuments, fetchJobs]);

  // Auto-refresh documents - less frequent when realtime is connected
  useEffect(() => {
    // When realtime is connected, just refresh every 30s as a fallback
    // When not connected, poll every 5s
    const interval = setInterval(
      refreshDocuments, 
      realtimeConnected ? 30000 : 5000
    );
    return () => clearInterval(interval);
  }, [refreshDocuments, realtimeConnected]);

  // Poll jobs - only when realtime is not connected
  useEffect(() => {
    if (realtimeConnected) return; // No polling needed
    
    const interval = setInterval(fetchJobs, activeJob?.status === "running" ? 2000 : 10000);
    return () => clearInterval(interval);
  }, [fetchJobs, activeJob?.status, realtimeConnected]);

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
      await refreshDocuments();
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
      await refreshDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to clear locks");
    } finally {
      setIsClearingLocks(false);
    }
  };

  // Retry failed documents
  const retryFailed = async () => {
    setIsRetrying(true);
    setError(null);
    try {
      // Reset failed documents to pending, then trigger processing
      const response = await fetch(`${API_BASE_URL}/rags/${ragId}/retry-failed`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!response.ok) throw new Error("Failed to retry failed documents");
      const data = await response.json();
      setTriggerMessage(data.message || "Retrying failed documents...");
      setLastTriggeredAt(new Date());
      await refreshDocuments();
      await fetchJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retry failed documents");
    } finally {
      setIsRetrying(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "pending": return <Clock className="h-4 w-4 text-muted-foreground" />;
      case "processing": return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
      case "completed": return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed": return <AlertCircle className="h-4 w-4 text-red-500" />;
      default: return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "pending": return <Badge variant="secondary">Pending</Badge>;
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

      {/* Active Job Progress */}
      {activeJob && (
        <Card className={
          activeJob.status === "running" 
            ? "border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-950/30"
            : activeJob.status === "completed"
            ? "border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-950/30"
            : activeJob.status === "failed"
            ? "border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-950/30"
            : ""
        }>
          <CardContent className="pt-6">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {activeJob.status === "running" ? (
                    <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
                  ) : activeJob.status === "completed" ? (
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-red-500" />
                  )}
                  <span className="font-medium">
                    {activeJob.status === "running" ? "Processing Documents..." : 
                     activeJob.status === "completed" ? "Processing Complete" : "Processing Failed"}
                  </span>
                </div>
                <span className="text-sm font-medium">{activeJob.progress}%</span>
              </div>
              <Progress value={activeJob.progress} className="h-2" />
              {activeJob.message && (
                <p className="text-sm text-muted-foreground">{activeJob.message}</p>
              )}
              {activeJob.error_message && (
                <p className="text-sm text-red-600 dark:text-red-400">{activeJob.error_message}</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Pending</p>
                <p className="text-2xl font-bold">{pendingCount}</p>
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
                Document Processing Status
                {/* Realtime connection indicator */}
                {realtimeConnected ? (
                  <span className="flex items-center gap-1 text-xs font-normal text-green-600 dark:text-green-400" title="Live updates enabled">
                    <Wifi className="h-3 w-3" />
                    Live
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs font-normal text-muted-foreground" title={realtimeError || "Polling for updates"}>
                    <WifiOff className="h-3 w-3" />
                    Polling
                  </span>
                )}
              </CardTitle>
              <CardDescription>
                {lastTriggeredAt && (
                  <>Last triggered: {lastTriggeredAt.toLocaleTimeString()}. </>
                )}
                Click &quot;Process Pending&quot; to send documents to Modal for MinerU extraction.
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
                onClick={refreshDocuments}
                disabled={isRefreshing}
              >
                <RefreshCw className={`h-4 w-4 mr-1 ${isRefreshing ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              <Button
                size="sm"
                onClick={triggerProcessing}
                disabled={isTriggering || pendingCount === 0}
              >
                {isTriggering ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-1" />
                )}
                Process Pending ({pendingCount})
              </Button>
              {failedCount > 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={retryFailed}
                  disabled={isRetrying}
                  className="text-red-600 hover:text-red-700 border-red-300"
                >
                  {isRetrying ? (
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  ) : (
                    <RotateCcw className="h-4 w-4 mr-1" />
                  )}
                  Retry Failed ({failedCount})
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {documents.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Activity className="h-10 w-10 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No documents uploaded yet</p>
              <p className="text-xs mt-1">Go to the Upload tab to add documents</p>
            </div>
          ) : (
            <ScrollArea className="h-[400px]">
              <div className="space-y-3">
                {documents.map(doc => (
                  <div
                    key={doc.id}
                    className={`flex items-center gap-4 p-4 rounded-lg border ${
                      doc.status === "pending" 
                        ? "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800"
                        : doc.status === "processing"
                        ? "bg-blue-50 dark:bg-blue-950/30 border-blue-300 dark:border-blue-700"
                        : doc.status === "completed"
                        ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800"
                        : "bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800"
                    }`}
                  >
                    {getStatusIcon(doc.status)}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <span className="font-medium truncate">
                          {doc.original_filename}
                        </span>
                        {getStatusBadge(doc.status)}
                      </div>
                      {doc.error_message && (
                        <p className="text-xs text-red-600 dark:text-red-400 mt-1 truncate">
                          {doc.error_message}
                        </p>
                      )}
                    </div>
                    <div className="text-right text-xs text-muted-foreground">
                      {doc.chunk_count > 0 && <div>{doc.chunk_count} chunks</div>}
                      <div>{formatDate(doc.created_at)}</div>
                      {doc.processed_at && (
                        <div>Processed: {formatDate(doc.processed_at)}</div>
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
