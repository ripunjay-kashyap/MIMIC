import type { Metadata } from "next";
import Link from "next/link";
import { HealthGate } from "@/components/HealthGate";
import { MOCK } from "@/lib/config";
import "./globals.css";
export const metadata: Metadata = { title: "MIMIC × GhostQA", description: "Explore usability through six independent synthetic users." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body><a href="#main" className="skip-link">Skip to content</a><header className="site-header"><div className="shell header-inner"><Link className="brand" href="/">MIMIC <span>× GhostQA</span></Link><div className="header-links">{MOCK && <span className="mock-label">Mock mode</span>}<Link href="/">New run</Link></div></div></header>
    <main id="main" className="shell main"><HealthGate>{children}</HealthGate></main>
    <footer className="shell footer">Synthetic usability testing · Observations are evidence; interpretations are hypotheses.</footer>
  </body></html>;
}
