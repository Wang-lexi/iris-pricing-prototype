"""Streamlit page: Project Roadmap.

Documentation only. It shows what the prototype already does, what is planned, and how the
pieces connect. It does not calculate or change any pricing result.

    streamlit run app/dashboard.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from src.roadmap import (
    CURRENT,
    CURRENT_COMPONENTS,
    EXECUTIVE_SUMMARY,
    FUTURE,
    LIMITATIONS,
    LONGER,
    PHASES,
    STATUSES,
    STYLE,
    WORKSTREAMS,
    workflow_dot,
)

st.set_page_config(page_title="Project Roadmap", layout="wide")
st.markdown(
    "<style>.block-container{max-width:100%;padding-left:2.5rem;padding-right:2.5rem;}</style>",
    unsafe_allow_html=True)

BORDER_STYLE = {CURRENT: "solid", FUTURE: "dashed", LONGER: "dotted"}


def badge(status: str) -> str:
    """A small coloured label. The border style differs too, so it works without colour."""
    c = STYLE[status]["border"]
    return (f"<span style='display:inline-block;border:2px {BORDER_STYLE[status]} {c};"
            f"background:{c}22;border-radius:12px;padding:1px 10px;font-size:0.82rem;"
            f"font-weight:600;white-space:nowrap'>{status}</span>")


st.title("Project Roadmap")
st.caption("From a pricing diagnostic prototype to a reusable, AI-assisted pricing "
           "decision-support workflow for Iris consultants. The prototype uses synthetic data.")
st.markdown(
    "**Status key:** " + " &nbsp; ".join(badge(s) for s in STATUSES)
    + " &nbsp; Only the first is built today.", unsafe_allow_html=True)
st.markdown(
    "**Jump to:** [Summary](#summary) · [Workflow](#workflow) · [Four workstreams](#workstreams) · "
    "[Phases](#phases) · [Limitations](#limitations)")

# --------------------------------------------------------------- summary
st.header("Executive summary", anchor="summary")
with st.container(border=True):
    st.markdown(EXECUTIVE_SUMMARY[0])
    for line in EXECUTIVE_SUMMARY[1:]:
        st.markdown(f"- {line}")

# -------------------------------------------------------------- workflow
st.header("How the pieces connect", anchor="workflow")
st.caption("Solid teal boxes and arrows exist today. Dashed orange are planned workstreams. "
           "Dotted grey is a possible later extension.")
st.graphviz_chart(workflow_dot(), width="stretch")
st.markdown(
    "**Today's workflow:** Price Waterfall → Regression Diagnosis → Root Cause Investigation → "
    "What-if Simulation → Consultant Review. The three built steps are the pages "
    "**dashboard**, **Regression Diagnosis** and **Root Cause Simulation** in the sidebar.")

# ----------------------------------------------------------- workstreams
st.header("The four workstreams", anchor="workstreams")
st.caption("Working descriptions of the project's four workstreams.")
for row in (WORKSTREAMS[:2], WORKSTREAMS[2:]):
    cols = st.columns(2)
    for col, ws in zip(cols, row):
        with col, st.container(border=True):
            st.markdown(f"### {ws['id']} · {ws['name']}")
            st.markdown(badge(ws["status"]) + f" &nbsp; **{ws['coverage']}**", unsafe_allow_html=True)
            st.markdown(ws["goal"])
            st.markdown("**Built today**")
            st.markdown("\n".join(f"- {t}" for t in ws["built"]))
            st.markdown("**Next**")
            st.markdown("\n".join(f"- {t}" for t in ws["next"]))
            st.caption("Needs: " + ws["needs"])

# ---------------------------------------------------------------- phases
st.header("Proposed phases", anchor="phases")
st.caption("A suggested order: confirm the base, then segment, then guide prices, then size "
           "opportunities. Later phases depend on earlier ones.")
st.dataframe(pd.DataFrame({
    "Phase": [p["phase"] for p in PHASES],
    "Workstream": [p["workstream"] for p in PHASES],
    "What happens": [f"{p['title']}: {p['focus']}" for p in PHASES],
    "Needs first": [p["needs"] for p in PHASES],
    "Proposed deliverable": [p["deliverable"] for p in PHASES],
    "Already in place": [p["in_place"] or "-" for p in PHASES],
    "Status": [p["status"] for p in PHASES],
}), hide_index=True, width="stretch",
    column_config={"What happens": st.column_config.TextColumn(width="large"),
                   "Already in place": st.column_config.TextColumn(width="medium")})
st.markdown(
    f"{badge(LONGER)} &nbsp; Knowledge retrieval (RAG) is an optional supporting capability, "
    "separate from the numerical analytics. It would not replace the four pricing workstreams "
    "and must not blur historical evidence with model predictions.", unsafe_allow_html=True)

with st.expander("What exists in the repository today"):
    st.dataframe(pd.DataFrame(CURRENT_COMPONENTS).rename(
        columns={"name": "Component", "file": "File", "what": "What it does"}),
        hide_index=True, width="stretch")
    st.caption("Not yet implemented: price-leakage detection module, data-generation module and "
               "the exploratory notebooks are empty placeholders.")

# ------------------------------------------------------------ limitations
st.header("Important limitations", anchor="limitations")
with st.container(border=True):
    st.markdown("\n".join(f"- {t}" for t in LIMITATIONS))
st.caption("No financial savings, model performance claims, client approval or completed workstream "
           "deliverables are claimed on this page.")
