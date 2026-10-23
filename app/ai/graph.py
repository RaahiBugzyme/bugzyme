from typing import Any, Dict, List, Optional, TypedDict

from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, START, END

from app.ai.death_zone import analyze_death_zone, is_death_zone
from app.ai.suggestions import suggest_next_messages


class ConversationState(TypedDict, total=False):
    # Input
    db: Session
    requesting_user_id: int
    requesting_user: str
    messages: List[Any]

    # Death-zone analysis
    death_zone: Dict[str, Any]
    should_generate: bool

    # AI suggestion output
    suggestion_result: Optional[Dict[str, Any]]
    error: Optional[str]


def detect_death_zone_node(
    state: ConversationState,
) -> Dict[str, Any]:
    """Analyze recent conversation engagement."""

    messages = state.get("messages")

    if not isinstance(messages, list) or not messages:
        raise ValueError("Messages must be a non-empty list.")

    result = analyze_death_zone(messages)

    should_generate = is_death_zone(result)

    return {
        "death_zone": result,
        "should_generate": should_generate,
        "suggestion_result": None,
        "error": None,
    }


def route_after_detection(
    state: ConversationState,
) -> str:
    """Decide whether AI suggestions are needed."""

    if state.get("should_generate", False):
        return "generate_suggestions"

    return "finish"


def generate_suggestions_node(
    state: ConversationState,
) -> Dict[str, Any]:
    """Generate suggestions using the existing AI module."""

    db = state.get("db")
    requesting_user_id = state.get("requesting_user_id")
    requesting_user = state.get("requesting_user")
    messages = state.get("messages")

    if db is None:
        raise ValueError("Database session is required.")

    if requesting_user_id is None:
        raise ValueError("Requesting user ID is required.")

    if not requesting_user:
        raise ValueError("Requesting user name is required.")

    if not isinstance(messages, list) or not messages:
        raise ValueError("Messages must be a non-empty list.")

    result = suggest_next_messages(
        db=db,
        requesting_user_id=requesting_user_id,
        requesting_user=requesting_user,
        messages=messages,
    )

    return {"suggestion_result": result}


def build_conversation_graph():
    """Build and compile the Bugzyme LangGraph workflow."""

    workflow = StateGraph(ConversationState)

    workflow.add_node(
        "detect_death_zone",
        detect_death_zone_node,
    )

    workflow.add_node(
        "generate_suggestions",
        generate_suggestions_node,
    )

    workflow.add_node(
        "finish",
        lambda state: {},
    )

    workflow.add_edge(START, "detect_death_zone")

    workflow.add_conditional_edges(
        "detect_death_zone",
        route_after_detection,
        {
            "generate_suggestions": "generate_suggestions",
            "finish": "finish",
        },
    )

    workflow.add_edge("generate_suggestions", END)
    workflow.add_edge("finish", END)

    return workflow.compile()


# Compile once when this module is imported.
conversation_graph = build_conversation_graph()


def run_conversation_workflow(
    db: Session,
    requesting_user_id: int,
    requesting_user: str,
    messages: List[Any],
) -> Dict[str, Any]:
    """Run the complete death-zone detection workflow."""

    return conversation_graph.invoke(
        {
            "db": db,
            "requesting_user_id": requesting_user_id,
            "requesting_user": requesting_user,
            "messages": messages,
        }
    )
