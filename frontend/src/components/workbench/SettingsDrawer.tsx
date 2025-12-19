"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
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
    console.log("[Settings] Applying settings:", localSettings);
    onSettingsChange(localSettings);
    setIsOpen(false);
  };

  const handleReset = () => {
    setLocalSettings(defaultSettings);
  };

  const handleSliderChange = (key: "relevanceThreshold" | "maxStudies" | "yearCutoff", divisor = 1) => 
    (values: number[]) => handleChange(key, values[0] / divisor);
  
  const handleSelectChange = <T extends string>(key: keyof SearchSettings) =>
    (value: T) => handleChange(key, value as SearchSettings[typeof key]);
  
  const handleSwitchChange = (key: "useReranking" | "includeOlderStudies") =>
    (checked: boolean) => handleChange(key, checked);

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1">
          <Settings className="h-4 w-4" />
          Search Settings
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Search Settings</DialogTitle>
          <DialogDescription>
            Configure how evidence is retrieved and answers are generated.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
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
                <SelectItem value="executive">Executive Summary</SelectItem>
                <SelectItem value="research">Detailed Research</SelectItem>
                <SelectItem value="policy">Policy Brief</SelectItem>
                <SelectItem value="citations">Citations Only</SelectItem>
              </SelectContent>
            </Select>
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
        </div>

        <DialogFooter className="flex gap-2">
          <Button variant="outline" onClick={handleReset} className="gap-1">
            <RotateCcw className="h-3 w-3" />
            Reset
          </Button>
          <Button onClick={handleApply}>
            Apply Settings
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export { defaultSettings };
