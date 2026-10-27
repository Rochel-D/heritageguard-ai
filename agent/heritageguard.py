"""HeritageGuard AI: a three-step policy agent (analyse -> recommend -> review).
Uses the Gemini API with JSON-schema output. Set GEMINI_API_KEY before running."""
import json
import os
import pathlib
import time

from google import genai
from google.genai import types

DATA = pathlib.Path(__file__).resolve().parent.parent / "data"
# GEMINI_MODEL (if set) is tried first. Check AI Studio for models your key can use.
MODELS = list(dict.fromkeys(m for m in (os.getenv("GEMINI_MODEL"), "gemini-3.5-flash", "gemini-3.1-flash-lite") if m))
TIMEOUT_MS = 60_000          # give up on a single request after 60 s
RETRY_WAITS = (3, 8)         # seconds to wait before each retry on "server busy" errors
BUSY = ("503", "504", "429", "UNAVAILABLE", "DEADLINE", "RESOURCE_EXHAUSTED")

SYSTEM = """You are HeritageGuard AI, a policy recommendation assistant for heritage conservation in Goa, India.
Rules:
- Use ONLY the supplied evidence for facts about the site. Never invent facts, statistics, costs or citations.
- Do not cite laws, guidelines, standards or funding schemes unless they are in the evidence; if you use general knowledge, put it under 'assumptions'.
- UNCERTAIN FACTS are unconfirmed: use them only where directly relevant, and list them under 'evidence_to_verify'.
- 'evidence_to_verify' lists only claims THIS recommendation depends on that the evidence does not confirm. Do not copy unrelated items.
- Give at least two trade-offs for every recommendation.
- Name stakeholders by role or organisation, never as named individuals.
- Impacts are expectations, not measured results.
- Do not recommend restoration work without a qualified structural assessment.
- Stay neutral: analyse the governance problem, do not blame individuals or groups.
- You advise decision-makers; you do not make the decision."""

REVIEW_SYSTEM = """You are a strict reviewer. Compare the recommendations with the evidence.
List every statement that (a) states a site fact, number or citation not in the evidence, or
(b) refers to an external law, guideline, standard, scheme or general claim (for example 'in accordance with
conservation guidelines') that is not in the evidence. Return an empty list only if everything is supported."""

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
    data = json.loads((DATA / "article_facts.json").read_text())
    firm = [f for f in data["facts"] if "[verify]" not in f]
    shaky = [f.replace(" [verify]", "") for f in data["facts"] if "[verify]" in f]
    pasted = article_text.strip() or "(none provided)"
    return (
        f"SOURCE: {data['source']}\n\nARTICLE TEXT (pasted by user):\n{pasted}\n\n"
        "KEY FACTS:\n" + "\n".join(f"- {f}" for f in firm)
        + "\n\nUNCERTAIN FACTS (read from a scan, not confirmed):\n" + "\n".join(f"- {f}" for f in shaky)
    )


def load_policy_areas() -> list:
    return json.loads((DATA / "policy_areas.json").read_text())


# ---- LLM call: timeout, retry on busy errors, fall back across models ----
def call_json(system: str, prompt: str, schema: dict):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it as a Colab secret or environment variable.")
    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
    last = None
    for model in MODELS:
        for attempt in range(len(RETRY_WAITS) + 1):
            try:
                r = client.models.generate_content(
                    model=model, contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system, temperature=0.2,
                        response_mime_type="application/json", response_schema=schema))
                return json.loads(r.text), model
            except Exception as e:
                last = e
                busy = any(b in str(e) for b in BUSY)
                if not busy or attempt == len(RETRY_WAITS):
                    break  # not retryable, or retries used up: try the next model
                time.sleep(RETRY_WAITS[attempt])
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
