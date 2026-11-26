import { test } from "node:test";
import assert from "node:assert/strict";
import { BUILTIN, parseTheme, problems, themeCss } from "./themes.ts";
import { DEFAULTS, clean, decode, encode } from "./appearance.ts";

test("every built-in theme is readable in light and dark", () => {
  for (const t of BUILTIN) assert.deepEqual([...problems(t.light, `${t.id} light`), ...problems(t.dark, `${t.id} dark`)], []);
});

test("a custom theme can change a few colours of a built-in one", () => {
  const r = parseTheme("moss", 'label: Moss\nextends: sage\nlight: { accent: "#3d5a2f" }\n');
  assert.ok("theme" in r);
  assert.equal(r.theme.light.accent, "#3d5a2f");
  assert.match(themeCss(r.theme), /--accent:#3d5a2f/);
});

test("nothing but hex colours under known names gets into the stylesheet", () => {
  for (const bad of [
    'light: { accent: "red;}</style><script>" }',
    'light: { accent: "url(https://example.test/x)" }',
    'light: { "x:y}body{": "#000000" }',
    'extends: nope',
  ]) assert.ok("error" in parseTheme("bad", bad), bad);
  assert.ok("error" in parseTheme("../etc", "label: x"));
  assert.ok("error" in parseTheme("clay", "label: x"));
});

test("a theme that is too faint to read is refused, with the reason", () => {
  const r = parseTheme("ghost", 'light: { text: "#EEEEEE" }');
  assert.ok("error" in r);
  assert.match(r.error, /light: text on bg/);
});

test("appearance cookies are cleaned and survive a round trip", () => {
  assert.deepEqual(decode(undefined), DEFAULTS);
  assert.deepEqual(decode("theme=<b>&mode=purple&text=__proto__&contrast=toString"), DEFAULTS);
  const a = clean({ theme: "plum", mode: "dark", text: "largest", contrast: "high", motion: "reduce" });
  assert.deepEqual(decode(encode(a)), a);
});
