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

**Both are authored, neither is derived.** Deriving dark from light produces
cold, muddy colour, and warmth is the point here. The dark palette is a warm
charcoal — brown-black rather than blue-black — with the accent lifted and
desaturated, because clay that reads rich on paper turns to mud on charcoal.

The OS preference wins by default; an explicit `data-theme` attribute overrides
it in either direction.

**Every pair meets WCAG AA** (4.5:1 for body text, 3:1 for the intentionally
faint tier). That was measured, not judged by eye — the warm palette's low
contrast between adjacent neutrals makes eyeballing unreliable. If you change a
colour, re-check it rather than trusting it looks fine.

## Using the tokens

Everything is a CSS custom property in
[`src/styles/tokens.css`](src/styles/tokens.css). **A literal colour, size or
radius anywhere else is a bug.**

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

## Status, and what comes next

The token layer exists and is loaded. **There are no components yet**, and that
is deliberate: Konzol currently has three placeholder pages, and designing
components for screens that do not exist means guessing.

Build them as real screens arrive. Once there is a genuine component library
with exported parts, `/design-sync` becomes worth running — it can then teach a
design agent to build new Konzol screens from Novak's actual components rather
than generic ones. Running it today would sync an empty shell.
