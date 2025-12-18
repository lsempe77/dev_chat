"use client";

import { useState } from "react";
import { Filter } from "@/types";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Plus, Check } from "lucide-react";

interface FilterDrawerProps {
  isOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  currentFilters: Filter[];
  onAddFilter: (filter: Filter) => void;
  onRemoveFilter: (filter: Filter) => void;
}

// Available filter options
const filterOptions: Record<string, { type: Filter["type"]; values: string[] }> = {
  Country: {
    type: "country",
    values: ["Kenya", "India", "Mexico", "Bangladesh", "Nigeria", "Ethiopia", "Brazil", "Indonesia", "Ghana", "Uganda"],
  },
  Sector: {
    type: "sector",
    values: ["Education", "Health", "Social Protection", "Agriculture", "WASH", "Nutrition", "Microfinance", "Governance"],
  },
  "Study Type": {
    type: "studyType",
    values: ["RCT", "Quasi-experimental", "Systematic Review", "Meta-analysis", "Natural Experiment"],
  },
  "Year Range": {
    type: "yearRange",
    values: ["2020-2025", "2015-2019", "2010-2014", "2005-2009", "Before 2005"],
  },
  Confidence: {
    type: "confidence",
    values: ["High", "Medium", "Low"],
  },
};

export function FilterDrawer({ 
  isOpen: controlledIsOpen, 
  onOpenChange, 
  currentFilters, 
  onAddFilter, 
  onRemoveFilter 
}: FilterDrawerProps) {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  
  // Use controlled state if provided, otherwise use internal state
  const isOpen = controlledIsOpen !== undefined ? controlledIsOpen : internalIsOpen;
  const setIsOpen = onOpenChange || setInternalIsOpen;

  const isFilterActive = (type: Filter["type"], value: string) => {
    return currentFilters.some((f) => f.type === type && f.value.toLowerCase() === value.toLowerCase());
  };

  const toggleFilter = (type: Filter["type"], value: string, category: string) => {
    const existing = currentFilters.find((f) => f.type === type && f.value.toLowerCase() === value.toLowerCase());
    
    if (existing) {
      onRemoveFilter(existing);
    } else {
      onAddFilter({
        id: `${type}-${value.toLowerCase().replace(/\s+/g, "-")}`,
        type,
        value: value.toLowerCase(),
        label: `${category}: ${value}`,
      });
    }
  };

  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1">
          <Plus className="h-3 w-3" />
          Add Filter
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-[350px] sm:w-[400px]">
        <SheetHeader>
          <SheetTitle>Add Filters</SheetTitle>
        </SheetHeader>
        
        <div className="mt-6 space-y-6">
          {Object.entries(filterOptions).map(([category, { type, values }]) => (
            <div key={category}>
              <h4 className="text-sm font-medium mb-2">{category}</h4>
              <div className="flex flex-wrap gap-2">
                {values.map((value) => {
                  const active = isFilterActive(type, value);
                  return (
                    <Badge
                      key={value}
                      variant={active ? "default" : "outline"}
                      className="cursor-pointer hover:bg-muted transition-colors"
                      onClick={() => toggleFilter(type, value, category)}
                    >
                      {active && <Check className="h-3 w-3 mr-1" />}
                      {value}
                    </Badge>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-8 pt-4 border-t">
          <p className="text-sm text-muted-foreground mb-2">
            <strong>{currentFilters.length}</strong> filters active
          </p>
          <Button 
            onClick={() => setIsOpen(false)} 
            className="w-full"
          >
            Apply Filters
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
