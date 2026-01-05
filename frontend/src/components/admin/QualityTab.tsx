"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  ExternalLink,
  Target,
  FlaskConical,
  FileText,
  Loader2,
  Info,
  Microscope,
  GitBranch,
  Database,
  Sparkles,
} from "lucide-react";
import {
  getLatestMetrics,
  type LatestMetricsResponse,
} from "@/lib/admin-api";

// =============================================================================
// Constants
// =============================================================================

const LANGFUSE_PROJECT_URL = "https://cloud.langfuse.com/project/cmjafx1vd00qkad06prpgl80o";

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

function LangfuseFeatureCard({
  icon: Icon,
  title,
  description,
  href,
  buttonText,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
  href: string;
  buttonText: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Icon className="h-5 w-5 text-primary" />
          {title}
        </CardTitle>
        <CardDescription className="text-sm">
          {description}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="outline" size="sm" asChild className="w-full">
          <a href={href} target="_blank" rel="noopener noreferrer">
            {buttonText}
            <ExternalLink className="h-4 w-4 ml-2" />
          </a>
        </Button>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function QualityTab() {
  const [metrics, setMetrics] = useState<LatestMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load data on mount
  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const metricsData = await getLatestMetrics();
      setMetrics(metricsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
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
            Track citation quality and experiment with prompts using Langfuse
          </p>
        </div>
        <Button asChild>
          <a
            href={LANGFUSE_PROJECT_URL}
            target="_blank"
            rel="noopener noreferrer"
          >
            <ExternalLink className="h-4 w-4 mr-2" />
            Open Langfuse
          </a>
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <XCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Current Metrics (from last local evaluation) */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Target className="h-5 w-5" />
          <h3 className="text-lg font-semibold">Baseline Metrics</h3>
          <Badge variant="outline">From test suite</Badge>
        </div>

        {metrics?.status === "no_runs" || !metrics?.metrics ? (
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>
              Baseline metrics from evaluation runs. Current values are from the MiniCheck test suite 
              documented in <a href="https://github.com/lsempe77/dev_chat/blob/main/docs/EVALUATION_FRAMEWORK.md" 
              target="_blank" rel="noopener noreferrer" className="underline">EVALUATION_FRAMEWORK.md</a>.
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-4 md:grid-cols-4">
          <MetricCard
            label="Faithfulness"
            value={metrics?.metrics?.faithfulness ?? 0.70}
            target={metrics?.targets?.faithfulness ?? 0.7}
            description="Claims grounded in context"
          />
          <MetricCard
            label="Citation Recall"
            value={metrics?.metrics?.citation_recall ?? 1.0}
            target={metrics?.targets?.citation_recall ?? 0.7}
            description="Sentences with valid citations"
          />
          <MetricCard
            label="Citation Precision"
            value={metrics?.metrics?.citation_precision ?? 1.0}
            target={metrics?.targets?.citation_precision ?? 0.7}
            description="Citations that support claims"
          />
          <MetricCard
            label="Overall Score"
            value={metrics?.metrics?.overall_score ?? 0.90}
            target={metrics?.targets?.overall_score ?? 0.8}
            description="Combined quality score"
          />
        </div>
      </div>

      <Separator />

      {/* Langfuse Features */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Sparkles className="h-5 w-5" />
          <h3 className="text-lg font-semibold">Experiment & Iterate</h3>
        </div>

        <Alert>
          <FlaskConical className="h-4 w-4" />
          <AlertDescription>
            Use <strong>Langfuse</strong> for prompt engineering, A/B testing, and detailed trace analysis. 
            All DevChat queries are automatically traced to Langfuse with full context.
          </AlertDescription>
        </Alert>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <LangfuseFeatureCard
            icon={Microscope}
            title="Traces"
            description="View detailed traces of every query: retrieval, reranking, and synthesis steps"
            href={`${LANGFUSE_PROJECT_URL}/traces`}
            buttonText="View Traces"
          />
          <LangfuseFeatureCard
            icon={GitBranch}
            title="Prompts"
            description="Version and A/B test different system prompts to improve quality"
            href={`${LANGFUSE_PROJECT_URL}/prompts`}
            buttonText="Manage Prompts"
          />
          <LangfuseFeatureCard
            icon={Database}
            title="Datasets"
            description="Create test datasets with golden questions to run evaluations"
            href={`${LANGFUSE_PROJECT_URL}/datasets`}
            buttonText="Manage Datasets"
          />
          <LangfuseFeatureCard
            icon={FlaskConical}
            title="Experiments"
            description="Run evaluations with different configs and compare results"
            href={`${LANGFUSE_PROJECT_URL}/experiments`}
            buttonText="Run Experiments"
          />
        </div>
      </div>

      <Separator />

      {/* Quick Reference */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <FileText className="h-5 w-5" />
          Quick Reference
        </h3>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Current Configuration</CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Synthesis Model</span>
                <code className="text-xs bg-muted px-2 py-0.5 rounded">gpt-4o</code>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Embedding Model</span>
                <code className="text-xs bg-muted px-2 py-0.5 rounded">cohere-embed-v4</code>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Reranker</span>
                <code className="text-xs bg-muted px-2 py-0.5 rounded">cohere-rerank-v3.5</code>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Synthesis Method</span>
                <code className="text-xs bg-muted px-2 py-0.5 rounded">claim-ledger</code>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Evaluation Methods</CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              <div className="flex justify-between">
                <span className="text-muted-foreground">NLI Model</span>
                <code className="text-xs bg-muted px-2 py-0.5 rounded">MiniCheck-Flan-T5</code>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Lane A</span>
                <span className="text-xs">Faithfulness (claim→context)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Lane B</span>
                <span className="text-xs">Citation alignment (ALCE)</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Test Cases</span>
                <code className="text-xs bg-muted px-2 py-0.5 rounded">8 golden queries</code>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

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
