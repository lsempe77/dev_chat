"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Play,
  RefreshCw,
  ExternalLink,
  Clock,
  Target,
  TrendingUp,
  FileText,
  Loader2,
  Info,
} from "lucide-react";
import {
  getLatestMetrics,
  getEvaluationHistory,
  runEvaluation,
  getEvaluationRun,
  type LatestMetricsResponse,
  type EvaluationHistory,
  type EvaluationRun,
} from "@/lib/admin-api";

// =============================================================================
// Helper Components
// =============================================================================

function MetricCard({
  label,
  value,
  target,
  description,
}: {
  label: string;
  value: number | null;
  target: number;
  description?: string;
}) {
  const percentage = value !== null ? value * 100 : 0;
  const targetPercentage = target * 100;
  const meetsTarget = value !== null && value >= target;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">{label}</CardTitle>
          {value !== null && (
            meetsTarget ? (
              <CheckCircle2 className="h-4 w-4 text-green-500" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-amber-500" />
            )
          )}
        </div>
        {description && (
          <CardDescription className="text-xs">{description}</CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          <div className="flex items-baseline justify-between">
            <span className="text-2xl font-bold">
              {value !== null ? `${percentage.toFixed(1)}%` : "—"}
            </span>
            <span className="text-xs text-muted-foreground">
              Target: {targetPercentage}%
            </span>
          </div>
          <Progress
            value={percentage}
            className={`h-2 ${meetsTarget ? "[&>div]:bg-green-500" : "[&>div]:bg-amber-500"}`}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function RunHistoryRow({ run, onViewDetails }: { run: EvaluationRun; onViewDetails: (id: string) => void }) {
  const isComplete = !!run.completed_at;
  const runDate = run.completed_at || run.started_at;
  
  return (
    <TableRow>
      <TableCell>
        <div className="flex items-center gap-2">
          {isComplete ? (
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          ) : (
            <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
          )}
          <span className="font-medium">{run.evaluator}</span>
        </div>
      </TableCell>
      <TableCell>
        <Badge variant="outline">{run.run_type}</Badge>
      </TableCell>
      <TableCell>
        {isComplete ? (
          <span className="font-mono text-sm">
            {(run.metrics.faithfulness * 100).toFixed(1)}%
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        {isComplete ? (
          <span className="font-mono text-sm">
            {(run.metrics.citation_recall * 100).toFixed(1)}%
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        {isComplete ? (
          <span className="font-mono text-sm">
            {(run.metrics.citation_precision * 100).toFixed(1)}%
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell>
        <span className="text-sm text-muted-foreground">
          {run.num_successful}/{run.num_queries}
        </span>
      </TableCell>
      <TableCell>
        <span className="text-sm text-muted-foreground">
          {new Date(runDate).toLocaleDateString()}
        </span>
      </TableCell>
      <TableCell>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onViewDetails(run.id)}
          disabled={!isComplete}
        >
          Details
        </Button>
      </TableCell>
    </TableRow>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function QualityTab() {
  const [metrics, setMetrics] = useState<LatestMetricsResponse | null>(null);
  const [history, setHistory] = useState<EvaluationHistory | null>(null);
  const [selectedRun, setSelectedRun] = useState<(EvaluationRun & { details?: Record<string, unknown> }) | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [numQueries, setNumQueries] = useState("5");

  // Load data on mount
  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [metricsData, historyData] = await Promise.all([
        getLatestMetrics(),
        getEvaluationHistory(10),
      ]);
      setMetrics(metricsData);
      setHistory(historyData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }

  async function handleRunEvaluation() {
    setRunning(true);
    setError(null);
    try {
      const result = await runEvaluation({
        evaluator: "minicheck",
        num_queries: parseInt(numQueries),
      });
      
      // Show success message
      setError(null);
      
      // Poll for completion
      pollForCompletion(result.run_id);
      
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start evaluation");
      setRunning(false);
    }
  }

  async function pollForCompletion(runId: string) {
    const maxAttempts = 60; // 5 minutes max
    let attempts = 0;
    
    const poll = async () => {
      try {
        const run = await getEvaluationRun(runId);
        
        if (run.completed_at) {
          // Completed - reload data
          setRunning(false);
          loadData();
          return;
        }
        
        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 5000); // Poll every 5 seconds
        } else {
          setRunning(false);
          setError("Evaluation timed out. Check history for results.");
          loadData();
        }
      } catch {
        setRunning(false);
        loadData();
      }
    };
    
    setTimeout(poll, 3000); // Start polling after 3 seconds
  }

  async function handleViewDetails(runId: string) {
    try {
      const run = await getEvaluationRun(runId);
      setSelectedRun(run);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load run details");
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Quality Monitoring</h2>
          <p className="text-muted-foreground">
            Track citation quality and answer faithfulness over time
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadData}
            disabled={loading || running}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            asChild
          >
            <a
              href="https://cloud.langfuse.com/project/cmjafx1vd00qkad06prpgl80o"
              target="_blank"
              rel="noopener noreferrer"
            >
              <ExternalLink className="h-4 w-4 mr-2" />
              Langfuse Traces
            </a>
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="destructive">
          <XCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Current Metrics */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Target className="h-5 w-5" />
            Current Metrics
          </h3>
          {metrics?.last_run && (
            <span className="text-sm text-muted-foreground flex items-center gap-1">
              <Clock className="h-4 w-4" />
              Last run: {new Date(metrics.last_run).toLocaleString()}
            </span>
          )}
        </div>

        {metrics?.status === "no_runs" ? (
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>
              No evaluation runs yet. Run the test suite to see quality metrics.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="grid gap-4 md:grid-cols-4">
            <MetricCard
              label="Faithfulness"
              value={metrics?.metrics?.faithfulness ?? null}
              target={metrics?.targets?.faithfulness ?? 0.7}
              description="Claims grounded in retrieved context"
            />
            <MetricCard
              label="Citation Recall"
              value={metrics?.metrics?.citation_recall ?? null}
              target={metrics?.targets?.citation_recall ?? 0.7}
              description="Sentences with valid citations"
            />
            <MetricCard
              label="Citation Precision"
              value={metrics?.metrics?.citation_precision ?? null}
              target={metrics?.targets?.citation_precision ?? 0.7}
              description="Citations that support their claims"
            />
            <MetricCard
              label="Overall Score"
              value={metrics?.metrics?.overall_score ?? null}
              target={metrics?.targets?.overall_score ?? 0.8}
              description="Combined quality score"
            />
          </div>
        )}
      </div>

      <Separator />

      {/* Run Evaluation */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Play className="h-5 w-5" />
            Run Evaluation
          </CardTitle>
          <CardDescription>
            Execute the test suite to measure current quality metrics
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Queries:</span>
              <Select value={numQueries} onValueChange={setNumQueries}>
                <SelectTrigger className="w-20">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="3">3</SelectItem>
                  <SelectItem value="5">5</SelectItem>
                  <SelectItem value="8">8</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={handleRunEvaluation}
              disabled={running}
            >
              {running ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-2" />
                  Run Test Suite
                </>
              )}
            </Button>
            {running && (
              <span className="text-sm text-muted-foreground">
                This may take 2-5 minutes...
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      <Separator />

      {/* Run History */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <TrendingUp className="h-5 w-5" />
          Evaluation History
        </h3>

        {history && history.runs.length > 0 ? (
          <Card>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Evaluator</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Faithfulness</TableHead>
                  <TableHead>Recall</TableHead>
                  <TableHead>Precision</TableHead>
                  <TableHead>Queries</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {history.runs.map((run) => (
                  <RunHistoryRow
                    key={run.id}
                    run={run}
                    onViewDetails={handleViewDetails}
                  />
                ))}
              </TableBody>
            </Table>
          </Card>
        ) : (
          <Alert>
            <FileText className="h-4 w-4" />
            <AlertDescription>
              No evaluation runs recorded yet. Run the test suite to start tracking quality.
            </AlertDescription>
          </Alert>
        )}
      </div>

      {/* Run Details Modal */}
      {selectedRun && (
        <Card className="mt-4">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Run Details: {selectedRun.id.slice(0, 8)}...</CardTitle>
              <Button variant="ghost" size="sm" onClick={() => setSelectedRun(null)}>
                Close
              </Button>
            </div>
            <CardDescription>
              {selectedRun.evaluator} • {selectedRun.run_type} • {selectedRun.completed_at ? new Date(selectedRun.completed_at).toLocaleString() : "In progress"}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="grid grid-cols-4 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Faithfulness:</span>{" "}
                  <span className="font-mono">{(selectedRun.metrics.faithfulness * 100).toFixed(1)}%</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Recall:</span>{" "}
                  <span className="font-mono">{(selectedRun.metrics.citation_recall * 100).toFixed(1)}%</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Precision:</span>{" "}
                  <span className="font-mono">{(selectedRun.metrics.citation_precision * 100).toFixed(1)}%</span>
                </div>
                <div>
                  <span className="text-muted-foreground">Latency:</span>{" "}
                  <span className="font-mono">{selectedRun.avg_latency_ms?.toFixed(0) ?? "—"}ms</span>
                </div>
              </div>

              {selectedRun.details && (
                <div className="mt-4">
                  <h4 className="font-medium mb-2">Per-Query Results</h4>
                  <div className="max-h-64 overflow-y-auto">
                    <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto">
                      {JSON.stringify(selectedRun.details, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Documentation Link */}
      <Alert>
        <FileText className="h-4 w-4" />
        <AlertDescription>
          For details on the evaluation methodology, see{" "}
          <a
            href="https://github.com/lsempe77/dev_chat/blob/main/docs/EVALUATION_FRAMEWORK.md"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-primary"
          >
            EVALUATION_FRAMEWORK.md
          </a>
        </AlertDescription>
      </Alert>
    </div>
  );
}
