"""Gradio interface for HeritageGuard AI. Works in Colab: demo.launch(share=True)."""
import json

import gradio as gr

from agent.heritageguard import run_agent


def bl(title, items):
    return f"**{title}**\n" + "\n".join(f"- {i}" for i in items) + "\n\n" if items else ""


def render(result):
    a = result["analysis"]
    out = f"*Model used: {result['model']}*\n\n## Issue analysis\n"
    out += "".join(f"- **{p['issue']}**: {p['evidence']}\n" for p in a["problems"]) + "\n"
    out += bl("Stakeholders", a["stakeholders"]) + bl("Priorities", a["priorities"])
    out += "## Policy recommendations\n"
    for p in result["policies"]:
        out += f"\n### {p['area']}: {p['recommendation']}\n{p['justification']}\n\n"
        out += bl("Evidence from the article", p["evidence_from_article"]) + bl("Assumptions", p["assumptions"])
        out += bl("Expected benefits", p["expected_benefits"]) + bl("Trade-offs", p["trade_offs"])
        out += bl("Implementation challenges", p["implementation_challenges"])
        out += bl("Success indicators", p["success_indicators"]) + bl("Evidence to verify", p["evidence_to_verify"])
    out += "\n## Reviewer flags\n"
    flags = "".join(f"- **{f['policy']}**: {f['concern']}\n" for f in result["review_flags"])
    return out + (flags or "No unsupported claims flagged (automated check; still review manually).\n")


def generate(article, progress=gr.Progress()):
    try:
        result = run_agent(article, progress=lambda m: progress(int(m[5]) / 4, desc=m))
    except Exception as e:
        return f"**Agent failed:** {e}", None
    with open("output.json", "w") as f:
        json.dump(result, f, indent=2)
    return render(result), "output.json"


def build_ui():
    with gr.Blocks(title="HeritageGuard AI") as demo:
        gr.Markdown("# HeritageGuard AI: Policy Recommendation Agent\n"
                    "Mount Carmel Church, Chimbel, Goa. Advice for decision-makers; "
                    "structural and restoration decisions need qualified experts.")
        article = gr.Textbox(label="Paste the article text", lines=10)
        btn = gr.Button("Generate recommendations", variant="primary")
        result_md = gr.Markdown()
        file = gr.File(label="Download output.json")
        btn.click(generate, article, [result_md, file])
    return demo


if __name__ == "__main__":
    build_ui().launch()
