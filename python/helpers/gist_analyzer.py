"""
Vessels Gist Analyzer

Extracts understanding from multi-party conversations using:
- Graphiti: Entity extraction, semantic search, relationship traversal
- Memory: Recall relevant past interactions
- Audio Analysis: Voice emotion detection (Hume.ai integration point)
- Graph Queries: Entity relationships and temporal patterns

No lazy LLM-only analysis - uses the full toolkit.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum

from python.helpers.canvas import (
    ConversationRoom,
    ConversationGist,
    ConversationTurn,
    CanvasContentType,
    EmotionalState,
    EntityAgent,
    HumanProxy,
    Participant,
)
from python.helpers.graph_store import GraphStore, get_graph_store, MemoryArea
from python.helpers.print_style import PrintStyle

if TYPE_CHECKING:
    from agent import Agent


# =============================================================================
# Audio Analysis Integration
# =============================================================================

class AudioFeatures:
    """
    Audio features extracted from voice input.
    Integration point for Hume.ai, Whisper, or other audio analysis.
    """

    def __init__(self):
        self.pitch_mean: float = 0.0
        self.pitch_variance: float = 0.0
        self.speech_rate: float = 0.0  # words per minute
        self.pause_ratio: float = 0.0  # pauses / speech duration
        self.volume_mean: float = 0.0
        self.volume_variance: float = 0.0

        # Hume.ai prosody scores (when available)
        self.prosody_scores: Dict[str, float] = {}

        # Raw emotion predictions
        self.emotion_scores: Dict[str, float] = {}

    @classmethod
    def from_hume_response(cls, hume_data: Dict) -> "AudioFeatures":
        """Parse Hume.ai EVI response into AudioFeatures."""
        features = cls()

        # Extract prosody predictions
        if "prosody" in hume_data:
            prosody = hume_data["prosody"]
            features.prosody_scores = {
                e["name"]: e["score"]
                for e in prosody.get("predictions", [])
            }

        # Extract emotion predictions
        if "emotions" in hume_data:
            features.emotion_scores = {
                e["name"]: e["score"]
                for e in hume_data["emotions"]
            }

        # Extract from models array (Hume API format)
        if "models" in hume_data:
            for model in hume_data.get("models", []):
                if "prosody" in model:
                    for pred in model["prosody"].get("predictions", []):
                        for emotion in pred.get("emotions", []):
                            features.emotion_scores[emotion["name"]] = emotion["score"]

        return features

    @classmethod
    def from_whisper_result(cls, whisper_data: Dict) -> "AudioFeatures":
        """Extract basic features from Whisper transcription result."""
        features = cls()

        # Whisper provides segments with timing
        segments = whisper_data.get("segments", [])
        if segments:
            # Calculate speech rate from segment timing
            total_duration = segments[-1].get("end", 0) - segments[0].get("start", 0)
            total_words = sum(len(s.get("text", "").split()) for s in segments)
            if total_duration > 0:
                features.speech_rate = (total_words / total_duration) * 60

            # Calculate pause ratio
            total_pause = 0
            for i in range(1, len(segments)):
                gap = segments[i].get("start", 0) - segments[i-1].get("end", 0)
                if gap > 0.1:  # Count gaps > 100ms as pauses
                    total_pause += gap

            if total_duration > 0:
                features.pause_ratio = total_pause / total_duration

        return features

    def infer_emotional_state(self) -> Tuple[EmotionalState, float]:
        """
        Infer emotional state from audio features.
        Returns (state, confidence).
        """
        # If we have Hume emotion scores, use them directly
        if self.emotion_scores:
            return self._from_hume_emotions()

        # Otherwise infer from prosody/speech patterns
        return self._from_prosody()

    def _from_hume_emotions(self) -> Tuple[EmotionalState, float]:
        """Map Hume emotion scores to EmotionalState."""
        scores = self.emotion_scores

        # Map Hume emotions to our states
        mappings = [
            (EmotionalState.EXCITED, ["Excitement", "Joy", "Enthusiasm", "Amusement"]),
            (EmotionalState.STRESSED, ["Anxiety", "Fear", "Distress", "Tension"]),
            (EmotionalState.CONFUSED, ["Confusion", "Doubt", "Uncertainty"]),
            (EmotionalState.FRUSTRATED, ["Frustration", "Anger", "Annoyance", "Contempt"]),
            (EmotionalState.SATISFIED, ["Satisfaction", "Contentment", "Relief", "Calmness"]),
            (EmotionalState.CURIOUS, ["Interest", "Curiosity", "Concentration", "Contemplation"]),
            (EmotionalState.URGENT, ["Determination", "Realization"]),
        ]

        best_state = EmotionalState.NEUTRAL
        best_score = 0.0

        for state, hume_names in mappings:
            state_score = max(
                (scores.get(name, 0.0) for name in hume_names),
                default=0.0
            )
            if state_score > best_score:
                best_score = state_score
                best_state = state

        return (best_state, best_score)

    def _from_prosody(self) -> Tuple[EmotionalState, float]:
        """Infer emotion from prosodic features."""
        # High pitch variance + fast speech = excited
        if self.pitch_variance > 0.7 and self.speech_rate > 160:
            return (EmotionalState.EXCITED, 0.6)

        # High pause ratio + slow speech = confused or stressed
        if self.pause_ratio > 0.3 and self.speech_rate < 100:
            return (EmotionalState.CONFUSED, 0.5)

        # Very fast speech + low pause ratio = urgent
        if self.speech_rate > 180 and self.pause_ratio < 0.1:
            return (EmotionalState.URGENT, 0.5)

        # High volume variance = stressed or frustrated
        if self.volume_variance > 0.6:
            return (EmotionalState.STRESSED, 0.4)

        return (EmotionalState.NEUTRAL, 0.3)


# =============================================================================
# Graphiti Integration
# =============================================================================

class GraphitiAnalyzer:
    """
    Uses Graphiti for entity extraction and relationship analysis.
    """

    def __init__(self):
        self._graph_store: Optional[GraphStore] = None

    async def _ensure_store(self) -> GraphStore:
        if self._graph_store is None:
            self._graph_store = await get_graph_store()
        return self._graph_store

    async def add_conversation_episode(
        self,
        room_id: str,
        turn: ConversationTurn,
        participant: Participant,
    ) -> None:
        """
        Add a conversation turn as an episode for entity extraction.
        Graphiti will automatically extract entities and relationships.
        """
        store = await self._ensure_store()

        # Format episode content with participant context
        episode_content = f"""
[Conversation Turn in Room {room_id}]
Speaker: {participant.name} ({participant.participant_type.value})
Content: {turn.content}
Timestamp: {turn.timestamp.isoformat()}
"""

        if isinstance(participant, EntityAgent):
            episode_content += f"Entity Kind: {participant.entity_kind.value}\n"
            if participant.location:
                episode_content += f"Location: {participant.location}\n"

        elif isinstance(participant, HumanProxy):
            episode_content += f"Role: {participant.role}\n"

        # Add to Graphiti - this triggers entity extraction
        try:
            from graphiti_core.nodes import EpisodeType
            await store.graphiti.add_episode(
                name=f"turn_{turn.id}",
                episode_body=episode_content,
                source=EpisodeType.message,
                reference_time=turn.timestamp,
                group_id=f"room:{room_id}",
            )
        except Exception as e:
            PrintStyle.error(f"Failed to add episode to Graphiti: {e}")

    async def search_related_facts(
        self,
        query: str,
        room_id: str,
        limit: int = 10,
    ) -> List[Dict]:
        """
        Search for facts related to the conversation query.
        Uses Graphiti's hybrid search (semantic + keyword + graph).
        """
        store = await self._ensure_store()

        try:
            results = await store.graphiti.search(
                query=query,
                num_results=limit,
                group_ids=[f"room:{room_id}"],
            )

            facts = []
            for result in results:
                facts.append({
                    "id": getattr(result, "uuid", ""),
                    "fact": getattr(result, "fact", str(result)),
                    "score": getattr(result, "score", 1.0),
                    "entity_name": getattr(result, "name", None),
                    "created_at": getattr(result, "created_at", None),
                })

            return facts

        except Exception as e:
            PrintStyle.error(f"Graphiti search failed: {e}")
            return []

    async def get_entity_relationships(
        self,
        entity_ids: List[str],
        room_id: str,
    ) -> List[Dict]:
        """
        Query graph for relationships between entities.
        """
        store = await self._ensure_store()

        if not entity_ids:
            return []

        try:
            # Cypher query to find relationships
            entity_names = ", ".join(f"'{eid}'" for eid in entity_ids)
            query = f"""
            MATCH (e1:Entity)-[r]-(e2:Entity)
            WHERE e1.name IN [{entity_names}] OR e2.name IN [{entity_names}]
            RETURN e1.name as source, type(r) as relationship, e2.name as target,
                   r.fact as fact
            LIMIT 50
            """

            results = await store._driver.execute_query(query)

            relationships = []
            for row in results or []:
                relationships.append({
                    "source": row.get("source"),
                    "relationship": row.get("relationship"),
                    "target": row.get("target"),
                    "fact": row.get("fact"),
                })

            return relationships

        except Exception as e:
            PrintStyle.error(f"Relationship query failed: {e}")
            return []

    async def extract_entities_from_text(self, text: str) -> List[Dict]:
        """
        Extract entities mentioned in text using Graphiti's search.
        """
        store = await self._ensure_store()

        try:
            # Search for entities mentioned in text
            results = await store.graphiti.search(
                query=text,
                num_results=10,
            )

            extracted = []
            seen = set()
            for result in results:
                name = getattr(result, "name", None)
                if name and name not in seen:
                    seen.add(name)
                    extracted.append({
                        "name": name,
                        "type": getattr(result, "entity_type", "unknown"),
                        "summary": getattr(result, "summary", ""),
                    })

            return extracted

        except Exception as e:
            PrintStyle.error(f"Entity extraction failed: {e}")
            return []


# =============================================================================
# Memory Integration
# =============================================================================

class MemoryAnalyzer:
    """
    Uses the graph-based memory system to recall relevant context.
    """

    async def recall_relevant_memories(
        self,
        query: str,
        memory_subdir: str = "default",
        limit: int = 5,
    ) -> List[Dict]:
        """
        Search memories for relevant past interactions.
        """
        try:
            store = await get_graph_store()
            results = await store.search_memories(
                query=query,
                limit=limit,
                threshold=0.6,
                memory_subdir=memory_subdir,
            )
            return results

        except Exception as e:
            PrintStyle.error(f"Memory recall failed: {e}")
            return []

    async def find_past_interactions(
        self,
        entity_ids: List[str],
        memory_subdir: str = "default",
    ) -> List[Dict]:
        """
        Find past interactions involving specific entities.
        """
        if not entity_ids:
            return []

        # Search for memories mentioning these entities
        query = " OR ".join(entity_ids)
        return await self.recall_relevant_memories(query, memory_subdir)


# =============================================================================
# Content Inference
# =============================================================================

class ContentInferrer:
    """
    Infers appropriate canvas content from conversation signals.
    No LLM needed - uses pattern matching and entity analysis.
    """

    # Keywords that suggest specific content types
    CONTENT_TRIGGERS = {
        CanvasContentType.MAP: [
            "where", "location", "place", "route", "directions", "map",
            "garden", "kitchen", "farm", "address", "area", "distance",
            "near", "far", "between", "path", "drive", "walk", "pickup",
        ],
        CanvasContentType.CALENDAR: [
            "when", "schedule", "time", "date", "calendar", "tomorrow",
            "today", "week", "month", "available", "busy", "meeting",
            "appointment", "pickup", "delivery", "shift", "slot",
        ],
        CanvasContentType.VISUALIZATION: [
            "how many", "count", "total", "data", "chart", "graph",
            "statistics", "impact", "numbers", "percentage", "trend",
            "increase", "decrease", "compare", "analysis", "meals",
        ],
        CanvasContentType.GALLERY: [
            "show", "picture", "photo", "image", "look", "see",
            "what does", "looks like",
        ],
        CanvasContentType.ENTITY_VIEW: [
            "tell me about", "what is", "describe", "details",
            "information", "status", "health", "condition",
        ],
    }

    # Emotional state to ambient mood mapping
    EMOTION_TO_MOOD = {
        EmotionalState.EXCITED: "energetic",
        EmotionalState.STRESSED: "concerned",
        EmotionalState.CONFUSED: "focused",
        EmotionalState.FRUSTRATED: "concerned",
        EmotionalState.SATISFIED: "celebratory",
        EmotionalState.CURIOUS: "focused",
        EmotionalState.URGENT: "focused",
        EmotionalState.NEUTRAL: "calm",
    }

    # Location patterns for Puna, Hawaii
    PUNA_LOCATIONS = {
        "pahoa": {"lat": 19.4969, "lng": -154.9453},
        "kalapana": {"lat": 19.3589, "lng": -154.9714},
        "volcano": {"lat": 19.4300, "lng": -155.2366},
        "hilo": {"lat": 19.7074, "lng": -155.0847},
        "keaau": {"lat": 19.5122, "lng": -155.0375},
        "leilani": {"lat": 19.4639, "lng": -154.9145},
        "pohoiki": {"lat": 19.4561, "lng": -154.8519},
        "seaview": {"lat": 19.4833, "lng": -154.9333},
        "nanawale": {"lat": 19.5042, "lng": -154.9111},
        "orchidland": {"lat": 19.5333, "lng": -155.0667},
    }

    def infer_content_types(
        self,
        conversation_text: str,
        entities_discussed: List[str],
        locations_mentioned: List[Dict],
        time_references: List[str],
    ) -> List[CanvasContentType]:
        """
        Infer appropriate content types from conversation signals.
        """
        suggested = []
        text_lower = conversation_text.lower()

        # Check each content type's triggers
        for content_type, triggers in self.CONTENT_TRIGGERS.items():
            if any(trigger in text_lower for trigger in triggers):
                suggested.append(content_type)

        # Add based on structured data
        if locations_mentioned and CanvasContentType.MAP not in suggested:
            suggested.append(CanvasContentType.MAP)

        if time_references and CanvasContentType.CALENDAR not in suggested:
            suggested.append(CanvasContentType.CALENDAR)

        if entities_discussed and CanvasContentType.ENTITY_VIEW not in suggested:
            # Only suggest entity view if discussing specific entities
            if any(phrase in text_lower for phrase in ["about", "how is", "what about"]):
                suggested.append(CanvasContentType.ENTITY_VIEW)

        return suggested

    def infer_ambient_mood(self, emotional_state: EmotionalState) -> str:
        """Get ambient mood from emotional state."""
        return self.EMOTION_TO_MOOD.get(emotional_state, "calm")

    def extract_locations_from_text(self, text: str) -> List[Dict]:
        """
        Extract location references from text.
        Returns list of {name, lat?, lng?}
        """
        locations = []
        text_lower = text.lower()

        # Check known Puna locations
        for name, coords in self.PUNA_LOCATIONS.items():
            if name in text_lower:
                locations.append({
                    "name": name.title(),
                    "lat": coords["lat"],
                    "lng": coords["lng"],
                })

        # Check for common location words
        location_words = ["garden", "kitchen", "farm", "house", "home"]
        for word in location_words:
            if word in text_lower and not any(loc["name"].lower() == word for loc in locations):
                # Add without coordinates - will need geocoding
                locations.append({"name": word.title()})

        return locations

    def extract_time_references(self, text: str) -> List[str]:
        """
        Extract time references from text.
        """
        time_patterns = [
            "today", "tomorrow", "yesterday",
            "this morning", "this afternoon", "this evening", "tonight",
            "next week", "next month", "this week",
            "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        ]

        text_lower = text.lower()
        found = []

        for pattern in time_patterns:
            if pattern in text_lower:
                found.append(pattern)

        # Also look for time patterns like "at 3pm", "9:00"
        time_regex = r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)?\b'
        matches = re.findall(time_regex, text)
        found.extend(matches)

        return found


# =============================================================================
# Gist Analyzer - Main Class
# =============================================================================

class GistAnalyzer:
    """
    Analyzes conversations using Graphiti, Memory, and Audio analysis.
    No lazy LLM calls - uses actual infrastructure.
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self.graphiti = GraphitiAnalyzer()
        self.memory = MemoryAnalyzer()
        self.content_inferrer = ContentInferrer()
        self._analysis_lock = asyncio.Lock()

    async def analyze(
        self,
        room: ConversationRoom,
        audio_features: Optional[AudioFeatures] = None,
    ) -> ConversationGist:
        """
        Analyze conversation using all available tools.

        Args:
            room: The conversation room
            audio_features: Optional audio analysis from voice input

        Returns:
            ConversationGist with extracted understanding
        """
        async with self._analysis_lock:
            # Get recent conversation text
            conversation_text = room.get_conversation_text(20)
            if not conversation_text:
                return room.gist

            # 1. Add recent turns to Graphiti for entity extraction
            recent_turns = room.get_recent_turns(5)
            for turn in recent_turns:
                participant = room.get_participant(turn.participant_id)
                if participant:
                    await self.graphiti.add_conversation_episode(
                        room.id, turn, participant
                    )

            # 2. Extract entities from Graphiti
            entities_found = await self.graphiti.extract_entities_from_text(
                conversation_text
            )
            entity_ids = [e["name"] for e in entities_found]

            # Also include room entity agents
            for agent in room.get_entity_agents():
                if agent.id not in entity_ids:
                    entity_ids.append(agent.id)

            # 3. Get entity relationships from graph
            relationships = await self.graphiti.get_entity_relationships(
                entity_ids, room.id
            )

            # 4. Search for related facts
            related_facts = await self.graphiti.search_related_facts(
                conversation_text, room.id, limit=5
            )

            # 5. Recall relevant memories
            memories = await self.memory.recall_relevant_memories(
                conversation_text, limit=3
            )

            # 6. Extract locations and times from text
            locations = self.content_inferrer.extract_locations_from_text(
                conversation_text
            )
            time_refs = self.content_inferrer.extract_time_references(
                conversation_text
            )

            # 7. Determine emotional state
            if audio_features:
                emotional_state, confidence = audio_features.infer_emotional_state()
            else:
                # Infer from text patterns if no audio
                emotional_state = self._infer_emotion_from_text(conversation_text)

            # 8. Infer content types
            suggested_content = self.content_inferrer.infer_content_types(
                conversation_text,
                entity_ids,
                locations,
                time_refs,
            )

            # 9. Extract topics from entities and facts
            topics = self._extract_topics(entities_found, related_facts, conversation_text)

            # 10. Identify pending questions
            questions = self._extract_questions(conversation_text)

            # 11. Identify action items
            actions = self._extract_actions(conversation_text)

            # 12. Build intent from context
            intent = self._build_intent(topics, actions, entity_ids)

            # Build the gist
            gist = ConversationGist(
                topics=topics,
                intent=intent,
                entities_discussed=entity_ids,
                locations_mentioned=locations,
                time_references=time_refs,
                emotional_tone=emotional_state,
                suggested_content=suggested_content,
                action_items=actions,
                questions_pending=questions,
            )

            # Update room
            room.update_gist(gist)

            return gist

    def _infer_emotion_from_text(self, text: str) -> EmotionalState:
        """Infer emotion from text when audio is unavailable."""
        text_lower = text.lower()

        # Urgency indicators
        if any(word in text_lower for word in ["urgent", "asap", "emergency", "now", "hurry", "quickly"]):
            return EmotionalState.URGENT

        # Confusion indicators
        if any(word in text_lower for word in ["confused", "don't understand", "unclear", "what do you mean"]):
            return EmotionalState.CONFUSED

        # Count question marks as confusion indicator
        if text.count("?") >= 3:
            return EmotionalState.CONFUSED

        # Frustration indicators
        if any(word in text_lower for word in ["frustrated", "annoying", "problem", "issue", "not working", "broken"]):
            return EmotionalState.FRUSTRATED

        # Excitement indicators
        if any(word in text_lower for word in ["excited", "great", "amazing", "wonderful", "awesome", "love"]):
            return EmotionalState.EXCITED

        # Exclamation marks as excitement indicator
        if text.count("!") >= 2:
            return EmotionalState.EXCITED

        # Satisfaction indicators
        if any(word in text_lower for word in ["thanks", "perfect", "good", "works", "solved", "done"]):
            return EmotionalState.SATISFIED

        # Curiosity indicators
        if any(word in text_lower for word in ["wonder", "curious", "interesting", "tell me more", "how does"]):
            return EmotionalState.CURIOUS

        return EmotionalState.NEUTRAL

    def _extract_topics(
        self,
        entities: List[Dict],
        facts: List[Dict],
        text: str,
    ) -> List[str]:
        """Extract topic keywords from entities and facts."""
        topics = set()

        # Add entity names as topics
        for entity in entities:
            if name := entity.get("name"):
                topics.add(name.lower())

        # Add key terms from facts
        for fact in facts:
            if fact_text := fact.get("fact"):
                # Extract significant words
                words = fact_text.split()
                for word in words:
                    word_clean = word.strip(".,!?").lower()
                    if len(word_clean) > 4:
                        topics.add(word_clean)

        # Extract nouns from conversation (simple heuristic)
        # Words that appear after "the", "a", "this" are likely topics
        text_lower = text.lower()
        for pattern in [r'the (\w+)', r'a (\w+)', r'this (\w+)', r'about (\w+)']:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                if len(match) > 3:
                    topics.add(match)

        return list(topics)[:10]  # Limit to top 10

    def _extract_questions(self, text: str) -> List[str]:
        """Extract unanswered questions from conversation."""
        questions = []
        lines = text.split("\n")

        for line in lines:
            if "?" in line:
                # Extract just the question part
                parts = line.split(":")
                if len(parts) > 1:
                    question = parts[1].strip()
                else:
                    question = line.strip()

                if question.endswith("?"):
                    questions.append(question)

        return questions[-5:]  # Last 5 questions

    def _extract_actions(self, text: str) -> List[str]:
        """Extract action items from conversation."""
        actions = []
        text_lower = text.lower()

        # Action indicator phrases
        action_phrases = [
            "need to", "should", "will", "going to", "let's",
            "can you", "could you", "please", "make sure",
        ]

        lines = text.split("\n")
        for line in lines:
            line_lower = line.lower()
            if any(phrase in line_lower for phrase in action_phrases):
                # Extract the action
                parts = line.split(":")
                if len(parts) > 1:
                    action = parts[1].strip()
                else:
                    action = line.strip()

                if len(action) > 10:  # Filter very short lines
                    actions.append(action)

        return actions[-5:]  # Last 5 actions

    def _build_intent(
        self,
        topics: List[str],
        actions: List[str],
        entities: List[str],
    ) -> str:
        """Build a one-sentence intent from context."""
        if actions:
            return actions[0]  # First action often captures intent

        if topics:
            if entities:
                return f"Discussing {', '.join(topics[:2])} involving {entities[0]}"
            return f"Discussing {', '.join(topics[:3])}"

        return "General conversation"

    async def should_update_canvas(
        self,
        room: ConversationRoom,
        turns_since_update: int = 3,
    ) -> bool:
        """
        Determine if canvas should update.
        Uses pattern matching, not LLM.
        """
        recent_turns = room.get_recent_turns(turns_since_update)
        if len(recent_turns) < turns_since_update:
            return False

        # Check for visual trigger keywords
        visual_triggers = [
            "show", "see", "look", "map", "where", "when", "schedule",
            "calendar", "photo", "picture", "graph", "chart", "data",
        ]

        for turn in recent_turns:
            content_lower = turn.content.lower()
            if any(trigger in content_lower for trigger in visual_triggers):
                return True

        # Check emotional state
        if room.gist.emotional_tone in [
            EmotionalState.CONFUSED,
            EmotionalState.CURIOUS,
        ]:
            return True

        return False


# =============================================================================
# Content Generator
# =============================================================================

class ContentGenerator:
    """
    Generates canvas content based on gist analysis.
    Uses entity data and relationships, not LLM generation.
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self.analyzer = GistAnalyzer(agent)

    async def generate_for_room(
        self,
        room: ConversationRoom,
        audio_features: Optional[AudioFeatures] = None,
    ) -> List[Dict]:
        """
        Generate canvas content based on conversation analysis.
        """
        # Analyze conversation
        gist = await self.analyzer.analyze(room, audio_features)

        generated = []

        # Generate for each suggested content type
        for content_type in gist.suggested_content:
            element = await self._generate_for_type(room, gist, content_type)
            if element:
                generated.append(element.to_dict())

        # Always set ambient based on emotional tone
        mood = self.analyzer.content_inferrer.infer_ambient_mood(gist.emotional_tone)
        ambient = room.generate_ambient(
            mood=mood,
            imagery={"theme": gist.topics[0] if gist.topics else "nature"},
            triggered_by="system",
        )
        generated.append(ambient.to_dict())

        return generated

    async def _generate_for_type(
        self,
        room: ConversationRoom,
        gist: ConversationGist,
        content_type: CanvasContentType,
    ):
        """Generate specific content type."""

        if content_type == CanvasContentType.MAP:
            if gist.locations_mentioned:
                return room.generate_map(
                    title="Locations",
                    locations=gist.locations_mentioned,
                    triggered_by="gist_analysis",
                )

        elif content_type == CanvasContentType.CALENDAR:
            if gist.time_references:
                # Build events from time references
                events = [{"title": ref, "allDay": True} for ref in gist.time_references]
                return room.generate_calendar(
                    title="Schedule",
                    events=events,
                    triggered_by="gist_analysis",
                )

        elif content_type == CanvasContentType.ENTITY_VIEW:
            # Show first discussed entity
            if gist.entities_discussed:
                entity_id = gist.entities_discussed[0]
                entity = room.get_participant(entity_id)
                if isinstance(entity, EntityAgent):
                    return room.generate_entity_view(
                        entity=entity,
                        triggered_by="gist_analysis",
                    )

        elif content_type == CanvasContentType.VISUALIZATION:
            # Generate basic visualization from action items or topics
            if gist.action_items:
                return room.generate_visualization(
                    title="Action Items",
                    data={
                        "labels": [f"Item {i+1}" for i in range(len(gist.action_items))],
                        "values": [1] * len(gist.action_items),
                    },
                    chart_type="bar",
                    triggered_by="gist_analysis",
                )

        return None

    async def update_on_turn(
        self,
        room: ConversationRoom,
        turn: ConversationTurn,
        audio_features: Optional[AudioFeatures] = None,
    ) -> bool:
        """
        Check and update canvas after a turn.
        """
        should_update = await self.analyzer.should_update_canvas(room)

        if should_update:
            generated = await self.generate_for_room(room, audio_features)
            return len(generated) > 0

        return False


# =============================================================================
# Emotional Context (Enhanced)
# =============================================================================

class EmotionalContext:
    """
    Tracks emotional state with audio analysis integration.
    """

    def __init__(self):
        self._states: Dict[str, EmotionalState] = {}
        self._audio_features: Dict[str, AudioFeatures] = {}
        self._history: List[Dict] = []

    def update_from_audio(
        self,
        participant_id: str,
        audio_features: AudioFeatures,
    ) -> EmotionalState:
        """Update emotional state from audio analysis."""
        self._audio_features[participant_id] = audio_features
        state, confidence = audio_features.infer_emotional_state()
        self._states[participant_id] = state

        self._history.append({
            "participant_id": participant_id,
            "state": state.value,
            "confidence": confidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        return state

    def update_from_hume(
        self,
        participant_id: str,
        hume_response: Dict,
    ) -> EmotionalState:
        """Update from Hume.ai response."""
        features = AudioFeatures.from_hume_response(hume_response)
        return self.update_from_audio(participant_id, features)

    def update_from_whisper(
        self,
        participant_id: str,
        whisper_result: Dict,
    ) -> EmotionalState:
        """Update from Whisper transcription result."""
        features = AudioFeatures.from_whisper_result(whisper_result)
        return self.update_from_audio(participant_id, features)

    def get_state(self, participant_id: str) -> EmotionalState:
        return self._states.get(participant_id, EmotionalState.NEUTRAL)

    def get_adaptation_hints(self, participant_id: str) -> Dict[str, Any]:
        """Get response adaptation hints based on emotional state."""
        state = self.get_state(participant_id)

        adaptations = {
            EmotionalState.NEUTRAL: {
                "pace": "normal", "tone": "balanced",
                "detail_level": "moderate", "reassurance": False,
            },
            EmotionalState.EXCITED: {
                "pace": "energetic", "tone": "enthusiastic",
                "detail_level": "concise", "reassurance": False,
            },
            EmotionalState.STRESSED: {
                "pace": "calm", "tone": "reassuring",
                "detail_level": "simple", "reassurance": True,
            },
            EmotionalState.CONFUSED: {
                "pace": "slow", "tone": "patient",
                "detail_level": "detailed", "reassurance": True,
            },
            EmotionalState.FRUSTRATED: {
                "pace": "calm", "tone": "empathetic",
                "detail_level": "simple", "reassurance": True,
            },
            EmotionalState.SATISFIED: {
                "pace": "normal", "tone": "warm",
                "detail_level": "moderate", "reassurance": False,
            },
            EmotionalState.CURIOUS: {
                "pace": "normal", "tone": "engaging",
                "detail_level": "detailed", "reassurance": False,
            },
            EmotionalState.URGENT: {
                "pace": "quick", "tone": "focused",
                "detail_level": "essential", "reassurance": False,
            },
        }

        return adaptations.get(state, adaptations[EmotionalState.NEUTRAL])


# =============================================================================
# Content Predictor
# =============================================================================

class ContentPredictor:
    """
    Predicts content needs from conversation patterns and entity relationships.
    """

    def __init__(self, agent: "Agent"):
        self.agent = agent
        self.graphiti = GraphitiAnalyzer()

    async def predict_upcoming_needs(
        self,
        room: ConversationRoom,
    ) -> List[Dict]:
        """
        Predict what content might be needed based on:
        - Entity relationships in graph
        - Conversation patterns
        - Historical interaction patterns
        """
        predictions = []
        gist = room.gist

        # Get entity relationships
        relationships = await self.graphiti.get_entity_relationships(
            gist.entities_discussed,
            room.id,
        )

        # If entities have location relationships, predict map need
        for rel in relationships:
            if rel.get("relationship") in ["LOCATED_AT", "NEAR", "CONNECTED_TO"]:
                predictions.append({
                    "type": "map",
                    "confidence": 0.8,
                    "reason": f"Entities have location relationships",
                })
                break

        # If multiple entities with relationships, predict relationship view
        if len(relationships) >= 3:
            predictions.append({
                "type": "relationship",
                "confidence": 0.7,
                "reason": "Multiple entity relationships to visualize",
            })

        # If time references accumulating, predict calendar
        if len(gist.time_references) >= 2:
            predictions.append({
                "type": "calendar",
                "confidence": 0.7,
                "reason": "Multiple time references mentioned",
            })

        # If locations accumulating, predict map
        if len(gist.locations_mentioned) >= 2:
            predictions.append({
                "type": "map",
                "confidence": 0.8,
                "reason": "Multiple locations mentioned",
            })

        return predictions

    async def prefetch_content(
        self,
        room: ConversationRoom,
        generator: ContentGenerator,
    ) -> None:
        """
        Pre-generate predicted content for faster display.
        """
        predictions = await self.predict_upcoming_needs(room)

        for prediction in predictions:
            if prediction["confidence"] >= 0.7:
                spec = {
                    "type": prediction["type"],
                    "spec": {},
                    "priority": int(prediction["confidence"] * 10),
                }
                try:
                    await generator._generate_for_type(
                        room,
                        room.gist,
                        CanvasContentType(prediction["type"])
                    )
                except Exception as e:
                    PrintStyle.error(f"Prefetch failed: {e}")
