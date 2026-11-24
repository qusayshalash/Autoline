# Working on AutoLine

**Read [`docs/PROJECT.md`](docs/PROJECT.md) first.** It holds what this project is, where
it stands, which features are built but locked and why, where the data lives, the owner's
decisions that are not to be reopened, and what comes next. The filter-fitment data has
its own notes in [`docs/fitment.md`](docs/fitment.md). How the code is built and tested:
[`README.md`](README.md).

The rules that matter most:

- **Talk to the owner, Qusay, in Arabic** (Levantine), concise and structured, and offer
  options early rather than guessing.
- **Commit, push or deploy only when asked.** Work has been pushed straight to `main`.
- **Never commit the local unlocks** in `frontend/src/App.tsx` and
  `frontend/src/features.ts` marked `LOCAL PREVIEW ONLY - do not commit`. The catalog and
  the record card stay locked until the owner opens them - together.
- **Never commit the fitment database** or any catalogue data; it lives in
  `<DATA_DIR>/reference/`.
- **Never guess a filter part number.** A wrong filter damages an engine; what has no
  source is shown as not available.
- **Measure on the real registry before making a rule about it**, and state the figures.
- **The server is shared with another system, ChequeFlow.** Do not touch its containers,
  firewall or `.env` files, and never prune Docker on that machine.
- **No secrets in the repository** - server address, keys, passwords.
- Before pushing: `cd backend && pytest`, then `npx tsc -b` and `npx oxlint src` in
  `frontend`. Backend tests also check rules in the frontend code.
