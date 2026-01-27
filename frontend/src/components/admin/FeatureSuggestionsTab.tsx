"use client";

import { useState, useEffect } from "react";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  FeatureSuggestion,
  FeatureSuggestionsResponse,
  FeatureCategory,
  ImpactLevel,
  EffortLevel,
} from "@/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Category colors and icons
const categoryConfig: Record<FeatureCategory, { color: string; icon: string }> = {
  retrieval: { color: "bg-blue-100 text-blue-800", icon: "🔍" },
  analysis: { color: "bg-purple-100 text-purple-800", icon: "📊" },
  visualization: { color: "bg-green-100 text-green-800", icon: "📈" },
  export: { color: "bg-yellow-100 text-yellow-800", icon: "📤" },
  collaboration: { color: "bg-pink-100 text-pink-800", icon: "👥" },
  automation: { color: "bg-cyan-100 text-cyan-800", icon: "⚡" },
  quality: { color: "bg-orange-100 text-orange-800", icon: "✅" },
  integration: { color: "bg-indigo-100 text-indigo-800", icon: "🔗" },
};

// Impact/Effort badge colors
const impactColors: Record<ImpactLevel, string> = {
  high: "bg-green-500 text-white",
  medium: "bg-yellow-500 text-white",
  low: "bg-gray-400 text-white",
};

const effortColors: Record<EffortLevel, string> = {
  low: "bg-green-500 text-white",
  medium: "bg-yellow-500 text-white",
  high: "bg-red-500 text-white",
};

interface FeatureSuggestionsTabProps {
  projectName?: string;
  documentCount?: number;
  queryCount?: number;
  commonTopics?: string[];
}

export function FeatureSuggestionsTab({
  projectName = "DevChat RAG Project",
  documentCount = 0,
  queryCount = 0,
  commonTopics = [],
}: FeatureSuggestionsTabProps) {
  const [suggestions, setSuggestions] = useState<FeatureSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generatedAt, setGeneratedAt] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<FeatureCategory | "all">("all");

  const fetchSuggestions = async (useDefault = false) => {
    setLoading(true);
    setError(null);

    try {
      let response: Response;

      if (useDefault) {
        response = await fetch(`${API_BASE_URL}/api/feature-suggestions/default`);
      } else {
        response = await fetch(`${API_BASE_URL}/api/feature-suggestions`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            project_name: projectName,
            document_count: documentCount,
            query_count: queryCount,
            common_topics: commonTopics,
          }),
        });
      }

      if (!response.ok) {
        throw new Error(`Failed to fetch suggestions: ${response.statusText}`);
      }

      const data: FeatureSuggestionsResponse = await response.json();
      setSuggestions(data.suggestions);
      setGeneratedAt(data.generated_at);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch suggestions");
      // Try default suggestions as fallback
      if (!useDefault) {
        fetchSuggestions(true);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Start with default suggestions for fast initial load
    fetchSuggestions(true);
  }, []);

  const categories = ["all", ...Object.keys(categoryConfig)] as const;

  const filteredSuggestions = selectedCategory === "all"
    ? suggestions
    : suggestions.filter(s => s.category === selectedCategory);

  if (loading) {
    return (
      <div className="space-y-4 p-4">
        <div className="flex items-center justify-between mb-6">
          <div>
            <Skeleton className="h-8 w-64 mb-2" />
            <Skeleton className="h-4 w-96" />
          </div>
          <Skeleton className="h-10 w-40" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[...Array(6)].map((_, i) => (
            <Card key={i}>
              <CardHeader>
                <Skeleton className="h-6 w-48 mb-2" />
                <Skeleton className="h-4 w-full" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-4 w-3/4" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-4">
      {/* Header */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Feature Suggestions</h2>
          <p className="text-muted-foreground">
            AI-generated feature ideas based on your project context
          </p>
          {generatedAt && (
            <p className="text-xs text-muted-foreground mt-1">
              Generated: {new Date(generatedAt).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => fetchSuggestions(true)}
            disabled={loading}
          >
            Load Defaults
          </Button>
          <Button
            onClick={() => fetchSuggestions(false)}
            disabled={loading}
          >
            {loading ? "Generating..." : "Generate New Ideas"}
          </Button>
        </div>
      </div>

      {/* Error display */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          {error}
        </div>
      )}

      {/* Category filter */}
      <div className="flex flex-wrap gap-2">
        {categories.map((cat) => (
          <Button
            key={cat}
            variant={selectedCategory === cat ? "default" : "outline"}
            size="sm"
            onClick={() => setSelectedCategory(cat as FeatureCategory | "all")}
          >
            {cat === "all" ? "All" : (
              <>
                {categoryConfig[cat as FeatureCategory].icon}{" "}
                {cat.charAt(0).toUpperCase() + cat.slice(1)}
              </>
            )}
          </Button>
        ))}
      </div>

      {/* Suggestions grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredSuggestions.map((suggestion) => (
          <Card key={suggestion.id} className="hover:shadow-lg transition-shadow">
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xl">
                    {categoryConfig[suggestion.category].icon}
                  </span>
                  <CardTitle className="text-lg">{suggestion.title}</CardTitle>
                </div>
                <Badge className={categoryConfig[suggestion.category].color}>
                  {suggestion.category}
                </Badge>
              </div>
              <CardDescription className="mt-2">
                {suggestion.description}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-4">
                {suggestion.rationale}
              </p>
              <div className="flex gap-2">
                <Badge className={impactColors[suggestion.impact]}>
                  Impact: {suggestion.impact}
                </Badge>
                <Badge className={effortColors[suggestion.effort]}>
                  Effort: {suggestion.effort}
                </Badge>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Empty state */}
      {filteredSuggestions.length === 0 && !loading && (
        <div className="text-center py-12 text-muted-foreground">
          <p>No suggestions found for the selected category.</p>
          <Button
            variant="link"
            onClick={() => setSelectedCategory("all")}
          >
            Show all suggestions
          </Button>
        </div>
      )}

      {/* Summary stats */}
      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-lg">Suggestion Summary</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {suggestions.filter(s => s.impact === "high").length}
              </div>
              <div className="text-sm text-muted-foreground">High Impact</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-green-600">
                {suggestions.filter(s => s.effort === "low").length}
              </div>
              <div className="text-sm text-muted-foreground">Low Effort</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-purple-600">
                {new Set(suggestions.map(s => s.category)).size}
              </div>
              <div className="text-sm text-muted-foreground">Categories</div>
            </div>
            <div className="text-center">
              <div className="text-2xl font-bold text-blue-600">
                {suggestions.length}
              </div>
              <div className="text-sm text-muted-foreground">Total Ideas</div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
