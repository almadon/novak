/**
 * How one device likes the console to look. Kept in a cookie so the page is right on the first paint
 * and no script has to run. The default for everything is "follow the system".
 *
 * To add a setting: add it to OPTIONS, then style its data-attribute in styles/globals.css.
 */
export const COOKIE = "novak_appearance";

export const OPTIONS = {
  mode: { label: "Light or dark", choices: { system: "Follow this device", light: "Light", dark: "Dark" } },
  text: { label: "Text size", choices: { small: "Small", default: "Default", large: "Large", largest: "Largest" } },
  contrast: { label: "Contrast", choices: { standard: "Standard", high: "High" } },
  motion: { label: "Motion", choices: { system: "Follow this device", reduce: "Reduce" } },
} as const;

export interface Appearance { theme: string; mode: string; text: string; contrast: string; motion: string }
export const DEFAULTS: Appearance = { theme: "clay", mode: "system", text: "default", contrast: "standard", motion: "system" };

/** Anything unrecognised falls back to the default: a cookie is input like any other. */
export function clean(input: Partial<Record<keyof Appearance, unknown>>): Appearance {
  const out = { ...DEFAULTS };
  for (const key of Object.keys(OPTIONS) as (keyof typeof OPTIONS)[]) {
    const v = input[key];
    if (typeof v === "string" && Object.hasOwn(OPTIONS[key].choices, v)) out[key] = v;
  }
  if (typeof input.theme === "string" && /^[a-z][a-z0-9-]{0,31}$/.test(input.theme)) out.theme = input.theme;
  return out;
}

export const encode = (a: Appearance): string => new URLSearchParams({ ...a }).toString();
export const decode = (v: string | undefined): Appearance => clean(Object.fromEntries(new URLSearchParams(v ?? "")));
