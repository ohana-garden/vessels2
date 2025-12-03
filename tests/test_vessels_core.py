"""
Vessels Core Test Suite

Comprehensive tests for all Vessels modules:
- Entity Ontology (universal personas for all entity types)
- Moral Geometry (15-dimensional ethical space)
- Kala (non-currency contribution visibility)
- Hume Integration (voice/persona system)
- Graph Store (FalkorDB operations)

Run with: pytest tests/test_vessels_core.py -v
Or run individual test classes: pytest tests/test_vessels_core.py::TestEntityOntology -v
"""

import pytest
import asyncio
import json
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Test Embedded Defaults Loading
# =============================================================================

class TestEmbeddedDefaults:
    """Test that all embedded defaults load correctly."""

    def test_all_defaults_load(self):
        """Verify all default modules load without errors."""
        from python.helpers.embedded_defaults import get_all_defaults
        defaults = get_all_defaults()
        assert len(defaults) > 0, "Should have defaults"
        print(f"Loaded {len(defaults)} default modules")

    def test_entity_ontology_defaults_exist(self):
        """Verify entity ontology defaults exist."""
        from python.helpers.embedded_defaults import ENTITY_ONTOLOGY_DEFAULTS
        assert "entity_ontology" in ENTITY_ONTOLOGY_DEFAULTS
        code = ENTITY_ONTOLOGY_DEFAULTS["entity_ontology"]["code"]
        assert len(code) > 1000, "Entity ontology code should be substantial"

    def test_moral_geometry_defaults_exist(self):
        """Verify moral geometry defaults exist."""
        from python.helpers.embedded_defaults import MORAL_GEOMETRY_DEFAULTS
        assert "moral_geometry" in MORAL_GEOMETRY_DEFAULTS
        assert "spectral" in MORAL_GEOMETRY_DEFAULTS

    def test_kala_defaults_exist(self):
        """Verify Kala defaults exist."""
        from python.helpers.embedded_defaults import KALA_DEFAULTS
        assert "kala" in KALA_DEFAULTS
        code = KALA_DEFAULTS["kala"]["code"]
        assert "KalaEvent" in code, "Should contain KalaEvent class"

    def test_hume_defaults_exist(self):
        """Verify Hume voice defaults exist."""
        from python.helpers.embedded_defaults import HUME_DEFAULTS
        assert "hume_voice" in HUME_DEFAULTS
        code = HUME_DEFAULTS["hume_voice"]["code"]
        assert "HumeVoiceClient" in code, "Should contain HumeVoiceClient class"


# =============================================================================
# Test Code Compilation
# =============================================================================

class TestCodeCompilation:
    """Test that all embedded code compiles correctly."""

    def test_entity_ontology_compiles(self):
        """Verify entity ontology code compiles."""
        import ast
        from python.helpers.embedded_defaults import ENTITY_ONTOLOGY_DEFAULTS
        code = ENTITY_ONTOLOGY_DEFAULTS["entity_ontology"]["code"]
        ast.parse(code)  # Raises SyntaxError if invalid

    def test_moral_geometry_compiles(self):
        """Verify moral geometry code compiles."""
        import ast
        from python.helpers.embedded_defaults import MORAL_GEOMETRY_DEFAULTS
        code = MORAL_GEOMETRY_DEFAULTS["moral_geometry"]["code"]
        ast.parse(code)

    def test_spectral_compiles(self):
        """Verify spectral analysis code compiles."""
        import ast
        from python.helpers.embedded_defaults import MORAL_GEOMETRY_DEFAULTS
        code = MORAL_GEOMETRY_DEFAULTS["spectral"]["code"]
        ast.parse(code)

    def test_kala_compiles(self):
        """Verify Kala code compiles."""
        import ast
        from python.helpers.embedded_defaults import KALA_DEFAULTS
        code = KALA_DEFAULTS["kala"]["code"]
        ast.parse(code)

    def test_hume_voice_compiles(self):
        """Verify Hume voice code compiles."""
        import ast
        from python.helpers.embedded_defaults import HUME_DEFAULTS
        code = HUME_DEFAULTS["hume_voice"]["code"]
        ast.parse(code)


# =============================================================================
# Test Entity Ontology Logic
# =============================================================================

class TestEntityOntology:
    """Test entity ontology classes and enums."""

    @pytest.fixture
    def entity_module(self):
        """Compile and return the entity ontology module."""
        from python.helpers.embedded_defaults import ENTITY_ONTOLOGY_DEFAULTS
        code = ENTITY_ONTOLOGY_DEFAULTS["entity_ontology"]["code"]
        module_globals = {}
        exec(code, module_globals)
        return module_globals

    def test_entity_type_enum(self, entity_module):
        """Test EntityType enum has all expected values."""
        EntityType = entity_module["EntityType"]
        assert EntityType.HUMAN.value == "human"
        assert EntityType.AGENT.value == "agent"
        assert EntityType.PLANT.value == "plant"
        assert EntityType.MACHINE.value == "machine"
        assert EntityType.SYSTEM.value == "system"
        assert EntityType.BIOME.value == "biome"
        assert EntityType.CONCEPT.value == "concept"

    def test_voice_source_enum(self, entity_module):
        """Test VoiceSource enum."""
        VoiceSource = entity_module["VoiceSource"]
        assert VoiceSource.SELF.value == "self"
        assert VoiceSource.PROXY.value == "proxy"
        assert VoiceSource.SENSOR.value == "sensor"
        assert VoiceSource.COLLECTIVE.value == "collective"
        assert VoiceSource.EMERGENT.value == "emergent"

    def test_temporal_scale_enum(self, entity_module):
        """Test TemporalScale enum spans all timescales."""
        TemporalScale = entity_module["TemporalScale"]
        assert TemporalScale.MILLISECONDS.value == "milliseconds"
        assert TemporalScale.GEOLOGICAL.value == "geological"
        # Should have many intermediate values
        assert len(list(TemporalScale)) >= 10

    def test_spatial_scale_enum(self, entity_module):
        """Test SpatialScale enum."""
        SpatialScale = entity_module["SpatialScale"]
        assert SpatialScale.MICROSCOPIC.value == "microscopic"
        assert SpatialScale.PLANETARY.value == "planetary"

    def test_entity_persona_creation(self, entity_module):
        """Test creating an EntityPersona."""
        EntityPersona = entity_module["EntityPersona"]
        EntityType = entity_module["EntityType"]
        VoiceSource = entity_module["VoiceSource"]

        persona = EntityPersona(
            id="test_persona",
            name="Test Entity",
            entity_type=EntityType.HUMAN,
            voice_source=VoiceSource.SELF,
        )
        assert persona.id == "test_persona"
        assert persona.name == "Test Entity"
        assert persona.entity_type == EntityType.HUMAN
        assert persona.can_self_voice() == True

    def test_plant_needs_spokesperson(self, entity_module):
        """Test that plant entities need spokespersons."""
        EntityPersona = entity_module["EntityPersona"]
        EntityType = entity_module["EntityType"]
        VoiceSource = entity_module["VoiceSource"]

        plant = EntityPersona(
            id="my_plant",
            name="Garden Rose",
            entity_type=EntityType.PLANT,
            voice_source=VoiceSource.PROXY,
        )
        assert plant.needs_spokesperson() == True
        assert plant.can_self_voice() == False

    def test_entity_to_dict(self, entity_module):
        """Test EntityPersona serialization."""
        EntityPersona = entity_module["EntityPersona"]
        EntityType = entity_module["EntityType"]

        persona = EntityPersona(
            id="test",
            name="Test",
            entity_type=EntityType.AGENT,
        )
        data = persona.to_dict()
        assert data["id"] == "test"
        assert data["name"] == "Test"
        assert data["entity_type"] == "agent"

    def test_entity_from_dict(self, entity_module):
        """Test EntityPersona deserialization."""
        EntityPersona = entity_module["EntityPersona"]
        EntityType = entity_module["EntityType"]

        data = {
            "id": "restored",
            "name": "Restored Entity",
            "entity_type": "human",
            "voice_source": "self",
        }
        persona = EntityPersona.from_dict(data)
        assert persona.id == "restored"
        assert persona.entity_type == EntityType.HUMAN

    def test_moral_dimension_setting(self, entity_module):
        """Test setting moral geometry dimensions."""
        EntityPersona = entity_module["EntityPersona"]

        persona = EntityPersona(id="test", name="Test")
        persona.set_moral_dimension("compassion", 0.8)
        persona.set_moral_dimension("justice", 0.6)

        assert persona.get_moral_dimension("compassion") == 0.8
        assert persona.get_moral_dimension("justice") == 0.6
        assert persona.get_moral_dimension("nonexistent") == 0.0

    def test_moral_dimension_clamping(self, entity_module):
        """Test that moral dimensions are clamped to [-1, 1]."""
        EntityPersona = entity_module["EntityPersona"]

        persona = EntityPersona(id="test", name="Test")
        persona.set_moral_dimension("test", 5.0)  # Should clamp to 1.0
        assert persona.get_moral_dimension("test") == 1.0

        persona.set_moral_dimension("test", -5.0)  # Should clamp to -1.0
        assert persona.get_moral_dimension("test") == -1.0

    def test_boundary_dataclass(self, entity_module):
        """Test Boundary dataclass."""
        Boundary = entity_module["Boundary"]

        boundary = Boundary(
            id="b1",
            description="No harm to others",
            severity="hard",
            protects="physical wellbeing",
        )
        data = boundary.to_dict()
        assert data["severity"] == "hard"

        restored = Boundary.from_dict(data)
        assert restored.description == "No harm to others"

    def test_story_dataclass(self, entity_module):
        """Test Story dataclass."""
        Story = entity_module["Story"]

        story = Story(
            id="s1",
            title="My Journey",
            summary="A tale of growth",
            values_revealed=["perseverance", "courage"],
        )
        assert story.timestamp  # Should auto-generate
        data = story.to_dict()
        assert "perseverance" in data["values_revealed"]

    def test_elicitation_session(self, entity_module):
        """Test ElicitationSession creation and phase advancement."""
        ElicitationSession = entity_module["ElicitationSession"]
        ElicitationPhase = entity_module["ElicitationPhase"]
        EntityType = entity_module["EntityType"]

        session = ElicitationSession(
            id="sess1",
            entity_id="ent1",
            entity_type=EntityType.HUMAN,
        )
        assert session.current_phase == ElicitationPhase.OPENING

        session.advance_phase(ElicitationPhase.STORIES)
        assert session.current_phase == ElicitationPhase.STORIES
        assert ElicitationPhase.OPENING.value in session.phases_completed

    def test_witness_persona_template(self, entity_module):
        """Test Witness agent template creation."""
        create_witness_persona = entity_module["create_witness_persona"]

        witness = create_witness_persona("vessel_1")
        assert witness["traits"]["warmth"] >= 0.9
        assert witness["role"] == "elicitation_witness"

    def test_mirror_persona_template(self, entity_module):
        """Test Mirror agent template creation."""
        create_mirror_persona = entity_module["create_mirror_persona"]

        mirror = create_mirror_persona("vessel_1")
        assert mirror["traits"]["pattern_recognition"] >= 0.9
        assert mirror["role"] == "elicitation_mirror"

    def test_plant_persona_template(self, entity_module):
        """Test plant persona template."""
        create_plant_persona_template = entity_module["create_plant_persona_template"]
        EntityType = entity_module["EntityType"]
        VoiceSource = entity_module["VoiceSource"]

        plant = create_plant_persona_template("v1", "Garden Rose", "flowering shrub")
        assert plant.entity_type == EntityType.PLANT
        assert plant.voice_source == VoiceSource.PROXY
        assert "water" in plant.dependencies

    def test_elicitation_duration_estimate(self, entity_module):
        """Test elicitation duration estimation."""
        estimate_elicitation_duration = entity_module["estimate_elicitation_duration"]
        EntityType = entity_module["EntityType"]
        TemporalScale = entity_module["TemporalScale"]

        human_duration = estimate_elicitation_duration(EntityType.HUMAN, TemporalScale.DAYS)
        assert "hour" in human_duration.lower()

        biome_duration = estimate_elicitation_duration(EntityType.BIOME, TemporalScale.DECADES)
        # Biomes take longer


# =============================================================================
# Test Moral Geometry Logic
# =============================================================================

class TestMoralGeometry:
    """Test moral geometry module."""

    @pytest.fixture
    def moral_module(self):
        """Compile and return the moral geometry module."""
        from python.helpers.embedded_defaults import MORAL_GEOMETRY_DEFAULTS
        code = MORAL_GEOMETRY_DEFAULTS["moral_geometry"]["code"]
        module_globals = {}
        exec(code, module_globals)
        return module_globals

    def test_moral_dimensions_defined(self, moral_module):
        """Test that all 15 moral dimensions are defined."""
        MORAL_DIMENSIONS = moral_module["MORAL_DIMENSIONS"]
        assert len(MORAL_DIMENSIONS) == 15
        assert "compassion" in MORAL_DIMENSIONS
        assert "justice" in MORAL_DIMENSIONS
        assert "truth" in MORAL_DIMENSIONS

    def test_moral_vector_creation(self, moral_module):
        """Test MoralVector creation."""
        MoralVector = moral_module["MoralVector"]

        vector = MoralVector()
        # Should initialize with zeros
        assert vector.compassion == 0.0

        # Set some values
        vector.compassion = 0.8
        vector.justice = 0.6
        assert vector.compassion == 0.8

    def test_moral_vector_to_dict(self, moral_module):
        """Test MoralVector serialization."""
        MoralVector = moral_module["MoralVector"]

        vector = MoralVector(compassion=0.7, justice=0.5)
        data = vector.to_dict()
        assert data["compassion"] == 0.7
        assert data["justice"] == 0.5


# =============================================================================
# Test Kala Logic
# =============================================================================

class TestKala:
    """Test Kala contribution visibility module."""

    @pytest.fixture
    def kala_module(self):
        """Compile and return the Kala module."""
        from python.helpers.embedded_defaults import KALA_DEFAULTS
        code = KALA_DEFAULTS["kala"]["code"]
        module_globals = {}
        exec(code, module_globals)
        return module_globals

    def test_kala_event_creation(self, kala_module):
        """Test KalaEvent creation."""
        KalaEvent = kala_module["KalaEvent"]

        event = KalaEvent(
            id="event1",
            name="Team Meeting",
            hours=2.0,
        )
        assert event.id == "event1"
        assert event.name == "Team Meeting"
        assert event.hours == 2.0

    def test_kala_event_add_participant(self, kala_module):
        """Test adding participants to KalaEvent."""
        KalaEvent = kala_module["KalaEvent"]

        event = KalaEvent(id="e1", name="Workshop", hours=1.5)
        event.add_participant("alice")
        event.add_participant("bob")

        assert len(event.participants) == 2

    def test_kala_computation(self, kala_module):
        """Test Kala computation with equal distribution."""
        KalaEvent = kala_module["KalaEvent"]
        KALA_PER_HOUR = kala_module["KALA_PER_HOUR"]

        event = KalaEvent(id="e1", name="Session", hours=2.0)
        event.add_participant("alice")
        event.add_participant("bob")

        total = event.compute_kala()

        # Base: 2 participants * 2 hours * KALA_PER_HOUR
        expected_base = 2 * 2.0 * KALA_PER_HOUR
        assert event.base_kala == expected_base
        # Each gets equal share
        assert event.kala_per_participant == total / 2

    def test_human_view(self, kala_module):
        """Test HumanView (asymmetric visibility)."""
        HumanView = kala_module["HumanView"]

        view = HumanView(
            participant_id="alice",
            events_participated=["e1", "e2"],
            total_contributions=5,
        )
        assert view.participant_id == "alice"
        assert view.total_contributions == 5
        # Human view should NOT expose patterns
        assert not hasattr(view, "all_patterns")

    def test_agent_view(self, kala_module):
        """Test AgentView (full patterns visible)."""
        AgentView = kala_module["AgentView"]

        view = AgentView(
            patterns_detected=["burnout_risk", "high_engagement"],
            attractor_states={"community_health": 0.8},
        )
        assert "burnout_risk" in view.patterns_detected


# =============================================================================
# Test Hume Voice Logic
# =============================================================================

class TestHumeVoice:
    """Test Hume voice/persona module."""

    @pytest.fixture
    def hume_module(self):
        """Compile and return the Hume module."""
        from python.helpers.embedded_defaults import HUME_DEFAULTS
        code = HUME_DEFAULTS["hume_voice"]["code"]
        module_globals = {}
        exec(code, module_globals)
        return module_globals

    def test_voice_style_enum(self, hume_module):
        """Test VoiceStyle enum."""
        VoiceStyle = hume_module["VoiceStyle"]
        assert VoiceStyle.WARM.value == "warm"
        assert VoiceStyle.PROFESSIONAL.value == "professional"

    def test_emotion_category_enum(self, hume_module):
        """Test EmotionCategory enum has 36+ emotions."""
        EmotionCategory = hume_module["EmotionCategory"]
        emotions = list(EmotionCategory)
        assert len(emotions) >= 36, "Hume prosody model has 36 emotions"

    def test_emotional_state_creation(self, hume_module):
        """Test EmotionalState creation."""
        EmotionalState = hume_module["EmotionalState"]

        state = EmotionalState(
            emotions={"joy": 0.8, "interest": 0.6},
            dominant_emotion="joy",
            arousal=0.7,
            valence=0.8,
        )
        assert state.dominant_emotion == "joy"
        assert state.valence > 0

    def test_voice_profile_creation(self, hume_module):
        """Test VoiceProfile creation."""
        VoiceProfile = hume_module["VoiceProfile"]

        profile = VoiceProfile(
            voice_style="warm",
            pitch="medium",
            pace="natural",
        )
        data = profile.to_dict()
        assert data["voice_style"] == "warm"

    def test_agent_persona_creation(self, hume_module):
        """Test AgentPersona creation."""
        AgentPersona = hume_module["AgentPersona"]
        VoiceProfile = hume_module["VoiceProfile"]

        voice = VoiceProfile(voice_style="professional")
        persona = AgentPersona(
            id="agent1",
            name="Helper",
            voice=voice,
            traits={"warmth": 0.8},
        )
        assert persona.name == "Helper"
        data = persona.to_dict()
        assert data["traits"]["warmth"] == 0.8

    def test_ohana_coordinator_template(self, hume_module):
        """Test Ohana coordinator persona template."""
        create_ohana_coordinator_persona = hume_module["create_ohana_coordinator_persona"]

        persona = create_ohana_coordinator_persona("v1", "Coordinator")
        assert persona.is_human_proxy == False
        assert persona.voice.voice_style == "nurturing"

    def test_human_proxy_template(self, hume_module):
        """Test human proxy persona template."""
        create_human_proxy_persona = hume_module["create_human_proxy_persona"]

        persona = create_human_proxy_persona(
            vessel_id="v1",
            human_id="human1",
            proxy_name="Parent Self",
            proxy_role="parent",
        )
        assert persona.is_human_proxy == True
        assert persona.human_id == "human1"


# =============================================================================
# Test Graph Store Node Types
# =============================================================================

class TestGraphStoreNodeTypes:
    """Test graph store node type definitions."""

    def test_all_node_types_defined(self):
        """Test that all expected node types exist."""
        from python.helpers.graph_store import VesselNodeType

        # Entity ontology types
        assert VesselNodeType.ENTITY.value == "entity"
        assert VesselNodeType.ELICITATION_SESSION.value == "elicitation_session"
        assert VesselNodeType.SPOKESPERSON.value == "spokesperson"
        assert VesselNodeType.SENSOR_SOURCE.value == "sensor_source"
        assert VesselNodeType.STORY.value == "story"
        assert VesselNodeType.BOUNDARY.value == "boundary"
        assert VesselNodeType.CYCLE.value == "cycle"

        # Moral geometry types
        assert VesselNodeType.MORAL_VECTOR.value == "moral_vector"
        assert VesselNodeType.MORAL_TRAJECTORY.value == "moral_trajectory"

        # Kala types
        assert VesselNodeType.KALA_EVENT.value == "kala_event"
        assert VesselNodeType.KALA_PATTERN.value == "kala_pattern"

        # Hume types
        assert VesselNodeType.PERSONA.value == "persona"
        assert VesselNodeType.VOICE_SESSION.value == "voice_session"


# =============================================================================
# Test Graph Store Operations (Mocked)
# =============================================================================

class TestGraphStoreOperations:
    """Test graph store operations with mocked database."""

    @pytest.fixture
    def mock_graph_store(self):
        """Create a mock graph store for testing."""
        from python.helpers.graph_store import GraphStore, GraphStoreConfig

        with patch('python.helpers.graph_store.FalkorDB'):
            with patch('python.helpers.graph_store.AsyncFalkorDB'):
                config = GraphStoreConfig(
                    host="localhost",
                    port=6379,
                    database="test",
                )
                store = GraphStore(config)
                store._content_store = {}  # Simple dict for testing

                # Mock save/get/list methods
                async def mock_save(path, content, **kwargs):
                    store._content_store[path] = content
                    return path

                async def mock_get(path):
                    return store._content_store.get(path)

                async def mock_list(**kwargs):
                    return list(store._content_store.keys())

                store.save_content = mock_save
                store.get_content = mock_get
                store.list_content = mock_list

                return store

    @pytest.mark.asyncio
    async def test_save_and_load_entity(self, mock_graph_store):
        """Test saving and loading an entity."""
        store = mock_graph_store

        entity_data = {
            "id": "test_entity",
            "name": "Test Entity",
            "entity_type": "human",
            "voice_source": "self",
        }

        await store.save_entity("test_entity", entity_data, "test_vessel")
        loaded = await store.load_entity("test_entity", "test_vessel")

        assert loaded is not None
        assert loaded["name"] == "Test Entity"

    @pytest.mark.asyncio
    async def test_list_entities_with_filter(self, mock_graph_store):
        """Test listing entities with type filter."""
        store = mock_graph_store

        # Save multiple entities
        await store.save_entity("human1", {
            "id": "human1",
            "entity_type": "human",
        }, "v1")
        await store.save_entity("plant1", {
            "id": "plant1",
            "entity_type": "plant",
        }, "v1")

        # List all
        all_entities = await store.list_entities("v1")
        assert len(all_entities) == 2

        # Filter by type
        humans = await store.list_entities("v1", entity_type="human")
        assert len(humans) == 1
        assert humans[0]["entity_type"] == "human"

    @pytest.mark.asyncio
    async def test_save_elicitation_session(self, mock_graph_store):
        """Test saving an elicitation session."""
        store = mock_graph_store

        session_data = {
            "id": "sess1",
            "entity_id": "ent1",
            "entity_type": "human",
            "current_phase": "opening",
            "is_active": True,
        }

        await store.save_elicitation_session("sess1", session_data, "v1")
        loaded = await store.load_elicitation_session("sess1", "v1")

        assert loaded is not None
        assert loaded["current_phase"] == "opening"

    @pytest.mark.asyncio
    async def test_save_spokesperson(self, mock_graph_store):
        """Test saving a spokesperson."""
        store = mock_graph_store

        spokesperson_data = {
            "id": "sp1",
            "name": "Gardener",
            "entity_id": "plant1",
            "relationship": "caretaker",
        }

        await store.save_spokesperson("sp1", spokesperson_data, "v1")
        loaded = await store.load_spokespersons_for_entity("plant1", "v1")

        assert len(loaded) == 1
        assert loaded[0]["relationship"] == "caretaker"

    @pytest.mark.asyncio
    async def test_save_story(self, mock_graph_store):
        """Test saving a story."""
        store = mock_graph_store

        story_data = {
            "id": "story1",
            "title": "The Beginning",
            "summary": "How it all started",
            "values_revealed": ["courage", "hope"],
        }

        await store.save_story("story1", story_data, "ent1", "v1")
        stories = await store.load_stories_for_entity("ent1", "v1")

        assert len(stories) == 1
        assert stories[0]["title"] == "The Beginning"


# =============================================================================
# Integration Tests (Require Running Services)
# =============================================================================

@pytest.mark.integration
class TestIntegration:
    """Integration tests requiring FalkorDB and other services.

    Run with: pytest tests/test_vessels_core.py -v -m integration
    These tests are skipped by default unless services are available.
    """

    @pytest.fixture
    def live_graph_store(self):
        """Create a live graph store connection."""
        import os
        from python.helpers.graph_store import GraphStore, GraphStoreConfig

        config = GraphStoreConfig(
            host=os.getenv("FALKORDB_HOST", "localhost"),
            port=int(os.getenv("FALKORDB_PORT", "6379")),
            database="vessels_test",
        )

        try:
            store = GraphStore(config)
            return store
        except Exception as e:
            pytest.skip(f"FalkorDB not available: {e}")

    @pytest.mark.asyncio
    async def test_real_entity_roundtrip(self, live_graph_store):
        """Test full entity save/load with real database."""
        store = live_graph_store

        entity_data = {
            "id": f"test_{datetime.now().timestamp()}",
            "name": "Integration Test Entity",
            "entity_type": "agent",
            "voice_source": "self",
            "moral_position": {"compassion": 0.8, "justice": 0.7},
        }

        entity_id = await store.save_entity(
            entity_data["id"],
            entity_data,
            "integration_test"
        )

        loaded = await store.load_entity(entity_id, "integration_test")
        assert loaded is not None
        assert loaded["moral_position"]["compassion"] == 0.8


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
