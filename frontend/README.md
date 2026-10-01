# MIMIC × GhostQA frontend

Next.js App Router, TypeScript and Tailwind. All application work is inside `frontend/`.

```sh
npm install
NEXT_PUBLIC_MOCK=1 npm run dev
```

Open http://localhost:3000. Choose **Prefill demo**, check authorization, create a run, review the six personas, and **Deploy Swarm**. The scripted stream emits at 300 ms intervals and finishes in roughly 22 seconds. Open the report, follow an evidence link, and use arrow keys in replay. Click a screenshot placeholder to open the full-size overlay; Escape closes it.

Mock run inputs and start times persist in browser localStorage. Reloading reconstructs the current states and replays available history; it does not restart the run. Mock streams contain 73 events: selected milestones, final action results, screenshots and outcomes. Action counts include intervening actions. Power completes in eight actions, impatient and cautious abandon, low-literacy backtracks then fails, explorer exhausts its budget, and chaos completes after duplicate payment submissions. Gray screenshot placeholders never make external requests. Mock interpretations are labeled as templates.

For the live backend, unset `NEXT_PUBLIC_MOCK` or set it to `0` and set `NEXT_PUBLIC_API_URL` (defaults to http://localhost:8000). These are public, build-time variables; restart/rebuild after changing them. The backend must allow this frontend origin through CORS. No secrets belong in these variables.

```sh
npm run build
npx tsc --noEmit
npm run lint
```

The dev and build scripts explicitly use Webpack to honor the handoff's no-Turbopack requirement. System fonts avoid external font requests. No extra UI or state libraries were added.

## Contract decisions

- `?step=` in an evidence link carries an **event sequence number**, as specified by the report contract. Replay resolves it to the event's containing action step. A literal step number is accepted only if no event sequence matches.
- Typed event payloads narrow the documented `payload: any` without changing the wire format.
- A null screenshot URL displays a placeholder. Only a supplied signed URL is used as an image source; storage paths are not assumed publicly accessible.
- The five trait bars are digital literacy, patience, risk tolerance, reading tolerance and exploration. Risk sensitivity is represented by risk tolerance, per the wire type.

## Browser verification

With the mock dev server running and the repository's existing Python Playwright environment available:

```sh
../backend/.venv/bin/python tests/verify_mock.py
```

This walks setup → review → live → reload → report → all six replays, checks evidence selection, arrow navigation and screenshot overlays, then checks each screen at 390px. Screenshots are saved to `/tmp/mimic-p10/`. It also exercises the frontend API error and SSE behavior through browser route stubs when `NEXT_PUBLIC_MOCK=0`; see `tests/verify_network.py`.

On Linux machines that exhaust filesystem watchers, run `WATCHPACK_POLLING=true NEXT_PUBLIC_MOCK=1 npm run dev`. This changes only the dev-server watcher mechanism.
