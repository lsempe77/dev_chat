"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { StudyCard } from "./StudyCard";
import { Study, Citation } from "@/types";
import { Download } from "lucide-react";

interface EvidencePanelProps {
  studies: Study[];
  citations: Citation[];
  highlightedCitation?: number;
  selectedStudies: Study[];
  onSelectStudy: (study: Study) => void;
  onExcludeStudy: (study: Study) => void;
  onOpenPdf: (study: Study) => void;
  query?: string;
  answer?: string;
}

export function EvidencePanel({
  studies,
  citations,
  highlightedCitation,
  selectedStudies,
  onSelectStudy,
  onExcludeStudy,
  onOpenPdf,
  query = "",
  answer = "",
}: EvidencePanelProps) {
  // Get citation number for each study
  const getCitationNumber = (studyId: string): number | undefined => {
    const citation = citations.find((c) => c.studyId === studyId);
    return citation?.id;
  };

  // Check if study is selected for comparison
  const isSelected = (study: Study): boolean => {
    return selectedStudies.some((s) => s.id === study.id);
  };

  // Check if study should be highlighted (matches clicked citation)
  const isHighlighted = (study: Study): boolean => {
    if (!highlightedCitation) return false;
    const citation = citations.find((c) => c.id === highlightedCitation);
    return citation?.studyId === study.id;
  };

  // Export results as CSV
  const handleExportCSV = () => {
    const headers = ["Citation #", "Title", "Authors", "Year", "Country", "Sector", "Study Type", "Confidence", "Relevance Score", "Key Finding", "PDF URL"];
    const rows = studies.map((s) => [
      getCitationNumber(s.id) || "",
      s.title,
      s.authors,
      s.year,
      s.country,
      s.sector || "",
      s.studyType,
      s.confidence,
      s.score ? (s.score * 100).toFixed(0) + "%" : "",
      s.snippet,
      s.pdfUrl || ""
    ]);
    
    const csv = [headers.join(","), ...rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `evidence_results_${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Export full results including answer as JSON
  const handleExportJSON = () => {
    const exportData = {
      exportDate: new Date().toISOString(),
      query,
      answer,
      studyCount: studies.length,
      studies: studies.map((s) => ({
        citationNumber: getCitationNumber(s.id),
        ...s
      }))
    };
    
    const json = JSON.stringify(exportData, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `evidence_results_${new Date().toISOString().split("T")[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          📚 Evidence
          <span className="text-sm font-normal text-muted-foreground">
            ({studies.length} studies)
          </span>
        </h2>
        <div className="flex items-center gap-2">
          {selectedStudies.length > 0 && (
            <span className="text-sm text-purple-600 dark:text-purple-400">
              {selectedStudies.length} selected
            </span>
          )}
          {studies.length > 0 && (
            <div className="flex gap-1">
              <Button variant="outline" size="sm" onClick={handleExportCSV} title="Download as CSV">
                <Download className="h-3 w-3 mr-1" />
                CSV
              </Button>
              <Button variant="outline" size="sm" onClick={handleExportJSON} title="Download as JSON">
                <Download className="h-3 w-3 mr-1" />
                JSON
              </Button>
            </div>
          )}
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-3 pr-4">
          {studies.map((study) => (
            <StudyCard
              key={study.id}
              study={study}
              citationNumber={getCitationNumber(study.id)}
              isHighlighted={isHighlighted(study)}
              isSelected={isSelected(study)}
              onSelect={onSelectStudy}
              onExclude={onExcludeStudy}
              onOpenPdf={onOpenPdf}
            />
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
