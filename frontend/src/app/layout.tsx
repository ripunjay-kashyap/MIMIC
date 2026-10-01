import type { Metadata } from "next";
import { Figtree, Newsreader } from "next/font/google";
import Link from "next/link";
import { HealthGate } from "@/components/HealthGate";
import { PersonaSprite } from "@/components/PersonaSprite";
import { MOCK } from "@/lib/config";
import "./globals.css";

const sans = Figtree({ subsets: ["latin"], variable: "--font-figtree", display: "swap" });
const serif = Newsreader({ subsets: ["latin"], variable: "--font-serif", axes: ["opsz"], style: ["normal", "italic"], display: "swap" });

export const metadata: Metadata = {
  title: "MIMIC × GhostQA",
  description: "Ship to synthetic users before real users. Six perspectives. Every step, evidenced.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body>
        <a href="#main" className="skip-link">Skip to content</a>
        <header className="site-header">
          <div className="shell header-inner">
            <Link className="brand" href="/" aria-label="MIMIC × GhostQA home">
              <PersonaSprite size={34} />
              <span className="brand-name">MIMIC <span>× GhostQA</span></span>
            </Link>
            <nav className="header-links" aria-label="Main navigation">
              {MOCK && <span className="mock-label">Mock mode</span>}
              <Link href="/case-study" prefetch={false}>Case study</Link>
              <Link className="header-cta" href="/">New run</Link>
            </nav>
          </div>
        </header>
        <main id="main" className="shell main"><HealthGate>{children}</HealthGate></main>
        <footer className="shell footer">
          <span>MIMIC × GhostQA. Evidence before intuition.</span>
          <span>Synthetic observations, human judgment.</span>
        </footer>
      </body>
    </html>
  );
}
