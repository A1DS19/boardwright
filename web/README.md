# Boardwright — landing page

The marketing site for [Boardwright](https://github.com/A1DS19/boardwright). TanStack Start on Cloudflare Workers, Tailwind 4, Biome.

## Develop

```bash
pnpm install
pnpm dev          # http://localhost:3000
```

## Build & deploy

```bash
pnpm build
pnpm exec wrangler deploy   # requires CLOUDFLARE_API_TOKEN
```

CI deploys on push to `main` when files under `web/` change. See `.github/workflows/deploy-web.yml`.

## Quality

```bash
pnpm exec biome check src/
pnpm exec tsc --noEmit
pnpm test
```

## Structure

```
web/
├── src/
│   ├── routes/
│   │   ├── __root.tsx       # SEO, JSON-LD, theme bootstrap, header/footer
│   │   └── index.tsx        # landing page (Hero, Benefits, HowItWorks, FinalCta)
│   ├── components/
│   │   ├── ui/              # shadcn-style primitives (Button, Input)
│   │   ├── shared/          # Header, Footer, ThemeToggle
│   │   └── newsletter-form.tsx
│   ├── server/
│   │   └── waitlist.ts      # Buttondown waitlist server function
│   ├── lib/utils.ts
│   └── styles.css           # design tokens + utility components
├── public/                   # favicon, og-image, manifest, robots.txt
└── wrangler.jsonc
```

## Design system (quick reference)

- **Brand color:** PCB-trace green, `oklch(0.62 0.15 152)` (≈ `#1ea861`).
- **Secondary accent:** copper, `oklch(0.68 0.13 55)`.
- **Typography:** Inter Variable everywhere (body, display, mono fallback).
- **Background pattern:** orthogonal grid + via-style dots at intersections (`.brand-grid`).
- **Glow:** soft green radial used in hero and final CTA (`.brand-glow`).

Full token list lives in `src/styles.css`. Light and dark modes are CSS variables on `:root` and `.dark`.

## Branding assets — TODO

`public/favicon.ico` and `public/og-image.png` are placeholder assets carried over from the scaffold. They need to be replaced with Boardwright artwork before public launch:

- **favicon.ico** — multi-resolution (16/24/32/64) ICO. PCB-trace green on dark or light.
- **og-image.png** — 1200×630, PNG, large title + subtitle + brand mark. Used for OpenGraph and Twitter card previews.

The pages and metadata otherwise render correctly with the placeholders in place.

## Waitlist

The signup form posts to a TanStack server function (`src/server/waitlist.ts`) that forwards to Buttondown. Set `BUTTONDOWN_API_KEY` in `.dev.vars` for local testing and as a wrangler secret in production:

```bash
pnpm exec wrangler secret put BUTTONDOWN_API_KEY
```

Without the key set, the form returns "Subscriptions are temporarily unavailable" — the page itself still renders.
