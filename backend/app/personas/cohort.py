"""Deterministic cohort generation: the six locked templates instantiated for a run (zero LLM calls)."""

from app.config import get_settings
from app.models.schemas import PersonaState
from app.personas.templates import HARD_MAX_ACTIONS, TEMPLATES

# Funnel of our own demo site; used for deterministic progress. Other targets fall back to estimated progress.
DEMO_MILESTONES = [
    "/demo/", "/demo/plans.html", "/demo/details.html", "/demo/verify.html",
    "/demo/review.html", "/demo/pay.html", "/demo/confirmed.html",
]


def persona_id_for(persona_type: str) -> str:
    return f"{persona_type.replace('_', '-')}-01"


def generate_cohort(goal: str) -> list[PersonaState]:
    models = get_settings().groq_models or ["fake"]
    cohort = []
    for i, t in enumerate(TEMPLATES):
        cohort.append(PersonaState(
            persona_id=persona_id_for(t.persona_type),
            persona_type=t.persona_type,
            label=t.label,
            blurb=t.blurb,
            goal=goal,
            digital_literacy=t.digital_literacy,
            patience=t.patience,
            risk_tolerance=t.risk_tolerance,
            reading_tolerance=t.reading_tolerance,
            exploration=t.exploration,
            device=t.device,
            llm_model=models[(i // 2) % len(models)],  # 2 personas pinned per Groq model
            max_actions=min(t.max_actions, HARD_MAX_ACTIONS),
            max_failed_attempts=t.max_failed_attempts,
            abandon_frustration=t.abandon_frustration,
        ))
    return cohort


def milestones_for(target_url: str) -> list[str] | None:
    return DEMO_MILESTONES if "/demo/" in target_url else None
