import json

import streamlit as st

from agent.heritageguard import run_agent

st.set_page_config(page_title="HeritageGuard AI", layout="wide")
st.title("HeritageGuard AI: Policy Recommendation Agent")
st.caption("Mount Carmel Church, Chimbel, Goa. Advice for decision-makers; structural and restoration decisions need qualified experts.")

article = st.text_area("Paste the article text here", height=260,
                       placeholder="Times of India (Goa): Govt boost for historic Mount Carmel site...")


def bullets(title, items):
    if items:
        st.markdown(f"**{title}**")
        for i in items:
            st.markdown(f"- {i}")


if st.button("Generate recommendations", type="primary"):
    if not article.strip():
        st.warning("No article text pasted. The agent will use only the built-in key facts.")
    try:
        with st.status("Running the agent...", expanded=True) as status:
            result = run_agent(article, progress=lambda m: st.write(m))
            status.update(label="Done", state="complete")
    except Exception as e:
        st.error(f"Agent failed: {e}")
        st.stop()

    st.caption(f"Model used: {result['model']}")
    a = result["analysis"]
    st.header("Issue analysis")
    for p in a["problems"]:
        st.markdown(f"- **{p['issue']}**: {p['evidence']}")
    c1, c2 = st.columns(2)
    with c1:
        bullets("Stakeholders", a["stakeholders"])
    with c2:
        bullets("Priorities", a["priorities"])

    st.header("Policy recommendations")
    for p in result["policies"]:
        with st.expander(f"{p['area']}: {p['recommendation']}", expanded=True):
            st.write(p["justification"])
            bullets("Evidence from the article", p["evidence_from_article"])
            bullets("Assumptions", p["assumptions"])
            bullets("Expected benefits", p["expected_benefits"])
            bullets("Trade-offs", p["trade_offs"])
            bullets("Implementation challenges", p["implementation_challenges"])
            bullets("Success indicators", p["success_indicators"])
            bullets("Evidence to verify", p["evidence_to_verify"])

    st.header("Reviewer flags")
    if result["review_flags"]:
        for f in result["review_flags"]:
            st.markdown(f"- **{f['policy']}**: {f['concern']}")
    else:
        st.success("No unsupported claims flagged. This is an automated check, so still review manually.")

    st.download_button("Download output.json", json.dumps(result, indent=2), "output.json", "application/json")
