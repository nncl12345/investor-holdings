"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { TrendingUp } from "lucide-react";

const links = [
  { href: "/", label: "Feed" },
  { href: "/investors", label: "Investors" },
  { href: "/alerts", label: "Alerts" },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <header className="border-b border-border bg-card sticky top-0 z-50">
      <div className="container mx-auto px-4 max-w-6xl flex items-center gap-8 h-14">
        <Link href="/" className="flex items-center gap-2 font-semibold text-foreground">
          <TrendingUp className="w-4 h-4 text-primary" />
          Holdings
        </Link>
        <nav className="flex items-center gap-1">
          {links.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={cn(
                "px-3 py-1.5 rounded-md text-sm transition-colors",
                pathname === href
                  ? "bg-accent text-foreground font-medium"
                  : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
              )}
            >
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
