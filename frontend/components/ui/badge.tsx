import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
  {
    variants: {
      variant: {
        default: "bg-primary/10 text-primary ring-primary/20",
        secondary: "bg-secondary text-secondary-foreground ring-border",
        destructive: "bg-destructive/10 text-destructive ring-destructive/20",
        activist: "bg-amber-500/10 text-amber-400 ring-amber-500/20",
        passive: "bg-blue-500/10 text-blue-400 ring-blue-500/20",
        new: "bg-emerald-500/10 text-emerald-400 ring-emerald-500/20",
        exited: "bg-red-500/10 text-red-400 ring-red-500/20",
        increased: "bg-green-500/10 text-green-400 ring-green-500/20",
        decreased: "bg-orange-500/10 text-orange-400 ring-orange-500/20",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export function Badge({
  className,
  variant,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
