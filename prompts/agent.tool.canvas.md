# Canvas Tools

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
