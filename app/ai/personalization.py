"""Compatibility import for the canonical conversation suggestion engine.

Older scripts imported ``suggest_next_messages`` from this module. Keep that
public entry point while ensuring the application has only one implementation.
"""
from app.ai.suggestions import suggest_next_messages

__all__ = ["suggest_next_messages"]
