import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "../../lib/utils";

type SelectOption = {
  label: string;
  value: string;
};

type SelectProps = {
  value: string;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder: string;
  label: string;
};

export function Select({ value, onValueChange, options, placeholder, label }: SelectProps) {
  return (
    <label className="grid gap-2 text-sm">
      <span className="text-xs font-medium uppercase tracking-normal text-muted-foreground">{label}</span>
      <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
        <SelectPrimitive.Trigger className="inline-flex h-11 w-full items-center justify-between rounded-lg border border-input bg-black/35 px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-primary/25">
          <SelectPrimitive.Value placeholder={placeholder} />
          <SelectPrimitive.Icon>
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          </SelectPrimitive.Icon>
        </SelectPrimitive.Trigger>
        <SelectPrimitive.Portal>
          <SelectPrimitive.Content className="z-50 overflow-hidden rounded-lg border border-white/10 bg-[#111827] text-foreground shadow-2xl">
            <SelectPrimitive.Viewport className="p-1">
              {options.map((option) => (
                <SelectPrimitive.Item
                  key={option.value}
                  value={option.value}
                  className={cn(
                    "relative flex cursor-pointer select-none items-center rounded-md py-2 pl-8 pr-3 text-sm outline-none data-[highlighted]:bg-primary/20",
                  )}
                >
                  <SelectPrimitive.ItemIndicator className="absolute left-2 inline-flex items-center">
                    <Check className="h-4 w-4" />
                  </SelectPrimitive.ItemIndicator>
                  <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                </SelectPrimitive.Item>
              ))}
            </SelectPrimitive.Viewport>
          </SelectPrimitive.Content>
        </SelectPrimitive.Portal>
      </SelectPrimitive.Root>
    </label>
  );
}
