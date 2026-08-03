"""
Wires the research workflow:

    START -> planner -> (retriever if needed) -> generator -> guardrail -> evaluator -> END

The planner decides whether retrieval is needed; the conditional edge
skips straight to the generator when it isn't, so a plain question
doesn't pay for an unnecessary vector search.
"""
from langgraph.graph import END, START, StateGraph

from app.agents.graph.nodes.evaluator import evaluator_node
from app.agents.graph.nodes.generator import generator_node
from app.agents.graph.nodes.guardrail import guardrail_node
from app.agents.graph.nodes.planner import planner_node
from app.agents.graph.nodes.retriever import retriever_node
from app.agents.graph.state import ResearchState


def _route_after_planner(state: ResearchState) -> str:
    return "retriever" if state.get("needs_retrieval") else "generator"


def build_research_graph():
    graph = StateGraph(ResearchState)

    graph.add_node("planner", planner_node)
    graph.add_node("retriever", retriever_node)
    graph.add_node("generator", generator_node)
    graph.add_node("guardrail", guardrail_node)
    graph.add_node("evaluator", evaluator_node)

    graph.add_edge(START, "planner")
    graph.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"retriever": "retriever", "generator": "generator"},
    )
    graph.add_edge("retriever", "generator")
    graph.add_edge("generator", "guardrail")
    graph.add_edge("guardrail", "evaluator")
    graph.add_edge("evaluator", END)

    return graph.compile()


_compiled_graph = None


def get_research_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_research_graph()
    return _compiled_graph
