# AGENTS.md

Agent instructions for working in this repository.

## Read before coding

- `docs/AI_EXPERT_TEAM.md` — the AI Expert Team organization: roles, ownership map, Shared Output Contract, HANDOFF format, human approval gates
- `docs/architecture.md` — component boundaries and the normalized data contract
- `docs/model-assumptions.md` — model assumptions, sign conventions, and limitations
- `ROADMAP.md` — planned phases and signature capabilities
- `README.md` — user-facing workflows

## AI Expert Team organization

Adopt the role matching the task from `docs/AI_EXPERT_TEAM.md` and answer through its Shared Output Contract. When handing work off, end with the machine-parseable `HANDOFF:` block (all fields present; `owner` is exactly one roster role).

Core invariants (non-negotiable):

- `StatefulGexConsumer` is the ONLY layer that mutates market state.
- Incremental volumes accumulate; cumulative volumes replace; position sources are never summed for the same provider contract.
- Schema-v2 options require explicit `iv` + `iv_source`; configured defaults degrade feed quality, never masquerade as provider IV.
- Futures options use Black-76; equity/index options use Black-Scholes; per-contract DTE and multiplier before strike aggregation.
- `zero_gamma` is a documented compatibility field (strike-profile flip or nearest-neutral strike), never a portfolio root.
- Predictive market validity is `unmeasured` in every report. Never claim it.
- Live adapters never write credentials to logs, snapshots, fixtures, or reports; captured payloads are sanitized before entering the repo.
- No adapter is promoted past scaffold/uncertified status without an explicit, redacted `--ack-live-network` certification run.

## Session rules

- Update `CHANGELOG.md` for user-visible changes and `ROADMAP.md` for direction changes.
- Commit early on a clean branch (`agent/<topic>`); keep the tree clean — never sweep uncommitted work into unrelated commits.
- Run `python -m pytest -q` before claiming a change works.
- `.env` is gitignored — never commit it or print secret values.

## Agency specialists

Use the agency-agents-router plugin for this project. Search the Agency roster and load/delegate only the specialists needed for the current phase; don't preload the full roster. Global specialist skills available: backend-architect, frontend-developer, devops-automator, security-appsec-engineer, git-workflow-master.
