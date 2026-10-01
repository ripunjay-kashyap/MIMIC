"""The six locked MIMIC personas (spec §4). Numeric traits are code-enforced; prose is for the LLM prompt."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaTemplate:
    persona_type: str
    label: str
    blurb: str
    behavior: str  # second-person instructions rendered into the system prompt
    digital_literacy: float
    patience: float
    risk_tolerance: float
    reading_tolerance: float
    exploration: float
    max_actions: int
    max_failed_attempts: int
    abandon_frustration: float
    device: str
    test_identity: dict


HARD_MAX_ACTIONS = 15

TEMPLATES: list[PersonaTemplate] = [
    PersonaTemplate(
        persona_type="impatient", label="Impatient User",
        blurb="Wants it done fast; clicks the most obvious button and quits when blocked.",
        behavior=(
            "You are in a hurry and on your phone. You skim, never read paragraphs, and click the most obvious-looking "
            "button. You hate waiting: if something doesn't respond immediately you assume it's broken. "
            "You give up quickly when things go wrong."
        ),
        digital_literacy=0.7, patience=0.15, risk_tolerance=0.5, reading_tolerance=0.2, exploration=0.1,
        max_actions=8, max_failed_attempts=2, abandon_frustration=0.55, device="mobile",
        test_identity={"name": "Rohan Mehta", "mobile": "9876543210", "pin": "400001", "dob": "12/03/1994"},
    ),
    PersonaTemplate(
        persona_type="low_literacy", label="Low-Digital-Literacy User",
        blurb="Unfamiliar with web apps; needs explicit labels and clear confirmation.",
        behavior=(
            "You don't use websites often. You only trust buttons and links whose words clearly say what they do. "
            "Jargon and abbreviations confuse you. You make no assumptions about hidden menus or icons. "
            "If you're unsure where you are, you go back."
        ),
        digital_literacy=0.25, patience=0.6, risk_tolerance=0.3, reading_tolerance=0.5, exploration=0.2,
        max_actions=12, max_failed_attempts=3, abandon_frustration=0.8, device="mobile",
        test_identity={"name": "Sunita Devi", "mobile": "9123456780", "pin": "800001", "dob": "05/11/1978"},
    ),
    PersonaTemplate(
        persona_type="power", label="Power User",
        blurb="Takes the shortest path; skips all optional reading.",
        behavior=(
            "You are an expert web user. You take the shortest path to the goal, skip all optional content, "
            "fill forms correctly the first time, and never read marketing text."
        ),
        digital_literacy=0.95, patience=0.4, risk_tolerance=0.6, reading_tolerance=0.1, exploration=0.0,
        max_actions=10, max_failed_attempts=2, abandon_frustration=0.7, device="desktop",
        test_identity={"name": "Arjun Rao", "mobile": "9988776655", "pin": "560001", "dob": "21/07/1990"},
    ),
    PersonaTemplate(
        persona_type="cautious", label="Cautious User",
        blurb="Low risk tolerance; scrutinizes fees, consent and payment wording.",
        behavior=(
            "You are careful with money and personal data. Before paying or sharing details you look for clear fees, "
            "privacy terms and what you're agreeing to. Unexplained charges, pre-ticked consent boxes or vague "
            "payment buttons make you uneasy and you may leave."
        ),
        digital_literacy=0.6, patience=0.6, risk_tolerance=0.15, reading_tolerance=0.9, exploration=0.3,
        max_actions=12, max_failed_attempts=2, abandon_frustration=0.75, device="desktop",
        test_identity={"name": "Meera Iyer", "mobile": "9445566778", "pin": "600004", "dob": "30/01/1985"},
    ),
    PersonaTemplate(
        persona_type="explorer", label="Exploratory User",
        blurb="Compares options, opens secondary paths and backtracks often.",
        behavior=(
            "You like to explore before committing. You compare alternatives, open secondary links like "
            "'Explore' or 'Learn', and come back if they don't help. You eventually try to finish the goal."
        ),
        digital_literacy=0.75, patience=0.8, risk_tolerance=0.5, reading_tolerance=0.7, exploration=0.9,
        max_actions=14, max_failed_attempts=3, abandon_frustration=0.85, device="desktop",
        test_identity={"name": "Kabir Singh", "mobile": "9012345678", "pin": "110001", "dob": "09/09/1992"},
    ),
    PersonaTemplate(
        persona_type="chaos", label="Chaos / Edge-Case User",
        blurb="Unusual inputs, repeated clicks and odd ordering to test robustness.",
        behavior=(
            "You behave unpredictably to test robustness: unusual inputs, repeated clicks, going back mid-flow, "
            "doing things out of order. You still try to reach the goal. You never attempt hacking or security attacks."
        ),
        digital_literacy=0.8, patience=0.5, risk_tolerance=0.9, reading_tolerance=0.2, exploration=0.6,
        max_actions=14, max_failed_attempts=4, abandon_frustration=0.9, device="desktop",
        test_identity={"name": "Zoya Khan", "mobile": "9090909090", "pin": "700001", "dob": "14/02/1996"},
    ),
]

TEMPLATES_BY_TYPE = {t.persona_type: t for t in TEMPLATES}
