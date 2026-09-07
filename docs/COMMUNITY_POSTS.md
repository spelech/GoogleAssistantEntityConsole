# Community Announcement Posts (Reddit & Home Assistant Forum)

This document contains pragmatic, technical post drafts for introducing **Google Assistant Entity Console** to **r/homeassistant** and the **Home Assistant Community Forum**.

---

## 1. Reddit Post Draft (r/homeassistant)

### **Title**:
```text
Google Assistant Entity Console: A sidebar dashboard for entity exposure, voice aliases, and regex blocklists
```

### **Body**:

Hey everyone,

If you self-host Home Assistant and expose devices to Google Assistant via the native `google_assistant:` integration, managing entity configs in YAML can become cumbersome as your smart home grows. Adding or removing entities, keeping track of friendly names, assigning voice aliases, and excluding noisy sensors (like battery levels) usually means manually editing configuration files and triggering reloads or restarts.

I built **Google Assistant Entity Console** to streamline this workflow. It runs as a native custom component and provides a sidebar panel to manage exposure, aliases, and blocklists directly from the UI.

### Motivation & Features

- **Automated YAML Generation**: Replaces manually maintained `entity_config` blocks with a structured YAML generator (`gaGen_YYMMDD.yaml`).
- **Entity Filtering**: Provides a regex blocklist engine to permanently exclude entity patterns (e.g. `.*_battery_level$`) without cluttering configuration files.
- **Alias & Nickname Management**: Allows editing voice nicknames inline on entity rows instead of looking up entity IDs and writing nested YAML lists.
- **Zero-Downtime Updates**: Triggers `homeassistant.reload_config_entry` on rebuild so updates take effect without restarting Home Assistant core.

### Overview & Screenshots

The UI supports two views depending on how you organize your setup:
- **Location-First**: Groups entities by `Floor -> Room (Area) -> Domain`.
- **Domain-First**: Groups entities by `Domain -> Floor -> Room (Area)`.

#### Location View (`Floor -> Room -> Domain`)
![Location View](https://raw.githubusercontent.com/spelech/googleAssistantConfigGen/main/brand/dashboard_location_view.png)

#### Domain View (`Domain -> Floor -> Room`)
![Domain View](https://raw.githubusercontent.com/spelech/googleAssistantConfigGen/main/brand/dashboard_domain_view.png)

#### Regex Blocklist Manager
![Blocklist View](https://raw.githubusercontent.com/spelech/googleAssistantConfigGen/main/brand/blocklist_modal_view.png)

### Key Technical Features

- **Native Sidebar Panel**: Integrates via a Web Component panel (`google-assistant-entity-console-panel`).
- **Inline Controls**: Click badges to toggle exposure state (*Exposed*, *Pending Add*, *Pending Remove*, *Not Exposed*), rename display names, and edit nickname chips.
- **Regex Blocklist Engine**: Pre-compiles regular expressions to filter entities before rendering or exporting to YAML.
- **AI Assistance (Optional & Local-Friendly)**:
  - Supports local endpoints (Ollama, LocalAI, vLLM via OpenAI-compatible API) or HA Assist agents.
  - Generates natural voice aliases using surrounding room context to avoid duplicate voice commands.
  - Evaluates natural language queries (e.g. *"Expose all bedroom lights and climate controls"*) to select entity IDs.
- **HA Theme Parity**: Maps standard Home Assistant CSS custom properties (`--primary-background-color`, `--card-background-color`, `--primary-color`) so it matches whatever dashboard theme you use.
- **Safe YAML Serialization**: Uses custom PyYAML loaders/dumpers to preserve `!secret` and `!include` tags without breaking existing configs.

### Quick Setup

1. Add custom repository in HACS: `https://github.com/spelech/googleAssistantConfigGen` (Category: Integration).
2. Download and restart Home Assistant.
3. Add the integration in **Settings** > **Devices & Services**.
4. In your `configuration.yaml`, include the generated file:
   ```yaml
   google_assistant: !include gaGen_062226.yaml
   ```

### Repo & Technical Docs

- **GitHub Repository**: https://github.com/spelech/googleAssistantConfigGen
- **Architecture Spec**: https://github.com/spelech/googleAssistantConfigGen/blob/main/docs/ARCHITECTURE.md
- **AI Engine Details**: https://github.com/spelech/googleAssistantConfigGen/blob/main/docs/AI_INTEGRATION.md
- **Theme Mapping Spec**: https://github.com/spelech/googleAssistantConfigGen/blob/main/docs/THEMING.md

Feedback and contributions welcome.

---

## 2. Home Assistant Community Forum Post Draft

### **Category**: Custom Integrations / Share your Projects
### **Title**:
```text
Google Assistant Entity Console - UI management for entity exposure, voice aliases, and regex blocklists
```

### **Body**:

Hi everyone,

Managing Google Assistant entity configuration in Home Assistant through manual YAML editing can be cumbersome, especially when dealing with dozens of devices across multiple rooms, setting up voice aliases, or excluding unwanted sensors.

I created **Google Assistant Entity Console** to manage this through a dedicated sidebar dashboard inside Home Assistant.

![Google Assistant Entity Console Logo](https://raw.githubusercontent.com/spelech/googleAssistantConfigGen/main/brand/logo.png)

### Key Functionality

1. **Visual Exposure Management**: Toggle exposure states per entity or batch-select across floors, rooms, or domains.
2. **Inline Alias Editing**: Add, update, or remove voice nicknames directly on entity rows.
3. **Regex Blocklisting**: Exclude entity ID patterns (e.g. `.*_battery_level$`, `.*_ble_.*`) using regular expression rules with syntax validation.
4. **Structured YAML Generation**: Automatically compiles entity configuration into a timestamped file (`gaGen_YYMMDD.yaml`), preserving `!secret` and `!include` tags.
5. **Optional AI Assistance**: Integrate with local LLMs (Ollama/LocalAI) or Home Assistant Assist agents for room-aware alias generation and intent-based entity selection.
6. **Native Dashboard Theme Inheritance**: Uses Home Assistant CSS custom properties to automatically match light, dark, or custom themes.

### Screenshots

Location View (`Floor -> Room -> Domain`):
![Location View](https://raw.githubusercontent.com/spelech/googleAssistantConfigGen/main/brand/dashboard_location_view.png)

Domain View (`Domain -> Floor -> Room`):
![Domain View](https://raw.githubusercontent.com/spelech/googleAssistantConfigGen/main/brand/dashboard_domain_view.png)

Blocklist Manager:
![Blocklist View](https://raw.githubusercontent.com/spelech/googleAssistantConfigGen/main/brand/blocklist_modal_view.png)

### Installation

1. Add custom repository in HACS: `https://github.com/spelech/googleAssistantConfigGen` (Category: Integration).
2. Download and restart Home Assistant.
3. Configure via **Settings** > **Devices & Services** > **Add Integration**.
4. Point your `configuration.yaml` to the generated file:
   ```yaml
   google_assistant: !include gaGen_062226.yaml
   ```

### Documentation & Repository

- Repository: https://github.com/spelech/googleAssistantConfigGen
- Architecture Spec: https://github.com/spelech/googleAssistantConfigGen/blob/main/docs/ARCHITECTURE.md
- AI Engine Spec: https://github.com/spelech/googleAssistantConfigGen/blob/main/docs/AI_INTEGRATION.md
- Theme Integration Spec: https://github.com/spelech/googleAssistantConfigGen/blob/main/docs/THEMING.md

Let me know if you have any questions or feedback.
