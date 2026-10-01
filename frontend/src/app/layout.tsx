import type { Metadata } from "next";
import Link from "next/link";
import { HealthGate } from "@/components/HealthGate";
import { PersonaSprite } from "@/components/PersonaSprite";
import { MOCK } from "@/lib/config";
import "./globals.css";

export const metadata: Metadata = {
  title: "MIMIC × GhostQA",
  description: "Ship to synthetic users before real users. Six perspectives. Every step, evidenced.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <a href="#main" className="skip-link">Skip to content</a>
        <header className="site-header">
          <div className="shell header-inner">
            <Link className="brand" href="/" aria-label="MIMIC × GhostQA home">
              <PersonaSprite size={30} />
              <span className="brand-name">MIMIC <span>× GhostQA</span></span>
            </Link>
            <nav className="header-links" aria-label="Main navigation">
              {MOCK && <span className="mock-label">Mock mode</span>}
              <Link href="/case-study" prefetch={false}>Case study</Link>
              <Link href="/">New run <span aria-hidden="true">↗</span></Link>
            </nav>
          </div>
        </header>
        <main id="main" className="shell main"><HealthGate>{children}</HealthGate></main>
        <footer className="shell footer">
          <span>MIMIC × GhostQA <span aria-hidden="true">/</span> Evidence before intuition.</span>
          <span>Synthetic observations. Human judgment.</span>
        </footer>
      </body>
    </html>
  );
}
