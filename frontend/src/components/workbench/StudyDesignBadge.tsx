"use client";

import { Badge } from "@/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { StudyDesign } from "@/types";

/**
 * Study design display information
 */
const STUDY_DESIGN_INFO: Record<StudyDesign, {
  label: string;
  category: string;
  color: string;
  evidenceWeight: number;
}> = {
  // Experimental (Green tones)
  rct: { 
    label: "RCT", 
    category: "Experimental", 
    color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200 border-emerald-300",
    evidenceWeight: 1.0
  },
  cluster_rct: { 
    label: "Cluster RCT", 
    category: "Experimental", 
    color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200 border-emerald-300",
    evidenceWeight: 0.95
  },
  stepped_wedge: { 
    label: "Stepped Wedge", 
    category: "Experimental", 
    color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200 border-emerald-300",
    evidenceWeight: 0.9
  },
  
  // Quasi-Experimental (Blue tones)
  regression_discontinuity: { 
    label: "RDD", 
    category: "Quasi-Experimental", 
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300",
    evidenceWeight: 0.85
  },
  difference_in_differences: { 
    label: "DiD", 
    category: "Quasi-Experimental", 
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300",
    evidenceWeight: 0.8
  },
  synthetic_control: { 
    label: "Synth Control", 
    category: "Quasi-Experimental", 
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300",
    evidenceWeight: 0.8
  },
  instrumental_variable: { 
    label: "IV", 
    category: "Quasi-Experimental", 
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300",
    evidenceWeight: 0.75
  },
  propensity_score: { 
    label: "PSM", 
    category: "Quasi-Experimental", 
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300",
    evidenceWeight: 0.7
  },
  interrupted_time_series: { 
    label: "ITS", 
    category: "Quasi-Experimental", 
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300",
    evidenceWeight: 0.7
  },
  matching: { 
    label: "Matching", 
    category: "Quasi-Experimental", 
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300",
    evidenceWeight: 0.65
  },
  natural_experiment: { 
    label: "Natural Exp", 
    category: "Quasi-Experimental", 
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300",
    evidenceWeight: 0.75
  },
  
  // Observational (Yellow/Amber tones)
  cohort: { 
    label: "Cohort", 
    category: "Observational", 
    color: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 border-amber-300",
    evidenceWeight: 0.6
  },
  case_control: { 
    label: "Case-Control", 
    category: "Observational", 
    color: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 border-amber-300",
    evidenceWeight: 0.55
  },
  cross_sectional: { 
    label: "Cross-Sectional", 
    category: "Observational", 
    color: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 border-amber-300",
    evidenceWeight: 0.5
  },
  descriptive: { 
    label: "Descriptive", 
    category: "Observational", 
    color: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 border-amber-300",
    evidenceWeight: 0.4
  },
  
  // Qualitative (Purple tones)
  qualitative: { 
    label: "Qualitative", 
    category: "Qualitative", 
    color: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 border-purple-300",
    evidenceWeight: 0.4
  },
  mixed_methods: { 
    label: "Mixed Methods", 
    category: "Qualitative", 
    color: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 border-purple-300",
    evidenceWeight: 0.5
  },
  case_study: { 
    label: "Case Study", 
    category: "Qualitative", 
    color: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 border-purple-300",
    evidenceWeight: 0.45
  },
  ethnography: { 
    label: "Ethnography", 
    category: "Qualitative", 
    color: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200 border-purple-300",
    evidenceWeight: 0.4
  },
  
  // Observational additions
  panel: { 
    label: "Panel", 
    category: "Observational", 
    color: "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200 border-amber-300",
    evidenceWeight: 0.55
  },
  propensity_score_matching: { 
    label: "PSM", 
    category: "Quasi-Experimental", 
    color: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 border-blue-300",
    evidenceWeight: 0.7
  },
  
  // Synthesis (Teal tones)
  systematic_review: { 
    label: "Syst Review", 
    category: "Synthesis", 
    color: "bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200 border-teal-300",
    evidenceWeight: 0.9
  },
  meta_analysis: { 
    label: "Meta-Analysis", 
    category: "Synthesis", 
    color: "bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200 border-teal-300",
    evidenceWeight: 0.85
  },
  
  // Other (Gray tones)
  modeling: { 
    label: "Modeling", 
    category: "Other", 
    color: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200 border-slate-300",
    evidenceWeight: 0.3
  },
  theory: { 
    label: "Theory", 
    category: "Other", 
    color: "bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-200 border-slate-300",
    evidenceWeight: 0.25
  },
  unknown: { 
    label: "Unknown", 
    category: "Other", 
    color: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 border-slate-300",
    evidenceWeight: 0.3
  },
};

interface StudyDesignBadgeProps {
  design: StudyDesign;
  confidence?: number;
  showTooltip?: boolean;
  size?: "sm" | "md";
}

export function StudyDesignBadge({ 
  design, 
  confidence, 
  showTooltip = true,
  size = "sm"
}: StudyDesignBadgeProps) {
  const info = STUDY_DESIGN_INFO[design] || STUDY_DESIGN_INFO.unknown;
  
  const badge = (
    <Badge 
      variant="outline" 
      className={`${info.color} font-medium ${size === "sm" ? "text-xs py-0" : "text-sm"}`}
    >
      {info.label}
    </Badge>
  );
  
  if (!showTooltip) {
    return badge;
  }
  
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {badge}
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <div className="text-xs space-y-1">
            <p className="font-semibold">{info.category}</p>
            <p>Evidence Weight: {(info.evidenceWeight * 100).toFixed(0)}%</p>
            {confidence !== undefined && (
              <p>Classification Confidence: {(confidence * 100).toFixed(0)}%</p>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/**
 * Get the evidence weight for a study design
 */
export function getEvidenceWeight(design: StudyDesign): number {
  return STUDY_DESIGN_INFO[design]?.evidenceWeight || 0.3;
}

/**
 * Get the category for a study design
 */
export function getStudyDesignCategory(design: StudyDesign): string {
  return STUDY_DESIGN_INFO[design]?.category || "Other";
}
