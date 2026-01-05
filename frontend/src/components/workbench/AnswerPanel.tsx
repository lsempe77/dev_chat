"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Citation, EvidenceHealth, AnswerStyle } from "@/types";
import { AlertTriangle, Info, Lightbulb, Copy, Check } from "lucide-react";

interface AnswerPanelProps {
  answer: string;
  citations: Citation[];
  evidenceHealth: EvidenceHealth;
  suggestions: string[];
  answerStyle: AnswerStyle;
  isLoading?: boolean;
  onCitationClick: (citationId: number) => void;
  onSuggestionClick: (suggestion: string) => void;
}

export function AnswerPanel({
  answer,
  citations,
  evidenceHealth,
  suggestions,
  isLoading = false,
  onCitationClick,
  onSuggestionClick,
}: AnswerPanelProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      // Try modern Clipboard API first
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(answer);
      } else {
        // Fallback for non-secure contexts (like VS Code Simple Browser)
        const textArea = document.createElement("textarea");
        textArea.value = answer;
        textArea.style.position = "fixed";
        textArea.style.left = "-999999px";
        textArea.style.top = "-999999px";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        document.execCommand("copy");
        textArea.remove();
      }
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
      // Still show copied as user may have manually copied
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Render a single citation button
  const renderCitationButton = (citationId: number, key: string): React.ReactNode => {
    const isValidCitation = citations.some(c => c.id === citationId);
    
    if (isValidCitation) {
      return (
        <button
          key={key}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onCitationClick(citationId);
          }}
          className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 text-xs font-mono bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 rounded hover:bg-blue-200 dark:hover:bg-blue-800 transition-colors mx-0.5"
        >
          {citationId}
        </button>
      );
    } else {
      return (
        <span key={key} className="text-orange-500" title="Citation not found">
          [{citationId}]
        </span>
      );
    }
  };

  // Custom renderer for citations in markdown - converts [1], [2], [1,2], [1, 2, 3] to clickable bubbles
  const renderCitationLinks = (text: string): React.ReactNode => {
    // Match single [1] or combined [1,2] [1, 2, 3] patterns
    const parts = text.split(/(\[\d+(?:\s*,\s*\d+)*\])/g);
    
    return parts.map((part, index) => {
      // Check for combined citations like [1,2] or [1, 2, 3]
      const multiMatch = part.match(/\[(\d+(?:\s*,\s*\d+)+)\]/);
      if (multiMatch) {
        // Parse all citation numbers
        const citationIds = multiMatch[1].split(/\s*,\s*/).map(n => parseInt(n, 10));
        return (
          <span key={index}>
            {citationIds.map((citationId, i) => renderCitationButton(citationId, `${index}-${i}`))}
          </span>
        );
      }
      
      // Check for single citation like [1]
      const singleMatch = part.match(/\[(\d+)\]/);
      if (singleMatch) {
        const citationId = parseInt(singleMatch[1], 10);
        return renderCitationButton(citationId, `${index}`);
      }
      
      return <span key={index}>{part}</span>;
    });
  };

  // Recursively process all children to find citation patterns [1], [2], etc.
  const processNode = (node: React.ReactNode): React.ReactNode => {
    // Handle strings - this is where citations like [1] appear
    if (typeof node === "string") {
      if (/\[\d+\]/.test(node)) {
        return renderCitationLinks(node);
      }
      return node;
    }
    
    // Handle numbers
    if (typeof node === "number") {
      return node;
    }
    
    // Handle arrays
    if (Array.isArray(node)) {
      return node.map((child, i) => (
        <React.Fragment key={i}>{processNode(child)}</React.Fragment>
      ));
    }
    
    // Handle React elements - recursively process children
    if (React.isValidElement(node)) {
      const props = node.props as { children?: React.ReactNode };
      if (props.children !== undefined) {
        return React.cloneElement(
          node,
          { ...props, key: node.key },
          processNode(props.children)
        );
      }
    }
    
    return node;
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          💬 Answer
        </h2>
        {answer && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCopy}
            className="gap-1.5"
          >
            {copied ? (
              <>
                <Check className="h-4 w-4 text-green-600" />
                Copied!
              </>
            ) : (
              <>
                <Copy className="h-4 w-4" />
                Copy
              </>
            )}
          </Button>
        )}
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-4 pr-4">
          {/* Main Answer */}
          <div className="prose prose-sm dark:prose-invert max-w-none">
            {isLoading ? (
              <div className="animate-pulse space-y-2">
                <div className="h-4 bg-muted rounded w-full"></div>
                <div className="h-4 bg-muted rounded w-5/6"></div>
                <div className="h-4 bg-muted rounded w-4/6"></div>
              </div>
            ) : (
              <>
              <ReactMarkdown
                components={{
                  // Override paragraph to handle citation links
                  p: ({ children }) => (
                    <p className="mb-3 leading-relaxed">
                      {processNode(children)}
                    </p>
                  ),
                  // Style headings - but hide "References" heading since we have our own
                  h2: ({ children }) => {
                    const text = String(children);
                    if (text.toLowerCase() === "references") {
                      return null; // Hide the LLM's References heading
                    }
                    return (
                      <h2 className="text-base font-semibold mt-4 mb-2 text-foreground">
                        {children}
                      </h2>
                    );
                  },
                  h3: ({ children }) => (
                    <h3 className="text-sm font-semibold mt-3 mb-1 text-foreground">
                      {processNode(children)}
                    </h3>
                  ),
                  // Style bold text
                  strong: ({ children }) => (
                    <strong className="font-semibold text-foreground">
                      {processNode(children)}
                    </strong>
                  ),
                  // Style italic text
                  em: ({ children }) => (
                    <em className="italic">{processNode(children)}</em>
                  ),
                  // Style lists - but hide reference lists
                  ul: ({ children }) => {
                    // Check if this is a reference list (children are citations)
                    const childArray = Array.isArray(children) ? children : [children];
                    const isReferenceList = childArray.some((child: React.ReactNode) => {
                      if (child && typeof child === 'object' && 'props' in child) {
                        const props = (child as React.ReactElement).props as { children?: React.ReactNode };
                        const text = String(props?.children || '');
                        return text.includes('(2023)') || text.includes('(2022)') || text.includes('(2021)');
                      }
                      return false;
                    });
                    if (isReferenceList) {
                      return null; // Hide reference lists from LLM
                    }
                    return (
                      <ul className="list-disc list-inside mb-3 space-y-1">
                        {children}
                      </ul>
                    );
                  },
                  li: ({ children }) => (
                    <li className="text-sm">{processNode(children)}</li>
                  ),
                  // Style horizontal rules
                  hr: () => <Separator className="my-4" />,
                }}
              >
                {answer}
              </ReactMarkdown>

              {/* Citations Reference - right after the answer */}
              {citations.length > 0 && (
                <div className="mt-4 pt-4 border-t">
                  <h3 className="text-sm font-medium mb-3">References</h3>
                  <div className="space-y-2">
                    {citations.map((citation) => (
                      <button
                        key={citation.id}
                        onClick={() => onCitationClick(citation.id)}
                        className="flex items-start gap-2 w-full text-left hover:bg-muted/50 rounded-lg p-2 -ml-2 transition-colors"
                      >
                        <span className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-1.5 text-xs font-mono bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 rounded shrink-0">
                          {citation.id}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          {citation.study.authors} ({citation.study.year}).{" "}
                          <em>{citation.study.title}</em>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              </>
            )}
          </div>

          <Separator />

          {/* Evidence Health */}
          {(evidenceHealth.studyCount > 0 || evidenceHealth.gaps.length > 0) && (
            <Card className="bg-muted/50">
              <CardContent className="pt-4">
                <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
                  <Info className="h-4 w-4" />
                  Evidence Quality
                </h3>
                <div className="space-y-2 text-sm">
                  {evidenceHealth.studyCount > 0 && (
                    <div className="flex items-center gap-2">
                      <Badge variant={evidenceHealth.studyCount >= 5 ? "default" : "secondary"}>
                        {evidenceHealth.studyCount} studies
                      </Badge>
                      {evidenceHealth.dateRange && (
                        <span className="text-muted-foreground">
                          {evidenceHealth.dateRange}
                        </span>
                      )}
                    </div>
                  )}
                  {evidenceHealth.gaps.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-muted">
                      <p className="text-xs font-medium text-muted-foreground mb-1">Gaps identified:</p>
                      {evidenceHealth.gaps.map((gap, i) => (
                        <p key={i} className="flex items-start gap-1.5 text-yellow-600 dark:text-yellow-400 text-xs">
                          <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" />
                          <span>{gap}</span>
                        </p>
                      ))}
                    </div>
                  )}
                  {evidenceHealth.coverageWarning && (
                    <p className="text-yellow-600 dark:text-yellow-400 text-xs mt-2">
                      ⚠️ {evidenceHealth.coverageWarning}
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Query Coaching - show loading skeleton or suggestions */}
          {isLoading ? (
            <Card className="bg-muted/50">
              <CardContent className="pt-4">
                <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
                  <Lightbulb className="h-4 w-4" />
                  Try next
                </h3>
                <div className="space-y-2">
                  <div className="h-4 bg-muted rounded w-3/4 animate-pulse"></div>
                  <div className="h-4 bg-muted rounded w-2/3 animate-pulse"></div>
                  <div className="h-4 bg-muted rounded w-4/5 animate-pulse"></div>
                </div>
              </CardContent>
            </Card>
          ) : suggestions.length > 0 ? (
            <Card className="bg-muted/50">
              <CardContent className="pt-4">
                <h3 className="text-sm font-medium mb-2 flex items-center gap-2">
                  <Lightbulb className="h-4 w-4" />
                  Try next
                </h3>
                <div className="space-y-1">
                  {suggestions.map((suggestion, i) => (
                    <button
                      key={i}
                      onClick={() => onSuggestionClick(suggestion)}
                      className="block w-full text-left text-sm text-blue-600 dark:text-blue-400 hover:underline"
                    >
                      • {suggestion}
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          ) : null}


        </div>
      </ScrollArea>
    </div>
  );
}
