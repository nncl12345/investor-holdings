import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Nav } from "@/components/Nav";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Investor Holdings",
  description: "Track activist 13D/G filings and quarterly 13F holdings from SEC EDGAR",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={inter.className}>
        <div className="min-h-screen flex flex-col">
          <Nav />
          <main className="flex-1 container mx-auto px-4 py-6 max-w-6xl">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
