"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { MessageSquare, Trash2, Plus } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ChatHistoryItem {
  id: string;
  query: string;
  timestamp: Date;
  studyCount?: number;
  answer?: string;
  citationsUsed?: number;
}

interface ChatHistoryProps {
  history: ChatHistoryItem[];
  currentQueryId?: string;
  onSelectQuery: (item: ChatHistoryItem) => void;
  onDeleteQuery: (id: string) => void;
  onNewChat: () => void;
}

export function ChatHistory({
  history,
  currentQueryId,
  onSelectQuery,
  onDeleteQuery,
  onNewChat,
}: ChatHistoryProps) {
  // Format time ago
  const formatTimeAgo = (date: Date) => {
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  // Truncate query for display
  const truncateQuery = (query: string, maxLength: number = 50) => {
    if (query.length <= maxLength) return query;
    return query.substring(0, maxLength).trim() + "...";
  };

  return (
    <div className="h-full flex flex-col bg-muted/30 border-r">
      {/* Header */}
      <div className="p-3 border-b flex items-center justify-between">
        <h3 className="font-medium text-sm flex items-center gap-2">
          <MessageSquare className="h-4 w-4" />
          History
        </h3>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onNewChat} title="New chat">
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      {/* History List */}
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-1">
          {history.length === 0 ? (
            <div className="text-center py-8 px-4">
              <MessageSquare className="h-8 w-8 mx-auto mb-2 text-muted-foreground/50" />
              <p className="text-xs text-muted-foreground">
                Your queries will appear here
              </p>
            </div>
          ) : (
            history.map((item) => (
              <div
                key={item.id}
                className={cn(
                  "group relative rounded-lg p-2 cursor-pointer transition-colors",
                  currentQueryId === item.id
                    ? "bg-primary/10 border border-primary/20"
                    : "hover:bg-muted"
                )}
                onClick={() => onSelectQuery(item)}
              >
                <p className="text-sm font-medium line-clamp-2 pr-6">
                  {truncateQuery(item.query, 60)}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-xs text-muted-foreground">
                    {formatTimeAgo(item.timestamp)}
                  </span>
                  {item.studyCount !== undefined && (
                    <span className="text-xs text-muted-foreground">
                      • {item.studyCount} studies
                    </span>
                  )}
                </div>
                {/* Delete button - shows on hover */}
                <Button
                  variant="ghost"
                  size="icon"
                  className="absolute right-1 top-1 h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteQuery(item.id);
                  }}
                  title="Remove from history"
                >
                  <Trash2 className="h-3 w-3 text-muted-foreground hover:text-destructive" />
                </Button>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
