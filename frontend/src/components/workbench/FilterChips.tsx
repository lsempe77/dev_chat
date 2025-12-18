"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Filter } from "@/types";
import { X, Plus } from "lucide-react";

interface FilterChipsProps {
  filters: Filter[];
  onRemove: (filter: Filter) => void;
  onAdd: () => void;
  inferredFilters?: Filter[];
  onToggleInferred?: (filter: Filter) => void;
}

export function FilterChips({
  filters,
  onRemove,
  onAdd,
  inferredFilters = [],
  onToggleInferred,
}: FilterChipsProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 p-2 bg-muted/50 rounded-lg">
      <span className="text-sm text-muted-foreground">Active filters:</span>
      
      {filters.length === 0 && inferredFilters.length === 0 && (
        <span className="text-sm text-muted-foreground italic">None</span>
      )}

      {filters.map((filter) => (
        <Badge
          key={filter.id}
          variant="default"
          className="flex items-center gap-1 pr-1"
        >
          {filter.label}
          <button
            onClick={() => onRemove(filter)}
            className="ml-1 rounded-full hover:bg-primary-foreground/20 p-0.5"
          >
            <X className="h-3 w-3" />
          </button>
        </Badge>
      ))}

      {inferredFilters.length > 0 && (
        <>
          <span className="text-xs text-muted-foreground">|</span>
          <span className="text-xs text-muted-foreground">Inferred:</span>
          {inferredFilters.map((filter) => (
            <Badge
              key={filter.id}
              variant="outline"
              className="flex items-center gap-1 pr-1 opacity-70"
            >
              {filter.label}
              {onToggleInferred && (
                <button
                  onClick={() => onToggleInferred(filter)}
                  className="ml-1 rounded-full hover:bg-muted p-0.5"
                  title="Remove inferred filter"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </Badge>
          ))}
        </>
      )}

      <Button variant="ghost" size="sm" onClick={onAdd} className="h-6">
        <Plus className="h-3 w-3 mr-1" />
        Add
      </Button>
    </div>
  );
}
