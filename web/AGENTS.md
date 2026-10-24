# web (workspace front-end package)

The Node project for the web workspace. The React source lives in `src/`.

## Setup

- Use Node 22.12 or later (`engines` in `package.json`).
- Run `npm ci` in a fresh worktree. `node_modules/` is gitignored, so a new worktree has none.

## Gates

Run these four in `web/` before you commit. The CI `frontend` job and `scripts/local_ci.sh` run the same steps.

1. `npm run lint` (ESLint).
2. `npm run typecheck` (`tsc --noEmit`).
3. `npm test` (Vitest, `src/**/*.test.{ts,tsx}`).
4. `npm run build`.

## Build output

- `npm run build` empties and fills `src/omrs/transports/api/static/` at the repository root. That folder is gitignored.
- The Python wheel ships the folder through the Hatch `artifacts` entry in `pyproject.toml`. `scripts/check_web_wheel.py` fails a release wheel without it.
- `npm run dev` sends `/v1` requests to `http://127.0.0.1:8765`. Set `OMRS_API_URL` to use another server.

## Rules

1. Before UI work, read `DESIGN.md` and load the `omrs-design` skill.
2. There is no Prettier config. Do not run Prettier, because it rewrites whole files. Match the existing style by hand.
3. Read `src/AGENTS.md` before you edit in `src/`.

## Links

- [Root AGENTS.md](../AGENTS.md)
- [Front-end source guide](src/AGENTS.md)
- [Design system](DESIGN.md)
- [omrs-design skill](../.agents/skills/omrs-design/SKILL.md)
