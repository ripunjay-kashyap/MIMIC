import type { PersonaState } from "@/lib/types";

export type PersonaType = PersonaState["persona_type"];
export const personaColors: Record<PersonaType, string> = {
  impatient: "#ffad72", low_literacy: "#87bfff", power: "#72f0be",
  cautious: "#d4acff", explorer: "#f5d472", chaos: "#fa9ecb",
};
export const personaNames: Record<PersonaType, string> = {
  impatient: "Impatient", low_literacy: "Low literacy", power: "Power",
  cautious: "Cautious", explorer: "Explorer", chaos: "Chaos",
};

export function personaTypeFromId(id: string): PersonaType | "ghost" {
  const type = id.replace(/-\d+$/, "").replaceAll("-", "_");
  return type in personaColors ? type as PersonaType : "ghost";
}

// Integer coordinates keep these hand-authored silhouettes crisp at every size.
export function PixelGlyph({ type = "ghost" }: { type?: PersonaType | "ghost" }) {
  const color = type === "ghost" ? "#72f0be" : personaColors[type];
  return (
    <g shapeRendering="crispEdges">
      <path fill={color} d={type === "power"
        ? "M5 3h5v2h2v2h1v7h-2v-2H9v2H7v-2H5v2H3V7h1V5h1z"
        : type === "cautious"
          ? "M6 2h4v1h2v2h1v9h-3v-2H8v2H6v-2H3V5h1V3h2z"
          : "M5 3h6v1h2v2h1v8h-2v-2h-2v2H8v-2H6v2H3V6h1V4h1z"} />
      <path fill="#07121c" d="M6 6h2v3H6zm4 0h2v3h-2z" />
      <path fill="#f2fff9" d="M6 6h1v1H6zm4 0h1v1h-1z" />
      {type === "impatient" && <>
        <path fill="#e9f4ff" d="M1 8h4v1h1v4H5v1H1v-1H0V9h1zm1-2h2v2H2z" />
        <path fill="#132331" d="M2 9h1v2h2v1H2z" />
        <path fill={color} d="M13 3h3v1h-3zm1 2h2v1h-2z" />
      </>}
      {type === "low_literacy" && <>
        <path fill="#ecf3ff" d="M1 10h4l2 1 2-1h5v5H9l-2 1-2-1H1z" />
        <path fill="#36527b" d="M6 11h2v4H6zM2 12h3v1H2zm7 0h4v1H9z" />
      </>}
      {type === "power" && <path fill="#f9f39b" d="M12 1h3l-2 4h3l-5 7 1-5H9z" />}
      {type === "cautious" && <>
        <path fill="#eee2ff" d="M1 9h6v4H6v2H5v1H3v-1H2v-2H1z" />
        <path fill="#735497" d="M3 10h2v3H3z" />
      </>}
      {type === "explorer" && <>
        <path fill="#bd9047" d="M3 2h8v2h3v1H1V4h2z" />
        <path fill="#f4f5d7" d="M12 9h3v1h1v3h-1v1h-3v-1h-1v-3h1z" />
        <path fill="#75591b" d="M13 10h1v3h-1zm-1 1h3v1h-3z" />
      </>}
      {type === "chaos" && <>
        <path fill="#07121c" d="M3 10h3v1H3zm9-6h2v1h-2z" />
        <path fill="#87bfff" d="M0 5h2v2H0zm13 5h3v2h-3zM6 1h3v1H6z" />
        <path fill="#f5d472" d="M8 10h2v1H8zm6 5h2v1h-2z" />
      </>}
    </g>
  );
}

export function PersonaSprite({ type = "ghost", size = 40, label }: {
  type?: PersonaType | "ghost"; size?: number; label?: string;
}) {
  return (
    <svg className={`persona-sprite sprite-${type}`} width={size} height={size} viewBox="0 0 16 16"
      role={label ? "img" : undefined} aria-label={label} aria-hidden={label ? undefined : true}>
      <PixelGlyph type={type} />
    </svg>
  );
}
