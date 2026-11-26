/**
 * Themes are data. A theme is a light and a dark palette; every colour in the console comes from the
 * one that is chosen. Four are built in, and a deployment can add its own as
 * registry/themes/<id>.yaml without rebuilding the image:
 *
 *   label: Moss
 *   extends: sage            # optional, default clay: only list what you change
 *   light: { accent: "#46603a" }
 *   dark:  { accent: "#a9c795" }
 *
 * A custom theme is written by whoever runs the box, but it ends up inside a <style> element, so it is
 * parsed strictly: known keys only, six-digit hex values only. It must also pass the same contrast
 * checks as the built-in ones, or it is not offered and the Appearance page says why.
 *
 * No imports from "@/…" so the node test runner can load this file directly.
 */
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { parse } from "yaml";

export const KEYS = [
  "bg", "surface", "surface-sunken", "border", "border-strong", "text", "text-muted", "text-faint",
  "accent", "accent-hover", "accent-quiet", "on-accent",
  "ok", "ok-quiet", "warn", "warn-quiet", "danger", "danger-quiet",
] as const;
export type Key = (typeof KEYS)[number];
export type Palette = Record<Key, string>;
export interface Theme { id: string; label: string; about: string; light: Palette; dark: Palette; custom?: boolean }

// Status colours are shared: "this failed" should look the same whichever scheme is chosen.
const statusLight = { ok: "#3F6B3C", "ok-quiet": "#E6EFE4", warn: "#805300", "warn-quiet": "#F7EBD3", danger: "#9B3226", "danger-quiet": "#F7E2DE" };
const statusDark = { ok: "#86B87F", "ok-quiet": "#1E2A1D", warn: "#DDA83F", "warn-quiet": "#302614", danger: "#E5806D", "danger-quiet": "#331D19" };

type Base = Omit<Palette, keyof typeof statusLight>;
const make = (id: string, label: string, about: string, light: Base, dark: Base): Theme =>
  ({ id, label, about, light: { ...light, ...statusLight }, dark: { ...dark, ...statusDark } });

export const BUILTIN: Theme[] = [
  make("clay", "Clay", "Warm paper and terracotta. Novak's own.",
    { bg: "#FBF8F4", surface: "#FFFFFF", "surface-sunken": "#F2ECE4", border: "#E4DACF", "border-strong": "#CFC0B1", text: "#2A2422", "text-muted": "#665C55", "text-faint": "#857970", accent: "#A8482A", "accent-hover": "#8E3C22", "accent-quiet": "#F6E7DF", "on-accent": "#FFFFFF" },
    { bg: "#191614", surface: "#232019", "surface-sunken": "#121010", border: "#363029", "border-strong": "#4E4539", text: "#F0E9E1", "text-muted": "#ABA096", "text-faint": "#8A8078", accent: "#E28E63", "accent-hover": "#EFA47C", "accent-quiet": "#33251D", "on-accent": "#191614" }),
  make("sage", "Sage", "A kitchen herb shelf.",
    { bg: "#F8F8F2", surface: "#FFFFFF", "surface-sunken": "#EDEEE2", border: "#DCDECB", "border-strong": "#C2C6AC", text: "#24271F", "text-muted": "#575C4C", "text-faint": "#7A7F6C", accent: "#4C6636", "accent-hover": "#3D532B", "accent-quiet": "#E7EDDB", "on-accent": "#FFFFFF" },
    { bg: "#161812", surface: "#1F2219", "surface-sunken": "#10120D", border: "#31362A", "border-strong": "#464D3B", text: "#ECEEE2", "text-muted": "#A5AA96", "text-faint": "#848A76", accent: "#A9C584", "accent-hover": "#BCD59A", "accent-quiet": "#29321E", "on-accent": "#161812" }),
  make("harbour", "Harbour", "Sea glass on weathered wood.",
    { bg: "#F9F7F3", surface: "#FFFFFF", "surface-sunken": "#EEEBE3", border: "#DED9CC", "border-strong": "#C6BEAC", text: "#232625", "text-muted": "#565B57", "text-faint": "#787D78", accent: "#1F6670", "accent-hover": "#18535B", "accent-quiet": "#DFEEEE", "on-accent": "#FFFFFF" },
    { bg: "#151716", surface: "#1E2220", "surface-sunken": "#0F1110", border: "#303633", "border-strong": "#454E49", text: "#EAEDE8", "text-muted": "#A3AAA4", "text-faint": "#828A84", accent: "#79C2C6", "accent-hover": "#95D3D6", "accent-quiet": "#1B3132", "on-accent": "#151716" }),
  make("plum", "Plum", "Evening in the sitting room.",
    { bg: "#FAF7F6", surface: "#FFFFFF", "surface-sunken": "#F1EAEA", border: "#E2D6D8", "border-strong": "#CCBABF", text: "#2A2225", "text-muted": "#665a5e", "text-faint": "#85777c", accent: "#84395F", "accent-hover": "#6E2E4F", "accent-quiet": "#F4E3EC", "on-accent": "#FFFFFF" },
    { bg: "#181416", surface: "#221C20", "surface-sunken": "#110E10", border: "#372D33", "border-strong": "#4F4049", text: "#EFE7EB", "text-muted": "#AC9DA5", "text-faint": "#8C7E86", accent: "#DE92B6", "accent-hover": "#EBA9C7", "accent-quiet": "#35212C", "on-accent": "#181416" }),
];

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

// [foreground, background, minimum]: 4.5 for text that carries information, 3 for the faint tier.
const PAIRS: [Key, Key, number][] = [
  ...(["bg", "surface"] as Key[]).flatMap((on): [Key, Key, number][] => [
    ["text", on, 4.5], ["text-muted", on, 4.5], ["accent", on, 4.5], ["danger", on, 4.5], ["text-faint", on, 3],
  ]),
  ["text", "surface-sunken", 4.5], ["on-accent", "accent", 4.5], ["on-accent", "accent-hover", 4.5], ["accent", "accent-quiet", 4.5],
  ["ok", "ok-quiet", 4.5], ["warn", "warn-quiet", 4.5], ["danger", "danger-quiet", 4.5], ["text", "warn-quiet", 4.5],
];

/** Every pair that is too faint, as sentences. Empty means the palette is readable. */
export function problems(p: Palette, mode: string): string[] {
  return PAIRS.flatMap(([fg, bg, min]) => {
    const c = contrast(p[fg], p[bg]);
    return c < min ? [`${mode}: ${fg} on ${bg} is ${c.toFixed(2)}:1, needs ${min}:1`] : [];
  });
}

const ID_RE = /^[a-z][a-z0-9-]{0,31}$/;
const HEX_RE = /^#[0-9a-fA-F]{6}$/;

/** One custom theme file. Returns the theme, or why it was refused. */
export function parseTheme(id: string, text: string): { theme: Theme } | { error: string } {
  if (!ID_RE.test(id)) return { error: "the file name must be lowercase letters, digits and dashes" };
  if (BUILTIN.some((t) => t.id === id)) return { error: `"${id}" is already a built-in theme` };
  let doc: Record<string, unknown>;
  try {
    doc = (parse(text) ?? {}) as Record<string, unknown>;
  } catch {
    return { error: "the file is not valid YAML" };
  }
  const base = BUILTIN.find((t) => t.id === (doc.extends ?? "clay"));
  if (!base) return { error: "extends must name a built-in theme" };
  const palettes = { light: { ...base.light }, dark: { ...base.dark } };
  for (const mode of ["light", "dark"] as const) {
    const given = doc[mode] ?? {};
    if (typeof given !== "object" || Array.isArray(given)) return { error: `${mode} must be a list of colours` };
    for (const [k, v] of Object.entries(given as Record<string, unknown>)) {
      if (!(KEYS as readonly string[]).includes(k)) return { error: `${mode}: "${k.slice(0, 40)}" is not a colour name` };
      if (typeof v !== "string" || !HEX_RE.test(v)) return { error: `${mode}: ${k} must be a colour like "#336699", in quotes` };
      palettes[mode][k as Key] = v;
    }
  }
  const bad = [...problems(palettes.light, "light"), ...problems(palettes.dark, "dark")];
  if (bad.length) return { error: `too hard to read (${bad.slice(0, 3).join("; ")})` };
  const label = typeof doc.label === "string" && doc.label.trim() ? doc.label.trim().slice(0, 40) : id;
  const about = typeof doc.about === "string" ? doc.about.slice(0, 120) : "Added by this household.";
  return { theme: { id, label, about, ...palettes, custom: true } };
}

export async function loadThemes(root: string): Promise<{ themes: Theme[]; refused: { file: string; error: string }[] }> {
  const themes = [...BUILTIN];
  const refused: { file: string; error: string }[] = [];
  const dir = path.join(root, "themes");
  let files: string[] = [];
  try {
    files = (await readdir(dir)).filter((f) => f.endsWith(".yaml")).sort().slice(0, 40);
  } catch {
    return { themes, refused };
  }
  for (const file of files) {
    try {
      const r = parseTheme(file.slice(0, -5), await readFile(path.join(dir, file), "utf8"));
      if ("theme" in r) themes.push(r.theme);
      else refused.push({ file, error: r.error });
    } catch {
      refused.push({ file, error: "the file could not be read" });
    }
  }
  return { themes, refused };
}

const vars = (p: Palette) => KEYS.map((k) => `--${k}:${p[k]}`).join(";");

/** The chosen theme as CSS. The system setting wins unless data-theme on <html> says otherwise. */
export function themeCss(t: Theme): string {
  return `:root{${vars(t.light)}}@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){${vars(t.dark)}}}:root[data-theme="dark"]{${vars(t.dark)}}`;
}
