"""HeritageGuard AI: a three-step policy agent (analyse -> recommend -> review).
Uses the Gemini API with JSON-schema output. Set GEMINI_API_KEY before running."""
import json
import os
import pathlib

from google import genai
from google.genai import types

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
# Tries GEMINI_MODEL first (if set), then these. Check AI Studio for the free models your key can use.
MODELS = [m for m in (os.getenv("GEMINI_MODEL"), "gemini-3.5-flash", "gemini-2.5-flash") if m]

SYSTEM = """You are HeritageGuard AI, a policy recommendation assistant for heritage conservation in Goa, India.
Rules:
- Use ONLY the supplied evidence for facts about the site. Never invent facts, statistics, costs or citations.
- Put anything not in the evidence under 'assumptions' or 'evidence_to_verify'.
- Impacts are expectations, not measured results.
- Do not recommend restoration work without a qualified structural assessment.
- Stay neutral: analyse the governance problem, do not blame individuals or groups.
- You advise decision-makers; you do not make the decision."""

REVIEW_SYSTEM = """You are a strict reviewer. Compare the recommendations with the evidence.
List any statement in the recommendations that states a site fact, number or citation NOT supported by the evidence.
Return an empty list if everything is supported."""

STR = {"type": "string"}


def arr(item=STR):
    return {"type": "array", "items": item}


def obj(props):
    return {"type": "object", "properties": props, "required": list(props)}


ANALYSIS = obj({
    "problems": arr(obj({"issue": STR, "evidence": STR})),
    "stakeholders": arr(),
    "priorities": arr(),
})
POLICIES = arr(obj({
    "area": STR, "recommendation": STR, "justification": STR,
    "evidence_from_article": arr(), "assumptions": arr(),
    "expected_benefits": arr(), "trade_offs": arr(),
    "implementation_challenges": arr(), "success_indicators": arr(),
    "evidence_to_verify": arr(),
}))
REVIEW = arr(obj({"policy": STR, "concern": STR}))


# ---- Tools (plain Python, called by the agent) ----
def load_evidence(article_text: str) -> str:
    facts = (DATA / "article_facts.json").read_text()
    pasted = article_text.strip() or "(none provided)"
    return f"ARTICLE TEXT (pasted by user):\n{pasted}\n\nKEY FACTS FILE:\n{facts}"


def load_policy_areas() -> list:
    return json.loads((DATA / "policy_areas.json").read_text())


# ---- LLM call with fallback across models ----
def call_json(system: str, prompt: str, schema: dict):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set. See README step 5.")
    client = genai.Client(api_key=key)
    last = None
    for model in MODELS:
        try:
            r = client.models.generate_content(
                model=model, contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system, temperature=0.2,
                    response_mime_type="application/json", response_schema=schema))
            return json.loads(r.text), model
        except Exception as e:  # try the next model
            last = e
    raise RuntimeError(f"All models failed. Last error: {last}")


# ---- The agent ----
def run_agent(article_text: str, progress=lambda msg: None) -> dict:
    evidence = load_evidence(article_text)
    areas = load_policy_areas()

    progress("Step 1/3: analysing the issues")
    analysis, model = call_json(
        SYSTEM, f"EVIDENCE:\n{evidence}\n\nIdentify the conservation problems, stakeholders and priorities.", ANALYSIS)

    progress("Step 2/3: generating policy options")
    policies, _ = call_json(
        SYSTEM,
        f"EVIDENCE:\n{evidence}\n\nISSUE ANALYSIS:\n{json.dumps(analysis)}\n\n"
        f"Give exactly one recommendation for each policy area, in this order:\n{json.dumps(areas)}",
        POLICIES)

    progress("Step 3/3: reviewing for unsupported claims")
    review, _ = call_json(
        REVIEW_SYSTEM, f"EVIDENCE:\n{evidence}\n\nRECOMMENDATIONS:\n{json.dumps(policies)}", REVIEW)

    return {"model": model, "analysis": analysis, "policies": policies, "review_flags": review}
