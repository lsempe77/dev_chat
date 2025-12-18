"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Study } from "@/types";
import { FileText, GitCompare, X, ExternalLink } from "lucide-react";

interface StudyCardProps {
  study: Study;
  citationNumber?: number;
  isHighlighted?: boolean;
  isSelected?: boolean;
  onSelect?: (study: Study) => void;
  onExclude?: (study: Study) => void;
  onOpenPdf?: (study: Study) => void;
  onClick?: () => void;
}

const confidenceColors = {
  high: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  low: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

export function StudyCard({
  study,
  citationNumber,
  isHighlighted = false,
  isSelected = false,
  onSelect,
  onExclude,
  onOpenPdf,
  onClick,
}: StudyCardProps) {
  return (
    <Card
      id={`study-${study.id}`}
      className={`transition-all cursor-pointer ${
        isHighlighted
          ? "ring-2 ring-blue-500 bg-blue-50 dark:bg-blue-950"
          : ""
      } ${isSelected ? "ring-2 ring-purple-500" : ""}`}
      onClick={onClick}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            {citationNumber && (
              <Badge variant="outline" className="font-mono">
                [{citationNumber}]
              </Badge>
            )}
            <CardTitle className="text-sm font-medium leading-tight">
              {study.authors} ({study.year})
            </CardTitle>
          </div>
          <Badge className={confidenceColors[study.confidence]}>
            {study.confidence}
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground line-clamp-2">
          {study.title}
        </p>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex flex-wrap gap-1 mb-2">
          <Badge variant="secondary" className="text-xs">
            {study.country}
          </Badge>
          <Badge variant="secondary" className="text-xs">
            {study.studyType}
          </Badge>
          {study.sector && (
            <Badge variant="secondary" className="text-xs">
              {study.sector}
            </Badge>
          )}
        </div>

        {study.snippet && (
          <blockquote className="border-l-2 border-muted pl-3 text-sm text-muted-foreground italic mb-3 line-clamp-3">
            &quot;{study.snippet}&quot;
          </blockquote>
        )}

        <div className="flex gap-1 flex-wrap">
          {onOpenPdf && study.pdfUrl && (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onOpenPdf(study);
              }}
            >
              <FileText className="h-3 w-3 mr-1" />
              PDF
            </Button>
          )}
          <Button
            variant={isSelected ? "default" : "outline"}
            size="sm"
            className={isSelected ? "bg-purple-600 hover:bg-purple-700 text-white" : ""}
            onClick={(e) => {
              e.stopPropagation();
              onSelect?.(study);
            }}
          >
            <GitCompare className="h-3 w-3 mr-1" />
            {isSelected ? "✓ Selected" : "Compare"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              onExclude?.(study);
            }}
          >
            <X className="h-3 w-3 mr-1" />
            Exclude
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
