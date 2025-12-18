"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Settings, RotateCcw } from "lucide-react";
import type { AnswerStyle } from "@/types";

export interface SearchSettings {
  relevanceThreshold: number;
  maxStudies: number;
  answerStyle: AnswerStyle;
  useReranking: boolean;
  minConfidence: "all" | "medium" | "high";
  includeOlderStudies: boolean;
  yearCutoff: number;
}

const defaultSettings: SearchSettings = {
  relevanceThreshold: 0.5,
  maxStudies: 10,
  answerStyle: "executive",
  useReranking: true,
  minConfidence: "all",
  includeOlderStudies: true,
  yearCutoff: 2010,
};

interface SettingsDrawerProps {
  settings: SearchSettings;
  onSettingsChange: (settings: SearchSettings) => void;
}

export function SettingsDrawer({ settings, onSettingsChange }: SettingsDrawerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [localSettings, setLocalSettings] = useState<SearchSettings>(settings);

  const handleChange = <K extends keyof SearchSettings>(key: K, value: SearchSettings[K]) => {
    setLocalSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleApply = () => {
    onSettingsChange(localSettings);
    setIsOpen(false);
  };

  const handleReset = () => {
    setLocalSettings(defaultSettings);
  };

  // Typed handlers to avoid implicit any
  const handleSliderChange = (key: "relevanceThreshold" | "maxStudies" | "yearCutoff", divisor = 1) => 
    (values: number[]) => handleChange(key, values[0] / divisor);
  
  const handleSelectChange = <T extends string>(key: keyof SearchSettings) =>
    (value: T) => handleChange(key, value as SearchSettings[typeof key]);
  
  const handleSwitchChange = (key: "useReranking" | "includeOlderStudies") =>
    (checked: boolean) => handleChange(key, checked);

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1">
          <Settings className="h-4 w-4" />
          Settings
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-[350px] sm:w-[400px] px-6">
        <SheetHeader>
          <SheetTitle>Search Settings</SheetTitle>
          <SheetDescription>
            Configure how evidence is retrieved and answers are generated.
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-6 px-6">
          {/* Relevance Threshold */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Relevance Threshold</Label>
              <span className="text-sm text-muted-foreground font-mono">
                {(localSettings.relevanceThreshold * 100).toFixed(0)}%
              </span>
            </div>
            <Slider
              value={[localSettings.relevanceThreshold * 100]}
              onValueChange={handleSliderChange("relevanceThreshold", 100)}
              min={0}
              max={100}
              step={5}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Only include studies with relevance score above this threshold.
            </p>
          </div>

          {/* Max Studies */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Max Studies to Retrieve</Label>
              <span className="text-sm text-muted-foreground font-mono">
                {localSettings.maxStudies}
              </span>
            </div>
            <Slider
              value={[localSettings.maxStudies]}
              onValueChange={handleSliderChange("maxStudies")}
              min={3}
              max={25}
              step={1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Maximum number of studies to include in results.
            </p>
          </div>

          {/* Answer Style */}
          <div className="space-y-2">
            <Label>Answer Style</Label>
            <Select
              value={localSettings.answerStyle}
              onValueChange={handleSelectChange<AnswerStyle>("answerStyle")}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="executive">
                  <div className="flex flex-col">
                    <span>Executive Summary</span>
                    <span className="text-xs text-muted-foreground">Concise, key findings first</span>
                  </div>
                </SelectItem>
                <SelectItem value="research">
                  <div className="flex flex-col">
                    <span>Detailed Research</span>
                    <span className="text-xs text-muted-foreground">Comprehensive with methodology</span>
                  </div>
                </SelectItem>
                <SelectItem value="policy">
                  <div className="flex flex-col">
                    <span>Policy Brief</span>
                    <span className="text-xs text-muted-foreground">Actionable recommendations</span>
                  </div>
                </SelectItem>
                <SelectItem value="citations">
                  <div className="flex flex-col">
                    <span>Citations Only</span>
                    <span className="text-xs text-muted-foreground">Minimal synthesis, focus on sources</span>
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Minimum Confidence */}
          <div className="space-y-2">
            <Label>Minimum Study Confidence</Label>
            <Select
              value={localSettings.minConfidence}
              onValueChange={handleSelectChange<"all" | "medium" | "high">("minConfidence")}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All studies</SelectItem>
                <SelectItem value="medium">Medium or higher</SelectItem>
                <SelectItem value="high">High confidence only</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Filter studies by methodology quality rating.
            </p>
          </div>

          {/* Reranking Toggle */}
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Use Reranking</Label>
              <p className="text-xs text-muted-foreground">
                Apply AI reranking for better relevance
              </p>
            </div>
            <Switch
              checked={localSettings.useReranking}
              onCheckedChange={handleSwitchChange("useReranking")}
            />
          </div>

          {/* Year Cutoff */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Include Studies From</Label>
              <span className="text-sm text-muted-foreground font-mono">
                {localSettings.includeOlderStudies ? `${localSettings.yearCutoff}+` : "Recent only"}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <Switch
                checked={localSettings.includeOlderStudies}
                onCheckedChange={handleSwitchChange("includeOlderStudies")}
              />
              {localSettings.includeOlderStudies && (
                <Slider
                  value={[localSettings.yearCutoff]}
                  onValueChange={handleSliderChange("yearCutoff")}
                  min={1990}
                  max={2024}
                  step={1}
                  className="flex-1"
                />
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {localSettings.includeOlderStudies 
                ? `Include studies from ${localSettings.yearCutoff} onwards.`
                : "Only include studies from the last 5 years."}
            </p>
          </div>
        </div>

        <div className="mt-8 pt-4 border-t flex gap-2">
          <Button variant="outline" onClick={handleReset} className="gap-1">
            <RotateCcw className="h-3 w-3" />
            Reset
          </Button>
          <Button onClick={handleApply} className="flex-1">
            Apply Settings
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

export { defaultSettings };
