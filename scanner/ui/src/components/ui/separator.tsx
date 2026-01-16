import * as React from "react";
import { cn } from "../utils";

export function Separator({ className, orientation = "horizontal" }: { className?: string; orientation?: "horizontal" | "vertical" }) {
  return (
    <div
      role="separator"
      className={cn(orientation === "vertical" ? "w-px h-5 bg-slate-200" : "h-px w-full bg-slate-200", className)}
    />
  );
}
