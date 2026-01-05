"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { 
  Activity, 
  DollarSign, 
  FileText, 
  Users, 
  TrendingUp,
  Zap,
  Clock,
  AlertCircle,
  RefreshCw,
  Database,
  FolderKanban
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { 
  getUsageSummary, 
  getCostProjection,
  getAdminOverview,
} from "@/lib/admin-api/index";
import type { 
  UsageSummaryResponse,
  CostProjection,
  ModelBreakdown,
  AdminOverviewStats,
} from "@/lib/admin-api/types";

// =============================================================================
// Stats Card Component
// =============================================================================

interface StatsCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: React.ReactNode;
  trend?: {
    value: number;
    label: string;
  };
  loading?: boolean;
}

function StatsCard({ title, value, description, icon, trend, loading }: StatsCardProps) {
  if (loading) {
    return (
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-4 w-4" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-8 w-20 mb-1" />
          <Skeleton className="h-3 w-32" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <div className="h-4 w-4 text-muted-foreground">
          {icon}
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && (
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        )}
        {trend && (
          <div className="flex items-center gap-1 mt-1">
            <TrendingUp className={`h-3 w-3 ${trend.value >= 0 ? "text-green-500" : "text-red-500"}`} />
            <span className={`text-xs ${trend.value >= 0 ? "text-green-500" : "text-red-500"}`}>
              {trend.value >= 0 ? "+" : ""}{trend.value.toFixed(1)}%
            </span>
            <span className="text-xs text-muted-foreground">{trend.label}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Model Usage Card
// =============================================================================

interface ModelUsageProps {
  breakdown: ModelBreakdown[];
  loading?: boolean;
}

function ModelUsageCard({ breakdown, loading }: ModelUsageProps) {
  if (loading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-32" />
        </CardHeader>
        <CardContent className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  const totalCost = breakdown.reduce((sum: number, m: ModelBreakdown) => sum + m.cost_usd, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Usage by Model</CardTitle>
        <CardDescription>Cost breakdown by model</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {breakdown.length === 0 ? (
          <p className="text-sm text-muted-foreground">No usage data yet</p>
        ) : (
          breakdown.map((model: ModelBreakdown) => {
            const percentage = totalCost > 0 ? (model.cost_usd / totalCost) * 100 : 0;
            return (
              <div key={model.model} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{model.model}</span>
                  <span className="text-muted-foreground">
                    ${model.cost_usd.toFixed(4)}
                  </span>
                </div>
                <div className="h-2 bg-secondary rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-primary transition-all"
                    style={{ width: `${percentage}%` }}
                  />
                </div>
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{model.queries.toLocaleString()} queries</span>
                  <span>{(model.input_tokens + model.output_tokens).toLocaleString()} tokens</span>
                </div>
              </div>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Cost Projection Card
// =============================================================================

interface CostProjectionCardProps {
  projection: CostProjection | null;
  loading?: boolean;
}

function CostProjectionCard({ projection, loading }: CostProjectionCardProps) {
  if (loading || !projection) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-32" />
        </CardHeader>
        <CardContent className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-6 w-full" />
          ))}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Cost Projection</CardTitle>
        <CardDescription>
          Based on {projection.days_in_sample} days of data
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Daily Average</span>
          <span className="font-mono font-medium">
            ${projection.current_daily_avg.toFixed(2)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Projected Monthly</span>
          <span className="font-mono font-medium text-lg">
            ${projection.projected_monthly.toFixed(2)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Projected Annual</span>
          <span className="font-mono font-medium">
            ${projection.projected_annual.toFixed(2)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Overview Tab
// =============================================================================

export function OverviewTab() {
  const [usageData, setUsageData] = useState<UsageSummaryResponse | null>(null);
  const [costProjection, setCostProjection] = useState<CostProjection | null>(null);
  const [overview, setOverview] = useState<AdminOverviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const [usage, costs, overviewData] = await Promise.all([
        getUsageSummary(30).catch(() => null),
        getCostProjection(30).catch(() => null),
        getAdminOverview().catch(() => null),
      ]);

      setUsageData(usage);
      setCostProjection(costs);
      setOverview(overviewData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Format numbers for display
  const formatNumber = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n.toLocaleString();
  };

  const formatCurrency = (n: number) => {
    if (n >= 100) return `$${n.toFixed(0)}`;
    if (n >= 1) return `$${n.toFixed(2)}`;
    return `$${n.toFixed(4)}`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Overview</h2>
          <p className="text-muted-foreground">
            Usage metrics and cost tracking for the last 30 days
          </p>
        </div>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => fetchData(true)}
          disabled={refreshing}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Error Alert */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Main Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Total Queries"
          value={usageData ? formatNumber(usageData.total_queries) : "0"}
          description="Last 30 days"
          icon={<Activity className="h-4 w-4" />}
          loading={loading}
        />
        <StatsCard
          title="Total Cost"
          value={usageData ? formatCurrency(usageData.total_cost_usd) : "$0"}
          description="API costs this period"
          icon={<DollarSign className="h-4 w-4" />}
          loading={loading}
        />
        <StatsCard
          title="Tokens Used"
          value={usageData ? formatNumber(usageData.total_input_tokens + usageData.total_output_tokens) : "0"}
          description={usageData ? `${formatNumber(usageData.total_input_tokens)} in / ${formatNumber(usageData.total_output_tokens)} out` : "Input / Output"}
          icon={<Zap className="h-4 w-4" />}
          loading={loading}
        />
        <StatsCard
          title="Avg Latency"
          value={usageData ? `${usageData.avg_latency_ms.toFixed(0)}ms` : "—"}
          description={usageData && usageData.cache_hit_rate > 0 ? `${(usageData.cache_hit_rate * 100).toFixed(1)}% cache hits` : "Response time"}
          icon={<Clock className="h-4 w-4" />}
          loading={loading}
        />
      </div>

      {/* Secondary Stats - Platform Overview */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Users"
          value={overview ? overview.total_users.toLocaleString() : "0"}
          description="Registered accounts"
          icon={<Users className="h-4 w-4" />}
          loading={loading}
        />
        <StatsCard
          title="RAG Projects"
          value={overview ? overview.total_rag_projects.toLocaleString() : "0"}
          description="Active knowledge bases"
          icon={<FolderKanban className="h-4 w-4" />}
          loading={loading}
        />
        <StatsCard
          title="Documents"
          value={overview ? overview.total_documents.toLocaleString() : "0"}
          description={overview ? `${formatNumber(overview.total_chunks)} chunks` : "Across all projects"}
          icon={<FileText className="h-4 w-4" />}
          loading={loading}
        />
        <StatsCard
          title="Chunks"
          value={overview ? formatNumber(overview.total_chunks) : "0"}
          description="Total indexed vectors"
          icon={<Database className="h-4 w-4" />}
          loading={loading}
        />
      </div>

      {/* Details Grid */}
      <div className="grid gap-4 md:grid-cols-2">
        <ModelUsageCard 
          breakdown={usageData?.model_breakdown || []} 
          loading={loading}
        />
        <CostProjectionCard 
          projection={costProjection} 
          loading={loading}
        />
      </div>
    </div>
  );
}
