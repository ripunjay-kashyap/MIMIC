# MIMIC × GhostQA frontend

Next.js App Router, TypeScript and Tailwind. All application work is inside `frontend/`.

```sh
npm install
NEXT_PUBLIC_MOCK=1 npm run dev
```

Open the URL printed by Next.js. Choose **Prefill demo**, check authorization, create a run, review the six personas, and **Deploy Swarm**. The scripted stream emits at 300 ms intervals and finishes in roughly 51 seconds. Open the report, follow an evidence link, and use arrow keys in replay. Click a screenshot placeholder to open the full-size overlay; Escape closes it.

Mock run inputs and start times persist in browser localStorage. Reloading reconstructs the current states and replays available history; it does not restart the run. Mock streams contain 170 events: complete observation → decision → result → state sequences for selected milestones, followed by screenshots and outcomes. Every page transition is recorded; action counts may include intervening actions on the same page. Power completes in eight actions, impatient and cautious abandon, low-literacy backtracks then fails, explorer exhausts its budget, and chaos completes after duplicate payment submissions. The chaos replay includes a clearly labeled illustrative SVG; other null screenshot URLs show “Screenshot unavailable.” Mock interpretations are labeled “rule-based interpretation.”

For the live backend, unset `NEXT_PUBLIC_MOCK` or set it to `0` and set `NEXT_PUBLIC_API_URL` (see `.env.example` for local and deployed URLs). These are public, build-time variables; restart/rebuild after changing them. The backend must allow this frontend origin through CORS. No secrets belong in these variables.

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
FRONTEND_TEST_URL=<frontend-origin> NEXT_PUBLIC_API_URL=<configured-api-origin> ../backend/.venv/bin/python tests/verify_mock.py
```

This walks setup → review → live → reload → report → all six replays, checks evidence selection, arrow navigation and screenshot overlays, then checks each screen at 390px. Screenshots are saved to `/tmp/mimic-p10b/`. It also exercises the frontend API error and SSE behavior through browser route stubs when `NEXT_PUBLIC_MOCK=0`; see `tests/verify_network.py`.

On Linux machines that exhaust filesystem watchers, run `WATCHPACK_POLLING=true NEXT_PUBLIC_MOCK=1 npm run dev`. This changes only the dev-server watcher mechanism.

## P10b evidence and recovery

Replay contains a collapsed **What the persona saw** panel per observation, page alerts, typed input, short model names, friendly policy chips, the original model choice when overridden, and state signal chips. Observation prompts wrap and scroll. Live cards show only the most recent step's signals; a newer polled state hides stale signals. Reports group High / Medium / Low findings with counts and show supplied evidence images as 64px links into replay.

After 10 seconds without an SSE connection, live mode refreshes the run snapshot every 5 seconds while EventSource continues reconnecting. Polling stops on reconnect, completion, failure, or unmount. In-flight responses from before reconnection are ignored, as are older states in replayed SSE history. Poll failures remain visible and retry. Aggregation shows “Analyzing findings…” and completion exposes the report button.

`recent_hashes`, optional `decision.llm_action`, and optional `decision.tokens` follow the P10b handoff. At implementation time the API contract document did not yet list these fields. No backend or contract file was changed. Original model choices identify their element by `element_id`, since `llm_action` does not carry an element label.

The local browser scripts under `tests/` are ignored by the repository's existing root rule. They use the already-installed Python Playwright runtime. `verify_mock.py` covers all screens, richer evidence and mobile layout. With `NEXT_PUBLIC_MOCK=0`, use the same test URL variables for `verify_network.py` (HTTP errors, real EventSource reconnect and signed screenshot URLs) and `verify_polling.py` (controlled disconnect/reconnect timing, stale responses, terminal states and cleanup). All API requests in these two checks are intercepted; they do not contact a backend.

The P10b local-backend walkthrough was deferred under that handoff; the P12 handoff authorizes the local fake-LLM check described below.

## Journey map (P12)

Run pages offer Cards and Journey map tabs. Without a saved preference, cohort review opens Cards and deployment switches to the map. The report loads each saved persona journey and shows a static map above the metrics. Select a persona to highlight its routes or a page to inspect visits, findings and replay evidence. On mobile, scroll the diagram horizontally; the page details appear below it. Journey as text provides the same recorded routes without the diagram.

The graph uses observations and navigation results, never inferred transitions from persona snapshots. `checkGraphMatchesPersonas` checks the ordered route against normalized, collapsed `visited_paths` and reports missing transitions. Development reports warn on mismatches; production builds do not log these warnings.

```bash
npm run build && npx tsc --noEmit && npm run lint
npx tsx src/lib/journeyGraph.check.ts
NEXT_PUBLIC_MOCK=1 npm run build && NEXT_PUBLIC_MOCK=1 npx next start -p 3001
# In another terminal, from frontend/:
../backend/.venv/bin/python tests/verify_journey_map.py
```

For the authorized local fake-LLM backend, build with `NEXT_PUBLIC_API_URL=http://localhost:8000 NEXT_PUBLIC_MOCK=0`, serve on port 3001, and run the browser script with `JOURNEY_MODE=real`. It saves API journeys and screenshots in `/tmp/mimic-p12/real`. Run `npx tsx src/lib/journeyGraph.check.ts /tmp/mimic-p12/real/journeys.json` to apply the truthfulness gate to that run (nonzero exit on mismatches). No project dependencies are added; the requested `npx tsx` command uses the npm execution cache.

P12 verification (2026-10-01): mock graph has 9 nodes, 27 edges, 6 ends and no path mismatches. The actual fake-LLM run `a0644366-5286-4a8d-b0c5-c9bcbdfa4dc6` retained 395 events; its graph has 9 nodes, 33 edges and 6 ends. All six real path checks report the same mismatch: backend `visited_paths` starts after the first action and omits the initial observed Home page. The graph preserves the recorded Home observation; no route or persona snapshot is rewritten to hide this mismatch. End markers follow the last **observation**, as specified, even when a final navigation result reaches a further page.

The normal browser walkthrough on port 3001 is blocked by the backend's CORS configuration (health returns HTTP 200 without `Access-Control-Allow-Origin` for that origin). Real-data UI verification succeeded only in an isolated Chromium test instance launched with `JOURNEY_TEST_BYPASS_CORS=1 JOURNEY_MODE=real`; that flag affects only the temporary test browser. The application has no CORS bypass. Backend owner follow-up: allow `http://localhost:3001` and reconcile the initial-page omission with the truthfulness invariant. Backend files and the API contract were left untouched.
