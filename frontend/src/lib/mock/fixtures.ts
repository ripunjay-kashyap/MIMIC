import { API_URL } from "../config";
import type { CreateRun, EventPayloads, EventType, Finding, Metrics, PersonaState, RunEvent, RunSummary, TaskStatus } from "../types";

const profiles: Array<[PersonaState["persona_type"], string, string, number[], number, number]> = [
  ["impatient", "Impatient User", "Looks for the quickest route and loses patience with delays.", [.7, .2, .6, .2, .2], 8, .55],
  ["low_literacy", "Low-Digital-Literacy User", "Needs clear labels, familiar language and explicit next steps.", [.25, .7, .35, .6, .25], 12, .8],
  ["power", "Power User", "Takes the shortest route and notices unnecessary steps.", [.95, .7, .75, .4, .2], 12, .9],
  ["cautious", "Cautious User", "Checks commitments, consent and payment details before acting.", [.65, .8, .15, .9, .4], 12, .7],
  ["explorer", "Exploratory User", "Compares options and follows secondary paths.", [.8, .8, .6, .8, .95], 10, .9],
  ["chaos", "Chaos / Edge-Case User", "Tries unusual inputs, retries and repeated clicks.", [.85, .6, .9, .3, .85], 12, .95],
];
export function initialRun(id: string, input: CreateRun, createdAt: string): RunSummary {
  return { run_id: id, target_url: input.target_url, goal: input.goal, created_at: createdAt, status: "cohort_ready", error: null, metrics: null,
    personas: profiles.map(([type, label, blurb, traits, max, threshold], index) => ({
      persona_id: `${type}-01`, persona_type: type, label, blurb, goal: input.goal,
      digital_literacy: traits[0], patience: traits[1], risk_tolerance: traits[2], reading_tolerance: traits[3], exploration: traits[4],
      language: "English", device: index === 1 ? "mobile" : "desktop", llm_model: "fake",
      max_actions: max, max_failed_attempts: 2, abandon_frustration: threshold, action_count: 0, failed_attempts: 0, backtracks: 0,
      current_frustration: 0, progress: 0, progress_estimated: true, visited_paths: [], recent_hashes: [], task_status: "pending", termination_reason: null,
    })),
  };
}
type Moment = [number, string, string, string, number, number];
// Scripted milestones: counts include actions between the selected observations.
const scripts: Record<PersonaState["persona_type"], Moment[]> = {
  impatient: [[1,"plans.html","Get a Quote","I want to get this done quickly.",.05,.15], [3,"verify.html","Send OTP","I sent the code request. Nothing has changed.",.35,.5], [4,"verify.html","Send OTP","Still no response. I am leaving.",.65,.5]],
  low_literacy: [[1,"learn.html","Get Started","This sounds like the place to begin.",.1,.05], [2,"index.html","Browser Back","There is no next button. I need to go back.",.3,.05], [5,"details.html","Continue","Invalid input does not tell me what to change.",.7,.35]],
  power: [[1,"plans.html","Get a Quote","This is the direct path to a policy.",.02,.12], [2,"details.html","Select Basic","The basic plan fits this task.",.03,.24], [3,"verify.html","Application details","The required details are ready.",.04,.38], [4,"verify.html","Send OTP","Request the verification code.",.12,.48], [5,"review.html","Verify","The code is correct; continue.",.13,.65], [6,"pay.html","Confirm & Continue","These details were already entered.",.2,.8], [7,"confirmed.html","Proceed","Submit the application payment.",.2,.95], [8,"confirmed.html","Policy issued","The confirmation marker is visible.",.2,1]],
  cautious: [[2,"details.html","Select Basic","I will check the information before committing.",.1,.2], [6,"pay.html","Confirm & Continue","What are the applicable charges?",.45,.8], [7,"pay.html","Auto-renew and share my data with partners","Sharing is already selected. I cannot make an informed choice.",.75,.8]],
  explorer: [[1,"explore.html","Explore Plans","I want to compare the available plans.",.1,.1], [5,"explore.html","Talk to an advisor","The advisors are busy and I cannot select a plan here.",.4,.15], [10,"plans.html","Plans","I have used my action budget comparing routes.",.6,.25]],
  chaos: [[2,"details.html","Mobile number","I will try a five-digit number.",.05,.3], [3,"verify.html","Continue","A five-digit mobile number was accepted.",.1,.4], [8,"pay.html","Proceed twice","I will click Proceed twice before it redirects.",.2,.8], [9,"confirmed.html","Policy issued","Two successful payment records appeared.",.25,1]],
};
const outcomes: Record<PersonaState["persona_type"], [TaskStatus, string]> = {
  impatient: ["abandoned", "No visible feedback after requesting OTP."],
  low_literacy: ["failed", "Could not identify the field causing Invalid input after backtracking."],
  power: ["success", "Policy confirmation reached in 8 actions."],
  cautious: ["abandoned", "Unexplained charges and pre-selected data sharing."],
  explorer: ["budget_exhausted", "Reached the 10-action limit while comparing paths."],
  chaos: ["success", "Policy issued; duplicate payment records observed."],
};
const sourcePages: Record<string, string> = {
  "Get a Quote": "index.html",
  "Get Started": "index.html",
  "Explore Plans": "index.html",
  "Select Basic": "plans.html",
  "Application details": "details.html",
  "Mobile number": "details.html",
  "Continue": "details.html",
  "Send OTP": "verify.html",
  "Verify": "verify.html",
  "Confirm & Continue": "review.html",
  "Proceed": "pay.html",
  "Proceed twice": "pay.html",
  "Policy issued": "confirmed.html",
  "Browser Back": "learn.html",
  "Talk to an advisor": "explore.html",
  "Plans": "index.html",
  "Auto-renew and share my data with partners": "pay.html",
};

function observation(file: string, label: string, persona: PersonaState): EventPayloads["observation"] {
  const path = `/demo/${file}`;
  const alerts = persona.persona_type === "low_literacy" && file === "details.html" ? ["Invalid input"] : [];
  const content: Record<string, string> = {
    "index.html": "Find health insurance for your family. Get Started · Get a Quote · Explore Plans",
    "plans.html": "Compare Basic and Plus. Co-pay, deductible and sub-limit apply.",
    "learn.html": "Learn about health insurance. An introduction to premiums, coverage and policy terms.",
    "explore.html": "Compare our plans. All advisors are busy. Please try later.",
    "details.html": "Your application. Full name, mobile number, date of birth. Continue",
    "verify.html": "ONE MORE DETAIL Verify your mobile Send OTP. Demo code: 123456",
    "review.html": "Confirm your application details before continuing to payment.",
    "pay.html": "Total payable ₹4,812 including applicable charges*. Proceed",
    "confirmed.html": "Policy issued SS-2026-000123. Payment received ₹4,812" +
      (persona.persona_type === "chaos" ? " · Payment received ₹4,812" : ""),
  };
  const title = file === "verify.html" ? "Verify your mobile" : file.replace(".html", "");
  const noElements = file === "learn.html";
  const element = label === "Mobile number" || label === "Application details"
    ? `[1] input[text] "${label}" value=""`
    : `[1] button "${label}"`;
  const lines = [
    `URL: ${path}`,
    `TITLE: ${title} | SurakshaSetu`,
    `HEADINGS: ${title}`,
    ...(alerts.length ? [`MESSAGES ON PAGE: ${alerts.join(" | ")}`] : []),
    `PAGE TEXT: ${content[file] || title}`,
    "ELEMENTS:",
    ...(noElements ? ["(no interactive elements)"] : ['[0] link "SurakshaSetu home"', element]),
    ...(file === "pay.html" ? ['[2] checkbox "Auto-renew and share my data with partners" checked'] : []),
  ];
  return {
    title, path, alerts,
    element_count: noElements ? 0 : file === "pay.html" ? 3 : 2,
    summary: `${path} · ${title}`,
    page_hash: `mock-${file}-${alerts.join("-") || "ready"}`,
    prompt: lines.join("\n"),
  };
}

export function fixtureEvents(run: RunSummary): RunEvent[] {
  const events: RunEvent[] = [];
  const emit = <K extends EventType>(
    type: K,
    payload: EventPayloads[K],
    persona: PersonaState | null = null,
    step: number | null = null,
    url: string | null = null,
  ) => {
    events.push({
      run_id: run.run_id,
      seq: events.length + 1,
      persona_id: persona?.persona_id ?? null,
      ts: new Date(Date.parse(run.created_at) + (events.length + 1) * 300).toISOString(),
      type, step, url, payload,
    } as RunEvent);
  };
  emit("run_status", { status: "running" });
  const states = structuredClone(run.personas);
  for (const persona of states) {
    persona.task_status = "active";
    emit("persona_started", { persona: structuredClone(persona) }, persona);
  }
  // These are selected milestones, each with a complete ordered step payload.
  for (let round = 0; round < 8; round++) {
    for (const persona of states) {
      const script = scripts[persona.persona_type];
      const moment = script[round];
      if (!moment) continue;
      const [step, file, label, thought, frustration, progress] = moment;
      const url = `${API_URL}/demo/${file}`;
      const sourceFile = sourcePages[label] || file;
      const before = `${API_URL}/demo/${sourceFile}`;
      const observed = observation(sourceFile, label, persona);
      emit("observation", observed, persona, step, before);
      const action = label === "Browser Back" ? "back"
        : label === "Application details" || label === "Mobile number" ? "type"
          : label === "Policy issued" ? "done" : "click";
      const choice: EventPayloads["decision"]["action"] = {
        action,
        element_id: action === "back" || action === "done" ? null : 1,
        text: label === "Mobile number" ? "12345" : action === "type" ? "Test Applicant" : null,
        thought,
        confidence: persona.persona_type === "low_literacy" ? .45 : .9,
        expects: "A clear next step or confirmation.",
      };
      const tags = [];
      if (label === "Mobile number") tags.push("edge_case_input");
      if (label === "Proceed twice") tags.push("double_click");
      if (action === "back") tags.push("forced_back");
      if (action === "done") tags.push("deterministic");
      const fallback = persona.persona_type === "power" && step === 5;
      if (fallback) tags.push("fallback_model");
      emit("decision", {
        action: choice,
        model: fallback ? "gemini-3.5-flash-lite" : "fake",
        element_label: action === "back" || action === "done" ? null : label,
        policy_tags: tags,
        llm_action: label === "Mobile number" ? { ...choice, text: "9876543210" } : null,
        tokens: { prompt: action === "done" ? 0 : 420, completion: action === "done" ? 0 : 65 },
      }, persona, step, before);
      const last = round === script.length - 1;
      const ok = !(last && persona.persona_type === "low_literacy");
      const changed = before !== url || action === "type" || label === "Proceed twice";
      emit("action_result", {
        result: {
          ok, error: ok ? null : "Invalid input", url_before: before, url_after: url,
          navigated: before !== url, page_changed: changed, dialogs: [], duration_ms: 180,
        },
      }, persona, step, url);
      const deltas = {
        current_frustration: frustration - persona.current_frustration,
        progress: progress - persona.progress,
        action_count: step - persona.action_count,
      };
      const signals = [];
      if (action === "back") signals.push("backtrack");
      if (!changed && action === "click") signals.push("no_page_change");
      if (!ok) signals.push("action_failed", "error_message");
      if (file === "pay.html") signals.push("risk_page");
      if (deltas.progress > 0) signals.push("progress");
      if (label === "Verify") signals.push("delayed_change");
      if (persona.persona_type === "impatient" && last) signals.push("stuck");
      persona.action_count = step;
      persona.current_frustration = frustration;
      persona.progress = progress;
      persona.visited_paths.push(url);
      persona.recent_hashes = [...persona.recent_hashes, observed.page_hash].slice(-3);
      if (action === "back") persona.backtracks++;
      if (!ok) persona.failed_attempts = 2;
      emit("state_update", { state: structuredClone(persona), deltas, signals }, persona, step, url);
      if (last) {
        emit("screenshot", {
          reason: "Illustrative mock evidence (not a browser capture)",
          path: `mock/${persona.persona_id}.svg`,
          url: persona.persona_type === "chaos" ? "/mock-evidence.svg" : null,
        }, persona, step, url);
        const [status, reason] = outcomes[persona.persona_type];
        persona.task_status = status;
        persona.termination_reason = reason;
        emit("persona_finished", { status, reason, state: structuredClone(persona) }, persona, step, url);
      }
    }
  }
  emit("run_status", { status: "aggregating" });
  emit("run_status", { status: "completed" });
  return events;
}
export function snapshot(run: RunSummary, events: RunEvent[]): RunSummary {
  const result = structuredClone(run);
  for (const event of events) {
    if (event.type === "run_status") result.status = event.payload.status;
    const state = event.type === "persona_started" ? event.payload.persona : event.type === "state_update" || event.type === "persona_finished" ? event.payload.state : null;
    if (state) result.personas = result.personas.map(p => p.persona_id === state.persona_id ? structuredClone(state) : p);
  }
  if (result.status === "completed") result.metrics = fixtureMetrics(result.personas);
  return result;
}
export function fixtureMetrics(personas: PersonaState[]): Metrics {
  const count = (status: TaskStatus) => personas.filter(p => p.task_status === status).length;
  const actions = personas.map(p => p.action_count).sort((a,b) => a-b);
  return { completion_rate: count("success") / 6, abandonment_rate: count("abandoned") / 6,
    success_count: count("success"), failure_count: count("failed"), abandoned_count: count("abandoned"), budget_exhausted_count: count("budget_exhausted"), blocked_count: 0, error_count: 0,
    average_actions: actions.reduce((a,b) => a+b,0) / 6, median_actions: (actions[2] + actions[3]) / 2,
    unique_paths: 6, repeated_friction_points: 2, backtracks_total: personas.reduce((n,p) => n+p.backtracks,0),
    frustration_at_termination: Object.fromEntries(personas.map(p => [p.persona_id,p.current_frustration])),
  };
}
export function fixtureFindings(runId: string, events: RunEvent[]): Finding[] {
  const definitions: Array<[string, Finding["severity"], string, string[], string, string, string]> = [
    ["delayed_feedback", "high", "verify.html", ["impatient-01", "power-01"], "The impatient user abandoned on verification after repeating Send OTP; the power user also encountered this delay.", "Delayed feedback may make the verification request appear unresponsive.", "Show immediate acknowledgement and a clear delivery state."],
    ["risk_hesitation", "high", "pay.html", ["cautious-01", "power-01"], "The cautious user stopped at payment after questioning charges and pre-selected sharing; the power user continued.", "Unclear costs and bundled consent may reduce confidence at payment.", "Explain the full payable amount and make each consent choice explicit."],
    ["duplicate_submit_effect", "medium", "confirmed.html", ["chaos-01"], "The chaos user clicked Proceed twice and observed two successful payment records.", "The payment action may permit duplicate submissions during the redirect delay.", "Make submission idempotent and show a pending state."],
    ["backtrack", "low", "learn.html", ["low_literacy-01"], "The low-digital-literacy user returned from the learning article using browser Back.", "The introductory article may interrupt the purchase journey.", "Provide a clear next step from the article to plan selection."],
  ];
  return definitions.map(([category,severity,file,people,observed,interpretation,investigation], index) => ({
    id: `finding-${index+1}`, run_id: runId, category, severity, page: `/demo/${file}`, personas: people, observed, interpretation,
    suggested_investigation: investigation, source: "template",
    evidence: people.map(persona_id => {
      const event = events.find(e => e.persona_id === persona_id && e.type === "decision" && e.url?.endsWith(file))!;
      const shot = events.find(e => e.type === "screenshot" && e.persona_id === persona_id && e.step === event.step);
      return {
        persona_id,
        seq: event.seq,
        screenshot_path: shot?.type === "screenshot" ? shot.payload.path : null,
        screenshot_url: shot?.type === "screenshot" ? shot.payload.url : null,
      };
    }),
  }));
}
