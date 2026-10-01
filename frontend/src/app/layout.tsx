import type { Metadata } from "next";
import { Figtree, Newsreader } from "next/font/google";
import Link from "next/link";
import { HealthGate } from "@/components/HealthGate";
import { PersonaSprite } from "@/components/PersonaSprite";
import { ProjectBrief } from "@/components/ProjectBrief";
import { MOCK } from "@/lib/config";
import "./globals.css";

const sans = Figtree({ subsets: ["latin"], variable: "--font-figtree", display: "swap" });
const serif = Newsreader({ subsets: ["latin"], variable: "--font-serif", axes: ["opsz"], style: ["normal", "italic"], display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL("https://mimic-teal-one.vercel.app"),
  title: { default: "MIMIC × Ghost: multi-agent synthetic usability testing", template: "%s | MIMIC × Ghost" },
  description: "Your first users shouldn’t be your testers. Six AI personas test your site before launch, with evidence for every finding.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${sans.variable} ${serif.variable}`}>
      <body>
        <a href="#main" className="skip-link">Skip to content</a>
        <header className="site-header">
          <div className="shell header-inner">
            <Link className="brand" href="/" aria-label="MIMIC × Ghost home">
              <PersonaSprite size={34} />
              <span className="brand-name">MIMIC <span>× Ghost</span></span>
            </Link>
            <nav className="header-links" aria-label="Main navigation">
              {MOCK && <span className="mock-label">Mock mode</span>}
              <Link href="/case-study" prefetch={false}>Case study</Link>
              <Link className="header-cta" href="/">New run</Link>
            </nav>
          </div>
        </header>
        <main id="main" className="shell main"><HealthGate brief={<ProjectBrief />}>{children}</HealthGate></main>
        <footer className="shell footer">
          <span>MIMIC × Ghost. Evidence before intuition.</span>
          <span>Synthetic observations, human judgment.</span>
        </footer>
      </body>
    </html>
  );
}
