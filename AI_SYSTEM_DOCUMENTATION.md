# Bugzyme AI System: Source-Grounded Technical Notes

**Scope:** source-grounded architecture notes, updated on 2026-10-31 to reflect the implemented green-dot wiring and opt-in AI memory, profile controls, suggestion context/style changes, and the legacy compatibility wrapper.

## 1. Project AI Overview

Bugzyme is a FastAPI chat service with a single-page frontend in `index.html`. The AI path that is actually connected to the product is a synchronous REST request for suggestions. The backend loads recent text messages, runs a deterministic engagement heuristic in a LangGraph workflow, and only on a positive route calls the suggestion engine. That engine retrieves optional user memories, asks Groq to analyze and draft replies, validates them, and returns its result through the REST response. The frontend's existing AI button displays suggestions.

Memory extraction is now called only when a user enables personal AI memory and requests suggestions. It processes the requesting user’s own recent text messages, filters to eligible durable memory types, and stores a high-water message ID to avoid repeating extraction. The older `personalization.py` import now forwards to the canonical suggestion module. No AI workflow is started by a WebSocket event.

Primary entry points are [`app/main.py:35`](/Users/sandeepsharma/Desktop/bugzyme-new/app/main.py:35), where the graph runner is imported, and [`app/main.py:1894`](/Users/sandeepsharma/Desktop/bugzyme-new/app/main.py:1894), the authenticated `POST /chats/{chat_id}/suggestions` route. [`index.html:3185`](/Users/sandeepsharma/Desktop/bugzyme-new/index.html:3185) calls that route when the user opens AI Suggestions.

## 2. AI Technology Stack

| Layer | Actual implementation |
|---|---|
| HTTP / WebSocket server | FastAPI; application object `app` in `app/main.py` |
| Workflow | `langgraph.graph.StateGraph`, `START`, `END` in `app/ai/graph.py` |
| LLM provider | Groq Python client, created by `get_groq_client()` in `app/ai/extraction.py` |
| Configured chat model | `openai/gpt-oss-120b`, constant `MODEL_NAME` in `app/ai/extraction.py:10`; used by the suggestion, extraction, and interest modules |
| Embedding model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, in `app/ai/memory.py:11-13` |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2`, in `app/ai/memory.py:14`; loaded lazily |
| Vector storage/search | PostgreSQL `pgvector` SQLAlchemy `Vector(384)` column on `UserMemory.embedding`; cosine-distance query in `search_memories()` |
| Other model runtime | `sentence-transformers` and `torch` are listed in `requirements.txt`; the source caches the embedding and CrossEncoder objects with `lru_cache` |

No ChromaDB or FAISS implementation appears in the application source. `pgvector` is the actual vector integration. `requirements.txt` also includes FastAPI, SQLAlchemy, Groq, LangGraph and database/runtime dependencies; the full list is in that file. The source does not configure a separate embedding API provider.

## 3. Complete AI Architecture

```mermaid
flowchart TD
  FE[Frontend: index.html\nAI Suggestions button] -->|POST /chats/{chat_id}/suggestions| API[FastAPI route\nget_chat_suggestions]
  API -->|last 60 text messages, oldest to newest| G[LangGraph\nConversationState]
  G --> DZ[Heuristic death-zone detector\nanalyze_death_zone / is_death_zone]
  DZ -->|not a death zone| END[finish / response with empty suggestions]
  DZ -->|should_generate true| SG[Suggestion engine\napp/ai/suggestions.py]
  SG -->|up to 10 candidates for requesting user| PG[(PostgreSQL + pgvector\nuser_memories)]
  PG -->|top relevant memories| SG
  SG -->|analysis, draft, relevance calls| GROQ[Groq API\nopenai/gpt-oss-120b]
  SG -->|three validated suggestions| API
  END --> API
  API -->|JSON response| FE
  EX[Memory extraction helper\napp/ai/extraction.py] -. no caller in app .-> PG
  IX[Interest extraction helper\napp/ai/interest_extraction.py] -. no caller in app .-> PG
  FE -->|successful death-zone suggestions result\nscoped to chat ID| DOT[AI button green dot]
```

Solid connections are implemented application paths. Dashed extractor-to-database arrows are **not implemented**; those modules return data but do not persist it. The green-dot path is now wired in the frontend from the existing successful suggestions response; details and limits are in section 13.

There are no scheduled or background AI jobs in the inspected source. `process_message()` saves and delivers messages but does not call the AI graph. The AI flow is request-driven by `get_chat_suggestions()`.

## 4. AI Suggestion Generation

### Trigger and context

The user explicitly opens AI suggestions in the chat composer; `openAISuggestions()` sends `POST /chats/{chat_id}/suggestions` ([`index.html:3185-3210`](/Users/sandeepsharma/Desktop/bugzyme-new/index.html:3185)). The backend verifies chat membership, reads the latest **60** non-deleted rows whose `message_type == "text"`, reverses them into chronological order, resolves sender usernames, and supplies nonempty text messages to the graph ([`app/main.py:1894-1971`](/Users/sandeepsharma/Desktop/bugzyme-new/app/main.py:1894)). The suggestion engine then retains the latest **15** messages (`MAX_HISTORY_MESSAGES`) when formatting the transcript ([`app/ai/suggestions.py:15-21`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:15), [`app/ai/suggestions.py:309-326`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:309)). Language detection is separately run on up to the latest 12 input messages ([`app/ai/suggestions.py:1178-1182`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:1178)).

The requesting user's username and database ID are passed as personalization identity. The generation prompt receives a small style summary (typical message length, emoji/question use) derived only from that user's own recent messages; it is explicitly a writing-style hint rather than a personality inference. The history formatter retains the latest turns plus up to three older turns with overlapping topical words. Conversation text is shared with the model as a speaker-labelled transcript. Retrieved memory is user-specific: `search_memories()` filters by the requesting user's `user_id`; there is no `chat_id` field on `UserMemory` ([`app/ai/memory.py:203-245`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/memory.py:203), [`app/models.py:386-429`](/Users/sandeepsharma/Desktop/bugzyme-new/app/models.py:386)).

### Model calls, prompts, output

`suggest_next_messages()` in `app/ai/suggestions.py` retrieves memories, calls `_analyze_conversation()`, then `_generate_suggestions()`, and returns `analysis`, `memories_used`, and `suggestions` ([`app/ai/suggestions.py:1160-1215`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:1160)). The model constant is `openai/gpt-oss-120b`. `_call_model()` uses Groq chat completions and retries an empty/no-choice or length-truncated response once; completion budgets are capped at 2,000 tokens ([`app/ai/suggestions.py:96-164`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:96)).

Conversation analysis requests five concise JSON fields: `current_topic`, `conversation_tone`, `last_message_intent`, `conversation_state`, and `next_reply_strategy`. It retries parsing once and falls back to `DEFAULT_ANALYSIS` if both attempts fail ([`app/ai/suggestions.py:452-543`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:452)). The generation prompt asks for exactly three distinct messages in `natural`, `playful`, and `thoughtful` styles, each up to 20 words with no minimum length, matching the conversation language/script and answering the latest message. It forbids unsupported personal facts, plans, dates, venues, or commitments ([`app/ai/suggestions.py:545-659`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:545)).

The generator has two validation/generation attempts (`MAX_GENERATION_ATTEMPTS=2`). Each model call can itself retry once. Validation failures are fed back into the next generation prompt; if no attempt returns three validated suggestions, `_generate_suggestions()` raises `RuntimeError`, which the route logs and converts into HTTP 500 ([`app/ai/suggestions.py:1010-1153`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:1010), [`app/main.py:1972-1980`](/Users/sandeepsharma/Desktop/bugzyme-new/app/main.py:1972)).

## 5. Death-Zone Detection

“Death zone” is a product label for a low-engagement/stagnation heuristic, not a psychological diagnosis or a probability of lost interest. `analyze_death_zone()` is deterministic Python logic; it does not call an LLM. It normalizes message text/sender, drops deleted, blank, or non-text messages, then computes metrics over the latest 12 usable messages. A comparison baseline is made from all earlier usable messages when there are at least six of them ([`app/ai/death_zone.py:6-9`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/death_zone.py:6), [`app/ai/death_zone.py:30-80`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/death_zone.py:30), [`app/ai/death_zone.py:187-220`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/death_zone.py:187)).

For each window, the signals are:

- `substantive_rate`: fraction with at least five whitespace-separated words **or** 30 characters.
- `question_rate`: fraction containing `?`.
- `participation_balance`: `1 - (max(sender_count)-min(sender_count))/message_count` when at least two senders are present.
- `length_signal`: average word count divided by 12, capped at 1.
- `engagement_index`: `100 * (0.35*substantive + 0.20*questions + 0.20*balance + 0.25*length)`.

These are interpretable hand-written weights, not a trained score ([`app/ai/death_zone.py:83-142`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/death_zone.py:83)). At least eight usable messages and two identified participants are needed; otherwise the result is `insufficient_data`, score `None`, low confidence, and no route to suggestions. `engagement_change = recent_index - baseline_index`. Status is `possible_disengagement` at change ≤ -25, `declining` at ≤ -15, otherwise `stagnant` if recent index < 40, else `healthy`. Confidence is `medium` only with ≥24 usable messages and baseline; otherwise low. Score is `clamp(100 - recent_index + 0.8*max(0,-engagement_change), 0, 100)` ([`app/ai/death_zone.py:242-336`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/death_zone.py:242)).

`is_death_zone()` is true only when score is at least 60 and status is `stagnant`, `declining`, or `possible_disengagement`; insufficient data cannot trigger. This is the actual routing threshold, with optional helper argument `threshold=60` ([`app/ai/death_zone.py:339-364`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/death_zone.py:339)). `signals` contain explanatory text for recent brevity, low questions, uneven participation, and changes from baseline. These signals do not independently route the graph.

False positives are limited by the minimum message/participant requirement, baseline requirement for decline labels, a 60 score threshold, and the fact that the score is explicitly documented as not a probability. There is no calibration against labeled production outcomes in the inspected code. A “healthy” conversation ends the graph without invoking suggestion generation.

## 6. LangGraph Workflow

`ConversationState` is a `TypedDict(total=False)` with inputs `db`, `requesting_user_id`, `requesting_user`, `messages`; detector outputs `death_zone`, `should_generate`; result fields `suggestion_result`, `error` ([`app/ai/graph.py:10-23`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/graph.py:10)). The graph has nodes `detect_death_zone`, `generate_suggestions`, and `finish`. `START` leads to detection; `route_after_detection()` sends true to generation and false to finish; both lead to `END` ([`app/ai/graph.py:91-129`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/graph.py:91)).

```text
START -> detect_death_zone -> should_generate?
                              ├─ true  -> generate_suggestions -> END
                              └─ false -> finish -> END
```

The detector node stores the full detector dictionary and routing bool. The generator validates that DB session, requester ID/name, and non-empty message list exist before calling `app.ai.suggestions.suggest_next_messages()`. Exceptions are not caught in graph state: the declared `error` field is initialized to `None` by detection but never populated by an error-handling node. The REST route is the catch boundary and returns a generic 500 on any graph exception ([`app/ai/graph.py:26-88`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/graph.py:26)). A successful graph output includes the detector dictionary and `should_generate`, plus `suggestion_result` or `None`.

## 7. Embeddings and Memory

`UserMemory` is a PostgreSQL table model with `user_id`, text, type, confidence, optional source message ID, 384-dimensional vector, and creation time. It has ordinary user and user/type indexes; the model declares no pgvector ANN index ([`app/models.py:386-429`](/Users/sandeepsharma/Desktop/bugzyme-new/app/models.py:386)). `generate_embedding()` uses the multilingual SentenceTransformer and normalized vectors. `save_memory()` prevents case-insensitive exact duplicate text for the same user, embeds the text, and stores an optional `source_message_id` ([`app/ai/memory.py`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/memory.py)). Memory extraction is opt-in (`users.ai_memory_enabled`, default false), processes only the requesting user’s own authored messages in bounded batches, allows durable preferences/interests/communication style/goals/projects at confidence ≥0.7, and records a high-water message ID. `/me/ai-memories` supports private list/edit/delete/clear operations; disabling memory also prevents retrieval into prompts. Migration `a41d9e7c2b60` adds the opt-in and processing-cursor fields.

`search_memories()` embeds the supplied query, limits search to one `user_id`, orders by pgvector cosine distance, asks for at most 10 candidates by default, then filters by default cosine similarity ≥0.30 ([`app/ai/memory.py:203-269`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/memory.py:203)). `rerank_memories()` deduplicates, optionally applies keyword-based topic filtering, scores `[query, memory_text]` pairs using the CrossEncoder, sorts by `(intent_match, rerank_score, similarity)`, and returns at most five by default ([`app/ai/memory.py:276-385`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/memory.py:276)). The live suggestion flow requests up to 10 candidates and keeps at most four only where `intent_match == 1` ([`app/ai/suggestions.py:15-18`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:15), [`app/ai/suggestions.py:397-450`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:397)).

This is actual retrieval-augmented prompt context: retained memory text is inserted into the generation prompt only while the requesting user has memory enabled. Opted-in extraction calls `extract_memories()` and persists eligible output through `save_memory()`. `extract_interests()` remains isolated and does not save to a separate interest table. The repository has no Alembic migration referencing `user_memories`; `app/main.py` calls `Base.metadata.create_all()` at startup, which attempts to create model-declared tables. Database extension setup is not shown in the migrations inspected.

## 8. Prompt Engineering

The active suggestion prompts are in `app/ai/suggestions.py`. The conversation-analysis prompt treats transcript data as untrusted, demands five short fields, and has JSON repair/fallback behavior. The generation prompt makes the transcript the source of truth, prioritizes the final message, disallows invented plans/facts, respects consent, and asks for three distinct styles. The relevance-check prompt separately asks the same model to judge each suggestion against the latest message. Generation and relevance prompts both label conversation text as untrusted data ([`app/ai/suggestions.py:452-659`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:452), [`app/ai/suggestions.py:854-1003`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:854)).

`app/ai/extraction.py` has a separate long-term memory extraction system prompt with privacy-sensitive extraction restrictions: it forbids credentials, unnecessary sensitive details, unsupported psychological inference, and instructs the model to ignore instructions embedded in conversations ([`app/ai/extraction.py:13-129`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/extraction.py:13)). `interest_extraction.py` has its own per-speaker interest prompt ([`app/ai/interest_extraction.py:6-63`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/interest_extraction.py:6)).

## 9. Language Detection and Validation

`_detect_language()` is a lightweight marker-count heuristic, not a language-identification library. It counts Devanagari characters and matches Latin tokens against hard-coded English and Roman-Hindi word sets. It returns `english`, `hindi`/Devanagari, or `hinglish`/Roman script ([`app/ai/suggestions.py:167-268`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:167)). The generation prompt is augmented with explicit language and script instructions. Validators reject Hinglish candidates with no Hindi markers and reject Devanagari for Hinglish; Hindi candidates need at least one Devanagari character ([`app/ai/suggestions.py:792-829`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:792)).

Validation requires exactly one each of the three styles, up to 20 words, non-duplicate messages, valid JSON, nonempty text, adequate analysis fields, and no unsupported date/time/venue details. Relevance is checked by another Groq request and can trigger a full regeneration attempt. Hinglish Devanagari validation runs separately for each suggestion.

## 10. Reranking and Suggestion Quality

There are two different ranking/quality mechanisms. The CrossEncoder in `memory.py` ranks **memories**, not the three generated replies. Suggestions are filtered by deterministic structural/language/length/factual checks and a second Groq-based relevance judgment. There is no CrossEncoder reranking of candidate reply text. Unrelated suggestions, malformed JSON, duplicate styles, duplicate/near-substring replies, word-count violations, and unsupported specifics can cause regeneration ([`app/ai/suggestions.py:661-847`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:661), [`app/ai/suggestions.py:854-1153`](/Users/sandeepsharma/Desktop/bugzyme-new/app/ai/suggestions.py:854)).

## 11. Database and Data Flow

AI reads ordinary `messages` records through the suggestion endpoint and vector memory rows through `UserMemory`. Relevant tables/models are `User`, `Chat`, `Message`, `MessageReaction`, and `UserMemory` in `app/models.py`; only the first four represent chat product data, and `UserMemory` is the AI-specific table. `MessageResponse` exposes message text/type and delivery/read fields, but the AI suggestion route returns its own dictionary rather than a Pydantic response model ([`app/schemas.py:81-119`](/Users/sandeepsharma/Desktop/bugzyme-new/app/schemas.py:81)).

The suggestion route response currently has this actual shape:

```json
{
  "chat_id": 123,
  "death_zone": {"status": "...", "death_zone_score": 0.0},
  "should_generate": true,
  "suggestions": [{"style": "natural", "message": "..."}],
  "analysis": {},
  "memories_used": []
}
```

The object shown is a shape summary, not a captured production response; actual detector and suggestion contents vary. The route does not declare `response_model` and this endpoint is the only backend response in the source that carries death-zone results ([`app/main.py:1982-2004`](/Users/sandeepsharma/Desktop/bugzyme-new/app/main.py:1982)).

## 12. Frontend and Backend Integration

`index.html` contains the page structure, CSS, application state, REST helper, WebSocket handling, message rendering, and AI suggestion panel. The AI button and `aiSuggestionsDot` are adjacent in the composer markup ([`index.html:2448-2458`](/Users/sandeepsharma/Desktop/bugzyme-new/index.html:2448)). `openChat()` updates `APP.currentChatId` and invokes `updateDeathZoneDot(chatId)` ([`index.html:3675-3686`](/Users/sandeepsharma/Desktop/bugzyme-new/index.html:3675)). The WebSocket handler handles chat events such as messages/read receipts and does not handle a death-zone or suggestion event ([`app/main.py:2015-2529`](/Users/sandeepsharma/Desktop/bugzyme-new/app/main.py:2015)).

There is no AI event broadcast from backend. AI is synchronous REST, and chat message WebSockets do not trigger or report this workflow. Existing REST response can carry the decision, so a WebSocket addition is not required for the requested dot behavior.

## 13. Death-Zone Green Dot Indicator

### What exists now

The HTML has a small `#aiSuggestionsDot` span styled by `.ai-alert-dot`; it is now green. The previous chat-open implementation called `POST /chats/{chat_id}/death-zone`, but no such backend route exists. That call has been removed. `updateDeathZoneDot(chatId)` now restores only a per-chat frontend result recorded after a successful suggestions request. `openAISuggestions()` consumes the existing `POST /chats/{chat_id}/suggestions` response and enables the dot only when the returned `chat_id` matches, `should_generate === true`, and three nonempty suggestions were returned ([`index.html:3171-3223`](/Users/sandeepsharma/Desktop/bugzyme-new/index.html:3171)).

### Implemented connection and remaining boundary

1. **UI location:** the dot remains beside `#aiSuggestionsBtn` in the existing composer.
2. **Backend result:** backend code did not need modification. `get_chat_suggestions()` already returns `chat_id`, `should_generate`, `death_zone`, and `suggestions`; the route only returns a normal response after graph success. A thrown detector/suggestion failure returns HTTP 500.
3. **Visibility condition:** frontend requires matching response/chat IDs, `should_generate === true`, and exactly three usable suggestions. The graph's `should_generate` value comes from `is_death_zone()` and is the backend's authoritative route decision.
4. **Chat scoping / stale data:** `DEATH_ZONE_SUGGESTION_STATE` stores results by chat ID for the current page session. `CHAT_MESSAGE_REVISIONS` prevents an in-flight result from showing if messages changed during generation. Switching chats restores that chat's own state. New sent/received messages and message deletions clear its old indicator; healthy results, errors, chat deletion, and logout also clear relevant state.
5. **Healthy or insufficient conversation:** backend returns `should_generate=false` and no suggestions, so no dot is shown.
6. **Generation failure:** the caught request error clears the state, so no dot is shown.
7. **Normal suggestions:** there is no separate normal-suggestions API in this source. The dot is based on the graph route flag, not the button click or messages alone. If a normal suggestion route is added later, it must not reuse this positive condition without a server-side cause signal.
8. **Remaining product boundary:** indicator state is page-session-only; a browser reload clears it. It is shown after the user invokes suggestions and successful generation completes, not immediately on chat open. Immediate pre-generation visibility would require a distinct backend signal plus a definition for how to establish successful workflow trigger, or server-persisted workflow state; current code does not provide that.

The green dot is now wired end-to-end through the existing API response and the frontend. The backend response contract and AI generation behavior were not changed. The dot is intentionally cleared when conversation messages change, because the previous detection/generation result then describes stale input. It is shown only after successful generation, and it is not persisted across browser reloads.

## 14. Testing and Results

### Test source coverage found

| Test file | What it checks | External dependency / limitation |
|---|---|---|
| `test_death_zone.py` | Insufficient data, healthy, stagnant, decline, invalid inputs and threshold validation | Pure detector tests |
| `test_graph.py` | Graph nodes/routing and mocked suggestion generation | Imports app/database modules |
| `test_graph_edge_cases.py` | Missing state fields, error propagation, healthy skip, death-zone call | Some tests create `SessionLocal` |
| `test_graph_integration.py` | Actual detector plus mocked generation; healthy/insufficient skip and death-zone route | No Groq call by design, but imports app dependencies |
| `test_suggestion_quality.py` | Relevance failure causes regeneration; model steps mocked | Mock-based |
| `test_multilingual_conversation.py` | English/Hinglish real suggestion generation and style/language checks | Real Groq calls; not run |
| `test_conversation.py`, `test_personalized_reply.py` | Example real conversation/suggestion flows | Database and/or Groq; not run |
| `test_graph_live.py` | Live detector + graph + suggestion output | Database and Groq; not run |
| `test_memory.py`, `test_memory_save.py` | Save/search and duplicate persistence | Real database and local embedding model; may write persistent records |
| `test_extraction.py`, `test_interest_extraction.py` | Real extraction helpers | Groq; not run |
| `test_interest_extraction.py` | Speaker interest extraction and returned data shape | Groq; no save path |

**Execution:** `pytest` could not be run because the `pytest` command is not installed in this environment. The environment had no `DATABASE_URL` or `GROQ_API_KEY`, so DB-backed, model-backed, and paid/external API tests were intentionally not attempted; no dependencies were installed. I did execute the pure detector against the fixtures equivalent to `test_graph_integration.py`: healthy fixture => `healthy`, score `14.2`, confidence `medium`, change `0.0`, `is_death_zone=False`; short-message fixture => `stagnant`, score `77.9`, confidence `medium`, change `0.0`, `is_death_zone=True`. These are actual local function outputs, not mocked assertions. They do not prove the LangGraph or API works end-to-end. For the green-dot implementation, the complete inline JavaScript block passed `node --check`. A browser-free harness using the actual extracted frontend functions verified: death-zone + 3 replies shows the dot; healthy response, normal suggestions, mismatched chat ID, changed conversation during generation, and request failure all keep it hidden. `git diff --check` passed. Visual browser verification was unavailable because the local `file://` URL is blocked by the browser security policy.

No test can be called passing or failing beyond those manual detector executions because the repository suite did not run.

## 15. File-by-File Explanation

| File | Responsibility | Important functions/classes | Connections |
|---|---|---|---|
| `app/main.py` | FastAPI entry point, auth, REST, WebSocket and product message persistence | `get_chat_suggestions`, `process_message`, `handle_socket`, `mark_read` | Imports `run_conversation_workflow`; responds to frontend REST and chat sockets |
| `app/ai/graph.py` | Compiled LangGraph orchestration | `ConversationState`, `detect_death_zone_node`, `route_after_detection`, `generate_suggestions_node`, `build_conversation_graph`, `run_conversation_workflow` | Calls detector and active suggestion module |
| `app/ai/death_zone.py` | Deterministic engagement score/status | `_normalize_messages`, `_window_metrics`, `analyze_death_zone`, `is_death_zone` | Graph detector node calls it |
| `app/ai/suggestions.py` | Active AI analysis, memory retrieval, generation, validation | `_format_history`, `_detect_language`, `_retrieve_memories`, `_analyze_conversation`, `_build_generation_prompts`, `_validate_suggestions`, `_check_suggestion_relevance`, `_generate_suggestions`, `suggest_next_messages` | Called by graph; uses Groq client and `memory.py` |
| `app/ai/personalization.py` | Separate/older parallel suggestion implementation | Similar `_detect_language`, `_retrieve_memories`, `_analyze_conversation`, `_generate_suggestions`, `suggest_next_messages` | Referenced by `test_personalized_reply.py`, but no import/call from `app/main.py` or graph |
| `app/ai/memory.py` | Embedding, save, semantic retrieval and CrossEncoder reranking | `generate_embedding`, `save_memory`, `search_memories`, `rerank_memories` | Active suggestion engine retrieves from `UserMemory` |
| `app/ai/extraction.py` | Groq long-term-memory extraction to Python dict list | `get_groq_client`, `extract_memories` | Has no caller in app; output not saved automatically |
| `app/ai/interest_extraction.py` | Per-speaker interest extraction to JSON-derived dict | `extract_interests` | Test-only call found; no persistence/use in suggestions |
| `app/models.py` | SQLAlchemy models, including vector memory table | `UserMemory`, `Message`, `Chat`, `User` | Used by main, database, and memory layer |
| `app/schemas.py` | REST request/response schemas | `MessageResponse`, `ChatSummary`, `UserPublic` | General chat API; suggestion endpoint returns unmodeled dict |
| `app/database.py` | SQLAlchemy engine/session/Base | `get_db` | Backend and AI memory DB sessions |
| `app/connection_manager.py` | WebSocket registration and targeted delivery | `ConnectionManager`, `send_to_user`, `is_watching` | Used by `app/main.py`; no AI event-specific code |
| `index.html` | All-in-one frontend and AI suggestion UI | `openChat`, `updateDeathZoneDot`, `setDeathZoneSuggestionState`, `openAISuggestions`, `closeAISuggestions` | Calls suggestions API and consumes its actual death-zone/success fields; session-scoped dot |
| `test_death_zone.py` | Unit tests for detector | pytest test functions | Calls `death_zone.py` |
| `test_graph.py`, `test_graph_edge_cases.py`, `test_graph_integration.py` | Graph routing and error behavior tests | graph test functions | Use mocks for model generation; some edge cases open DB sessions |
| `test_suggestion_quality.py` | Mock-based retry/quality test | `test_generate_suggestions_retries_when_relevance_fails` | Tests active `suggestions.py` |
| `test_multilingual_conversation.py`, `test_conversation.py`, `test_personalized_reply.py`, `test_graph_live.py` | Example/live multilingual, graph and suggestion checks | `main()` / helpers | Use Groq and/or DB; not safe for this no-credentials inspection |
| `test_extraction.py`, `test_interest_extraction.py`, `test_memory.py`, `test_memory_save.py` | Extraction and memory samples | scripts | Real Groq, DB, or embedding model depending on file |
| `app/ai/suggestions.py.save` | Saved alternate/older suggestion implementation | duplicate helper/generation functions | No application import/reference found |

Important call chain and I/O:

1. `get_chat_suggestions(chat_id, current_user, db)` reads chat membership and recent message rows; returns a dictionary or HTTP error; calls `run_conversation_workflow()`.
2. `run_conversation_workflow(db, requesting_user_id, requesting_user, messages)` passes these values to `conversation_graph.invoke()` and returns graph state.
3. `detect_death_zone_node(state)` accepts messages and returns `death_zone`, `should_generate`, `suggestion_result=None`, `error=None`.
4. `route_after_detection(state)` returns node name `generate_suggestions` or `finish` based only on `should_generate`.
5. `generate_suggestions_node(state)` calls `suggest_next_messages(db, requesting_user_id, requesting_user, messages)` and returns `suggestion_result`.
6. `suggest_next_messages(...)` returns analysis, used memory text, and three suggestions; failures raise, then backend translates the error to HTTP 500.
7. `openAISuggestions()` sends REST request, renders suggestion cards and “Use reply” handlers; currently it hides the death-zone dot rather than reading this response's detection flag.

## 16. Implemented vs Partially Implemented Features

### Fully implemented in source

- Deterministic detector and threshold-based graph routing.
- Authenticated, membership-checked suggestions endpoint that loads recent text messages and calls the LangGraph workflow.
- Groq-based conversation analysis and three-style reply generation with parsing, structural checks, retries and an LLM relevance check.
- User-scoped vector memory search and prompt-context inclusion **when memory records exist**.
- Frontend suggestion panel and use-reply interaction.

### Partially implemented / disconnected

- Long-term memory extraction is connected to suggestions only after explicit opt-in; user-scoped list/edit/delete/clear routes manage the resulting memories.
- `save_memory()` and `search_memories()` are connected. The `UserMemory` table is created through SQLAlchemy metadata at startup rather than an inspected Alembic migration.
- Interest extraction returns per-speaker lists but nothing stores or consumes them.
- `personalization.py` is retained as a compatibility wrapper; graph/API use the canonical `suggestions.py` implementation.
- Green dot is driven by the successful suggestions response; no separate pre-generation detector endpoint exists.

### Not implemented / potential gaps

- No backend `POST /chats/{chat_id}/death-zone` endpoint (not required by the implemented dot flow, which uses the existing suggestions response).
- No AI suggestion/death-zone WebSocket event, background job, or automatic trigger on message arrival.
- No reply CrossEncoder reranking.
- No tested/persisted detector history or learned calibration; each API request recomputes current heuristics from messages.
- No automatic database-backed per-speaker interest profile.

## 17. Technical Limitations and Improvement Opportunities

These are observations for later work, not changes made here.

- **Duplicate logic:** `personalization.py` is now a small compatibility wrapper over `suggestions.py`. `suggestions.py.save` remains an unreferenced saved copy and is not part of runtime.
- **Hard-coded detector policy:** 12-message window, 8-message floor, six-message baseline, weights, status cutoffs (-15/-25 and index 40), and routing score 60 are fixed constants. The detector itself notes the threshold needs labeled calibration.
- **Potential AI cost/latency:** an ordinary successful suggestion call may make separate Groq calls for analysis, generation, and relevance; generation can retry and model calls may retry on empty/truncated output. Memory CrossEncoder inference and embeddings also run in the request path. Exact latency/cost is provider/model/account dependent and was not measured.
- **Vector-search scale:** source shows cosine-distance ordering and limit 10 but no ANN index declaration; this may require scanning many per-user memories as that table grows. Verify deployed PostgreSQL extension/index state before changing schema.
- **Memory coverage:** extraction sees up to the most recent 60 chat text messages at suggestion time and advances in batches of 30 own-authored messages; older history is outside the route's current window. Memories are global to the user's account, not tied to one chat.
- **Language validator:** Hinglish Devanagari checks now run independently for each suggestion.
- **Error-state mismatch:** graph state declares `error`, but exceptions propagate instead of being represented there. The HTTP route catches broadly and returns a generic 500; frontend can show error text but cannot distinguish provider, validation, or internal failures.
- **Privacy/data handling:** AI memory is off by default and requires explicit opt-in. The user can list, edit, delete individual memories, or clear all; extraction only retains allowlisted durable memory types from their own authored messages. Conversation text and selected memories are still sent to Groq for suggestions; this is a code observation, not a statement about provider or deployment policies.
- **DB migration coverage:** `UserMemory` is defined in ORM and `create_all()` is called on app startup; no Alembic migration referencing `user_memories` was found. Deployment should verify schema setup and pgvector extension availability rather than assuming migrations create it.
- **Green dot consistency:** current implementation uses the successful graph response, scopes the dot by chat, rejects in-flight results after message changes, and clears on healthy/failure/new messages. State is not persisted across reloads; pre-generation indication would need a separate product/backend flow.
- **Test gaps/status:** there are unit, graph, integration-style, quality, multilingual, and live scripts, but local full-suite status could not be verified here. Live scripts may call Groq and database scripts can persist test rows; they should be run only in a configured test environment.

### Scenario walk-throughs

These use the real detector behavior; only the two fixture scores below were executed locally. Downstream suggestion examples are descriptive, not captured API outputs.

**Scenario 1 — healthy conversation:** User opens AI suggestions, backend reads up to 60 recent text messages, detector calculates a healthy status / score below the 60 routing threshold, graph sets `should_generate=False`, takes `finish`, and returns an empty `suggestions` list. The frontend shows its healthy/no-suggestions message and keeps the dot hidden.

**Scenario 2 — low engagement:** With the actual integration fixture of 24 short messages alternating between two senders, local detector output was `status=stagnant`, `death_zone_score=77.9`, `confidence=medium`, `engagement_change=0.0`, `is_death_zone=True`. The graph route calls `suggest_next_messages`; on success the REST route includes `should_generate=true` and three suggestions. The frontend then shows the green dot for that chat only. If a new message arrives before the response, the revision check rejects the stale dot.

**Scenario 3 — detector positive, generator failure:** Detector sets `should_generate=True`; generation node then may fail from DB/memory/model/validation or other exceptions. The graph does not convert the failure into `error` state; it propagates. `get_chat_suggestions()` logs the exception and returns HTTP 500. The frontend catch handler displays a failure message. The dot should remain hidden because suggestions did not successfully return. Current frontend catches the error but has no explicit success-coupled dot update; `updateDeathZoneDot()` is an unrelated failed request to the missing endpoint.
