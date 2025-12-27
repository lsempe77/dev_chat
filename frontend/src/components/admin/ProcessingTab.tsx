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
  FileText
} from "lucide-react";
import { 
  getProcessingJobs, 
  triggerProcessing,
  type ProcessingJob as APIProcessingJob 
} from "@/lib/admin-api";

interface ProcessingJob {
  id: string;
  filename: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress: number;
  startedAt?: string;
  completedAt?: string;
  error?: string;
  pages?: number;
  chunks?: number;
}

export function ProcessingTab() {
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isTriggering, setIsTriggering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [triggerMessage, setTriggerMessage] = useState<string | null>(null);
  const [queuedCount, setQueuedCount] = useState(0);
  const [processingCount, setProcessingCount] = useState(0);
  const [completedCount, setCompletedCount] = useState(0);
  const [failedCount, setFailedCount] = useState(0);

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
      
      setJobs(mappedJobs);
      setQueuedCount(response.queued_count);
      setProcessingCount(response.processing_count);
      setCompletedCount(response.completed_count);
      setFailedCount(response.failed_count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch jobs");
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    refreshJobs();
  }, [refreshJobs]);

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

  const cancelJob = async (jobId: string) => {
    // TODO: Implement cancel via specific endpoint when available
    console.log("Cancelling job:", jobId);
  };

  const startBatchProcessing = async () => {
    setIsTriggering(true);
    setTriggerMessage(null);
    setError(null);
    
    try {
      const response = await triggerProcessing({ max_documents: 10 });
      setTriggerMessage(response.message);
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
                Real-time status of PDF processing jobs. "Process All Pending" will send all queued PDFs to Modal for batch processing.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={startBatchProcessing}
                disabled={isTriggering || queuedCount === 0}
                title={queuedCount > 0 ? `Process all ${queuedCount} pending PDFs` : "No pending PDFs to process"}
              >
                {isTriggering ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                    Triggering...
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-1" />
                    Process All Pending {queuedCount > 0 && `(${queuedCount})`}
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
                    className="flex items-center gap-4 p-4 rounded-lg border bg-card"
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
                          <RefreshCw className="h-3 w-3 mr-1" />
                          Retry
                        </Button>
                      )}
                      {(job.status === "queued" || job.status === "processing") && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => cancelJob(job.id)}
                        >
                          Cancel
                        </Button>
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
