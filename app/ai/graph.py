from typing import Any, Dict, List, Optional, TypedDict

from sqlalchemy.orm import Session
from langgraph.graph import StateGraph, START, END

from app.ai.death_zone import analyze_death_zone, is_death_zone
from app.ai.suggestions import suggest_next_messages
from app.ai.conversation_intelligence import build_conversation_intelligence
from app.ai.targeting import analyze_participant_effort
from app.ai.recovery_strategy import select_recovery_strategy


class ConversationState(TypedDict, total=False):
    # Input
    db: Session
    requesting_user_id: int
    requesting_user: str
    messages: List[Any]

    # Death-zone analysis
    death_zone: Dict[str, Any]
    should_generate: bool
    intelligence: Dict[str, Any]
    participant_effort: Dict[str, Any]
    recovery: Dict[str, Any]
    chat_id: Optional[int]
    avoid_suggestions: List[str]
    manual_request: bool

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
    intelligence = build_conversation_intelligence(messages, death_zone=result)
    effort = analyze_participant_effort(messages)
    previous = []
    db = state.get("db")
    chat_id = state.get("chat_id")
    requester_id = state.get("requesting_user_id")
    if db is not None and chat_id is not None and requester_id is not None:
        try:
            from app.models import AIRecoveryIntervention
            recent = db.query(AIRecoveryIntervention).filter_by(chat_id=chat_id, user_id=requester_id).order_by(AIRecoveryIntervention.created_at.desc()).limit(30).all()
            previous = [row.strategy for row in recent if row.status == "unsuccessful"]
            from app.models import AISuggestionRecord, AISuggestionEvent
            from app.ai.strategy_performance import summarize_strategy_performance
            feedback_rows = db.query(
                AISuggestionRecord.strategy, AISuggestionEvent.details_json,
            ).join(AISuggestionEvent, AISuggestionEvent.suggestion_id == AISuggestionRecord.id).filter(
                AISuggestionRecord.chat_id == chat_id,
                AISuggestionRecord.user_id == requester_id,
                AISuggestionEvent.event_type == "user_feedback",
            ).all()
            feedback = []
            for strategy_name, details_json in feedback_rows:
                try:
                    rating = __import__("json").loads(details_json or "{}").get("rating")
                    feedback.append({"strategy": strategy_name, "rating": rating})
                except (TypeError, ValueError):
                    continue
            performance = summarize_strategy_performance(feedback)
            previous.extend(strategy_name for strategy_name, value in performance.items()
                            if value.get("avoid_for_now"))
        except Exception:
            # Historical strategy data is optional; analysis must still work.
            db.rollback()
            previous = []
    recovery = select_recovery_strategy(messages, intelligence, previous)
    identified_senders = {
        str(item.get("sender_id"))
        for item in messages
        if isinstance(item, dict) and item.get("sender_id") is not None
    }
    # Older internal/test callers provide display names only. The authenticated
    # API always supplies sender IDs and applies the participant-target gate.
    target_matches = (
        not identified_senders
        and (
            state.get("requesting_user_id") is None
            or str(state.get("requesting_user_id")) not in identified_senders
        )
    ) or (
        effort.get("eligible") is True
        and effort.get("target_user_id") == state.get("requesting_user_id")
    )
    automatic_should_generate = is_death_zone(result) and target_matches and (
        recovery.get("should_intervene", True) or not identified_senders
    )

    should_generate = (
        True if state.get("manual_request", False)
        else automatic_should_generate
    )

    return {
        "death_zone": result,
        "should_generate": should_generate,
        "intelligence": intelligence,
        "participant_effort": effort,
        "recovery": recovery,
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
        intelligence=state.get("intelligence"),
        recovery=state.get("recovery"),
        avoid_suggestions=state.get("avoid_suggestions"),
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
    chat_id: Optional[int] = None,
    avoid_suggestions: Optional[List[str]] = None,
    manual_request: bool = False,
) -> Dict[str, Any]:
    """Run the complete death-zone detection workflow."""

    return conversation_graph.invoke(
        {
            "db": db,
            "requesting_user_id": requesting_user_id,
            "requesting_user": requesting_user,
            "messages": messages,
            "chat_id": chat_id,
            "avoid_suggestions": avoid_suggestions or [],
            "manual_request": manual_request,
        }
    )
