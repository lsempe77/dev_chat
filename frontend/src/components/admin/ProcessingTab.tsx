"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { 
  Activity, 
  Play, 
  Pause, 
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Clock,
  Loader2,
  FileText
} from "lucide-react";

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

// Mock data - replace with API calls
const mockJobs: ProcessingJob[] = [
  {
    id: "1",
    filename: "systematic_review_education_kenya.pdf",
    status: "processing",
    progress: 65,
    startedAt: new Date(Date.now() - 180000).toISOString(),
    pages: 45,
  },
  {
    id: "2",
    filename: "rct_cash_transfers_2023.pdf",
    status: "queued",
    progress: 0,
  },
  {
    id: "3",
    filename: "impact_evaluation_health_india.pdf",
    status: "completed",
    progress: 100,
    startedAt: new Date(Date.now() - 600000).toISOString(),
    completedAt: new Date(Date.now() - 300000).toISOString(),
    pages: 32,
    chunks: 156,
  },
  {
    id: "4",
    filename: "meta_analysis_agriculture.pdf",
    status: "failed",
    progress: 45,
    startedAt: new Date(Date.now() - 900000).toISOString(),
    error: "PDF extraction failed: corrupted file",
  },
];

export function ProcessingTab() {
  const [jobs, setJobs] = useState<ProcessingJob[]>(mockJobs);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Auto-refresh every 5 seconds
  useEffect(() => {
    if (!autoRefresh) return;
    
    const interval = setInterval(() => {
      refreshJobs();
    }, 5000);
    
    return () => clearInterval(interval);
  }, [autoRefresh]);

  const refreshJobs = async () => {
    setIsRefreshing(true);
    
    // TODO: Replace with actual API call
    // const response = await fetch("/api/admin/jobs");
    // const data = await response.json();
    // setJobs(data.jobs);
    
    // Simulate API delay
    await new Promise(resolve => setTimeout(resolve, 500));
    setIsRefreshing(false);
  };

  const retryJob = async (jobId: string) => {
    // TODO: Implement retry API call
    console.log("Retrying job:", jobId);
  };

  const cancelJob = async (jobId: string) => {
    // TODO: Implement cancel API call
    console.log("Cancelling job:", jobId);
  };

  const startBatchProcessing = async () => {
    // TODO: Trigger Modal orchestrator
    console.log("Starting batch processing...");
  };

  const queuedCount = jobs.filter(j => j.status === "queued").length;
  const processingCount = jobs.filter(j => j.status === "processing").length;
  const completedCount = jobs.filter(j => j.status === "completed").length;
  const failedCount = jobs.filter(j => j.status === "failed").length;

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
              <Loader2 className="h-8 w-8 text-blue-500 animate-spin" />
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
                Real-time status of PDF processing jobs
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAutoRefresh(!autoRefresh)}
              >
                {autoRefresh ? (
                  <>
                    <Pause className="h-4 w-4 mr-1" />
                    Pause
                  </>
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-1" />
                    Resume
                  </>
                )}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={refreshJobs}
                disabled={isRefreshing}
              >
                <RefreshCw className={`h-4 w-4 mr-1 ${isRefreshing ? "animate-spin" : ""}`} />
                Refresh
              </Button>
              <Button
                size="sm"
                onClick={startBatchProcessing}
                disabled={queuedCount === 0}
              >
                <Play className="h-4 w-4 mr-1" />
                Start Processing
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {jobs.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Activity className="h-10 w-10 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No processing jobs</p>
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
