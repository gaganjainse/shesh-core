# 🌊 shesh-wave — Wave Terminal as Shesh Mission Control

Wrapper for forked [`gaganjainse/waveterm`](https://github.com/gaganjainse/waveterm)
(upstream [`wavetermdev/waveterm`](https://github.com/wavetermdev/waveterm), 22k★, actively maintained).

> **Policy: integrate, never rewrite.** Wave = Electron/React 19 + Monaco + xterm-webgl frontend
> (~60k LOC TS) and a Go backend (~75k LOC: `pkg/waveobj`, `pkg/wps`, `pkg/wconfig`,
> `pkg/blockcontroller`, `pkg/wshrpc`, `pkg/remote`, `pkg/secretstore`, …).
> A Rust reimplementation was attempted in `shesha-kernel` (the `shesh-waveobj/-wps/-blockctl/…`
> crates literally mirror Wave's Go packages 1:1) and is **formally abandoned** — see judgment in
> shesh-ecosystem ADR. This repo is where Shesh meets stock Wave through *documented* surfaces only.

## Integration surfaces (no patches needed)

| Surface | File/API | Shesh use |
|---|---|---|
| Custom widgets | `~/.waveterm/config/widgets.json` | shesh-memory recall, shesh-audit trail, shesh-system GPU/power, swarm queue status as widget-bar entries |
| `wsh` CLI RPC | `wsh` (see upstream `docs/wsh-reference`) | Shesh agents create/read blocks, set workspaces, drive panes from MCP tools |
| Workspaces | `docs/workspaces` | one workspace per federation layer (brain/mind/soma) |
| Wave AI | OpenAI-compatible endpoint config | point at **OmniRoute** (`shesh-omniroute`) for free big models, or local **Ollama** (phi4-mini, qwen2.5-coder) — 6 GB VRAM budget honored |
| Secrets | Wave `secretstore` / `docs/secrets` | API keys resolved via **shesh-secrets** (`env:`/`gopass:`/`file:0600`) — never plaintext |

## Layout (planned)

- `config/widgets.json` — the Shesh widget bar
- `config/keybindings.json` — Hyprland-consistent bindings
- `wsh/` — scripts: `wave-mission-control.sh` (spawn 4-pane ops layout), swarm dashboard block
- `docs/` — integration notes, screenshots, decisions

## Fork policy

- Fork tracks upstream `main` (weekly sync via Action, TBD).
- Patches only when unavoidable, **upstream PR first**, fork is the pin + fallback.
- RAM note: Electron Wave ≈ 250–500 MB — acceptable as *mission control*; daily-driver terminals stay alacritty/foot + tmux.

## Security

Security posture and vulnerability reporting: [canonical ecosystem security
policy](https://github.com/gaganjainse/shesh-ecosystem/blob/main/SECURITY.md).
