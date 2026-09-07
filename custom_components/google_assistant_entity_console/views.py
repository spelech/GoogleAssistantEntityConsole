import logging
import os
import re
from aiohttp import web
import yaml

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry,
    device_registry,
    entity_registry,
    floor_registry,
)
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class Secret:
    def __init__(self, value: str):
        self.value = value

class Include:
    def __init__(self, value: str):
        self.value = value

def secret_representer(dumper, data):
    return dumper.represent_scalar('!secret', data.value)

def include_representer(dumper, data):
    return dumper.represent_scalar('!include', data.value)

# Register representers on SafeDumper
yaml.SafeDumper.add_representer(Secret, secret_representer)
yaml.SafeDumper.add_representer(Include, include_representer)

DEFAULT_YAML_HEADER = [
    "project_id: !secret googleassistant_projectName",
    "service_account: !include SERVICE_ACCOUNT.json",
    "report_state: true",
    "secure_devices_pin: !secret google_device_pin",
    "expose_by_default: false",
]


def extract_yaml_header(content: str | None) -> list[str]:
    """Extract top-level header lines before entity_config: from existing YAML content."""
    if not content or not isinstance(content, str) or not content.strip():
        return list(DEFAULT_YAML_HEADER)

    header_raw: list[str] = []
    for line in content.splitlines():
        if line.strip().startswith("entity_config:"):
            break
        header_raw.append(line)

    while header_raw and (not header_raw[-1].strip() or header_raw[-1].strip().startswith("#")):
        header_raw.pop()

    trimmed_lines = [line.strip() for line in header_raw if line.strip()]

    has_keys = any(":" in line and not line.startswith("#") for line in trimmed_lines)
    if not has_keys:
        return list(DEFAULT_YAML_HEADER)

    return trimmed_lines


import json

def load_blocklist(hass: HomeAssistant) -> list:
    filepath = hass.config.path("google_assistant_entity_console_blocklist.json")
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception as err:
        _LOGGER.error("Failed to load blocklist: %s", err)
    return []

def save_blocklist(hass: HomeAssistant, blocklist: list):
    filepath = hass.config.path("google_assistant_entity_console_blocklist.json")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(blocklist, f, indent=2)
    except Exception as err:
        _LOGGER.error("Failed to save blocklist: %s", err)

def _read_file_content(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


async def get_current_yaml_filename(hass: HomeAssistant):
    config_path = hass.config.path("configuration.yaml")
    try:
        config_content = await hass.async_add_executor_job(_read_file_content, config_path)
        include_pattern = r"google_assistant:\s*!include\s*(gaGen_\d{6}\.yaml)"
        match = re.search(include_pattern, config_content)
        if match:
            return match.group(1)
    except FileNotFoundError:
        pass
    except Exception as err:
        _LOGGER.error("Failed to read configuration.yaml: %s", err)
    return None


async def load_yaml_exposed_entities(hass: HomeAssistant, filename: str):
    if not filename:
        return {}
    filepath = hass.config.path(filename)
    
    try:
        class CustomLoader(yaml.SafeLoader):
            pass
        CustomLoader.add_constructor('!secret', lambda loader, node: node.value)
        CustomLoader.add_constructor('!include', lambda loader, node: node.value)
        
        content = await hass.async_add_executor_job(_read_file_content, filepath)
        
        data = yaml.load(content, Loader=CustomLoader)
        if data and isinstance(data, dict):
            entity_config = data.get("entity_config", {})
            exposed = {}
            for ent_id, cfg in entity_config.items():
                if isinstance(cfg, dict) and cfg.get("expose", False):
                    exposed[ent_id] = {
                        "name": cfg.get("name"),
                        "aliases": cfg.get("aliases", []),
                        "room": cfg.get("room")
                    }
            return exposed
    except FileNotFoundError:
        pass
    except Exception as err:
        _LOGGER.error("Failed to load/parse yaml file %s: %s", filename, err)
    return {}


async def async_fetch_entities_data(hass: HomeAssistant):
    ent_reg = entity_registry.async_get(hass)
    dev_reg = device_registry.async_get(hass)
    area_reg = area_registry.async_get(hass)
    floor_reg = floor_registry.async_get(hass)

    # Identify all light group members in Home Assistant
    light_group_members = set()
    for state in hass.states.async_all("light"):
        if state.attributes and "entity_ids" in state.attributes:
            members = state.attributes.get("entity_ids")
            if isinstance(members, list):
                for m in members:
                    light_group_members.add(m)
    for state in hass.states.async_all("group"):
        if state.attributes and "entity_ids" in state.attributes:
            members = state.attributes.get("entity_ids")
            if isinstance(members, list):
                for m in members:
                    if m.startswith("light."):
                        light_group_members.add(m)

    # Build area name and floor mapping
    area_map = {}
    area_floor_map = {}
    for area in area_reg.async_list_areas():
        area_map[area.id] = area.name
        area_floor_map[area.id] = area.floor_id

    # Build floor name mapping
    floor_map = {floor.floor_id: floor.name for floor in floor_reg.async_list_floors()}

    # Load currently exposed YAML config to compare
    yaml_filename = await get_current_yaml_filename(hass)
    yaml_exposed = await load_yaml_exposed_entities(hass, yaml_filename)

    # Build device mappings
    device_area_map = {}
    device_name_map = {}
    for device in dev_reg.devices.values():
        device_area_map[device.id] = device.area_id
        device_name_map[device.id] = device.name_by_user or device.name

    # Load blocklist
    blocklist = load_blocklist(hass)
    compiled_blocklist = []
    for pattern in blocklist:
        try:
            compiled_blocklist.append(re.compile(pattern))
        except re.error as err:
            _LOGGER.error("Invalid regex in blocklist '%s': %s", pattern, err)

    active_entities = []
    for entry in ent_reg.entities.values():
        # Filter out disabled and hidden entities
        if entry.disabled_by or entry.hidden_by:
            continue

        entity_id = entry.entity_id

        # Check blocklist
        is_blocked = False
        for rx in compiled_blocklist:
            if rx.search(entity_id):
                is_blocked = True
                break
        if is_blocked:
            continue

        device_id = entry.device_id
        domain = entity_id.split(".")[0]

        # Filter supported domains and specific device classes as per Google Assistant integration docs
        device_class = entry.device_class or entry.original_device_class or ""
        supported_domains = {
            "alarm_control_panel", "button", "camera", "climate", "cover", "fan",
            "group", "humidifier", "input_boolean", "input_button", "input_select",
            "light", "lawn_mower", "lock", "media_player", "scene", "script",
            "select", "switch", "vacuum", "valve", "water_heater"
        }

        if domain not in supported_domains:
            if domain == "binary_sensor":
                if device_class not in {"carbon_monoxide", "door", "garage_door", "lock", "moisture", "opening", "smoke", "window"}:
                    continue
            elif domain == "event":
                if device_class != "doorbell":
                    continue
            elif domain == "sensor":
                if device_class not in {"aqi", "carbon_dioxide", "carbon_monoxide", "humidity", "pm10", "pm25", "temperature", "volatile_organic_compounds"}:
                    continue
            else:
                continue

        # Resolve Area and Floor
        area_id = entry.area_id
        if not area_id and device_id:
            area_id = device_area_map.get(device_id)
        
        area_name = "TBA"
        floor_name = "TBA"
        if area_id:
            area_name = area_map.get(area_id, "TBA")
            floor_id = area_floor_map.get(area_id)
            if floor_id:
                floor_name = floor_map.get(floor_id, "TBA")

        # Resolve Display Name
        display_name = entry.name
        if (not display_name or not isinstance(display_name, str)) and device_id:
            display_name = device_name_map.get(device_id)
        if not display_name or not isinstance(display_name, str):
            display_name = entry.original_name
        if not display_name or not isinstance(display_name, str):
            # Fallback to formatting entity ID name part
            name_part = entity_id.split(".")[-1]
            display_name = name_part.replace("_", " ").title()
        display_name = str(display_name)

        # Resolve should_expose
        should_expose = False
        if entry.options and "conversation" in entry.options:
            should_expose = entry.options["conversation"].get("should_expose", False)

        # Compare with what is in the yaml file
        yaml_exp = entity_id in yaml_exposed

        # Clean/filter aliases (strictly allow only valid string values)
        raw_aliases = entry.aliases or []
        clean_aliases = [
            str(a) for a in raw_aliases
            if a and isinstance(a, str) and a != "0" and a != 0
        ]

        platform = entry.platform or ""
        device_class = entry.device_class or ""
        in_group = entity_id in light_group_members

        # Resolve state availability
        state_obj = hass.states.get(entity_id)
        is_unavailable = state_obj is None or state_obj.state in ("unavailable", "unknown")

        active_entities.append({
            "entity_id": entity_id,
            "name": entry.name,
            "original_name": entry.original_name,
            "display_name": display_name,
            "device_class": device_class,
            "platform": platform,
            "should_expose": should_expose,
            "yaml_exposed": yaml_exp,
            "area": area_name,
            "floor": floor_name,
            "domain": domain,
            "aliases": clean_aliases,
            "in_group": in_group,
            "unavailable": is_unavailable
        })

    return active_entities


class EntitiesView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/entities"
    name = "api:google_assistant_entity_console:entities"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            entities = await async_fetch_entities_data(hass)
            yaml_filename = (await get_current_yaml_filename(hass)) or "None"
            
            # Read version natively via Home Assistant loader
            from homeassistant.loader import async_get_integration
            try:
                integration = await async_get_integration(hass, DOMAIN)
                version = integration.version
            except Exception:
                version = "Unknown"

            return self.json({
                "entities": entities,
                "yaml_filename": yaml_filename,
                "version": version
            })
        except Exception as err:
            _LOGGER.exception("Failed to fetch entities registry")
            return self.json({"error": str(err)}, status_code=500)


class UpdateEntityView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/entities/update"
    name = "api:google_assistant_entity_console:entities:update"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
            entity_id = body.get("entity_id")
            name = body.get("name")
            aliases = body.get("aliases")
            should_expose = body.get("should_expose")

            if not entity_id:
                return self.json({"error": "Missing entity_id"}, status_code=400)

            ent_reg = entity_registry.async_get(hass)
            entry = ent_reg.async_get(entity_id)
            if not entry:
                return self.json({"error": f"Entity {entity_id} not found"}, status_code=404)

            # Filter out any "0", 0, or empty values from aliases
            clean_aliases = None
            if aliases is not None:
                clean_aliases = [a for a in aliases if a and a != "0" and a != 0]

            # Update entry details
            ent_reg.async_update_entity(
                entity_id,
                name=name if name else None,
                aliases=set(clean_aliases) if clean_aliases is not None else None
            )

            # Update conversation (exposure) option namespace
            ent_reg.async_update_entity_options(
                entity_id,
                "conversation",
                {"should_expose": bool(should_expose)}
            )

            return self.json({"success": True})
        except Exception as err:
            _LOGGER.exception("Failed to update entity settings")
            return self.json({"error": str(err)}, status_code=500)


class RebuildView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/rebuild"
    name = "api:google_assistant_entity_console:rebuild"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            now = dt_util.now()
            date_str = now.strftime("%m%d%y")
            filename = f"gaGen_{date_str}.yaml"
            filepath = hass.config.path(filename)

            active_entities = await async_fetch_entities_data(hass)

            # Sort entities by floor, area, domain, entity_id
            sorted_entities = sorted(
                active_entities,
                key=lambda x: (x["floor"] or "TBA", x["area"] or "TBA", x["domain"], x["entity_id"])
            )

            existing_filename = await get_current_yaml_filename(hass)
            existing_filepath = None
            if existing_filename:
                cand_path = hass.config.path(existing_filename)
                if os.path.exists(cand_path):
                    existing_filepath = cand_path
            if not existing_filepath and os.path.exists(filepath):
                existing_filepath = filepath

            existing_content = ""
            if existing_filepath:
                try:
                    existing_content = await hass.async_add_executor_job(_read_file_content, existing_filepath)
                except Exception as err:
                    _LOGGER.warning("Failed to read existing YAML header from %s: %s", existing_filepath, err)
                    existing_content = ""

            header_lines = extract_yaml_header(existing_content)
            yaml_lines = list(header_lines) + ["entity_config:"]

            current_floor = None
            current_area = None
            current_domain = None
            exposed_count = 0

            for entity in sorted_entities:
                if not entity["should_expose"]:
                    continue

                exposed_count += 1
                
                # Check for Floor transition
                ent_floor = entity["floor"] or "TBA"
                if ent_floor != current_floor:
                    current_floor = ent_floor
                    current_area = None
                    current_domain = None
                    yaml_lines.append(f"\n  # {'='*70}")
                    yaml_lines.append(f"  # Floor: {current_floor}")
                    yaml_lines.append(f"  # {'='*70}")

                # Check for Area (Room) transition
                ent_area = entity["area"] or "TBA"
                if ent_area != current_area:
                    current_area = ent_area
                    current_domain = None
                    yaml_lines.append(f"\n  # --- Room: {current_area} ---")

                # Check for Domain transition
                ent_domain = entity["domain"]
                if ent_domain != current_domain:
                    current_domain = ent_domain
                    yaml_lines.append(f"  # Type: {current_domain.title()}")

                # Dump this single entity config
                cfg = {
                    "expose": True,
                    "name": entity["display_name"]
                }
                if entity["aliases"]:
                    cfg["aliases"] = entity["aliases"]
                if entity["area"] and entity["area"] != "TBA":
                    cfg["room"] = entity["area"]

                single_cfg = {entity["entity_id"]: cfg}
                dumped = yaml.dump(single_cfg, Dumper=yaml.SafeDumper, sort_keys=False, width=1000)

                for line in dumped.splitlines():
                    if line.strip():
                        yaml_lines.append(f"  {line}")

            cleaned_yaml = "\n".join(yaml_lines) + "\n"

            # Syntax validation step
            class CustomLoader(yaml.SafeLoader):
                pass
            CustomLoader.add_constructor('!secret', lambda loader, node: node.value)
            CustomLoader.add_constructor('!include', lambda loader, node: node.value)

            try:
                yaml.load(cleaned_yaml, Loader=CustomLoader)
            except Exception as val_err:
                return self.json({"error": f"Generated YAML failed validation: {val_err}"}, status_code=500)

            # Write file
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(cleaned_yaml)

            # Dynamically update configuration.yaml
            config_path = hass.config.path("configuration.yaml")
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    config_content = f.read()
                
                include_pattern = r"google_assistant:\s*!include\s*gaGen_\d{6}\.yaml"
                if re.search(include_pattern, config_content):
                    config_content = re.sub(
                        include_pattern,
                        f"google_assistant: !include {filename}",
                        config_content
                    )
                    with open(config_path, "w", encoding="utf-8") as f:
                        f.write(config_content)
                else:
                    _LOGGER.warning("Could not find google_assistant !include line in configuration.yaml")

            return self.json({
                "success": True,
                "exposed_count": exposed_count,
                "yaml_written": filepath
            })
        except Exception as err:
            _LOGGER.exception("Failed to rebuild configs")
            return self.json({"error": str(err)}, status_code=500)


class RestartView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/restart"
    name = "api:google_assistant_entity_console:restart"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            await hass.services.async_call("homeassistant", "restart", blocking=False)
            return self.json({"success": True})
        except Exception as err:
            _LOGGER.exception("Failed to trigger Home Assistant restart")
            return self.json({"error": str(err)}, status_code=500)


class BlocklistView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/blocklist"
    name = "api:google_assistant_entity_console:blocklist"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            blocklist = load_blocklist(hass)
            return self.json({"blocklist": blocklist})
        except Exception as err:
            _LOGGER.exception("Failed to get blocklist")
            return self.json({"error": str(err)}, status_code=500)

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
            blocklist = body.get("blocklist")
            if not isinstance(blocklist, list):
                return self.json({"error": "Blocklist must be a list"}, status_code=400)
            
            # Syntax validation for regexes
            for pattern in blocklist:
                try:
                    re.compile(pattern)
                except re.error as err:
                    return self.json({"error": f"Invalid regex pattern '{pattern}': {err}"}, status_code=400)

            save_blocklist(hass, blocklist)
            return self.json({"success": True, "blocklist": blocklist})
        except Exception as err:
            _LOGGER.exception("Failed to update blocklist")
            return self.json({"error": str(err)}, status_code=500)


class BlocklistAddView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/blocklist/add"
    name = "api:google_assistant_entity_console:blocklist:add"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
            pattern = body.get("pattern")
            if not pattern:
                return self.json({"error": "Missing pattern"}, status_code=400)

            try:
                re.compile(pattern)
            except re.error as err:
                return self.json({"error": f"Invalid regex pattern: {err}"}, status_code=400)

            blocklist = load_blocklist(hass)
            if pattern not in blocklist:
                blocklist.append(pattern)
                save_blocklist(hass, blocklist)

            return self.json({"success": True, "blocklist": blocklist})
        except Exception as err:
            _LOGGER.exception("Failed to add to blocklist")
            return self.json({"error": str(err)}, status_code=500)


# AI Settings Storage Helpers
def load_ai_settings(hass: HomeAssistant) -> dict:
    filepath = hass.config.path("google_assistant_entity_console_ai_settings.json")
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as err:
        _LOGGER.error("Failed to load AI settings: %s", err)
    return {}

def save_ai_settings(hass: HomeAssistant, settings: dict):
    filepath = hass.config.path("google_assistant_entity_console_ai_settings.json")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as err:
        _LOGGER.error("Failed to save AI settings: %s", err)


# AI API Views
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.conversation import async_converse, async_get_agent_info
from homeassistant.core import Context

async def async_call_llm(hass: HomeAssistant, prompt: str, settings: dict) -> str:
    ai_source = settings.get("ai_source", "openai")
    
    if ai_source == "home_assistant":
        ha_agent_id = settings.get("ha_agent_id")
        if not ha_agent_id:
            raise ValueError("Home Assistant conversation agent is not selected. Please configure it in Settings.")
            
        result = await async_converse(
            hass=hass,
            text=prompt,
            conversation_id=None,
            context=Context(),
            agent_id=ha_agent_id
        )
        
        # Check if error response
        if result.response.response_type == "error":
            raise RuntimeError(f"HA Conversation Agent error: {result.response.as_dict().get('speech', {}).get('plain', {}).get('speech', 'Unknown error')}")
            
        response_text = result.response.as_dict().get("speech", {}).get("plain", {}).get("speech", "")
        if not response_text:
            raise RuntimeError("HA Conversation Agent returned an empty response.")
        return response_text.strip()
        
    else: # openai compatible api
        base_url = settings.get("base_url", "").rstrip("/")
        api_key = settings.get("api_key", "")
        model = settings.get("model", "")
        
        if not base_url or not model:
            raise ValueError("AI settings are incomplete. Please configure base URL and Model in Settings.")
            
        session = async_get_clientsession(hass)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
            
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.1,
            "max_tokens": 1000
        }
        
        async with session.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=25) as resp:
            if resp.status == 200:
                data = await resp.json()
                content = data["choices"][0]["message"]["content"].strip()
                return content
            else:
                err_text = await resp.text()
                raise RuntimeError(f"API Error ({resp.status}): {err_text}")


class AIHaAgentsView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/ai/ha_agents"
    name = "api:google_assistant_entity_console:ai:ha_agents"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            agents = async_get_agent_info(hass)
            serialized_agents = []
            for agent in agents:
                serialized_agents.append({
                    "id": agent.id,
                    "name": agent.name
                })
            return self.json({"agents": serialized_agents})
        except Exception as err:
            return self.json({"error": str(err)}, status_code=500)


class AISettingsView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/ai/settings"
    name = "api:google_assistant_entity_console:ai:settings"

    async def get(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            settings = load_ai_settings(hass)
            return self.json({"settings": settings})
        except Exception as err:
            return self.json({"error": str(err)}, status_code=500)

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
            settings = body.get("settings", {})
            if not isinstance(settings, dict):
                return self.json({"error": "Settings must be a dictionary"}, status_code=400)
            
            save_ai_settings(hass, settings)
            return self.json({"success": True, "settings": settings})
        except Exception as err:
            return self.json({"error": str(err)}, status_code=500)


class AIModelsView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/ai/models"
    name = "api:google_assistant_entity_console:ai:models"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
            base_url = body.get("base_url", "").rstrip("/")
            api_key = body.get("api_key", "")
            
            if not base_url:
                return self.json({"error": "Missing base URL"}, status_code=400)
                
            session = async_get_clientsession(hass)
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                
            async with session.get(f"{base_url}/models", headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return self.json({"error": f"Failed to fetch models (HTTP {resp.status}): {text}"}, status_code=resp.status)
                
                data = await resp.json()
                models = []
                
                def parse_item(item):
                    if not isinstance(item, dict) or "id" not in item:
                        return None
                    return {
                        "id": item["id"],
                        "name": item.get("name") or item["id"],
                        "pricing": item.get("pricing") or {}
                    }

                if isinstance(data, dict) and "data" in data:
                    for item in data["data"]:
                        parsed = parse_item(item)
                        if parsed:
                            models.append(parsed)
                elif isinstance(data, list):
                    for item in data:
                        parsed = parse_item(item)
                        if parsed:
                            models.append(parsed)
                
                # Sort models by name
                models.sort(key=lambda m: m["name"].lower())
                return self.json({"models": models})
        except Exception as err:
            _LOGGER.exception("Failed to query models")
            return self.json({"error": str(err)}, status_code=500)


class AIGenerateNicknamesView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/ai/generate_nicknames"
    name = "api:google_assistant_entity_console:ai:generate_nicknames"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
            entities_to_gen = body.get("entities", [])
            if not entities_to_gen:
                return self.json({"error": "No entities provided"}, status_code=400)
                
            settings = load_ai_settings(hass)
            base_url = settings.get("base_url", "").rstrip("/")
            api_key = settings.get("api_key", "")
            model = settings.get("model", "")
            prompt_template = settings.get("nickname_prompt", "").strip()
            
            # Default fallback template
            if not prompt_template:
                prompt_template = (
                    "You are an assistant helping configure Google Assistant aliases for smart home entities.\n"
                    "For the following entity, generate 2-4 clean, natural-language nicknames (aliases) that a user would typically say to control the device.\n"
                    "Do NOT include markdown, explanations, bullet points, numbers, quotes, or punctuation.\n"
                    "Return the nicknames ONLY as a single comma-separated list on a single line.\n\n"
                    "Entity ID: {entity_id}\n"
                    "Friendly Name: {friendly_name}\n"
                    "Aliases:"
                )
                
            results = {}
            for ent in entities_to_gen:
                ent_id = ent.get("entity_id")
                friendly = ent.get("display_name") or ent.get("name") or ent_id.split(".")[-1]
                
                # Render prompt
                prompt = prompt_template.format(entity_id=ent_id, friendly_name=friendly)
                try:
                    content = await async_call_llm(hass, prompt, settings)
                    aliases = [a.strip().strip('"').strip("'") for a in content.split(",") if a.strip()]
                    results[ent_id] = aliases
                except Exception as err:
                    _LOGGER.error("LLM nickname request failed for %s: %s", ent_id, err)
                        
            return self.json({"results": results})
        except Exception as err:
            _LOGGER.exception("Failed to generate nicknames")
            return self.json({"error": str(err)}, status_code=500)


class AISuggestExposureView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/ai/suggest_exposure"
    name = "api:google_assistant_entity_console:ai:suggest_exposure"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
            entity_list = body.get("entities", [])
            user_intent = body.get("user_intent", "")
            
            if not entity_list:
                return self.json({"error": "No entities provided"}, status_code=400)
            if not user_intent:
                return self.json({"error": "No user intent/criteria provided"}, status_code=400)
                
            settings = load_ai_settings(hass)
            base_url = settings.get("base_url", "").rstrip("/")
            api_key = settings.get("api_key", "")
            model = settings.get("model", "")
            prompt_template = settings.get("exposure_prompt", "").strip()
            
            # Default fallback template
            if not prompt_template:
                prompt_template = (
                    "You are an assistant helping configure which smart home entities to expose to Google Assistant.\n"
                    "Given a list of entities with their IDs, names, and domains, and the user's intent: '{user_intent}'.\n"
                    "Determine which entities from the list should be exposed.\n"
                    "Return ONLY a JSON list of entity IDs that should be exposed. Do not wrap in markdown codeblocks (e.g. ```json). Just return the raw JSON list.\n\n"
                    "Entities:\n"
                    "{entities_list}"
                )
                
            # Serialize entities briefly for the prompt context
            serialized_ents = []
            for ent in entity_list:
                serialized_ents.append({
                    "entity_id": ent.get("entity_id"),
                    "name": ent.get("display_name") or ent.get("name"),
                    "domain": ent.get("domain")
                })
                
            entities_str = json.dumps(serialized_ents, indent=2)
            prompt = prompt_template.format(user_intent=user_intent, entities_list=entities_str)
            
            content = await async_call_llm(hass, prompt, settings)
            
            # Clean markdown formatting if returned
            if content.startswith("```"):
                content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
                content = re.sub(r"\n?```$", "", content)
            content = content.strip()
            
            try:
                exposed_ids = json.loads(content)
                if isinstance(exposed_ids, list):
                    return self.json({"exposed_ids": exposed_ids})
            except Exception as parse_err:
                _LOGGER.error("Failed to parse LLM JSON exposure suggestions: %s (Raw: %s)", parse_err, content)
                return self.json({"error": f"LLM returned invalid format: {content}"}, status_code=502)
        except Exception as err:
            _LOGGER.exception("Failed to suggest exposure")
            return self.json({"error": str(err)}, status_code=500)


class AIGenerateSingleEntityNicknameView(HomeAssistantView):
    url = "/api/google_assistant_entity_console/ai/generate_single_nickname"
    name = "api:google_assistant_entity_console:ai:generate_single_nickname"

    async def post(self, request: web.Request) -> web.Response:
        hass = request.app["hass"]
        try:
            body = await request.json()
            entity_id = body.get("entity_id")
            display_name = body.get("display_name")
            room_entities = body.get("room_entities", [])
            
            if not entity_id:
                return self.json({"error": "Missing entity_id"}, status_code=400)
                
            settings = load_ai_settings(hass)
            base_url = settings.get("base_url", "").rstrip("/")
            api_key = settings.get("api_key", "")
            model = settings.get("model", "")
            prompt_template = settings.get("single_nickname_prompt", "").strip()
            
            # Default fallback template
            if not prompt_template:
                prompt_template = (
                    "You are an assistant helping configure Google Assistant aliases for a specific smart home entity.\n"
                    "For the target entity, generate 2-4 clean, natural-language nicknames (aliases) that a user would typically say to control the device.\n"
                    "Avoid markdown, explanations, bullet points, numbers, quotes, or punctuation.\n"
                    "Use the context of other entities in the same room to avoid duplicate, confusing, or conflicting names.\n"
                    "Return the nicknames ONLY as a single comma-separated list on a single line.\n\n"
                    "Target Entity ID: {entity_id}\n"
                    "Target Friendly Name: {friendly_name}\n"
                    "Other Entities in same room: {room_context}\n"
                    "Aliases:"
                )
                
            # Serialize room context with names and current nicknames/aliases
            context_list = []
            for e in room_entities:
                if e.get("entity_id") != entity_id:
                    aliases_list = e.get("aliases", [])
                    aliases_str = f", current nicknames: {aliases_list}" if aliases_list else ""
                    context_list.append(f"{e.get('entity_id')} (name: {e.get('display_name') or e.get('name') or ''}{aliases_str})")
            room_context_str = "; ".join(context_list) if context_list else "None"
            
            prompt = prompt_template.format(
                entity_id=entity_id,
                friendly_name=display_name or entity_id.split(".")[-1],
                room_context=room_context_str
            )
            
            content = await async_call_llm(hass, prompt, settings)
            aliases = [a.strip().strip('"').strip("'") for a in content.split(",") if a.strip()]
            return self.json({"aliases": aliases})
        except Exception as err:
            _LOGGER.exception("Failed to generate single nickname")
            return self.json({"error": str(err)}, status_code=500)
