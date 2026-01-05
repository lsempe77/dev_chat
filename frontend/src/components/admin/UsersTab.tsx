"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { 
  Users, 
  Database, 
  FileText,
  DollarSign,
  Calendar,
  RefreshCw,
  AlertCircle,
  ChevronRight,
} from "lucide-react";

// =============================================================================
// Types
// =============================================================================

interface RagProject {
  id: string;
  name: string;
  description?: string;
  document_count: number;
  chunk_count: number;
  created_at: string;
  last_query_at?: string;
}

interface UserWithRags {
  id: string;
  email: string;
  created_at: string;
  last_sign_in_at?: string;
  rag_projects: RagProject[];
  total_queries: number;
  total_cost_usd: number;
}

// =============================================================================
// API Functions (to be implemented in backend)
// =============================================================================

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getUsers(): Promise<UserWithRags[]> {
  // TODO: Implement GET /admin/users endpoint
  // For now, return mock data to show the UI
  const response = await fetch(`${API_BASE_URL}/admin/users`);
  if (!response.ok) {
    throw new Error("Failed to fetch users");
  }
  return response.json();
}

// =============================================================================
// User Card Component
// =============================================================================

interface UserCardProps {
  user: UserWithRags;
}

function UserCard({ user }: UserCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
              <Users className="h-5 w-5 text-primary" />
            </div>
            <div>
              <CardTitle className="text-base">{user.email}</CardTitle>
              <CardDescription className="text-xs">
                Joined {new Date(user.created_at).toLocaleDateString()}
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <div className="text-sm font-medium">{user.rag_projects.length} RAGs</div>
              <div className="text-xs text-muted-foreground">
                {user.total_queries} queries
              </div>
            </div>
            <Badge variant={user.total_cost_usd > 0 ? "default" : "secondary"}>
              ${user.total_cost_usd.toFixed(2)}
            </Badge>
            <Button 
              variant="ghost" 
              size="sm"
              onClick={() => setExpanded(!expanded)}
            >
              <ChevronRight className={`h-4 w-4 transition-transform ${expanded ? "rotate-90" : ""}`} />
            </Button>
          </div>
        </div>
      </CardHeader>
      
      {expanded && user.rag_projects.length > 0 && (
        <CardContent className="pt-0">
          <div className="border-t pt-4 space-y-3">
            <div className="text-sm font-medium text-muted-foreground">RAG Projects</div>
            {user.rag_projects.map((rag) => (
              <div key={rag.id} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-3">
                  <Database className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="font-medium text-sm">{rag.name}</div>
                    {rag.description && (
                      <div className="text-xs text-muted-foreground line-clamp-1">
                        {rag.description}
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-4 text-sm text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <FileText className="h-3 w-3" />
                    {rag.document_count} docs
                  </span>
                  <span>{rag.chunk_count.toLocaleString()} chunks</span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// =============================================================================
// Main Users Tab
// =============================================================================

export function UsersTab() {
  const [users, setUsers] = useState<UserWithRags[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchUsers = async (showRefresh = false) => {
    if (showRefresh) setRefreshing(true);
    else setLoading(true);
    setError(null);

    try {
      const data = await getUsers();
      setUsers(data);
    } catch (err) {
      // If the endpoint doesn't exist yet, show placeholder
      setError(
        err instanceof Error 
          ? err.message 
          : "Users endpoint not yet implemented"
      );
      // Show placeholder data for UI development
      setUsers([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  // Calculate totals
  const totalUsers = users.length;
  const totalRags = users.reduce((sum, u) => sum + u.rag_projects.length, 0);
  const totalQueries = users.reduce((sum, u) => sum + u.total_queries, 0);
  const totalCost = users.reduce((sum, u) => sum + u.total_cost_usd, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Users & RAG Projects</h2>
          <p className="text-muted-foreground">
            View all users and their knowledge bases
          </p>
        </div>
        <Button 
          variant="outline" 
          size="sm" 
          onClick={() => fetchUsers(true)}
          disabled={refreshing}
        >
          <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Users
            </CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{totalUsers}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total RAGs
            </CardTitle>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{totalRags}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Queries
            </CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">{totalQueries.toLocaleString()}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Cost
            </CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-8 w-16" />
            ) : (
              <div className="text-2xl font-bold">${totalCost.toFixed(2)}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Error Alert */}
      {error && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            <span className="font-medium">Note:</span> {error}
            <br />
            <span className="text-xs text-muted-foreground">
              The /admin/users endpoint needs to be implemented to show real data.
            </span>
          </AlertDescription>
        </Alert>
      )}

      {/* User List */}
      <div className="space-y-4">
        {loading ? (
          <>
            {[1, 2, 3].map((i) => (
              <Card key={i}>
                <CardHeader>
                  <Skeleton className="h-10 w-full" />
                </CardHeader>
              </Card>
            ))}
          </>
        ) : users.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-muted-foreground">
              <Users className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="font-medium">No users found</p>
              <p className="text-sm">
                Users will appear here once they sign up and create RAG projects.
              </p>
            </CardContent>
          </Card>
        ) : (
          users.map((user) => (
            <UserCard key={user.id} user={user} />
          ))
        )}
      </div>
    </div>
  );
}
