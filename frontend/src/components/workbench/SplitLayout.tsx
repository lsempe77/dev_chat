"use client";

import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ReactNode } from "react";

interface SplitLayoutProps {
  leftPanel: ReactNode;
  rightPanel: ReactNode;
  defaultLeftSize?: number;
}

export function SplitLayout({
  leftPanel,
  rightPanel,
  defaultLeftSize = 50,
}: SplitLayoutProps) {
  return (
    <ResizablePanelGroup
      direction="horizontal"
      className="min-h-[calc(100vh-200px)] rounded-lg border"
    >
      <ResizablePanel defaultSize={defaultLeftSize} minSize={30}>
        <div className="h-full overflow-auto p-4">{leftPanel}</div>
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel defaultSize={100 - defaultLeftSize} minSize={30}>
        <div className="h-full overflow-auto p-4">{rightPanel}</div>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
