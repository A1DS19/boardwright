# Boardwright — project plan

> Living document. Last updated: 2026-04-27.

This is the strategic source of truth for Boardwright. It is a decision journal, not a sprint backlog. Sections are added as thinking changes; older sections are left intact so the evolution of the project is visible.

If you only read one section, read **What Boardwright is** and **Validation gate (HARD)**.

---

## What Boardwright is

Boardwright is an AI co-pilot for KiCad. You describe a board in plain English ("USB-C rechargeable LED controller, 4 RGB channels, BLE control"), and Claude — running locally against your KiCad install — drives the design across all eight phases of PCB work: research, schematic capture, layout, copper pours, routing, validation, and fabrication outputs.

It is not an auto-generator. There is no black box. Boardwright is a tool surface — 41 KiCad operations exposed as MCP tools — that an AI agent uses methodically, the way a human engineer would.

The three-line pitch:

1. **Local-first.** Your KiCad, your libraries, your fab presets. Files stay on your machine.
2. **Open core.** The MCP server and tool catalog are open source. The agent is yours.
3. **Indie-maker first.** Built for the person who already opens KiCad on weekends, not for a 50-seat enterprise EE team.

---

## How the idea was chosen (and what was rejected)

We rejected three adjacent product shapes before landing here.

**Rejected: black-box PCB generator ("type a prompt, get Gerbers").** The market is full of attempts at this — JITX, Flux.ai's autonomous mode, Quilter — and the output is unreliable on anything past a reference design. Indie makers who already use KiCad don't trust it; pros don't either. The interesting problem isn't "remove the human" but "remove the toil." We're building toolwork, not magic.

**Rejected: another EDA tool from scratch.** Building a new schematic capture and layout tool in 2026 is a 5-year, $20M project with KiCad and Altium as incumbents. KiCad is open source, has a real plugin/IPC API, and has a community that already trusts it. Building *on* KiCad is a 10× cheaper path to the same outcome.

**Rejected: a closed-source SaaS PCB AI.** The ICP (indie KiCad users) is open-source-native. They will not paste their schematic into someone else's cloud. Open-core is not a marketing choice here — it is the price of entry.

**Selected: Boardwright** — a local MCP server bridging Claude Code (and eventually a desktop app) to KiCad, with an opinionated tool catalog covering the full PCB workflow. The agent runs locally, the files stay local, and the core is open.

---

## Competitive landscape

Three tiers. We compete with the third.

**Tier 1 — incumbent EDA suites with AI bolted on.** Altium Designer's Co-Pilot, Cadence Allegro X AI, Zuken CR-8000. Built for enterprise EE teams that already pay $5K–$30K/seat. Closed, proprietary file formats, no MCP, no local agent. Not our market.

**Tier 2 — VC-funded "AI PCB" startups.** Flux.ai (browser-based EDA + AI assistant), JITX (programmatic PCB), Quilter (AI autoroute). All cloud-first, all proprietary file formats, all betting that engineers will leave KiCad and Altium for them. They are well-funded and they will build features faster than we can. Our wedge against them: we don't ask anyone to leave KiCad.

**Tier 3 — what an indie maker does today.** Open KiCad, open Claude Code or ChatGPT in another window, copy-paste back and forth, run kicad-cli manually, search Mouser by hand. This is the workflow Boardwright replaces. It is also our real competitor: doing-it-yourself with a chatbot tab open. Boardwright wins if it's enough faster than that workflow that the maker stops switching tabs.

The strategic insight: as long as we win Tier 3, Tier 2 doesn't matter. Indie makers don't migrate to Flux to save 20 minutes. They stay in KiCad and they pay for tools that make KiCad better.

### (2026-04-27 revision) — the OSS field, after looking properly

The original three-tier framing still holds for the broad market, but it elided a fourth tier that turns out to matter more for our day-to-day positioning: **Tier 1.5 — open-source AI-PCB projects on GitHub.** A scan of the 11 most-starred repos in the space changes the picture in three concrete ways.

**The shape we picked is not unique.** There are now at least four MIT/Apache MCP servers for KiCad in active development. The closest neighbour — [`oaslananka/kicad-mcp-pro`](https://github.com/oaslananka/kicad-mcp-pro) (91⭐, MIT, last push today) — exposes 100+ tools across 11 categories, bundles DFM profiles for JLCPCB / PCBWay / OSH Park in its open core, and ships profile-based tool surfaces (`full`, `pcb_only`, `high_speed`) that solve the same context-bloat problem we solved with the 16-direct/25-routed split. They are ahead of us on raw tool surface and have stronger SI/PI/EMC heuristics. They are behind us on product framing — there is no Studio tier, no landing page, no indie-maker positioning. They are a tool; we intend to be a product. That distinction is real but it is not a moat against an MIT competitor of comparable quality, and we should not pretend otherwise.

[`Seeed-Studio/kicad-mcp-server`](https://github.com/Seeed-Studio/kicad-mcp-server) (33⭐) is the second-closest neighbour: 39 tools, multi-layered backend (S-expr parser + `pcbnew` + kicad-cli) much like ours, but explicitly marks PCB editing as "experimental" and has no declared license. Their distribution muscle (Seeed brand) is the threat, not their code. [`bunnyf/pcb-mcp`](https://github.com/bunnyf/pcb-mcp) (7⭐, **GPL-3.0**) ships 22 tools including a JLCPCB export bundle — license-incompatible with our open-core thesis, but a useful reference for the autoroute-as-async-task pattern.

**A different delivery shape is emerging.** [`nickleassdimebutt/kicad-claude-toolkit`](https://github.com/nickleassdimebutt/kicad-claude-toolkit) (0⭐ but pushed today) skips MCP entirely and ships **16 Claude Skills + a thin Python IPC bridge** to KiCad 10. If Claude Skills become the dominant integration surface in 2026 (plausible — they load on demand without the MCP install dance), an MCP-only stance ages badly. Our response should be additive, not defensive: ship a Skills pack on top of the MCP, not instead of it. Same backend, two surfaces.

**The "AI-native EDA" bet is real, but it's not our bet.** [`alplabai/signex`](https://github.com/alplabai/signex) (42⭐, Rust + wgpu + Iced, Apache-2.0 CE / proprietary Pro) is the most technically impressive project in the set. They are building a KiCad-format-compatible editor from scratch with Claude integration in the Pro tier. Timeline to feature parity is years; their bet is that the indie EE market will trade KiCad familiarity for a better editor. [`buildwithtrace/trace`](https://github.com/buildwithtrace/trace) (27⭐, GPL-3.0) is a softer version of the same bet — a KiCad fork with AI bolted in, cloud account required. Both validate that the AI-PCB problem is real; neither threatens our wedge directly because both ask users to leave KiCad. That's the trap we explicitly chose not to walk into (see Decisions Worth Remembering #8). Watching, not chasing.

**Cloud-only NL→PCB tools continue to be where the money goes and where indie users do not.** [`DJShreyans/ZIROEDA`](https://github.com/DJShreyans/ZIROEDA--Electronics-Prototyping-Platform) (TypeScript, Gemini, Vercel + Cloud Run) and the cloud paths inside [`assalas/pcb-designer-ai-agent`](https://github.com/assalas/pcb-designer-ai-agent) (custom non-commercial license, 8 months stale) are evidence — both for the appetite and for the pattern of these projects stalling once the demo shine wears off. Our local-first thesis is more right after seeing them, not less.

[`SuperMalinge/AI-PCB-Optimizer`](https://github.com/SuperMalinge/AI-PCB-Optimizer) and [`Twilight-Techy/pcb-defect-detector`](https://github.com/Twilight-Techy/pcb-defect-detector) are not competitors. The first is a TensorFlow layout-optimizer demo (14 months stale, no KiCad integration). The second is a manufactured-board image-QA tool — different problem, different ICP, mentioned only to keep the scan complete.

**Re-stated wedge after this scan:**

1. **MIT, not GPL, not source-available, not non-commercial.** Of the 11 repos, only 4 are permissively licensed in a way our ICP accepts. License posture is half our moat.
2. **Full 8-phase workflow with working schematic editing.** Seeed marks schematic editing experimental; signex hasn't shipped routing yet; bunnyf is PCB-only. Boardwright's S-expression editor for `.kicad_sch` is an actual differentiator.
3. **Product framing.** kicad-mcp-pro has the better tool surface; we have the better product story (Studio tier, indie ICP, landing page, validation gate). Execution speed on Phase 1 polish is what converts that asymmetry into a durable position.

**What this scan changed in the plan:** add `oaslananka/kicad-mcp-pro` to the README "Compared to" section (acknowledging it explicitly defuses HN comments before they happen); move bundled JLCPCB/PCBWay/OSH Park DFM profiles into the open-core roadmap (do not gate them behind Studio); and add a "Boardwright Skills" deliverable to Phase 2 architecture so we are not betting on MCP being the only integration surface in 18 months.

---

## ICP and distribution

**ICP:** the indie KiCad user. Hardware hackers, makers, hardware-startup founders soldering their own prototypes, consultants doing one-off boards, hobbyists shipping Tindie products. They already know KiCad. They've already shipped at least one board. They are technical, price-sensitive, and vocal.

What we are explicitly *not* targeting in v1:
- Enterprise EE teams (different tools, different budgets, different sales motion).
- People who don't already use KiCad ("AI-only EDA newcomers" is a market that does not yet exist).
- Pure schematic-only users — the value compounds with layout and fab.

**Distribution channels, ranked by expected ROI:**
1. Hacker News (Show HN) at v1 release.
2. /r/PrintedCircuitBoard, /r/AskElectronics, /r/KiCad.
3. Hackaday post (a single feature article moves more units than a month of Twitter).
4. KiCad community Discord and forum.
5. EEVblog forum.
6. A short demo video (60–90s) showing zero-to-Gerbers. This is the single highest-leverage asset we will produce.

What we will *not* do for v1: paid ads, conferences, partnerships, content marketing on a schedule. Those are post-validation moves.

---

## Positioning

**"Cursor for PCB design."** Indie makers know what Cursor is. The metaphor lands without explanation: an AI agent embedded in the tool you already use, accelerating the boring parts, leaving you in control. We will use this analogy explicitly in the landing page hero.

Rejected positioning candidates:
- *"AI co-pilot for hardware"* — too vague, sounds enterprise.
- *"Natural-language PCB factory"* — promises auto-generation we won't deliver.
- *"ChatGPT for KiCad"* — model-specific, dates badly.

**Tagline options under consideration:**
- "Describe a board. Get a board." (too magic, oversells.)
- "Your KiCad, with a brain." (cute but "brain" overused.)
- "Cursor for KiCad." (works, but legally risky and dependent on Cursor's brand staying relevant.)
- **"AI-native KiCad."** — current pick. Describes what it is, doesn't oversell, ages well.

---

## Pricing direction

**Open-core, two tiers, BYO LLM.**

**Free tier (the open core):**
- The MCP server
- All 41 tools (and a Boardwright Skills pack for Claude — see below)
- **Bundled DFM profiles for JLCPCB, PCBWay, OSH Park.** Hand-tuned DRC presets per fab house. This is table stakes after the 2026-04-27 competitive scan; gating them would lose to `kicad-mcp-pro` immediately.
- Local-first, no auth, no telemetry
- BYO Anthropic API key (or Claude Code's existing entitlement)
- pip install, brew install, source install
- Full source on GitHub, permissive license

**Paid tier ($19–29/mo, name TBD — "Boardwright Studio"?):**
- Desktop app (Tauri shell — see Architecture phase 2)
- Design history with diff view
- **One-click fab quote and order** (push Gerbers to JLCPCB / PCBWay / Aisler, get instant pricing, place the order). Distinct from DFM profiles — those check the design; this transacts.
- Premium component data (richer Mouser / Digi-Key / LCSC search, lifecycle/EOL flags, automatic alternates)
- Optional cloud sync of designs (encrypted, opt-in, not required)
- Priority support and design-review office hours

The free tier must remain genuinely useful on its own. Paid tier is for people who design boards regularly, not for hobbyists who do one a year. We expect <5% paid conversion of installs, and that is fine.

**Not on the roadmap:**
- Per-tool metering (kills the trust-building flywheel).
- Per-API-call pricing on top of the user's own LLM key (predatory).
- An enterprise tier (not until we have a hundred paying indie users; enterprise is a different company).

---

## Validation gate (HARD)

We do not write product code beyond the Phase 1 polish until this gate passes. This is the single most important section of this document.

**Pass condition:**

> Within 60 days of public release, **5 strangers** — not friends, not coworkers, not people we recruited — install Boardwright, design a real 2-or-4-layer board start-to-finish, generate fab-ready Gerbers, and complete the workflow in under 8 hours of session time, with no DM hand-holding from us. Of those 5, **3 or more say unprompted that they would pay $20/mo** for a paid tier.

**Pass conditions, restated as bullets so they can't be wiggled out of:**
- 5 ≠ 3 ≠ 4. Five.
- *Strangers.* If we recruited them, they don't count.
- *Real boards.* A copy of one of our examples doesn't count. Their own design.
- *Fab-ready.* Gerbers + drill + position + BOM. Not "a layout that looks done."
- *Under 8 hours.* If the median user takes 20 hours, the product is too hard.
- *No hand-holding.* Public docs and GitHub issues, yes. DMs, no.
- *Unprompted willingness to pay.* We do not ask "would you pay?". They volunteer it.

**Kill criteria:**

If after 60 days **fewer than 250 people install** Boardwright, or **fewer than 15 complete a design**, the indie-maker / local-first thesis is wrong. We do not push harder. We sit down, re-read this document, and decide whether the ICP, the distribution, or the product itself was the wrong call. We may pivot or we may shelve. We do not throw more code at a thesis that didn't validate.

**What we don't do until the gate passes:**
- No web app.
- No billing.
- No auth.
- No cloud.
- No Tauri desktop wrapper.
- No premium tier code.
- No paid ads.
- No Discord community.

The job, until the gate passes, is: ship a polished local tool, write good docs, post in the right places, watch installs.

---

## Architecture (planned, not yet built)

Four phases. Each gates on the previous validating.

**Phase 1 — Polish the local CLI tool. (Now → next 4–6 weeks.)**
- Rename package to `boardwright`. Publish to PyPI.
- Homebrew formula for macOS.
- GitHub Actions CI (lint, typecheck, tests on 3.10/3.11/3.12).
- Better README with a 60-second demo video.
- Landing page at boardwright.dev with waitlist.
- Open-source license clarified (currently has a LICENSE file but unverified — audit and confirm).

This is what gets shipped publicly. Phase 1 *is* the validation gate's product.

**Phase 2 — Desktop app shell + Skills pack. (Only after gate passes.)**
- Tauri 2 wrapper bundling the MCP server and an Anthropic SDK chat panel.
- Side-by-side: chat on the left, KiCad's PCB editor visible on the right (we don't render PCBs ourselves; we drive the user's KiCad).
- Onboarding flow: detect KiCad install, prompt for API key or Claude Code entitlement, walk through example project.
- This is the indie-maker unlock — the median KiCad user does not run Claude Code CLI today.
- **Boardwright Skills** — a Claude Skills pack that wraps the MCP tool catalog as discoverable workflows ("design a flashlight," "review my schematic," "generate fab outputs"). Same backend, second surface. Hedges against MCP being out-shipped by Skills in 2026; cribbed pattern from `kicad-claude-toolkit`. Ships free, in the open core.

**Phase 3 — Cloud companion. (Only after Phase 2 has paying users.)**
- Account system (only for the paid tier — free tier remains anonymous).
- Design history with diffs (designs sync optionally; Git-style branching).
- Fab integrations (one-click Gerber upload to JLCPCB / PCBWay / Aisler with quote pre-fill).
- Team workspaces (post-100-paid-users).

**Phase 4 — Headless KiCad in the cloud. (Maybe never.)**
- Only built if a real paying customer with a real budget asks for it. Speculative cloud-only design surface is exactly the trap Tier 2 competitors are stuck in.

---

## Current stack (what exists today)

This is the tool as of 2026-04-27. Everything below is shipped and working.

**Python MCP server, ~5,900 LOC.**
- `boardwright/dispatcher.py` — central tool registry; merges 41 schemas across 8 domain modules; handles scalar coercion for harnesses that serialize numbers as strings.
- `boardwright/router.py` — tool taxonomy. 16 "direct" tools visible in `list_tools()` for the common path; 25 "routed" tools hidden behind 5 meta-tools (`project_admin`, `research`, `schematic_advanced`, `pcb_layout_advanced`, `routing_advanced`) to keep Claude's tool-list context clean. Both surfaces reachable via `execute_tool`.
- `boardwright/backends.py` — hybrid runtime. `kipy` IPC for live PCB ops, `kicad-cli` subprocess for ERC/DRC and fab outputs, direct S-expression file editing for schematics, stub fallbacks for testing without KiCad.
- `boardwright/state.py` — single shared project state dict.
- `boardwright/schematic_io.py` — S-expression parser/serializer for `.kicad_sch`.
- `boardwright/sexpr.py` — minimal S-expression tokenizer.
- `boardwright/tools/` — eight domain modules: `project`, `filesystem`, `research`, `schematic`, `pcb_layout`, `routing`, `pcb_checks`, `fabrication`.

**External integrations.**
- KiCad 9.0+ via `kicad-python` IPC and `kicad-cli`.
- Mouser API for component search and stock/price (requires `MOUSER_API_KEY`).
- `pdfplumber` for datasheet text extraction.

**Testing.**
- Six pytest modules. Fake backends so CI runs without KiCad installed.

**Examples.**
- `examples/atmega-console` — ATmega328 console board.
- `examples/flashlight` — single-LED driver.
- `examples/temperature-reader` — LoRaWAN temp/humidity logger with autoroute.

**What is missing today** (the Phase 1 polish list):
- Not on PyPI.
- No CI workflow.
- No landing page.
- README still uses old "kicad-ai-project-creator" name in places.
- License file present but not audited.
- No structured logging.

---

## Operational runbook

Local development:

```bash
# install (editable)
pip install -e .

# run tests
pytest tests/

# run the MCP server directly (Claude Code wires this up automatically)
python -m boardwright.server

# register with Claude Code globally
claude mcp add --scope user boardwright python -m boardwright.server
```

Web (landing page):

```bash
cd web/
pnpm install
pnpm dev          # localhost:3000
pnpm build
pnpm exec biome check src/
```

Required environment variables (none for the MCP server core; component search optional):

- `MOUSER_API_KEY` — optional. Without it, `search_components` returns a graceful error instead of crashing.

Required external tools for full functionality:
- KiCad 9.0+ with **API enabled** (Preferences → Plugins → Enable KiCad API), restart required.
- For autorouting: Java 21 specifically. Java 25 silently writes a 0-byte session file. See troubleshooting.

---

## Next milestones (in order)

This is the only ordered list in this document. Each item ships before the next starts.

1. **`docs/PROJECT.md`** — this file. ✓
2. **Rename to Boardwright.** Python package, MCP server name, pyproject metadata, setup script, README. ✓
3. **GitHub Actions CI.** pytest on 3.10/3.11/3.12, ruff lint, typecheck. ✓
4. **README rewrite.** Lead with positioning, install via pip, KiCad prereqs, 60-second demo, then tool reference. Move Fedora/Java footnote to `docs/troubleshooting.md`. ✓
5. **Landing page at `web/`.** TanStack Start + Tailwind 4 + Cloudflare Workers, mirroring klickbrain's stack with PCB-trace green replacing honey-amber. Hero, Benefits, How-It-Works, Final-CTA. Buttondown waitlist. ✓
6. **DFM profiles for JLCPCB / PCBWay / OSH Park** — added to `boardwright/tools/pcb_checks.py` as `dfm_check_jlcpcb`, `dfm_check_pcbway`, `dfm_check_oshpark`. Hand-tuned DRC presets per fab house, in the free tier. Closes the gap with `kicad-mcp-pro` on the table-stakes axis.
7. **README "Compared to" section.** A short, fair-minded comparison against the four direct OSS competitors (`kicad-mcp-pro`, `Seeed-Studio/kicad-mcp-server`, `kicad-claude-toolkit`, `bunnyf/pcb-mcp`). Acknowledging the field defuses HN comments before they happen.
8. **PyPI release.** `pip install boardwright`. Pin a 0.3.0 version.
9. **Branding assets.** Replace `web/public/favicon.ico` and `web/public/og-image.png` with Boardwright artwork. Logo mark in PCB-trace green. OG image at 1200×630.
10. **60-second demo video.** Screen recording: install → describe board → Gerbers. The single artifact that drives the most traffic.
11. **Public launch.** Show HN, Hackaday tip, /r/PrintedCircuitBoard.

After 11 ships, we sit down and watch the validation gate. We do not start Phase 2 until the gate passes.

---

## Decisions worth remembering

Non-obvious choices that future-us should not re-litigate without strong reason.

1. **Tool taxonomy: 16 direct + 25 routed.** Putting all 41 tools in `list_tools()` blew up Claude's context window and degraded its tool-selection quality. The taxonomy was measured, not guessed.
2. **S-expression file editing for schematics.** kipy doesn't expose schematic ops the way it does PCB ops. Direct file editing is the only option until KiCad ships a richer IPC API. We accept the file-format coupling.
3. **Stub fallbacks.** Every backend has a stub mode so tests run without KiCad. This was added after CI broke twice on machines without KiCad installed.
4. **No autoroute lock-in.** We ship hooks for Freerouting but don't bundle it. Freerouting requires Java 21 specifically and that complexity belongs in user docs, not in our binary.
5. **`-mt 1` for Freerouting.** Multi-threaded optimizer creates clearance violations. Single-thread is slower but produces clean output.
6. **No telemetry in the free tier.** Indie makers will refuse it. The cost of "we don't know how people use the tool" is worth less than the cost of losing trust.
7. **Open core, not source-available.** A source-available license (BSL, FSL, etc.) reads as "trying to prevent forks" and the indie ICP punishes it. We accept that someone may fork the open core. Our moat is execution speed and the paid tier, not license hostility.
8. **Local-first, KiCad-bound.** We are explicitly not building a cloud EDA tool. Tier 2 competitors are; that is their bet. We are betting that "stay in KiCad" wins the indie market.
9. **Naming: Boardwright.** Final. "Wright" = builder, "Board" = PCB. Pronounceable, ownable, evokes craftsmanship over magic. Working title was "kicad-ai-project-creator," which described nothing.
10. **MCP and Skills, both surfaces.** Decided 2026-04-27 after seeing `kicad-claude-toolkit` ship Claude Skills + IPC bridge instead of MCP. The integration shape that wins 2026 is uncertain — Skills could displace MCP for Claude users, or MCP could remain the cross-agent standard. Ship both on the same backend rather than betting on one. Marginal cost is small; insurance value is large.
11. **DFM profiles in the free tier, not Studio.** Decided 2026-04-27. `kicad-mcp-pro` ships JLCPCB / PCBWay / OSH Park DRC presets in MIT core; gating ours behind paid would be an immediate loss. Studio's fab-tier value is *quote and order*, not *check the design*.

---

## What this doc is not

- **Not a sprint backlog.** Issues, milestones, and short-term work belong in GitHub Issues. This document is for *why*, not for *what next week*.
- **Not a marketing brief.** Landing-page copy is in `web/`. Tagline experiments live there.
- **Not a spec.** Tool behavior is documented in code, in tests, and in `kicad_agent_system_prompt.txt`.
- **Not a license.** See `LICENSE`.
- **Not a changelog.** Use git log.

This document is read top-to-bottom by future-us and by collaborators trying to understand the bet. When the bet changes, we add a dated section. We do not rewrite the past.
