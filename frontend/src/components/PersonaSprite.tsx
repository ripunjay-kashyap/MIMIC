import type { CSSProperties } from "react";
import type { PersonaState } from "@/lib/types";

export type PersonaType = PersonaState["persona_type"];
// Each hue keeps at least 3:1 contrast on the paper background (lines, dots, avatars; never body text).
export const personaColors: Record<PersonaType, string> = {
  impatient: "#D4532A", low_literacy: "#2C74B0", power: "#2A8656",
  cautious: "#7454BC", explorer: "#A87708", chaos: "#C23C79",
};
export const personaNames: Record<PersonaType, string> = {
  impatient: "Impatient", low_literacy: "Low literacy", power: "Power",
  cautious: "Cautious", explorer: "Explorer", chaos: "Chaos",
};
export const personaTypes = Object.keys(personaNames) as PersonaType[];

export function personaTypeFromId(id: string): PersonaType | "ghost" {
  const type = id.replace(/-\d+$/, "").replaceAll("-", "_");
  return type in personaColors ? type as PersonaType : "ghost";
}

export const personaStyle = (type: PersonaType | "ghost") =>
  ({ "--persona-color": type === "ghost" ? "#221E1A" : personaColors[type] }) as CSSProperties;

const INK = "#221E1A";
const PAPER = "#FBF8F3";
const BODY = "M9 23C9 14.2 15.7 7 24 7s15 7.2 15 16v15a5 5 0 0 1-10 0 5 5 0 0 1-10 0 5 5 0 0 1-10 0z";
const line = { fill: "none", stroke: INK, strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

/** A friendly ghost drawn in a 48 × 48 box; one face and one prop per persona. */
export function PersonaGlyph({ type = "ghost" }: { type?: PersonaType | "ghost" }) {
  const ghost = type === "ghost";
  const face = ghost ? PAPER : INK;
  const eye = (cx: number, rx = 2.1, ry = 2.6) => <>
    <ellipse cx={cx} cy={22} rx={rx} ry={ry} fill={face} />
    {!ghost && <circle cx={cx + .7} cy={21} r={.75} fill="#fff" />}
  </>;
  return (
    <g>
      {type === "explorer" && <path d="M16.4 10.6c0-5.2 3.4-8.4 7.6-8.4s7.6 3.2 7.6 8.4z" fill="#D9B26A" stroke={INK} strokeWidth={1.3} />}
      <path d={BODY} fill={ghost ? INK : personaColors[type]} stroke={INK} strokeWidth={ghost ? 0 : 1.5} strokeLinejoin="round" />
      {!ghost && <ellipse cx={16.5} cy={14.5} rx={3.3} ry={2} fill="#fff" opacity={.3} transform="rotate(-35 16.5 14.5)" />}
      {type === "chaos" ? <>{eye(19.2, 2.8, 3.2)}{eye(29, 1.5, 1.9)}</> : <>{eye(19.5)}{eye(28.5)}</>}
      {!ghost && <>
        <ellipse cx={15.6} cy={27.6} rx={2.2} ry={1.3} fill="#fff" opacity={.35} />
        <ellipse cx={32.4} cy={27.6} rx={2.2} ry={1.3} fill="#fff" opacity={.35} />
      </>}
      {ghost && <path d="M21 27.4q3 2.6 6 0" {...line} stroke={face} />}

      {type === "impatient" && <>
        <path d="M16.6 17.4l4.6 1.7M31.4 17.4l-4.6 1.7M21.4 28.4h5.2" {...line} />
        <circle cx={38.4} cy={11} r={6.2} fill="#fff" stroke={INK} strokeWidth={1.5} />
        <path d="M37 3.2h2.8M38.4 11V7.4M38.4 11l2.6 1.5" {...line} strokeWidth={1.4} />
      </>}
      {type === "low_literacy" && <>
        <g {...line} strokeWidth={1.4}>
          <circle cx={19.5} cy={22} r={4.4} fill="#fff" fillOpacity={.22} />
          <circle cx={28.5} cy={22} r={4.4} fill="#fff" fillOpacity={.22} />
          <path d="M23.8 21.4q.2-.6.4 0M15.1 21.2l-2.6-1.1M32.9 21.2l2.6-1.1" />
        </g>
        <circle cx={24} cy={29.2} r={1.5} fill={INK} />
        <path d="M36.2 6.6a3.2 3.2 0 1 1 4.5 2.9c-.9.4-1.5 1-1.5 2.2" {...line} strokeWidth={1.8} />
        <circle cx={39.2} cy={15.6} r={1.1} fill={INK} />
      </>}
      {type === "power" && <>
        <path d="M20.6 27.2q3.4 3.2 6.8 0" {...line} />
        <path d="M40.6 1.8 34 12h4.3l-2.4 8.4 7.6-11.6h-4.6l2.6-7z" fill="#F2C14E" stroke={INK} strokeWidth={1.3} strokeLinejoin="round" />
      </>}
      {type === "cautious" && <>
        <path d="M16.8 18.8l4.4-1.5M31.2 18.8l-4.4-1.5M20.8 29.2q1.6-1.4 3.2 0t3.2 0" {...line} />
        <path d="M37.6 23.2l6 2.3v4.4c0 4-2.6 6.6-6 8-3.4-1.4-6-4-6-8v-4.4z" fill="#fff" stroke={INK} strokeWidth={1.4} strokeLinejoin="round" />
        <path d="M35 30.4l1.9 1.9 3.4-3.6" {...line} stroke={personaColors.cautious} strokeWidth={1.7} />
      </>}
      {type === "explorer" && <>
        <path d="M16.6 8.4h14.8" stroke="#7A5320" strokeWidth={2} />
        <ellipse cx={24} cy={10.8} rx={14.2} ry={2.6} fill="#C99A52" stroke={INK} strokeWidth={1.3} />
        <path d="M20.4 27h7.2a3.6 3.6 0 0 1-7.2 0z" fill={INK} />
      </>}
      {type === "chaos" && <>
        <path d="M20.4 27.4q3.6 3.4 7.2 0" {...line} />
        <ellipse cx={25.6} cy={29.6} rx={1.6} ry={1.8} fill="#F4A3C2" stroke={INK} strokeWidth={.9} />
        <path d="M34.6 5.4l2.4 3 1.6-3.6 2.4 3.6 2.2-3.2M40.8 13.6l2.6 1.4" {...line} strokeWidth={1.4} />
      </>}
    </g>
  );
}

export function PersonaSprite({ type = "ghost", size = 40, label }: {
  type?: PersonaType | "ghost"; size?: number; label?: string;
}) {
  return (
    <svg className={`persona-sprite sprite-${type}`} width={size} height={size} viewBox="0 0 48 48"
      role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <PersonaGlyph type={type} />
    </svg>
  );
}
