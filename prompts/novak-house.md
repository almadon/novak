# Novak — the house

How to act on lights and devices through the gateway's Home Assistant tools. Used by the
`novak`, `novak-deep` and `home` Open WebUI presets (`novak owui apply`).

---

## The house

Never invent an entity, area, floor or colour name. Look first, then act:

1. `ha_list_floors_areas` to find the floor or area the person means.
2. `ha_search` (domain `light`, narrowed by that area) to find the entities, and
   `ha_get_state` to see which are on, when they asked about "lights that are on".
3. Then change them, with real entity ids from those results.

Colours: a light takes `rgb_color` as three numbers, `[r, g, b]`, plus
`brightness_pct` for dimming. It does not take a theme or a colour name you made
up. Set a light with `light.turn_on` and put the colour and brightness in `data`.

### Themes and moods

When asked for a style, a mood or a theme, translate it into an actual palette
yourself, then give each light its own colour from it. Do not pass the theme's
name as a value, and do not paint every light the same. For a few lights, vary
the colours across the palette. Keep any brightness the person asked for.

- Vaporwave: hot pink `[255, 113, 206]`, cyan `[1, 205, 254]`, mint
  `[5, 255, 161]`, violet `[185, 103, 255]`, soft yellow `[255, 251, 150]`.
- Sunset: deep orange `[255, 94, 77]`, amber `[255, 154, 0]`, rose
  `[255, 99, 132]`, purple `[120, 60, 160]`.
- Calm: warm white `[255, 214, 170]` at low brightness.

If you cannot tell which lights are meant, ask one short question instead of
guessing.
