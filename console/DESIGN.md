# Novak's design system

What Novak should look like, and why. Written plainly, like the rest of the
project's docs.

## The idea

**Novak lives in a house, not a datacentre.**

Most self-hosted software looks like infrastructure: blue-grey, dense, faintly
industrial. Novak is closer to a kitchen appliance you happen to trust — a
thing on a shelf that answers when spoken to. It should look calm and slightly
warm, closer to paper and clay than to aluminium.

That is not decoration. The project's whole argument is that this runs in your
home, on your hardware, holding things you told it in confidence. Software that
looks like a monitoring console invites you to treat it like one.

Three commitments follow:

- **Warm neutrals, never blue-grey.** Every grey here carries a red/yellow
  cast. It is the single decision that does most of the work.
- **One accent, used sparingly.** Clay. If everything is accented, nothing is.
- **Nothing loads from anywhere.** No web fonts, no CDNs. A system whose reason
  for existing is that your data stays put should not phone out to render a
  heading.

## Themes

A theme is data: a light and a dark palette in
[`src/lib/themes.ts`](src/lib/themes.ts). Four are built in: **Clay** (Novak's
own, and the default), **Sage**, **Harbour** and **Plum**. They change the
accent and tint the neutrals, and all of them keep the neutrals warm. Status
colours are shared, so a failure looks the same in every scheme.

**Both modes are authored, neither is derived.** Deriving dark from light
produces cold, muddy colour, and warmth is the point here.

**Every theme is checked.** A test measures each text and background pair in
light and dark (4.5:1, or 3:1 for the faint tier). If you change a colour, the
test tells you whether it is still readable.

### Adding your own

Put a file in `registry/themes/`, named for the theme (`moss.yaml`). No rebuild
is needed.

```yaml
label: Moss
about: Added by this household.
extends: sage          # optional, clay if left out: list only what you change
light: { accent: "#3d5a2f" }
dark:  { accent: "#a9c795" }
```

The colour names are the ones in `KEYS` in `themes.ts`, and values are
six-digit hex colours in quotes. The same contrast test applies. A file that
fails it, or contains anything else, is not offered, and the Appearance page
says why.

### What each person can change

The Appearance page offers colour scheme, light or dark, text size, high
contrast and reduced motion. Each follows the device until someone overrides
it, and the choice is kept in a cookie on that device. A new setting is one entry
in [`src/lib/appearance.ts`](src/lib/appearance.ts) and the CSS for it.

## Using the tokens

Everything is a CSS custom property. Colours come from the chosen theme; type,
space and shape are in [`src/styles/tokens.css`](src/styles/tokens.css). **A
literal colour, size or radius in a component or stylesheet is a bug.** The one
exception is `src/app/icon.svg`, because a favicon cannot read the page's tokens.

Tokens are named by **role**, not by shade:

```css
background: var(--surface-sunken);   /* yes — survives a palette change */
background: var(--warm-100);          /* no  — meaningless once it moves */
```

| Family | Tokens |
|---|---|
| Surfaces | `--bg` `--surface` `--surface-sunken` |
| Lines | `--border` `--border-strong` |
| Text | `--text` `--text-muted` `--text-faint` |
| Accent | `--accent` `--accent-hover` `--accent-quiet` `--on-accent` |
| Status | `--ok` `--warn` `--danger` (each with a `-quiet` tint) |
| Risk | `--risk-standard` `--risk-elevated` `--risk-dangerous` |
| Type | `--font-sans` `--font-mono`, `--text-xs` … `--text-2xl` |
| Space | `--space-1` … `--space-12` (4px base) |
| Shape | `--radius-sm` `--radius` `--radius-lg` `--radius-full` |
| Depth | `--shadow-sm` `--shadow` `--shadow-lg` |

### Risk tokens are not decoration

`--risk-standard`, `--risk-elevated` and `--risk-dangerous` map onto the exact
words the MCP registry uses. They are aliases of the status colours, so the UI
cannot invent a fourth risk level or quietly rename one — if the registry's
vocabulary changes, this breaks visibly rather than drifting.

Use them wherever a risk level is shown. Never substitute a raw status colour
there; the indirection is the point.

## Shape and weight

- **Rounded, not square.** `--radius` on cards and controls. Square corners
  read industrial; this shouldn't.
- **Shallow, warm shadows.** Light through a window, not a spotlight. Depth
  separates layers; it should not announce itself.
- **Generous line height** (`--leading-body`, 1.6) and a `68ch` measure on
  prose. This is a reading interface — memories, personas, decisions — not a
  dashboard of numbers.

## What not to do

- **No gradients, no glow, no glassmorphism.** The "AI product" visual idiom is
  the opposite of the impression this should give.
- **No colour-only meaning.** Risk levels need a word or icon too. Some people
  cannot tell your terracotta from your olive.
- **No hiding focus rings.** This surface can reconfigure the stack; keyboard
  users must see where they are.
- **No literal values.** If a token is missing, add one — don't inline a hex.

## Extending the console

| To add | Change |
|---|---|
| A colour scheme for one household | A file in `registry/themes/` |
| A built-in colour scheme | One entry in `BUILTIN` in `src/lib/themes.ts` |
| A display setting | `src/lib/appearance.ts`, plus CSS keyed on its data attribute |
| A page in the header | One line in `src/components/nav.tsx` |

Shared page pieces are plain CSS classes in `globals.css` (`.page`, `.list`,
`.empty`, `.pill`, `.summary`, `.notice`, `.button`). Reuse them before adding
new ones.
