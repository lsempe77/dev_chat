"use client";

import { Study } from "@/types";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { X, ExternalLink, FileText } from "lucide-react";

interface CompareModalProps {
  isOpen: boolean;
  onClose: () => void;
  studies: Study[];
  onRemoveStudy: (study: Study) => void;
}

const confidenceColors = {
  high: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  medium: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  low: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

const CompareField = ({ label, values, gridCols }: { label: string; values: (string | number | undefined)[]; gridCols: string }) => (
  <div className="grid gap-2" style={{ gridTemplateColumns: gridCols }}>
    <div className="font-medium text-sm text-muted-foreground py-2">{label}</div>
    {values.map((value, i) => (
      <div key={i} className="py-2 text-sm border-l pl-3 min-w-0 break-words">
        {value || "—"}
      </div>
    ))}
  </div>
);

export function CompareModal({ isOpen, onClose, studies, onRemoveStudy }: CompareModalProps) {
  if (studies.length === 0) return null;

  // Calculate min width per study column (250px min for better readability)
  const minColWidth = Math.max(250, Math.floor(1000 / Math.max(studies.length, 1)));
  const gridCols = `140px repeat(${studies.length}, minmax(${minColWidth}px, 1fr))`;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[99vw] h-[92vh] w-full flex flex-col overflow-hidden">
        <DialogHeader className="shrink-0">
          <DialogTitle className="flex items-center gap-2">
            Compare Studies
            <Badge variant="outline">{studies.length} selected</Badge>
          </DialogTitle>
        </DialogHeader>

        {/* Horizontal + Vertical scroll container */}
        <div className="flex-1 overflow-auto min-h-0">
          <div className="space-y-0 min-w-max">
            {/* Header Row - Study Titles */}
            <div 
              className="grid gap-2 sticky top-0 bg-background pb-2 border-b"
              style={{ gridTemplateColumns: gridCols }}
            >
              <div className="font-medium text-sm text-muted-foreground py-2">Field</div>
              {studies.map((study) => (
                <div key={study.id} className="border-l pl-3 py-2 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-sm line-clamp-2">{study.title}</p>
                      <p className="text-xs text-muted-foreground mt-1 truncate">
                        {study.authors}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 shrink-0"
                      onClick={() => onRemoveStudy(study)}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>

            {/* Comparison Rows */}
            <div className="divide-y">
              <CompareField 
                label="Year" 
                values={studies.map(s => s.year)} 
                gridCols={gridCols}
              />
              <CompareField 
                label="Country" 
                values={studies.map(s => s.country)} 
                gridCols={gridCols}
              />
              <CompareField 
                label="Sector" 
                values={studies.map(s => s.sector)} 
                gridCols={gridCols}
              />
              <CompareField 
                label="Study Type" 
                values={studies.map(s => s.studyType)} 
                gridCols={gridCols}
              />
              
              {/* Confidence with colored badges */}
              <div className="grid gap-2" style={{ gridTemplateColumns: gridCols }}>
                <div className="font-medium text-sm text-muted-foreground py-2">Confidence</div>
                {studies.map((study, i) => (
                  <div key={i} className="py-2 border-l pl-3 min-w-0">
                    <Badge className={confidenceColors[study.confidence]}>
                      {study.confidence}
                    </Badge>
                  </div>
                ))}
              </div>

              {/* Relevance Score */}
              <div className="grid gap-2" style={{ gridTemplateColumns: gridCols }}>
                <div className="font-medium text-sm text-muted-foreground py-2">Relevance Score</div>
                {studies.map((study, i) => (
                  <div key={i} className="py-2 border-l pl-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-blue-500 rounded-full"
                          style={{ width: `${(study.score || 0) * 100}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono">
                        {((study.score || 0) * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              {/* Key Finding */}
              <div className="grid gap-2" style={{ gridTemplateColumns: gridCols }}>
                <div className="font-medium text-sm text-muted-foreground py-2">Key Finding</div>
                {studies.map((study, i) => (
                  <div key={i} className="py-2 border-l pl-3">
                    <blockquote className="text-sm text-muted-foreground italic border-l-2 border-muted pl-2">
                      &quot;{study.snippet}&quot;
                    </blockquote>
                  </div>
                ))}
              </div>

              {/* PDF Links */}
              <div className="grid gap-2" style={{ gridTemplateColumns: gridCols }}>
                <div className="font-medium text-sm text-muted-foreground py-2">Source</div>
                {studies.map((study, i) => (
                  <div key={i} className="py-2 border-l pl-3">
                    {study.pdfUrl ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => window.open(study.pdfUrl, "_blank")}
                      >
                        <FileText className="h-3 w-3 mr-1" />
                        View PDF
                        <ExternalLink className="h-3 w-3 ml-1" />
                      </Button>
                    ) : (
                      <span className="text-xs text-muted-foreground">No PDF available</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t shrink-0">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          <Button onClick={() => {
            // Export comparison as CSV or share
            const headers = ["Title", "Authors", "Year", "Country", "Sector", "Study Type", "Confidence", "Score", "Key Finding"];
            const rows = studies.map(s => [
              s.title,
              s.authors,
              s.year,
              s.country,
              s.sector || "",
              s.studyType,
              s.confidence,
              s.score || "",
              s.snippet
            ]);
            
            const csv = [headers.join(","), ...rows.map(r => r.map(v => `"${v}"`).join(","))].join("\n");
            const blob = new Blob([csv], { type: "text/csv" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "study_comparison.csv";
            a.click();
            URL.revokeObjectURL(url);
          }}>
            Export Comparison
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
