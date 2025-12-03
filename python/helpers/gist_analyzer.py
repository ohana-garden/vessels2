"""
Vessels Gist Analyzer

Extracts understanding from multi-party conversations to drive canvas generation.
Analyzes what's being discussed, what participants want, and what visual content
would best illuminate the conversation.
"""

import asyncio
import json
from typing import Any, Optional, List, Dict, TYPE_CHECKING
from dataclasses import dataclass

from python.helpers.canvas import (
    ConversationRoom,
    ConversationGist,
    ConversationTurn,
    CanvasContentType,
    EmotionalState,
    EntityAgent,
    HumanProxy,
)
from python.helpers.print_style import PrintStyle
from python.helpers import dirty_json

if TYPE_CHECKING:
    from agent import Agent


# =============================================================================
# Gist Analysis Prompts
# =============================================================================

GIST_SYSTEM_PROMPT = """You analyze multi-party conversations to extract their essence.

The conversations involve:
- Human proxies: Represent humans in specific roles (gardener, coordinator, neighbor)
- Entity agents: Represent non-human things (plants, machines, places, biomes)

Your job is to understand:
1. What topics are being discussed
2. What the participants are trying to accomplish
3. What entities/locations/times are mentioned
4. The emotional tone of the conversation
5. What visual content would illuminate the discussion

Output valid JSON matching the schema provided."""

GIST_ANALYSIS_PROMPT = """Analyze this conversation and extract its gist.

PARTICIPANTS:
{participants}

RECENT CONVERSATION:
{conversation}

CURRENT CANVAS:
{canvas_state}

Extract:
1. topics: List of topic keywords being discussed
2. intent: What participants are trying to accomplish (one sentence)
3. entities_discussed: IDs of entities mentioned in conversation
4. locations_mentioned: Any locations with lat/lng if known, or names
5. time_references: Any dates, times, or scheduling mentioned
6. emotional_tone: One of: neutral, excited, stressed, confused, frustrated, satisfied, curious, urgent
7. suggested_content: What canvas content types would help. Options: map, calendar, visualization, gallery, entity_view, relationship, ambient
8. action_items: Any tasks or actions mentioned
9. questions_pending: Any unanswered questions

JSON schema:
{{
    "topics": ["topic1", "topic2"],
    "intent": "string describing goal",
    "entities_discussed": ["entity_id1", "entity_id2"],
    "locations_mentioned": [{{"name": "string", "lat": number, "lng": number}}],
    "time_references": ["tomorrow morning", "next Tuesday"],
    "emotional_tone": "neutral|excited|stressed|confused|frustrated|satisfied|curious|urgent",
    "suggested_content": ["map", "calendar"],
    "action_items": ["action1", "action2"],
    "questions_pending": ["question1"]
}}

Respond with only valid JSON."""


CONTENT_PREDICTION_PROMPT = """Based on the conversation gist, predict what content should be generated.

GIST:
{gist}

AVAILABLE ENTITIES:
{entities}

CURRENT CANVAS:
{canvas_state}

For each suggested content type, specify what exactly to show:

If map is suggested:
- What locations to show
- Any routes to draw
- What to highlight

If calendar is suggested:
- What time range
- What events to show
- What to highlight

If visualization is suggested:
- What data to show
- What chart type
- What to emphasize

If gallery is suggested:
- What images
- Related to which entities

If entity_view is suggested:
- Which entity to focus on
- What aspects to show

Output as JSON:
{{
    "content_specs": [
        {{
            "type": "map|calendar|visualization|gallery|entity_view|ambient",
            "spec": {{ ...type-specific details... }},
            "priority": 1-10,
            "reason": "why this content helps"
        }}
    ],
    "ambient_mood": "calm|energetic|focused|celebratory|concerned"
}}"""


# =============================================================================
# Gist Analyzer
# =============================================================================

class GistAnalyzer:
    """
    Analyzes conversations to extract meaning and drive canvas generation.
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self._last_analysis: Optional[ConversationGist] = None
        self._analysis_lock = asyncio.Lock()

    async def analyze(self, room: ConversationRoom,
                      force: bool = False) -> ConversationGist:
        """
        Analyze the current conversation state.

        Args:
            room: The conversation room to analyze
            force: Force re-analysis even if recent

        Returns:
            ConversationGist with extracted understanding
        """
        async with self._analysis_lock:
            # Get conversation context
            participants_text = self._format_participants(room)
            conversation_text = room.get_conversation_text(20)
            canvas_text = self._format_canvas(room)

            # Skip if no new content
            if not conversation_text and not force:
                return room.gist

            try:
                # Call LLM for analysis
                result = await self.agent.call_utility_model(
                    system=GIST_SYSTEM_PROMPT,
                    message=GIST_ANALYSIS_PROMPT.format(
                        participants=participants_text,
                        conversation=conversation_text,
                        canvas_state=canvas_text,
                    ),
                )

                # Parse response
                gist_data = dirty_json.try_parse(result)
                if not gist_data:
                    PrintStyle.error(f"Failed to parse gist: {result}")
                    return room.gist

                # Build ConversationGist
                gist = ConversationGist(
                    topics=gist_data.get("topics", []),
                    intent=gist_data.get("intent", ""),
                    entities_discussed=gist_data.get("entities_discussed", []),
                    locations_mentioned=gist_data.get("locations_mentioned", []),
                    time_references=gist_data.get("time_references", []),
                    emotional_tone=EmotionalState(
                        gist_data.get("emotional_tone", "neutral")
                    ),
                    suggested_content=[
                        CanvasContentType(c) for c in gist_data.get("suggested_content", [])
                        if c in [e.value for e in CanvasContentType]
                    ],
                    action_items=gist_data.get("action_items", []),
                    questions_pending=gist_data.get("questions_pending", []),
                )

                # Update room
                room.update_gist(gist)
                self._last_analysis = gist
                return gist

            except Exception as e:
                PrintStyle.error(f"Gist analysis failed: {e}")
                return room.gist

    async def predict_content(self, room: ConversationRoom) -> List[Dict]:
        """
        Predict what canvas content should be generated.

        Returns list of content specifications.
        """
        gist = room.gist
        if not gist.suggested_content:
            return []

        # Format context
        entities_text = self._format_entities(room)
        canvas_text = self._format_canvas(room)

        try:
            result = await self.agent.call_utility_model(
                system="You generate content specifications for a dynamic UI canvas.",
                message=CONTENT_PREDICTION_PROMPT.format(
                    gist=json.dumps(gist.to_dict(), indent=2),
                    entities=entities_text,
                    canvas_state=canvas_text,
                ),
            )

            prediction = dirty_json.try_parse(result)
            if not prediction:
                return []

            return prediction.get("content_specs", [])

        except Exception as e:
            PrintStyle.error(f"Content prediction failed: {e}")
            return []

    async def should_update_canvas(self, room: ConversationRoom,
                                   turns_since_update: int = 3) -> bool:
        """
        Determine if the canvas should be updated based on conversation flow.

        Factors considered:
        - Number of turns since last update
        - Topic changes
        - Entity mentions
        - Emotional state changes
        """
        recent_turns = room.get_recent_turns(turns_since_update)
        if len(recent_turns) < turns_since_update:
            return False

        # Check for topic keywords that suggest visual content
        visual_triggers = [
            "show", "see", "look", "map", "where", "when", "schedule",
            "calendar", "photo", "picture", "graph", "chart", "data",
            "route", "location", "place", "here", "there",
        ]

        for turn in recent_turns:
            content_lower = turn.content.lower()
            if any(trigger in content_lower for trigger in visual_triggers):
                return True

        # Check for entity mentions
        for turn in recent_turns:
            if turn.references_canvas:
                return True

        # Check emotional state changes
        if room.gist.emotional_tone in [
            EmotionalState.CONFUSED,
            EmotionalState.CURIOUS,
            EmotionalState.EXCITED,
        ]:
            return True

        return False

    def _format_participants(self, room: ConversationRoom) -> str:
        """Format participants for prompt."""
        lines = []
        for p in room.get_active_participants():
            ptype = p.participant_type.value.replace("_", " ").title()
            if isinstance(p, HumanProxy):
                lines.append(f"- {p.name} ({ptype}, role: {p.role})")
            elif isinstance(p, EntityAgent):
                lines.append(f"- {p.name} ({ptype}, kind: {p.entity_kind.value})")
            else:
                lines.append(f"- {p.name} ({ptype})")
        return "\n".join(lines) if lines else "No participants"

    def _format_entities(self, room: ConversationRoom) -> str:
        """Format entity agents for prompt."""
        lines = []
        for entity in room.get_entity_agents():
            lines.append(f"- {entity.id}: {entity.name} ({entity.entity_kind.value})")
            if entity.location:
                lines.append(f"  Location: {entity.location}")
            if entity.entity_data:
                lines.append(f"  Data: {json.dumps(entity.entity_data)}")
        return "\n".join(lines) if lines else "No entities"

    def _format_canvas(self, room: ConversationRoom) -> str:
        """Format current canvas state for prompt."""
        elements = room.get_canvas_state()
        if not elements:
            return "Canvas is empty"

        lines = []
        for el in elements:
            lines.append(f"- {el['contentType']}: {el['content'].get('title', 'Untitled')}")
        return "\n".join(lines)


# =============================================================================
# Content Generator
# =============================================================================

class ContentGenerator:
    """
    Generates canvas content based on conversation gist and predictions.
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self.analyzer = GistAnalyzer(agent)

    async def generate_for_room(self, room: ConversationRoom) -> List[Dict]:
        """
        Generate appropriate canvas content for the current conversation.

        Returns list of generated canvas elements.
        """
        # First analyze the conversation
        gist = await self.analyzer.analyze(room)

        # Get content predictions
        predictions = await self.analyzer.predict_content(room)

        generated = []
        for spec in predictions:
            try:
                element = await self._generate_element(room, spec)
                if element:
                    generated.append(element.to_dict())
            except Exception as e:
                PrintStyle.error(f"Failed to generate {spec.get('type')}: {e}")

        return generated

    async def _generate_element(self, room: ConversationRoom,
                                spec: Dict) -> Optional[Any]:
        """Generate a specific canvas element from specification."""
        content_type = spec.get("type")
        content_spec = spec.get("spec", {})
        priority = spec.get("priority", 5)

        if content_type == "map":
            return room.generate_map(
                title=content_spec.get("title", "Map"),
                locations=content_spec.get("locations", []),
                center=content_spec.get("center"),
                zoom=content_spec.get("zoom", 12),
                routes=content_spec.get("routes", []),
                priority=priority,
            )

        elif content_type == "calendar":
            return room.generate_calendar(
                title=content_spec.get("title", "Schedule"),
                events=content_spec.get("events", []),
                view=content_spec.get("view", "week"),
                highlighted=content_spec.get("highlighted", []),
                priority=priority,
            )

        elif content_type == "visualization":
            return room.generate_visualization(
                title=content_spec.get("title", "Data"),
                data=content_spec.get("data", {}),
                chart_type=content_spec.get("chartType", "bar"),
                priority=priority,
            )

        elif content_type == "gallery":
            return room.generate_gallery(
                title=content_spec.get("title", "Gallery"),
                images=content_spec.get("images", []),
                layout=content_spec.get("layout", "grid"),
                priority=priority,
            )

        elif content_type == "entity_view":
            entity_id = content_spec.get("entityId")
            entity = room.get_participant(entity_id)
            if isinstance(entity, EntityAgent):
                return room.generate_entity_view(
                    entity=entity,
                    priority=priority,
                )

        elif content_type == "ambient":
            return room.generate_ambient(
                mood=content_spec.get("mood", "calm"),
                imagery=content_spec.get("imagery", {}),
                priority=0,
            )

        return None

    async def update_on_turn(self, room: ConversationRoom,
                             turn: "ConversationTurn") -> bool:
        """
        Check if canvas should update after a turn and generate if needed.

        Returns True if canvas was updated.
        """
        # Check if update is warranted
        should_update = await self.analyzer.should_update_canvas(room)

        if should_update:
            generated = await self.generate_for_room(room)
            return len(generated) > 0

        return False


# =============================================================================
# Emotional Context (Hume.ai Integration)
# =============================================================================

class EmotionalContext:
    """
    Tracks emotional state from voice input (Hume.ai integration point).

    This adapts agent responses and canvas content based on detected emotions.
    """

    def __init__(self):
        self._current_state: Dict[str, EmotionalState] = {}  # participant_id -> state
        self._emotional_history: List[Dict] = []
        self._thresholds = {
            "excitement": 0.7,
            "frustration": 0.6,
            "confusion": 0.5,
            "stress": 0.6,
            "satisfaction": 0.7,
        }

    def update_emotional_state(self, participant_id: str,
                               emotions: Dict[str, float]) -> EmotionalState:
        """
        Update emotional state for a participant based on Hume.ai metrics.

        Args:
            participant_id: The participant whose emotion was detected
            emotions: Dict of emotion -> confidence (0-1)

        Returns:
            The determined EmotionalState
        """
        # Map Hume emotions to our states
        state = self._determine_state(emotions)
        self._current_state[participant_id] = state

        # Record history
        self._emotional_history.append({
            "participant_id": participant_id,
            "emotions": emotions,
            "state": state.value,
            "timestamp": asyncio.get_event_loop().time(),
        })

        # Keep only recent history
        if len(self._emotional_history) > 100:
            self._emotional_history = self._emotional_history[-100:]

        return state

    def _determine_state(self, emotions: Dict[str, float]) -> EmotionalState:
        """Determine overall emotional state from emotion scores."""
        # Check thresholds in priority order
        if emotions.get("excitement", 0) >= self._thresholds["excitement"]:
            return EmotionalState.EXCITED
        if emotions.get("frustration", 0) >= self._thresholds["frustration"]:
            return EmotionalState.FRUSTRATED
        if emotions.get("stress", 0) >= self._thresholds["stress"]:
            return EmotionalState.STRESSED
        if emotions.get("confusion", 0) >= self._thresholds["confusion"]:
            return EmotionalState.CONFUSED
        if emotions.get("curiosity", 0) >= 0.5:
            return EmotionalState.CURIOUS
        if emotions.get("satisfaction", 0) >= self._thresholds["satisfaction"]:
            return EmotionalState.SATISFIED
        if emotions.get("urgency", 0) >= 0.6:
            return EmotionalState.URGENT

        return EmotionalState.NEUTRAL

    def get_state(self, participant_id: str) -> EmotionalState:
        """Get current emotional state for a participant."""
        return self._current_state.get(participant_id, EmotionalState.NEUTRAL)

    def get_adaptation_hints(self, participant_id: str) -> Dict[str, Any]:
        """
        Get hints for adapting responses based on emotional state.

        Returns dict with:
        - pace: speaking pace adjustment
        - tone: tone adjustment
        - detail_level: how much detail to provide
        - reassurance: whether to add reassuring elements
        """
        state = self.get_state(participant_id)

        adaptations = {
            EmotionalState.NEUTRAL: {
                "pace": "normal",
                "tone": "balanced",
                "detail_level": "moderate",
                "reassurance": False,
            },
            EmotionalState.EXCITED: {
                "pace": "energetic",
                "tone": "enthusiastic",
                "detail_level": "concise",
                "reassurance": False,
            },
            EmotionalState.STRESSED: {
                "pace": "calm",
                "tone": "reassuring",
                "detail_level": "simple",
                "reassurance": True,
            },
            EmotionalState.CONFUSED: {
                "pace": "slow",
                "tone": "patient",
                "detail_level": "detailed",
                "reassurance": True,
            },
            EmotionalState.FRUSTRATED: {
                "pace": "calm",
                "tone": "empathetic",
                "detail_level": "simple",
                "reassurance": True,
            },
            EmotionalState.SATISFIED: {
                "pace": "normal",
                "tone": "warm",
                "detail_level": "moderate",
                "reassurance": False,
            },
            EmotionalState.CURIOUS: {
                "pace": "normal",
                "tone": "engaging",
                "detail_level": "detailed",
                "reassurance": False,
            },
            EmotionalState.URGENT: {
                "pace": "quick",
                "tone": "focused",
                "detail_level": "essential",
                "reassurance": False,
            },
        }

        return adaptations.get(state, adaptations[EmotionalState.NEUTRAL])


# =============================================================================
# Content Predictor
# =============================================================================

class ContentPredictor:
    """
    Predicts what content might be needed before it's explicitly requested.

    Uses conversation patterns and entity relationships to anticipate needs.
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self._prediction_cache: Dict[str, List[Dict]] = {}

    async def predict_upcoming_needs(self, room: ConversationRoom) -> List[Dict]:
        """
        Predict content that might be needed soon based on conversation flow.

        Returns list of predicted content needs with confidence scores.
        """
        gist = room.gist
        participants = room.get_active_participants()
        predictions = []

        # If discussing locations, predict map need
        if gist.locations_mentioned:
            predictions.append({
                "type": "map",
                "confidence": 0.8,
                "reason": "Locations are being discussed",
                "data": {"locations": gist.locations_mentioned},
            })

        # If discussing times/scheduling, predict calendar need
        if gist.time_references:
            predictions.append({
                "type": "calendar",
                "confidence": 0.7,
                "reason": "Times/dates are being mentioned",
                "data": {"time_references": gist.time_references},
            })

        # If multiple entities involved, predict relationship view
        entity_agents = room.get_entity_agents()
        if len(entity_agents) >= 2 and "relationship" in gist.topics:
            predictions.append({
                "type": "relationship",
                "confidence": 0.6,
                "reason": "Multiple entities in conversation",
                "data": {"entities": [e.id for e in entity_agents]},
            })

        # If discussing specific entity in depth
        for entity_id in gist.entities_discussed:
            entity = room.get_participant(entity_id)
            if isinstance(entity, EntityAgent):
                predictions.append({
                    "type": "entity_view",
                    "confidence": 0.7,
                    "reason": f"{entity.name} is being discussed",
                    "data": {"entity_id": entity_id},
                })

        # If action items accumulating, might want visualization
        if len(gist.action_items) >= 3:
            predictions.append({
                "type": "visualization",
                "confidence": 0.5,
                "reason": "Multiple action items to track",
                "data": {"action_items": gist.action_items},
            })

        # Cache and return
        self._prediction_cache[room.id] = predictions
        return predictions

    async def prefetch_content(self, room: ConversationRoom,
                               generator: ContentGenerator) -> None:
        """
        Pre-generate predicted content for faster display when needed.

        This runs in background to prepare content ahead of time.
        """
        predictions = await self.predict_upcoming_needs(room)

        for prediction in predictions:
            if prediction["confidence"] >= 0.7:
                # High confidence - generate now
                spec = {
                    "type": prediction["type"],
                    "spec": prediction["data"],
                    "priority": int(prediction["confidence"] * 10),
                }
                try:
                    await generator._generate_element(room, spec)
                except Exception as e:
                    PrintStyle.error(f"Prefetch failed for {prediction['type']}: {e}")
