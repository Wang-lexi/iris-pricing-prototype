"""Content of the Project Roadmap page: workstreams, phases, limitations and the workflow diagram.

Documentation only: nothing here calculates or changes any pricing result. Every item marked
CURRENT must exist in the repository (a test checks the files); everything else is planned
and must not be presented as finished.

The workstream descriptions are the team's working descriptions, not verified quotations from
the industry partner's original email.
"""

from __future__ import annotations

CURRENT = "Current prototype"
FUTURE = "Future development"
LONGER = "Longer-term integration"
STATUSES = (CURRENT, FUTURE, LONGER)

# colours: (border, fill). Border style also differs (solid / dashed / dotted) so the
# difference does not rely on colour alone.
STYLE = {
    CURRENT: {"border": "#2a9d8f", "fill": "#d9f0ec", "dot_style": "filled"},
    FUTURE: {"border": "#d9822b", "fill": "#fdf0dc", "dot_style": "filled,dashed"},
    LONGER: {"border": "#7b7b99", "fill": "#ececf3", "dot_style": "filled,dotted"},
}

EXECUTIVE_SUMMARY = (
    "Pricing consultants need to know where a client's list price goes before it becomes "
    "profit, and which discounts deserve a conversation. Today that means working through "
    "thousands of transactions by hand. This project builds a **repeatable, explainable "
    "workflow** that helps consultants do it faster and more consistently.",
    "**See where the money goes.** The price waterfall follows each transaction from list "
    "price to pocket margin, separating discounts, rebates, allowances and costs.",
    "**Know where to look.** A simple regression says how much discount a transaction "
    "would normally get; transactions far above that, or above their contract limit, are "
    "flagged for review.",
    "**Understand why, and test ideas.** The root cause view shows which deduction is "
    "unusual, and the what-if view lets a consultant change discount assumptions and "
    "compare outcomes before talking to a client.",
    "**The consultant stays in charge.** Every number can be traced step by step, and the "
    "tool supports decisions; it does not set prices. So far it has been built and tested "
    "on synthetic data only. No savings have been measured.",
)

# Components that exist today. A test checks that each file is in the repository.
CURRENT_COMPONENTS = [
    {"name": "Price Waterfall Analysis", "file": "app/dashboard.py",
     "what": "List revenue to invoice revenue, pocket revenue and pocket margin, for the whole "
             "company, one product or one transaction."},
    {"name": "Regression Diagnosis", "file": "app/pages/2_Regression_Diagnosis.py",
     "what": "Interpretable OLS regression of the total price reduction rate; actual versus "
             "predicted; flags unusual residuals and discounts above the contract limit."},
    {"name": "Root Cause and What-If", "file": "app/pages/3_Root_Cause_Simulation.py",
     "what": "Shows which deduction is unusual for a flagged transaction, then compares "
             "hypothetical discount assumptions with the original outcome."},
]

WORKSTREAMS = [
    {
        "id": "WS1", "name": "Price Leakage & Dispersion Analysis", "status": CURRENT,
        "coverage": "Largely covered by the current prototype",
        "goal": "Find the gaps between list, invoice and pocket prices, and the pricing "
                "inconsistencies behind them.",
        "built": [
            "Price waterfall with on-invoice discounts, four off-invoice adjustments "
            "(volume rebate, early-payment discount, credit, promotion), COGS and cost-to-serve",
            "Regression diagnosis: actual vs predicted price reduction, unusual residuals, "
            "contract discount-limit check",
            "Root cause view: each deduction compared with similar customers",
        ],
        "next": [
            "Validate on unseen data and with consultants (Phase A)",
            "Add a direct price-dispersion view for comparable transactions",
        ],
        "needs": "Real or anonymised client data; partner input on which anomalies matter commercially.",
    },
    {
        "id": "WS2", "name": "Customer & Product Micro-Segmentation", "status": FUTURE,
        "coverage": "Not started",
        "goal": "Group customers and products so pricing can be targeted by segment.",
        "built": [
            "Not built. Customer tier, channel, province, industry and product category "
            "already exist in the data and could seed the first segments",
        ],
        "next": [
            "Define customer and product segments",
            "Compare price realization, discounts and profitability within comparable segments",
            "Link segments back to the waterfall and regression",
        ],
        "needs": "Agreed segmentation criteria; richer customer and product attributes (purchasing behaviour, profitability).",
    },
    {
        "id": "WS3", "name": "Value-Based Price Guidance", "status": FUTURE,
        "coverage": "Not started",
        "goal": "Help consultants choose prices from cost, customer value, competition and "
                "constraints, instead of setting prices automatically.",
        "built": [
            "Not built. The what-if view shows benchmarks (typical and expected discount), "
            "which are not price recommendations",
        ],
        "next": [
            "Explore floor, target and stretch price corridors",
            "Combine internal pricing data with customer value and market information",
            "Give transparent recommendations that state their assumptions",
            "Estimate elasticity or optimize prices only if suitable data and credible assumptions exist",
        ],
        "needs": "Customer value, competitor and market information; cost and business constraints.",
    },
    {
        "id": "WS4", "name": "Financial Opportunity & Playbook", "status": FUTURE,
        "coverage": "Early demonstration only (what-if view)",
        "goal": "Quantify and prioritize opportunities, and turn the method into a reusable "
                "consulting playbook.",
        "built": [
            "What-if view: hypothetical effect of lower discounts on one transaction or on all "
            "flagged transactions. It assumes customers buy the same quantity, so it is an "
            "illustration, not a forecast",
        ],
        "next": [
            "Estimate opportunities by product and customer segment",
            "Compare alternative scenarios with risks and assumptions",
            "Prioritize by financial impact, feasibility and risk",
            "Write the reusable methodology and consultant-facing outputs, with documented human review",
        ],
        "needs": "Segments (WS2) and price guidance (WS3); volume-response assumptions; a consultant review process.",
    },
]

PHASES = [
    {"phase": "A", "title": "Validate the existing prototype", "workstream": "WS1", "status": FUTURE,
     "focus": "Verify joins and reconciliation, review data quality and pricing assumptions, test the "
              "regression on unseen data, confirm the flags are meaningful, document the limits of "
              "synthetic data.",
     "needs": "Consultant review; ideally anonymised real data.",
     "deliverable": "Validation report; documented assumptions and limitations.",
     "in_place": "Automated tests for waterfall reconciliation, table joins and regression outputs; "
                 "documented data checks; a chronological train/test split on synthetic data."},
    {"phase": "B", "title": "Customer & product micro-segmentation", "workstream": "WS2", "status": FUTURE,
     "focus": "Build meaningful segments; compare price realization and profitability inside them; "
              "find segment-specific opportunities.",
     "needs": "Phase A; segmentation criteria and richer attributes.",
     "deliverable": "Segment definitions; segment-level waterfall and comparison views.",
     "in_place": ""},
    {"phase": "C", "title": "Value-based price guidance", "workstream": "WS3", "status": FUTURE,
     "focus": "Floor, target and stretch corridors; recommendations with explained assumptions; "
              "elasticity or optimization only when data supports it.",
     "needs": "Phase B; customer value and market information.",
     "deliverable": "Price corridor prototype; recommendation explanations.",
     "in_place": ""},
    {"phase": "D", "title": "Financial opportunity & consulting playbook", "workstream": "WS4", "status": FUTURE,
     "focus": "Opportunity sizing by segment; scenario comparison with risks; prioritization; reusable "
              "methodology and human review log.",
     "needs": "Phases B and C; review process.",
     "deliverable": "Opportunity model; prioritized list; consulting playbook.",
     "in_place": "An early what-if view of discount scenarios."},
    {"phase": "Later", "title": "Knowledge retrieval and AI integration", "workstream": "Supporting",
     "status": LONGER,
     "focus": "A separate RAG-based search over authorized historical cases, frameworks and playbooks, "
              "kept apart from model results; possible integration with Iris's Abacus.AI environment.",
     "needs": "Data access and security permissions; the core workstreams.",
     "deliverable": "To be decided with the partner.",
     "in_place": ""},
]

LIMITATIONS = [
    "All data is **synthetic**; the prototype has not been validated on real client transactions.",
    "A statistical anomaly is **not** confirmed price leakage. There may be good commercial reasons for it.",
    "What-if results depend on assumptions about customer behaviour and volume.",
    "Regression shows patterns, not **causal effects** of changing a price.",
    "Value-based recommendations will need market, customer and operational information we do not have yet.",
    "Human consultant judgment remains essential.",
]

# (node id, label, status)
NODES = [
    ("data", "Transaction data\n(six synthetic CSV files)", CURRENT),
    ("wf", "Price Waterfall\nAnalysis", CURRENT),
    ("reg", "Regression\nDiagnosis", CURRENT),
    ("rc", "Root Cause\nInvestigation", CURRENT),
    ("wi", "What-if\nSimulation", CURRENT),
    ("cr", "Consultant\nReview", CURRENT),
    ("seg", "WS2 Customer & Product\nMicro-Segmentation", FUTURE),
    ("vbp", "WS3 Value-Based\nPrice Guidance", FUTURE),
    ("opp", "WS4 Financial Opportunity\n& Playbook", FUTURE),
    ("rag", "Knowledge Retrieval (RAG)\nhistorical cases and playbooks", LONGER),
    ("abacus", "Abacus.AI integration\n(subject to permissions)", LONGER),
]
# (from, to, status of the link)
EDGES = [
    ("data", "wf", CURRENT), ("wf", "reg", CURRENT), ("reg", "rc", CURRENT),
    ("rc", "wi", CURRENT), ("wi", "cr", CURRENT),
    ("wf", "seg", FUTURE), ("reg", "seg", FUTURE), ("seg", "vbp", FUTURE),
    ("vbp", "opp", FUTURE), ("wi", "opp", FUTURE), ("opp", "cr", FUTURE),
    ("rag", "cr", LONGER), ("rag", "abacus", LONGER),
]


def workflow_dot() -> str:
    """Graphviz source for the workflow diagram (rendered by Streamlit in the browser)."""
    lines = ["digraph G {", '  rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.5;',
             '  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, '
             'fontcolor="#1b1b1b", margin="0.15,0.08", penwidth=1.6];',
             '  edge [color="#666666", arrowsize=0.7, penwidth=1.3];']
    for node, label, status in NODES:
        st = STYLE[status]
        style = {"filled": "rounded,filled", "filled,dashed": "rounded,filled,dashed",
                 "filled,dotted": "rounded,filled,dotted"}[st["dot_style"]]
        label = label.replace("\n", "\\n")
        lines.append(f'  {node} [label="{label}", fillcolor="{st["fill"]}", color="{st["border"]}", '
                     f'style="{style}"];')
    for a, b, status in EDGES:
        style = {CURRENT: "solid", FUTURE: "dashed", LONGER: "dotted"}[status]
        lines.append(f'  {a} -> {b} [style={style}];')
    lines.append("}")
    return "\n".join(lines)
