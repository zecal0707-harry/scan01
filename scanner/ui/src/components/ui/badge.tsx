import * as React from "react";
import { cn } from "../utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "outline";
}

export function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const base = "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold";
  const map: Record<string, string> = {
    default: "bg-slate-900 text-white border-transparent",
    secondary: "bg-slate-100 text-slate-900 border-transparent",
    outline: "text-slate-900 border-slate-200"
  };
  return <div className={cn(base, map[variant], className)} {...props} />;
}
