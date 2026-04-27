# Troubleshooting

Real things that have bitten us. Add to this list when something else does.

---

## "KiCad is not running"

A live PCB tool (`place_footprint`, `route_trace`, `fill_zones`, `add_via`, `get_ratsnest`) returned this. Check:

1. **KiCad's IPC API is enabled.** Preferences → Plugins → check **"Enable KiCad API"**. Restart KiCad.
2. **The PCB Editor is open.** Launching the KiCad project manager alone is not enough. Double-click the `.kicad_pcb` so the PCB Editor window is up.
3. **`set_project` has been called** with absolute paths to the `.kicad_pcb` and `.kicad_sch`.
4. **Footprints exist on the board** before placing — Schematic Editor → Tools → *Update PCB from Schematic*, or run `assign_footprint` and update.

---

## Freerouting writes a 0-byte `.ses` file

KiCad's Freerouting plugin (Tools → Plugin and Content Manager) ships a Java jar that needs **Java 21 specifically**. Java 25 runs but silently produces a 0-byte session file, which KiCad then fails to import with `Expecting '(' in ... offset 1`.

### Fedora

```bash
sudo dnf install java-21-openjdk-headless
```

Launch KiCad with `JAVA_HOME` pointing at 21 so the plugin picks it up:

```bash
JAVA_HOME=/usr/lib/jvm/java-21-openjdk kicad &
```

Make it permanent:

```bash
echo 'export JAVA_HOME=/usr/lib/jvm/java-21-openjdk' >> ~/.zshrc
```

### Manual autoroute (skipping the plugin)

If the plugin is misbehaving, run Freerouting directly:

```bash
cd <project-dir>
/usr/lib/jvm/java-21-openjdk/bin/java -jar \
  ~/.local/share/kicad/9.0/3rdparty/plugins/app_freerouting_kicad-plugin/jar/freerouting-2.1.0.jar \
  -de freerouting.dsn -do freerouting.ses -mt 1 \
  -host "KiCad's Pcbnew,9.0.8-1.fc43"
```

Then re-import the session in pcbnew: **File → Import → Specctra Session**.

> **Always pass `-mt 1`.** Freerouting's multi-threaded optimizer is known to create clearance violations. Single-thread is slower but produces clean output.

---

## `search_components` returns an error

Set `MOUSER_API_KEY` in `.env` (see `.env.example`). Without it, component search returns a structured error instead of crashing — that is intentional, not a bug.

If the key is set and the call still fails, check:
- The key is current. Mouser keys expire and rate-limit aggressively.
- The free-tier rate limit is 30 requests/minute and 1000 requests/day.

---

## Tests fail on a machine without KiCad

They shouldn't — every backend has a stub fallback for testing. If they do, check that you have a recent enough KiCad-python install (`kicad-python>=0.6.0`); older versions raise import errors that bypass the fallback.

```bash
pip install -e ".[dev]"
pytest tests/
```

93 tests should pass in under a second.

---

## MCP server doesn't show up after `setup.sh`

```bash
claude mcp list
```

Should list `boardwright`. If it doesn't:

```bash
claude mcp remove boardwright    # in case a stale registration is hiding it
./setup.sh                        # re-register
```

The setup script registers at user scope (`--scope user`), so the server is available from every directory. If `/mcp` inside Claude Code doesn't show it, restart Claude Code — the MCP list is read on session start.
