import { cn } from "../utils";
import React, { createContext, useContext, useState } from "react";

type SelectCtx = { value: string; setValue: (v: string) => void; open: boolean; setOpen: (v: boolean) => void };
const Ctx = createContext<SelectCtx | null>(null);

export function Select({
  value,
  onValueChange,
  children,
}: {
  value: string;
  onValueChange: (v: string) => void;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Ctx.Provider
      value={{
        value,
        setValue: (v) => {
          onValueChange(v);
          setOpen(false);
        },
        open,
        setOpen,
      }}
    >
      <div className="relative">{children}</div>
    </Ctx.Provider>
  );
}

export const SelectTrigger = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(({ className, ...props }, ref) => {
  const ctx = useContext(Ctx);
  return (
    <div
      ref={ref}
      className={cn(
        "flex h-10 w-full items-center justify-between rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm cursor-pointer",
        className
      )}
      onClick={() => ctx?.setOpen(!ctx?.open)}
      {...props}
    />
  );
});
SelectTrigger.displayName = "SelectTrigger";

export const SelectValue = ({ children }: { children?: React.ReactNode }) => {
  const ctx = useContext(Ctx);
  return <span className="text-sm">{children || ctx?.value}</span>;
};

export function SelectContent({ className, children }: React.HTMLAttributes<HTMLDivElement>) {
  const ctx = useContext(Ctx);
  if (!ctx?.open) return null;
  return <div className={cn("absolute z-10 mt-1 w-full rounded-md border border-slate-200 bg-white shadow-sm p-1 space-y-1", className)}>{children}</div>;
}

export function SelectItem({ value, children }: { value: string; children: React.ReactNode }) {
  const ctx = useContext(Ctx);
  return (
    <div
      className="cursor-pointer rounded px-2 py-1 text-sm hover:bg-slate-100"
      onClick={() => ctx?.setValue(value)}
      role="option"
      aria-selected={ctx?.value === value}
    >
      {children}
    </div>
  );
}
