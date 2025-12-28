"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  Activity, 
  Play, 
  CheckCircle,
  AlertCircle,
  Clock,
  Loader2,
  FileText,
  RotateCw
} from "lucide-react";
import { 
  getProcessingJobs, 
  triggerProcessing,
  type ProcessingJob as APIProcessingJob 
} from "@/lib/admin-api";
import { useAdminContext, ProcessingJob } from "./AdminContext";

export function ProcessingTab() {
  const { processingState, setProcessingState } = useAdminContext();
  const { jobs, triggerMessage, lastTriggeredAt, triggeredJobCount, queuedCount, processingCount, completedCount, failedCount } = processingState;

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const PROCESSING_STALE_MS = 30 * 60 * 1000; // After 30 minutes, allow re-trigger even if queued remains

  // Check if processing is likely still running (triggered within last 10 min and jobs still queued)
  const isProcessingInModal = !!(lastTriggeredAt && queuedCount > 0);
  const isTriggerStale = !!(lastTriggeredAt && (Date.now() - lastTriggeredAt.getTime() > PROCESSING_STALE_MS));

  // Restore last trigger time from localStorage so refreshes keep the button disabled during processing
  useEffect(() => {
    const stored = localStorage.getItem("admin_processing_last_trigger");
    if (stored && !lastTriggeredAt) {
      const parsed = new Date(stored);
      if (!Number.isNaN(parsed.getTime())) {
        setProcessingState(prev => ({ ...prev, lastTriggeredAt: parsed }));
      }
    }
  }, []);

  // Fetch jobs from API
  const refreshJobs = useCallback(async () => {
    setIsRefreshing(true);
    setError(null);
    
    try {
      const response = await getProcessingJobs();
      
      // Map API response to component format
      const mappedJobs: ProcessingJob[] = response.jobs.map(j => ({
        id: j.id,
        filename: j.filename,
        status: j.status,
        progress: j.progress,
        startedAt: j.started_at,
        completedAt: j.completed_at,
        error: j.error,
        pages: j.pages,
        chunks: j.chunks,
      }));
      
      // Update all state in a single call to context
      setProcessingState(prev => ({
        ...prev,
        jobs: mappedJobs,
        queuedCount: response.queued_count,
        processingCount: response.processing_count,
        completedCount: response.completed_count,
        failedCount: response.failed_count,
        // Clear the persisted trigger flag once everything finishes
        lastTriggeredAt: (response.queued_count === 0 && response.processing_count === 0) ? null : prev.lastTriggeredAt,
      }));

      // Clear localStorage if processing finished
      if (response.queued_count === 0 && response.processing_count === 0) {
        localStorage.removeItem("admin_processing_last_trigger");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch jobs");
    } finally {
      setIsRefreshing(false);
    }
  }, [setProcessingState]);

  // Initial load only if jobs are empty
  useEffect(() => {
    if (jobs.length === 0) {
      refreshJobs();
    }
  }, []);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      refreshJobs();
    }, 5000);
    
    return () => clearInterval(interval);
  }, [refreshJobs]);

  const retryJob = async (jobId: string) => {
    // TODO: Implement retry via specific endpoint when available
    console.log("Retrying job:", jobId);
    await refreshJobs();
  };

  const startBatchProcessing = async () => {
    setIsTriggering(true);
    setError(null);
    
    try {
      const response = await triggerProcessing({ max_documents: 10 });
      const now = new Date();
      localStorage.setItem("admin_processing_last_trigger", now.toISOString());
      
      // Update context state
      setProcessingState(prev => ({
        ...prev,
        triggerMessage: response.message,
        lastTriggeredAt: now,
        triggeredJobCount: response.queued,
      }));
      
      // Refresh jobs after triggering
      await refreshJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger processing");
    } finally {
      setIsTriggering(false);
    }
  };

  const getStatusIcon = (status: ProcessingJob["status"]) => {
    switch (status) {
      case "queued":
        return <Clock className="h-4 w-4 text-muted-foreground" />;
      case "processing":
        return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />;
      case "completed":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed":
        return <AlertCircle className="h-4 w-4 text-red-500" />;
    }
  };

  const getStatusBadge = (status: ProcessingJob["status"]) => {
    switch (status) {
      case "queued":
        return <Badge variant="secondary">Queued</Badge>;
      case "processing":
        return <Badge className="bg-blue-500">Processing</Badge>;
      case "completed":
        return <Badge className="bg-green-500">Completed</Badge>;
      case "failed":
        return <Badge variant="destructive">Failed</Badge>;
    }
  };

  const formatDuration = (start: string, end?: string) => {
    const startDate = new Date(start);
    const endDate = end ? new Date(end) : new Date();
    const seconds = Math.floor((endDate.getTime() - startDate.getTime()) / 1000);
    
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
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
          <Button variant="ghost" size="sm" onClick={() => setProcessingState(prev => ({ ...prev, triggerMessage: null }))} className="ml-auto">
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
                {lastTriggeredAt ? (
                  <>Last triggered: {lastTriggeredAt.toLocaleTimeString()}. </>
                ) : null}
                Click &quot;Process Pending&quot; to send queued PDFs to Modal for processing.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={startBatchProcessing}
                disabled={isTriggering || queuedCount === 0 || (isProcessingInModal && !isTriggerStale)}
                title={
                  isProcessingInModal && !isTriggerStale
                    ? "Processing in Modal... please wait" 
                    : isProcessingInModal && isTriggerStale
                    ? "Processing seems stalled. You can re-trigger."
                    : queuedCount > 0 
                    ? `Process all ${queuedCount} pending PDFs` 
                    : "No pending PDFs to process"
                }
                className="min-w-[200px]"
              >
                {isTriggering ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    <span>Triggering Modal...</span>
                  </>
                ) : isProcessingInModal && !isTriggerStale ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    <span>Processing ({queuedCount} left)</span>
                  </>
                ) : isProcessingInModal && isTriggerStale ? (
                  <>
                    <RotateCw className="h-4 w-4 mr-2" />
                    <span>Re-trigger pending ({queuedCount})</span>
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-2" />
                    <span>Process Pending ({queuedCount})</span>
                  </>
                )}
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
                {jobs.map((job) => (
                  <div
                    key={job.id}
                    className={`flex items-center gap-4 p-4 rounded-lg border ${
                      job.status === "queued" 
                        ? (isProcessingInModal 
                          ? "bg-blue-50 dark:bg-blue-950/30 border-blue-300 dark:border-blue-700"
                          : "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800")
                        : job.status === "processing"
                        ? "bg-blue-50 dark:bg-blue-950/30 border-blue-300 dark:border-blue-700"
                        : job.status === "completed"
                        ? "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800"
                        : "bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800"
                    }`}
                  >
                    {getStatusIcon(job.status)}
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <p className="font-medium truncate">{job.filename}</p>
                        {getStatusBadge(job.status)}
                      </div>
                      
                      {job.status === "processing" && (
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-muted rounded-full h-2">
                            <div 
                              className="bg-blue-500 h-2 rounded-full transition-all"
                              style={{ width: `${job.progress}%` }}
                            />
                          </div>
                          <span className="text-xs text-muted-foreground w-10">
                            {job.progress}%
                          </span>
                        </div>
                      )}
                      
                      {job.error && (
                        <p className="text-xs text-red-500 mt-1">{job.error}</p>
                      )}
                      
                      <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                        {job.startedAt && (
                          <span>Duration: {formatDuration(job.startedAt, job.completedAt)}</span>
                        )}
                        {job.pages && <span>{job.pages} pages</span>}
                        {job.chunks && <span>{job.chunks} chunks indexed</span>}
                      </div>
                    </div>
                    
                    <div className="shrink-0 flex gap-1">
                      {job.status === "failed" && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => retryJob(job.id)}
                        >
                          <RotateCw className="h-3 w-3 mr-1" />
                          Retry
                        </Button>
                      )}
                      {job.status === "queued" && (
                        isProcessingInModal ? (
                          <Badge className="bg-blue-500 text-xs">
                            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                            Triggered – awaiting Modal/Qdrant
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs">
                            Awaiting trigger
                          </Badge>
                        )
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
