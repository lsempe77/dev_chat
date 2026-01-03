"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Search, Loader2 } from "lucide-react";
import { useState, useEffect, FormEvent } from "react";

interface SearchInputProps {
  onSearch: (query: string) => void;
  isLoading?: boolean;
  placeholder?: string;
  value?: string;  // External controlled value
}

export function SearchInput({
  onSearch,
  isLoading = false,
  placeholder = "Ask about development evidence...",
  value: externalValue,
}: SearchInputProps) {
  const [query, setQuery] = useState(externalValue || "");

  // Sync internal state with external value when it changes
  useEffect(() => {
    if (externalValue !== undefined) {
      setQuery(externalValue);
    }
  }, [externalValue]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (query.trim() && !isLoading) {
      onSearch(query.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex gap-2">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          className="pl-10"
          disabled={isLoading}
        />
      </div>
      <Button type="submit" disabled={isLoading || !query.trim()}>
        {isLoading ? (
          <>
            <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            Searching...
          </>
        ) : (
          "Search"
        )}
      </Button>
    </form>
  );
}
