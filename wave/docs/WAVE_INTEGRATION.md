# Shesh × Wave Terminal — integration strategy

Status: **adopted policy** (2026-08-12). Supersedes the abandoned Rust re-implementation
in `shesh-kernel` (the `shesh-waveobj` / `-wps` / `-blockctl` crates, a 1:1 mirror of
Wave's Go packages — see the ecosystem ADR-0018 for the adopt-vs-build judgment).

## 1. What Wave already gives us (verified against the fork, release lineage v0.11+)

| Concern | Wave surface we use | Why not build |
|---|---|---|
| GPU terminal | `xterm.js` + webgl frontend, Monaco editor embedded | ~60k LOC TS rewrite |
| Block model | `pkg/blockcontroller`, `pkg/waveobj` (Go) | 1:1 crates abandoned |
| RPC / scripting | `wsh` CLI + `wshrpc` (block-aware shell commands) | documented, stable |
| Remote hosts | `pkg/remote` (SSH, already SSH-agent aware) | our own agent work is *complementary*, not competing |
| Secrets | `pkg/secretstore` (OS keychain-backed) | do not re-implement crypto |
| Config | `pkg/wconfig` → `~/.waveterm/config/*.json` (JSON, documented keys) | this is where this repo lives |

Shesh therefore contributes **downstream configuration and orchestration**, never a forked
frontend. The fork exists only to pin a release we have audited.

## 2. Integration surfaces (all stock, no patches)

```
config/termthemes/shesh-dark.json   →  ~/.waveterm/config/termthemes/   (theme, drop-in)
config/widgets.shesh.json           →  merged into widgets.json          (dashboard blocks)
settings.json  ai:* keys            →  AI endpoint = local chain         (OmniRoute → Ollama → vLLM)
```

Installed by `scripts/install-shesh-wave.sh` (idempotent, backs up, never clobbers).
The AI chain uses Wave's **OpenAI-compatible endpoint keys** — OmniRoute exposes exactly
that API shape on `localhost:20128`, so Wave's AI blocks ride the same gateway as every
other Shesh component. One key store, one rate-limit policy, one audit log.

## 3. Idea — tmux as the terminal backend *inside* Wave blocks

**Problem Wave has and we can feel daily:** close a tab or the app, and the shell session
(and scrollback, job state, `python -i`, `apt` progress) dies with it. Wave 0.11 added
term-restore on restart, but that replays scrollback into a *fresh* shell — the process
tree is gone.

**The idea:** for persistent blocks, have the block spawn its shell *inside* a tmux
session instead of a bare pty:

```bash
# what the block would exec instead of /bin/bash directly:
tmux new-session -A -s "wave-${WAVE_BLOCKID:-main}"
```

- `-A` = attach if the session exists, create if not — exactly the semantics we want.
- Surviving app restarts: the tmux server outlives the Electron process; on restart the
  block re-attaches and *the real process tree* (not just scrollback) is still there.
- Composition with SSH is natural: run the same command through `wsh`'s remote layer so
  the remote side also runs tmux (nested `tmux -CC` is unnecessary; plain nested tmux
  works with `TERM` passthrough).
- Cost: one extra daemon process per host; scrollback capture then belongs to tmux
  (`capture-pane`), which Wave's history feature would need to read instead of its own
  ring buffer — **that is the only real Wave patch required**, and it is optional
  (fall back to Wave's own capture for non-persistent blocks).

**Status: not patched in.** We run stock Wave; this requires a waveobj/blockcontroller
hook (`TermOpts.UseShellInjection`-adjacent) to substitute the spawn command per block.
Tracked as an ecosystem roadmap item; the config surfaces in this repo work with or
without it. If upstream ever ships "tmux integration" (it is on their public roadmap
discussions), we adopt theirs and delete this section.

## 4. Watch item — libghostty for a future native Shesh shell

Ghostty (Mitchell Hashimoto) extracted its terminal core into **libghostty** (C ABI, Zig
build), explicitly so other apps can embed a first-class terminal without Electron.
If Shesh ever ships a *native* shell app (alongside Wave, not replacing it — e.g. a
lightweight boot/recovery console where Electron is too heavy, or the SheshAOS kiosk):

- renderer: libghostty's Metal/Vulkan paths (GPU, ligatures, kitty graphics)
- input: its key handling already matches what power users expect
- embedding libghostty is a self-contained native step: C ABI + its own Zig build
  system, living in its own crate/app — it would NOT reintroduce Zig into the
  SheshAOS main build (ADR-0001: no Zig/FFI in the main build; the old
  zig-backed `shesh-terminal` crate was removed in the 2026-08-12 excision).

**Status: watch-only.** Ghostty is pre-1.0 and libghostty's C ABI is not yet stable.
Decision gate: when libghostty ships a tagged release with ABI guarantees, prototype a
`shesh-console` embedding it for the recovery/kiosk case. Until then Wave is the shell
frontend — this is the *one* place we deliberately keep an eye on upstream-in-steal
instead of adopting today.

## 5. Hard rules

1. **Never** patch `waveterm` frontend/backend code in the fork; only pin releases and
   (rarely, with an ADR) cherry-pick security fixes.
2. Everything we ship must work against **stock** Wave installed at `~/.waveterm`.
3. Keys live in OmniRoute's secret store or Wave's own `secretstore` — never in
   `settings.json` (the installer writes an empty `ai:apitoken` deliberately).
4. If upstream Wave adds a feature natively (tmux backend, better widgets), we adopt and
   remove ours. Adopt > maintain.
