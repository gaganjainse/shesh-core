# shesh-core

**Shesh Brain/Soma core** — the consolidated home of the small `shesh-*` MCP
servers and tools that used to live in 16 separate repos.

Consolidation rationale (2026-08-13 fleet audit): federation (ADR D3) is right
for independently versioned services, but a 150-line module is not a service —
it's a file. 16 repos each re-carried their own `pyproject.toml` / CI /
SECURITY.md / dependabot with subtle drift (different ruff configs, missing
console scripts, cross-repo deps that can't resolve from PyPI). One repo fixes
all of that: one pyproject, one ruff config, one CI, one license, and relative
imports that always resolve.

## Modules

| Package | Layer | MCP console script |
|---|---|---|
| `shesh_audit` | Brain | `shesh-audit-mcp` |
| `shesh_secrets` | Brain | `shesh-secrets-mcp` |
| `shesh_brain` | Brain | `shesh-brain-mcp` |
| `shesh_mind` | Mind | `shesh-mind-mcp` |
| `shesh_acp` | Brain | `shesh-acp` (Agent Client Protocol) |
| `shesh_skills` | Mind | `shesh-skills-mcp` |
| `shesh_shell` | Soma | `shesh-shell-mcp` |
| `shesh_system` | Soma | `shesh-system-mcp` |
| `shesh_files` | Soma | — (library + classifier CLI) |
| `shesh_media` | Soma | `shesh-media-mcp` |
| `shesh_messaging` | Soma | `shesh-messaging-mcp` |
| `shesh_calendar` | Soma | `shesh-calendar-mcp` |
| `shesh_backup` | Soma | `shesh-backup-mcp` |
| `shesh_containers` | Soma | `shesh-containers-mcp` |
| `shesh_ebpf` | Soma | `shesh-ebpf-mcp` |
| `shesh_mcp_bundle` | Soma | `shesh-mcp-bundle-mcp` |
| `wave/` | Desktop | Wave terminal widgets + theme config |

The console-script **command names are unchanged** from the old repos, so every
existing MCP client config (`~/.config/shesh/mcp/*.json`) keeps working.

## Install

```bash
uv pip install -e .            # installs all packages + console scripts
pytest -q                      # full test suite
ruff check src/ tests/
```

Kept as separate repos (real, independently versioned services): `shesh-memory`,
`shesh-orchestrator`, `shesh-harness`, `shesh-phone`, `shesh-omniroute` — they
depend on `shesh-core>=0.1`.

See the ecosystem manifest (`manifests/components.toml`) and
`docs/architecture/REPO_TOPOLOGY.md` for the full picture.
