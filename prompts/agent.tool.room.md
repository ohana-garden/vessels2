# Conversation Room Tools

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
