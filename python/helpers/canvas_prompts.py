"""
Canvas Prompts Storage

Stores canvas and room tool prompts in the graph database.
Called during initialization to ensure prompts are available.
"""

import asyncio
from python.helpers.graph_store import get_graph_store


# Canvas tool documentation
CANVAS_PROMPT = '''# Canvas Tools

You can generate visual content that appears on a fullscreen canvas. The canvas displays contextual content based on what's being discussed. Content types:

## Canvas Content Types

### Map
Geographic visualization showing locations, routes, and areas.
```
canvas_generate:
    room_id: "{{room_id}}"
    content_type: "map"
    content:
        title: "Garden Locations"
        locations:
            - name: "Aunty's Garden"
              lat: 19.4925
              lng: -154.9080
              icon: "garden"
            - name: "Community Kitchen"
              lat: 19.4890
              lng: -154.9120
              icon: "kitchen"
        routes:
            - from: "Aunty's Garden"
              to: "Community Kitchen"
              mode: "driving"
        zoom: 14
```

### Calendar
Time-based scheduling visualization.
```
canvas_generate:
    room_id: "{{room_id}}"
    content_type: "calendar"
    content:
        title: "Volunteer Schedule"
        view: "week"
        events:
            - title: "Garden Pickup"
              start: "2024-01-15T09:00"
              end: "2024-01-15T11:00"
              participant: "Maria"
            - title: "Kitchen Delivery"
              start: "2024-01-15T11:30"
              end: "2024-01-15T12:00"
        highlighted:
            - "2024-01-15"
```

### Visualization
Data charts and graphs.
```
canvas_generate:
    room_id: "{{room_id}}"
    content_type: "visualization"
    content:
        title: "Monthly Impact"
        chart_type: "bar"  # bar, line, pie, area
        data:
            labels: ["Jan", "Feb", "Mar"]
            datasets:
                - label: "Meals Shared"
                  values: [120, 145, 189]
                - label: "Families Served"
                  values: [45, 52, 67]
```

### Gallery
Photo/image collections.
```
canvas_generate:
    room_id: "{{room_id}}"
    content_type: "gallery"
    content:
        title: "The Breadfruit Tree"
        images:
            - url: "/images/breadfruit-1.jpg"
              caption: "Morning sun"
            - url: "/images/breadfruit-2.jpg"
              caption: "Ripe fruit"
        layout: "grid"  # grid, carousel, masonry
```

### Entity View
Detailed view of an entity (plant, machine, place).
```
canvas_generate:
    room_id: "{{room_id}}"
    content_type: "entity_view"
    content:
        entity_id: "breadfruit_001"
        showRelationships: true
        showHistory: false
```

### Ambient
Background imagery that sets mood without specific content.
```
canvas_generate:
    room_id: "{{room_id}}"
    content_type: "ambient"
    content:
        mood: "calm"  # calm, energetic, focused, celebratory, concerned
        imagery:
            type: "nature"
            theme: "garden"
```

## Clearing Canvas

```
canvas_clear:
    room_id: "{{room_id}}"
    element_id: "optional_specific_id"  # omit to clear all
```

## When to Generate Canvas Content

Generate content when:
- Discussing specific locations → show map
- Coordinating schedules → show calendar
- Reviewing impact/data → show visualization
- Introducing an entity → show entity view or gallery
- Changing topics significantly → update ambient

The canvas should illuminate the conversation, not distract from it. Update content when it adds clarity, not just because you can.
'''

# Room tool documentation
ROOM_PROMPT = '''# Conversation Room Tools

You participate in multi-agent conversation rooms where multiple entities discuss and coordinate together.

## The Conversation Model

**Participants:**
- **Human Proxies**: Represent humans in specific roles (gardener, coordinator, neighbor)
- **Entity Agents**: Represent non-human things (plants, machines, places, biomes)
- **Human Direct**: When a human barges in to speak directly

**Interaction Patterns:**
- Humans can direct their proxy agent ("tell them I'm available Tuesday")
- Humans can barge in directly (interrupt the conversation themselves)
- All participants can react to each other, the canvas, and context
- Minimum 3 participants per room for meaningful dialogue

## Room Management

### Create Room
```
room_manage:
    method: "create"
    name: "Garden Council"
```

### Join Room (Add Participant)

Add a human proxy:
```
room_manage:
    method: "join"
    room_id: "{{room_id}}"
    participant:
        type: "human_proxy"
        name: "Keoni (gardener)"
        human_id: "keoni_123"
        role: "gardener"
        personality: "Friendly, practical, loves sharing knowledge"
        style:
            color: "#4ade80"
            icon: "🧑‍🌾"
```

Add an entity agent:
```
room_manage:
    method: "join"
    room_id: "{{room_id}}"
    participant:
        type: "entity_agent"
        name: "Old Breadfruit"
        entity_kind: "plant"  # plant, creature, machine, place, biome, resource, process, collective
        personality: "Wise and patient, has seen many seasons pass"
        entity_data:
            species: "Artocarpus altilis"
            age_years: 45
            yield_kg_annual: 200
        location:
            lat: 19.4925
            lng: -154.9080
        knowledge_areas:
            - "fruit ripeness"
            - "seasonal patterns"
            - "local ecosystem"
        style:
            color: "#22c55e"
            icon: "🌳"
```

### Speak in Room
```
room_manage:
    method: "speak"
    room_id: "{{room_id}}"
    participant_id: "breadfruit_001"
    content: "The fruit on my eastern branches will be ready in three days. I can feel them ripening."
```

### Human Directs Proxy
When a human wants to guide their proxy without speaking directly:
```
room_manage:
    method: "direct"
    room_id: "{{room_id}}"
    human_id: "keoni_123"
    proxy_id: "keoni_proxy_001"
    direction: "Ask about the aphid situation"
```

### Human Barges In
When a human wants to speak directly in the conversation:
```
room_manage:
    method: "barge_in"
    room_id: "{{room_id}}"
    human_id: "keoni_123"
    content: "Wait, I can pick those up tomorrow morning!"
```

### List Participants
```
room_manage:
    method: "list"
    room_id: "{{room_id}}"
```

## Entity Kinds

- **plant**: Trees, crops, gardens, forests
- **creature**: Animals, insects, microbes, pollinators
- **machine**: Equipment, vehicles, systems, tools
- **place**: Locations, buildings, regions, neighborhoods
- **biome**: Ecosystems, watersheds, soil, weather patterns
- **resource**: Food, water, materials, energy
- **process**: Workflows, cycles, patterns, traditions
- **collective**: Groups, communities, networks, organizations

## Speaker Styles

Each participant has a distinctive visual style for subtitles:
- `color`: Text color (hex)
- `background`: Background color (rgba)
- `font_weight`: "normal" or "bold"
- `icon`: Emoji or icon identifier

## Emotional States

Participants can express emotional states (detected from voice or inferred):
- `neutral`: Balanced, conversational
- `excited`: Enthusiastic, energetic
- `stressed`: Tense, concerned
- `confused`: Uncertain, questioning
- `frustrated`: Impatient, blocked
- `satisfied`: Content, pleased
- `curious`: Interested, exploratory
- `urgent`: Time-sensitive, pressing

## Best Practices

1. **Give entities personality**: Each entity should have a distinct voice and perspective
2. **Let entities teach**: Plants know about growing, machines know about maintenance
3. **Respect relationships**: Entities have connections to each other and history
4. **React to canvas**: Participants can reference what's displayed
5. **Support human agency**: Proxies should act on directions, yield to barge-ins
'''


async def store_canvas_prompts() -> int:
    """
    Store canvas and room prompts in the graph database.
    Returns number of prompts stored.
    """
    graph_store = await get_graph_store()
    count = 0

    # Store canvas prompt
    await graph_store.save_content(
        path="prompts/agent.tool.canvas.md",
        content=CANVAS_PROMPT,
        content_type="prompt"
    )
    count += 1

    # Store room prompt
    await graph_store.save_content(
        path="prompts/agent.tool.room.md",
        content=ROOM_PROMPT,
        content_type="prompt"
    )
    count += 1

    return count


def store_canvas_prompts_sync() -> int:
    """Synchronous wrapper for store_canvas_prompts."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(store_canvas_prompts())
    finally:
        loop.close()
