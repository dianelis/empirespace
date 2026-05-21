import type { ButtonHTMLAttributes } from "react";
import { cn } from "../../lib/utils";

export function Button({ className, ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center rounded-lg border border-white/10 bg-white/8 px-3 text-sm font-medium text-foreground transition hover:bg-white/14 focus:outline-none focus:ring-2 focus:ring-primary/30",
        className,
      )}
      {...props}
    />
  );
}
