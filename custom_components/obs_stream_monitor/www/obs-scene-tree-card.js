/**
 * OBS Szenen-Baum - a custom Lovelace card bundled with the OBS Stream
 * Monitor integration (custom_components/obs_stream_monitor/).
 *
 * Shows OBS's scenes -> sources -> filters as a click-through tree, with
 * toggles for source visibility (the "eye" icon in OBS) and filter
 * enable/disable, plus a settings dialog (the gear icon on each source/
 * filter row) to edit that source's or filter's raw OBS settings (text
 * content, colors, crop, chroma-key thresholds, ...). The toggles and tree
 * data come from the switch.* / sensor.* entities the integration creates
 * once "Szenen-Baum aktivieren" is turned on in the integration's Configure
 * dialog, discovered via their obs_role/scene/source/filter attributes (set
 * in switch.py / sensor.py) rather than by entity_id, so it keeps working
 * even if entities get renamed. The settings dialog is different: there's
 * no sensible way to turn an arbitrary, source-kind-specific settings blob
 * into entity state, so it instead calls custom WebSocket commands the
 * integration registers (see websocket_api.py) directly, fetching/pushing
 * settings on demand rather than through the usual 10s poll.
 *
 * The settings dialog's generic form shows OBS's own raw, technical field
 * names (e.g. "key_color") by default. Where the source/filter "kind" is
 * recognized, obs-settings-labels.js supplies a nicer label per field
 * (English/German, matched to the language Home Assistant is set to, via
 * hass.locale.language / hass.language) - see _fieldLabel()/_kindLabel()
 * below. An unrecognized kind or field just falls back to the raw name;
 * nothing stops working, it's purely cosmetic.
 *
 * One-time setup (can't be done by the integration automatically, Home
 * Assistant doesn't allow that): Settings -> Dashboards -> Resources ->
 * Add Resource -> URL "/obs_stream_monitor_card/obs-scene-tree-card.js",
 * Resource type "JavaScript-Modul". Then add a card of type
 * "custom:obs-scene-tree-card" to any dashboard. Full walkthrough in
 * docs/scene-tree-dashboard-setup.md.
 *
 * Config options (all optional):
 *   title:    custom card header text
 *   entry_id: only show entities from this one config entry (for setups
 *             with several OBS installations)
 *   scene:    pin the card to exactly this scene - skips the scenes list
 *             and starts straight at that scene's sources, so you can add
 *             one card per scene instead of one shared drill-down card
 *
 * No build step / framework dependency on purpose - this is a plain
 * custom element so it can be served as-is. The one exception is the
 * static import below: obs-settings-labels.js is served from the same
 * directory (see __init__.py), so it resolves as a plain relative URL,
 * no bundler needed.
 */
import { OBS_SETTINGS_LABELS } from "./obs-settings-labels.js";

(() => {
  if (customElements.get("obs-scene-tree-card")) {
    return;
  }

  const ESCAPE_MAP = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPE_MAP[c]);
  }

  // --- settings label/type helpers, shared by both custom elements below
  // (ObsSceneTreeCard's own settings dialog, and the single-field
  // ObsSettingCard) -------------------------------------------------------

  // Two-letter language code HA is currently set to ("de", "en", ...),
  // derived from hass.locale.language (modern frontends) or hass.language
  // (older ones), defaulting to English.
  function settingsLang(hass) {
    const raw = (hass && hass.locale && hass.locale.language) || (hass && hass.language) || "en";
    return String(raw).split("-")[0].toLowerCase();
  }

  // Looks up a "kind" in OBS_SETTINGS_LABELS, or null if unknown. Some
  // built-in OBS sources exist in versioned variants on the wire - e.g.
  // newer OBS builds report "text_gdiplus_v3" / "color_source_v3" instead
  // of the plain "text_gdiplus" / "color_source" id (OBS keeps the old,
  // unsuffixed id registered too, for loading old scene collections, but
  // newly created sources get the versioned one). The settings fields are
  // the same set either way, just with revised internal defaults - so if
  // the exact (possibly versioned) kind isn't in the table, retry with any
  // trailing "_v<digits>" stripped before giving up.
  function kindEntry(kind) {
    if (!kind) return null;
    if (OBS_SETTINGS_LABELS[kind]) return OBS_SETTINGS_LABELS[kind];
    const stripped = kind.replace(/_v\d+$/, "");
    if (stripped !== kind && OBS_SETTINGS_LABELS[stripped]) return OBS_SETTINGS_LABELS[stripped];
    return null;
  }

  // Nicer display name for a recognized source/filter "kind", or null if
  // this kind isn't in the lookup table (see obs-settings-labels.js).
  function kindLabel(kind, hass) {
    const entry = kindEntry(kind);
    if (!entry || !entry.label) return null;
    const lang = settingsLang(hass);
    return entry.label[lang] || entry.label.en || null;
  }

  // Nicer label for one settings field of a recognized kind, or null if
  // unknown (the caller falls back to the raw field key in that case). A
  // few plugins (e.g. Gradient Source) number otherwise-identical fields
  // ("midpoint_1".."midpoint_9") - if the exact key isn't found, retry with
  // any trailing "_<digits>" stripped.
  function fieldLabel(kind, fieldKey, hass) {
    const entry = kindEntry(kind);
    const fields = entry && entry.fields;
    if (!fields) return null;
    let fieldEntry = fields[fieldKey];
    if (!fieldEntry) {
      const stripped = fieldKey.replace(/_\d+$/, "");
      if (stripped !== fieldKey) fieldEntry = fields[stripped];
    }
    if (!fieldEntry) return null;
    const lang = settingsLang(hass);
    return fieldEntry[lang] || fieldEntry.en || null;
  }

  function settingsFieldType(value) {
    if (typeof value === "boolean") return "boolean";
    if (typeof value === "number") return "number";
    if (typeof value === "string") return "string";
    return "json"; // object, array, null - edited as raw JSON
  }

  class ObsSceneTreeCard extends HTMLElement {
    setConfig(config) {
      this._config = config || {};
      // "scene" pins the card to one scene (for a "one card per scene"
      // dashboard layout): it skips the scenes list entirely and starts
      // straight at that scene's sources, with no way to navigate to any
      // other scene from this card instance.
      const pinnedScene = this._config.scene || null;
      this._level = pinnedScene ? "sources" : "scenes";
      this._scene = pinnedScene;
      this._source = null;
      // Settings-editor dialog state (null = closed). See _openSourceSettings
      // / _openFilterSettings / _closeModal / _saveModalSettings.
      this._modal = null;
    }

    set hass(hass) {
      this._hass = hass;
      // Home Assistant calls this setter on every single state update
      // anywhere in the system - as often as every ~10s from this
      // integration's own poll alone. A normal _render() rebuilds the
      // whole shadow DOM from scratch, including the settings dialog
      // (from this._modal.settings), which silently threw away whatever
      // the user was mid-typing - making the dialog close to unusable.
      // So: while the dialog is open, skip the automatic re-render
      // entirely and just keep this._hass current for when it's needed
      // (WS calls, language lookups). The dialog's own lifecycle
      // (_openSourceSettings/_openFilterSettings/_closeModal/
      // _saveModalSettings) already calls _render() explicitly whenever
      // ITS state actually changes, so nothing is lost by skipping this -
      // and the rest of the card (hidden behind the dialog anyway) simply
      // catches up to the latest data the instant the dialog closes,
      // whether via Speichern, Abbrechen, or the X/backdrop.
      if (this._modal) {
        return;
      }
      this._render();
    }

    getCardSize() {
      return 5;
    }

    static getStubConfig() {
      return {};
    }

    // --- data access -------------------------------------------------

    _matchesEntry(attributes) {
      const entryId = this._config.entry_id;
      return !entryId || attributes.obs_entry_id === entryId;
    }

    _switchEntities() {
      const hass = this._hass;
      if (!hass) return [];
      return Object.values(hass.states).filter((st) => {
        if (!st.entity_id.startsWith("switch.")) return false;
        const a = st.attributes || {};
        return (a.obs_role === "scene_item" || a.obs_role === "filter") && this._matchesEntry(a);
      });
    }

    _sceneItemEntities() {
      return this._switchEntities().filter((e) => e.attributes.obs_role === "scene_item");
    }

    _filterEntities() {
      return this._switchEntities().filter((e) => e.attributes.obs_role === "filter");
    }

    _currentSceneName() {
      const hass = this._hass;
      if (!hass) return null;
      const sensor = Object.values(hass.states).find((st) => {
        const a = st.attributes || {};
        return (
          st.entity_id.startsWith("sensor.") &&
          a.obs_role === "sensor" &&
          a.obs_data_key === "scene" &&
          this._matchesEntry(a)
        );
      });
      return sensor ? sensor.state : null;
    }

    _scenes() {
      const names = [];
      for (const e of this._sceneItemEntities()) {
        const name = e.attributes.scene;
        if (name && !names.includes(name)) names.push(name);
      }
      return names.sort((a, b) => a.localeCompare(b));
    }

    // [[sourceName, representativeEntity], ...] - one row per source within a scene
    _sourcesInScene(scene) {
      const bySource = new Map();
      for (const e of this._sceneItemEntities()) {
        if (e.attributes.scene === scene) {
          bySource.set(e.attributes.source, e);
        }
      }
      return [...bySource.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    }

    _filtersForSource(source) {
      return this._filterEntities()
        .filter((e) => e.attributes.source === source)
        .sort((a, b) => a.attributes.filter.localeCompare(b.attributes.filter));
    }

    // --- actions -------------------------------------------------------

    _toggle(entityId, turnOn) {
      if (!this._hass) return;
      this._hass.callService("switch", turnOn ? "turn_on" : "turn_off", {
        entity_id: entityId,
      });
    }

    async _copyToClipboard(text) {
      try {
        if (navigator.clipboard && window.isSecureContext) {
          await navigator.clipboard.writeText(text);
          return true;
        }
      } catch (err) {
        // fall through to the legacy fallback below
      }
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(ta);
        return ok;
      } catch (err) {
        return false;
      }
    }

    _go(level, scene, source) {
      // A pinned card never shows the scenes list, so there's nothing to
      // navigate back to beyond its own scene.
      if (this._config.scene && level === "scenes") {
        level = "sources";
        scene = this._config.scene;
      }
      this._level = level;
      this._scene = scene === undefined ? this._scene : scene;
      this._source = source === undefined ? this._source : source;
      this._render();
    }

    // --- rendering -------------------------------------------------------

    _styles() {
      return `
        <style>
          ha-card { overflow: hidden; }
          .otc-header {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 4px;
            padding: 16px 16px 8px;
          }
          .otc-crumb-btn {
            background: none;
            border: none;
            color: var(--primary-color);
            font: inherit;
            font-size: 14px;
            cursor: pointer;
            padding: 4px 6px;
            border-radius: 6px;
          }
          .otc-crumb-btn:hover { background: var(--secondary-background-color); }
          .otc-crumb-current {
            font-size: 14px;
            font-weight: 500;
            color: var(--primary-text-color);
            padding: 4px 6px;
          }
          .otc-sep { color: var(--secondary-text-color); }
          .otc-row {
            display: flex;
            align-items: center;
            border-top: 1px solid var(--divider-color);
          }
          .otc-row-nav {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            padding: 10px 16px;
            cursor: pointer;
          }
          .otc-row-nav:hover { background: var(--secondary-background-color); }
          .otc-row-static {
            flex: 1;
            padding: 10px 16px;
          }
          .otc-main { display: flex; flex-direction: column; min-width: 0; }
          .otc-title {
            font-size: 15px;
            color: var(--primary-text-color);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .otc-subtitle { font-size: 12px; color: var(--secondary-text-color); }
          .otc-chevron { color: var(--secondary-text-color); font-size: 18px; padding-left: 8px; }
          .otc-empty { padding: 16px; color: var(--secondary-text-color); font-size: 14px; }
          .otc-toggle {
            position: relative;
            display: inline-block;
            width: 36px;
            height: 20px;
            flex: 0 0 auto;
            margin-right: 16px;
          }
          .otc-toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
          .otc-toggle .otc-slider {
            position: absolute;
            inset: 0;
            background-color: var(--switch-unchecked-track-color, #939393);
            transition: background-color 0.2s;
            border-radius: 20px;
            cursor: pointer;
          }
          .otc-toggle .otc-slider::before {
            position: absolute;
            content: "";
            height: 16px;
            width: 16px;
            left: 2px;
            top: 2px;
            background-color: #fff;
            transition: transform 0.2s;
            border-radius: 50%;
          }
          .otc-toggle input:checked + .otc-slider {
            background-color: var(--switch-checked-track-color, var(--primary-color));
          }
          .otc-toggle input:checked + .otc-slider::before { transform: translateX(16px); }
          .otc-toggle input:disabled + .otc-slider { opacity: 0.4; cursor: default; }
          .otc-entity-id {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 11px;
            color: var(--secondary-text-color);
            margin-top: 2px;
            cursor: pointer;
            width: fit-content;
          }
          .otc-entity-id:hover { color: var(--primary-color); }
          .otc-entity-id ha-icon {
            --mdc-icon-size: 14px;
            flex: 0 0 auto;
          }
          .otc-settings-btn {
            flex: 0 0 auto;
            background: none;
            border: none;
            color: var(--secondary-text-color);
            cursor: pointer;
            padding: 6px;
            margin-right: 4px;
            border-radius: 50%;
            display: inline-flex;
          }
          .otc-settings-btn:hover {
            background: var(--secondary-background-color);
            color: var(--primary-color);
          }
          .otc-modal-backdrop {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            padding: 16px;
            box-sizing: border-box;
          }
          .otc-modal {
            background: var(--card-background-color, #fff);
            color: var(--primary-text-color);
            border-radius: 12px;
            width: 100%;
            max-width: 480px;
            max-height: 85vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0, 0, 0, 0.3));
          }
          .otc-modal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            padding: 16px;
            border-bottom: 1px solid var(--divider-color);
          }
          .otc-modal-title { font-size: 16px; font-weight: 500; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
          .otc-modal-close {
            background: none;
            border: none;
            color: var(--secondary-text-color);
            cursor: pointer;
            padding: 4px;
            flex: 0 0 auto;
            display: inline-flex;
            border-radius: 50%;
          }
          .otc-modal-close:hover { background: var(--secondary-background-color); }
          .otc-modal-body { padding: 16px; overflow-y: auto; flex: 1; }
          .otc-modal-footer {
            display: flex;
            justify-content: flex-end;
            gap: 8px;
            padding: 12px 16px;
            border-top: 1px solid var(--divider-color);
          }
          .otc-btn {
            font: inherit;
            font-size: 14px;
            font-weight: 500;
            padding: 8px 16px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
          }
          .otc-btn-text { background: none; color: var(--primary-text-color); }
          .otc-btn-text:hover { background: var(--secondary-background-color); }
          .otc-btn-primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
          .otc-btn-primary:disabled { opacity: 0.5; cursor: default; }
          .otc-field { margin-bottom: 14px; }
          .otc-field label {
            display: block;
            font-size: 13px;
            color: var(--primary-text-color);
            margin-bottom: 4px;
          }
          .otc-field-key {
            font-size: 11px;
            color: var(--secondary-text-color);
            font-family: var(--code-font-family, ui-monospace, "SFMono-Regular", Consolas, monospace);
          }
          .otc-field input[type="text"],
          .otc-field input[type="number"],
          .otc-field textarea {
            width: 100%;
            box-sizing: border-box;
            font: inherit;
            font-size: 14px;
            padding: 8px 10px;
            border-radius: 6px;
            border: 1px solid var(--divider-color);
            background: var(--card-background-color, #fff);
            color: var(--primary-text-color);
          }
          .otc-field textarea { font-family: var(--code-font-family, ui-monospace, monospace); font-size: 12px; resize: vertical; }
          .otc-field input[type="checkbox"] { width: 18px; height: 18px; }
          .otc-modal-note { font-size: 12px; color: var(--secondary-text-color); margin: 0 0 14px; }
          .otc-modal-error {
            background: var(--error-color, #db4437);
            color: #fff;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
            margin-bottom: 14px;
          }
        </style>
      `;
    }

    _renderEntityId(entity) {
      return `
        <span class="otc-entity-id" data-copy-entity="${esc(entity.entity_id)}" title="${esc(entity.entity_id)} (Klicken zum Kopieren)">
          <ha-icon icon="mdi:content-copy"></ha-icon>
          Entitäts-ID
        </span>
      `;
    }

    _renderSourceSettingsButton(entity) {
      return `
        <button
          class="otc-settings-btn"
          data-settings-type="source"
          data-settings-entry="${esc(entity.attributes.obs_entry_id)}"
          data-settings-source="${esc(entity.attributes.source)}"
          title="Einstellungen bearbeiten"
        >
          <ha-icon icon="mdi:cog-outline"></ha-icon>
        </button>
      `;
    }

    _renderFilterSettingsButton(entity) {
      return `
        <button
          class="otc-settings-btn"
          data-settings-type="filter"
          data-settings-entry="${esc(entity.attributes.obs_entry_id)}"
          data-settings-source="${esc(entity.attributes.source)}"
          data-settings-filter="${esc(entity.attributes.filter)}"
          title="Einstellungen bearbeiten"
        >
          <ha-icon icon="mdi:cog-outline"></ha-icon>
        </button>
      `;
    }

    _renderToggle(entity) {
      const on = entity.state === "on";
      const unavailable = entity.state === "unavailable";
      return `
        <label class="otc-toggle">
          <input
            type="checkbox"
            data-toggle-entity="${esc(entity.entity_id)}"
            ${on ? "checked" : ""}
            ${unavailable ? "disabled" : ""}
          >
          <span class="otc-slider"></span>
        </label>
      `;
    }

    _renderHeader() {
      const pinned = !!this._config.scene;
      const crumbs = pinned ? [] : [{ label: "Szenen", level: "scenes" }];
      if (this._level === "sources" || this._level === "filters") {
        crumbs.push({ label: this._scene, level: "sources" });
      }
      if (this._level === "filters") {
        crumbs.push({ label: this._source, level: "filters" });
      }

      const parts = crumbs.map((crumb, idx) => {
        const isLast = idx === crumbs.length - 1;
        if (isLast) {
          return `<span class="otc-crumb-current">${esc(crumb.label)}</span>`;
        }
        return `<button class="otc-crumb-btn" data-go-level="${crumb.level}">${esc(crumb.label)}</button>`;
      });

      return `<div class="otc-header">${parts.join('<span class="otc-sep">›</span>')}</div>`;
    }

    _renderBody() {
      if (this._level === "scenes") {
        const scenes = this._scenes();
        if (!scenes.length) {
          return `<div class="otc-empty">Noch keine Daten. In den Integrations-Optionen "Szenen-Baum aktivieren" einschalten und kurz warten, bis einmal abgefragt wurde.</div>`;
        }
        const current = this._currentSceneName();
        return scenes
          .map((scene) => {
            const count = this._sourcesInScene(scene).length;
            const live = scene === current ? " 🔴" : "";
            return `
              <div class="otc-row">
                <div class="otc-row-nav" data-go-scene="${esc(scene)}">
                  <div class="otc-main">
                    <span class="otc-title">${esc(scene)}${live}</span>
                    <span class="otc-subtitle">${count} Quelle${count === 1 ? "" : "n"}</span>
                  </div>
                  <span class="otc-chevron">›</span>
                </div>
              </div>
            `;
          })
          .join("");
      }

      if (this._level === "sources") {
        const allScenes = this._scenes();
        if (!allScenes.length) {
          return `<div class="otc-empty">Noch keine Daten. In den Integrations-Optionen "Szenen-Baum aktivieren" einschalten und kurz warten, bis einmal abgefragt wurde.</div>`;
        }
        if (this._config.scene && !allScenes.includes(this._scene)) {
          return `<div class="otc-empty">Szene "${esc(this._scene)}" nicht gefunden. Name in der Karten-Konfiguration (Feld "scene") prüfen, Groß-/Kleinschreibung muss exakt stimmen.</div>`;
        }
        const sources = this._sourcesInScene(this._scene);
        if (!sources.length) {
          return `<div class="otc-empty">Keine Quellen in dieser Szene.</div>`;
        }
        return sources
          .map(([source, entity]) => {
            const filterCount = this._filtersForSource(source).length;
            const kind = entity.attributes.source_kind ? esc(entity.attributes.source_kind) : "";
            const filterNote = filterCount ? ` · ${filterCount} Filter` : "";
            return `
              <div class="otc-row">
                <div class="otc-row-nav" data-go-source="${esc(source)}">
                  <div class="otc-main">
                    <span class="otc-title">${esc(source)}</span>
                    <span class="otc-subtitle">${kind}${filterNote}</span>
                    ${this._renderEntityId(entity)}
                  </div>
                  <span class="otc-chevron">›</span>
                </div>
                ${this._renderSourceSettingsButton(entity)}
                ${this._renderToggle(entity)}
              </div>
            `;
          })
          .join("");
      }

      // filters
      const filters = this._filtersForSource(this._source);
      if (!filters.length) {
        return `<div class="otc-empty">Keine Filter auf dieser Quelle.</div>`;
      }
      return filters
        .map((entity) => {
          const kind = entity.attributes.filter_kind ? esc(entity.attributes.filter_kind) : "";
          return `
            <div class="otc-row">
              <div class="otc-row-static">
                <div class="otc-main">
                  <span class="otc-title">${esc(entity.attributes.filter)}</span>
                  <span class="otc-subtitle">${kind}</span>
                  ${this._renderEntityId(entity)}
                </div>
              </div>
              ${this._renderFilterSettingsButton(entity)}
              ${this._renderToggle(entity)}
            </div>
          `;
        })
        .join("");
    }

    // --- settings dialog: data -----------------------------------------

    // Thin wrappers around the module-level helpers above (shared with
    // ObsSettingCard) so the rest of this class's code doesn't change.
    _settingsFieldType(value) {
      return settingsFieldType(value);
    }

    _settingsLang() {
      return settingsLang(this._hass);
    }

    _kindEntry(kind) {
      return kindEntry(kind);
    }

    _kindLabel(kind) {
      return kindLabel(kind, this._hass);
    }

    _fieldLabel(kind, fieldKey) {
      return fieldLabel(kind, fieldKey, this._hass);
    }

    _renderSettingsFields(settings, kind) {
      const entries = Object.entries(settings || {});
      if (!entries.length) {
        return `<p class="otc-modal-note">Diese Quelle/dieser Filter meldet keine bearbeitbaren Felder.</p>`;
      }
      return entries
        .map(([key, value]) => {
          const type = this._settingsFieldType(value);
          const niceLabel = this._fieldLabel(kind, key);
          const labelHtml = niceLabel
            ? `${esc(niceLabel)} <span class="otc-field-key">(${esc(key)})</span>`
            : esc(key);
          if (type === "boolean") {
            return `
              <div class="otc-field">
                <label>${labelHtml}</label>
                <input type="checkbox" data-field="${esc(key)}" data-type="boolean" ${value ? "checked" : ""}>
              </div>
            `;
          }
          if (type === "number") {
            return `
              <div class="otc-field">
                <label>${labelHtml}</label>
                <input type="number" step="any" data-field="${esc(key)}" data-type="number" value="${esc(value)}">
              </div>
            `;
          }
          if (type === "string") {
            return `
              <div class="otc-field">
                <label>${labelHtml}</label>
                <input type="text" data-field="${esc(key)}" data-type="string" value="${esc(value)}">
              </div>
            `;
          }
          // nested object / array / null - shown as raw, editable JSON
          return `
            <div class="otc-field">
              <label>${labelHtml} (JSON)</label>
              <textarea data-field="${esc(key)}" data-type="json" rows="3">${esc(JSON.stringify(value, null, 2))}</textarea>
            </div>
          `;
        })
        .join("");
    }

    _collectSettingsFromForm(root) {
      const result = {};
      root.querySelectorAll("[data-field]").forEach((el) => {
        const key = el.dataset.field;
        const type = el.dataset.type;
        if (type === "boolean") {
          result[key] = el.checked;
        } else if (type === "number") {
          result[key] = el.value === "" ? 0 : Number(el.value);
        } else if (type === "json") {
          try {
            result[key] = JSON.parse(el.value);
          } catch (err) {
            throw new Error(`Ungültiges JSON bei "${key}": ${err.message}`);
          }
        } else {
          result[key] = el.value;
        }
      });
      return result;
    }

    // --- settings dialog: actions ---------------------------------------

    async _openSourceSettings(entryId, sourceName) {
      this._modal = {
        type: "source",
        entryId,
        source: sourceName,
        loading: true,
        saving: false,
        error: null,
        kind: null,
        settings: null,
      };
      this._render();
      try {
        const resp = await this._hass.callWS({
          type: "obs_stream_monitor/get_input_settings",
          entry_id: entryId,
          source_name: sourceName,
        });
        this._modal = { ...this._modal, loading: false, kind: resp.kind, settings: resp.settings };
      } catch (err) {
        this._modal = { ...this._modal, loading: false, error: this._wsErrorMessage(err) };
      }
      this._render();
    }

    async _openFilterSettings(entryId, sourceName, filterName) {
      this._modal = {
        type: "filter",
        entryId,
        source: sourceName,
        filter: filterName,
        loading: true,
        saving: false,
        error: null,
        kind: null,
        settings: null,
      };
      this._render();
      try {
        const resp = await this._hass.callWS({
          type: "obs_stream_monitor/get_filter_settings",
          entry_id: entryId,
          source_name: sourceName,
          filter_name: filterName,
        });
        this._modal = { ...this._modal, loading: false, kind: resp.kind, settings: resp.settings };
      } catch (err) {
        this._modal = { ...this._modal, loading: false, error: this._wsErrorMessage(err) };
      }
      this._render();
    }

    _wsErrorMessage(err) {
      if (err && typeof err === "object" && err.message) return err.message;
      return String(err);
    }

    _closeModal() {
      this._modal = null;
      this._render();
    }

    async _saveModalSettings() {
      if (!this._modal || this._modal.loading || this._modal.saving) return;
      const body = this._root.querySelector(".otc-modal-body");
      let values;
      try {
        values = this._collectSettingsFromForm(body);
      } catch (err) {
        this._modal.error = err.message;
        this._render();
        return;
      }
      this._modal.saving = true;
      this._modal.error = null;
      this._render();
      try {
        if (this._modal.type === "source") {
          await this._hass.callWS({
            type: "obs_stream_monitor/set_input_settings",
            entry_id: this._modal.entryId,
            source_name: this._modal.source,
            settings: values,
          });
        } else {
          await this._hass.callWS({
            type: "obs_stream_monitor/set_filter_settings",
            entry_id: this._modal.entryId,
            source_name: this._modal.source,
            filter_name: this._modal.filter,
            settings: values,
          });
        }
        this._modal = null;
      } catch (err) {
        this._modal.saving = false;
        this._modal.error = this._wsErrorMessage(err);
      }
      this._render();
    }

    // --- settings dialog: markup ----------------------------------------

    _renderModal() {
      if (!this._modal) return "";
      const m = this._modal;
      const title = m.type === "source" ? m.source : `${m.source} › ${m.filter}`;

      let body;
      if (m.loading) {
        body = `<p class="otc-modal-note">Lädt…</p>`;
      } else if (m.error && !m.settings) {
        body = `<div class="otc-modal-error">${esc(m.error)}</div>`;
      } else {
        const kindLabel = this._kindLabel(m.kind);
        const kindNote = m.kind ? (kindLabel ? `${kindLabel} (${m.kind})` : m.kind) : null;
        body = `
          ${m.error ? `<div class="otc-modal-error">${esc(m.error)}</div>` : ""}
          ${kindNote ? `<p class="otc-modal-note">Typ: ${esc(kindNote)}</p>` : ""}
          ${this._renderSettingsFields(m.settings, m.kind)}
        `;
      }

      return `
        <div class="otc-modal-backdrop" data-modal-close>
          <div class="otc-modal" data-modal-stop>
            <div class="otc-modal-header">
              <span class="otc-modal-title">Einstellungen: ${esc(title)}</span>
              <button class="otc-modal-close" data-modal-close title="Schließen">
                <ha-icon icon="mdi:close"></ha-icon>
              </button>
            </div>
            <div class="otc-modal-body">${body}</div>
            <div class="otc-modal-footer">
              <button class="otc-btn otc-btn-text" data-modal-close>Abbrechen</button>
              <button class="otc-btn otc-btn-primary" data-modal-save ${m.loading || m.saving || (m.error && !m.settings) ? "disabled" : ""}>
                ${m.saving ? "Speichert…" : "Speichern"}
              </button>
            </div>
          </div>
        </div>
      `;
    }

    _render() {
      if (!this._hass) return;
      if (!this._root) {
        this._root = this.attachShadow({ mode: "open" });
      }

      const title = this._config.title ?? this._config.scene ?? "OBS Szenen";
      this._root.innerHTML = `
        ${this._styles()}
        <ha-card header="${esc(title)}">
          ${this._renderHeader()}
          ${this._renderBody()}
        </ha-card>
        ${this._renderModal()}
      `;

      this._root.querySelectorAll("[data-go-level]").forEach((el) => {
        el.addEventListener("click", () => this._go(el.dataset.goLevel));
      });
      this._root.querySelectorAll("[data-go-scene]").forEach((el) => {
        el.addEventListener("click", () => this._go("sources", el.dataset.goScene));
      });
      this._root.querySelectorAll("[data-go-source]").forEach((el) => {
        el.addEventListener("click", () => this._go("filters", this._scene, el.dataset.goSource));
      });
      this._root.querySelectorAll("input[data-toggle-entity]").forEach((el) => {
        el.addEventListener("change", (ev) => {
          this._toggle(el.dataset.toggleEntity, ev.target.checked);
        });
      });
      this._root.querySelectorAll("[data-copy-entity]").forEach((el) => {
        el.addEventListener("click", async (ev) => {
          ev.stopPropagation();
          const entityId = el.dataset.copyEntity;
          const ok = await this._copyToClipboard(entityId);
          const icon = el.querySelector("ha-icon");
          if (icon) {
            icon.setAttribute("icon", ok ? "mdi:check" : "mdi:alert-circle-outline");
            setTimeout(() => icon.setAttribute("icon", "mdi:content-copy"), 1200);
          }
        });
      });
      this._root.querySelectorAll("[data-settings-type]").forEach((el) => {
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          const entryId = el.dataset.settingsEntry;
          const sourceName = el.dataset.settingsSource;
          if (el.dataset.settingsType === "source") {
            this._openSourceSettings(entryId, sourceName);
          } else {
            this._openFilterSettings(entryId, sourceName, el.dataset.settingsFilter);
          }
        });
      });
      const modalEl = this._root.querySelector(".otc-modal-backdrop");
      if (modalEl) {
        modalEl.addEventListener("click", () => this._closeModal());
        const dialogEl = this._root.querySelector("[data-modal-stop]");
        if (dialogEl) {
          dialogEl.addEventListener("click", (ev) => ev.stopPropagation());
        }
        this._root.querySelectorAll("[data-modal-close]").forEach((el) => {
          el.addEventListener("click", () => this._closeModal());
        });
        const saveBtn = this._root.querySelector("[data-modal-save]");
        if (saveBtn) {
          saveBtn.addEventListener("click", () => this._saveModalSettings());
        }
      }
    }
  }

  customElements.define("obs-scene-tree-card", ObsSceneTreeCard);

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "obs-scene-tree-card",
    name: "OBS Szenen-Baum",
    description:
      "Szenen -> Quellen -> Filter zum Durchklicken, mit Schaltern für Sichtbarkeit und Filter (OBS Stream Monitor).",
  });

  /**
   * OBS Einstellung - a small companion card that pins exactly ONE raw OBS
   * setting (the kind of field the big "OBS Szenen-Baum" card's gear-icon
   * dialog shows a whole form of - see that dialog for background) as its
   * own standalone dashboard card, so a value you check/change often (a
   * recording path, a text source's content, ...) doesn't need opening that
   * dialog every time. Reuses the exact same backend WebSocket commands
   * (websocket_api.py) and the same kind/field label lookup as that dialog.
   *
   * Config:
   *   source:   (required) the OBS source's own name, exactly as it's
   *             named inside OBS (not the Home Assistant entity name)
   *   field:    (required) the raw settings key to show, e.g. "path" or
   *             "text" - open the big card's settings dialog once to see
   *             the available raw keys (shown in parentheses next to each
   *             field's label) for that source/filter
   *   filter:   (optional) a filter name on that source - if set, targets
   *             that filter's settings instead of the source's own
   *   title:    (optional) card header override; defaults to the field's
   *             nice label (if the source/filter "kind" is recognized) or
   *             else the raw field key
   *   entry_id: (optional) only needed with more than one OBS Stream
   *             Monitor integration entry set up - picked automatically
   *             when there's just one
   */
  class ObsSettingCard extends HTMLElement {
    setConfig(config) {
      if (!config || !config.source || !config.field) {
        throw new Error(
          'obs-setting-card: "source" und "field" sind Pflichtfelder in der Karten-Konfiguration.'
        );
      }
      this._config = config;
      this._state = {
        loading: true,
        saving: false,
        error: null,
        kind: null,
        value: undefined,
        fieldType: null,
      };
      this._fetched = false;
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._fetched) {
        this._fetched = true;
        this._fetchValue();
        return;
      }
      // Same reasoning as ObsSceneTreeCard's hass setter: don't let the
      // ~10s-wide flood of unrelated state updates stomp on an in-progress
      // edit. This card never polls OBS itself (see module docstring
      // above), so there's nothing new to show on a routine hass update
      // anyway - only the initial fetch and explicit refresh/save matter.
      if (!this._root) this._render();
    }

    getCardSize() {
      return 2;
    }

    static getStubConfig() {
      return { source: "", field: "" };
    }

    // Resolves which config entry to talk to: explicit config.entry_id if
    // given, otherwise the sole OBS Stream Monitor entry currently set up
    // (every entity this integration creates - not just Szenen-Baum ones -
    // carries an "obs_entry_id" attribute, see sensor.py/switch.py). With
    // more than one entry and no explicit entry_id, fails clearly rather
    // than silently guessing which installation was meant.
    _resolveEntryId() {
      if (this._config.entry_id) return this._config.entry_id;
      const hass = this._hass;
      const ids = new Set();
      if (hass) {
        for (const st of Object.values(hass.states)) {
          const entryId = (st.attributes || {}).obs_entry_id;
          if (entryId) ids.add(entryId);
        }
      }
      if (ids.size === 1) return [...ids][0];
      if (ids.size === 0) {
        throw new Error("Keine OBS-Stream-Monitor-Integration gefunden.");
      }
      throw new Error(
        'Mehrere OBS-Stream-Monitor-Einträge gefunden - "entry_id" in der Karten-Konfiguration angeben.'
      );
    }

    _wsErrorMessage(err) {
      if (err && typeof err === "object" && err.message) return err.message;
      return String(err);
    }

    _fetchMessage(entryId) {
      return this._config.filter
        ? {
            type: "obs_stream_monitor/get_filter_settings",
            entry_id: entryId,
            source_name: this._config.source,
            filter_name: this._config.filter,
          }
        : {
            type: "obs_stream_monitor/get_input_settings",
            entry_id: entryId,
            source_name: this._config.source,
          };
    }

    _saveMessage(entryId, value) {
      const settings = { [this._config.field]: value };
      return this._config.filter
        ? {
            type: "obs_stream_monitor/set_filter_settings",
            entry_id: entryId,
            source_name: this._config.source,
            filter_name: this._config.filter,
            settings,
          }
        : {
            type: "obs_stream_monitor/set_input_settings",
            entry_id: entryId,
            source_name: this._config.source,
            settings,
          };
    }

    async _fetchValue() {
      this._state = { ...this._state, loading: true, error: null };
      this._render();
      try {
        const entryId = this._resolveEntryId();
        const resp = await this._hass.callWS(this._fetchMessage(entryId));
        const settings = resp.settings || {};
        if (!(this._config.field in settings)) {
          throw new Error(`Feld "${this._config.field}" nicht in den Einstellungen gefunden.`);
        }
        const value = settings[this._config.field];
        this._state = {
          loading: false,
          saving: false,
          error: null,
          kind: resp.kind,
          value,
          fieldType: settingsFieldType(value),
        };
      } catch (err) {
        this._state = { ...this._state, loading: false, error: this._wsErrorMessage(err) };
      }
      this._render();
    }

    _parseFormValue(raw) {
      const type = this._state.fieldType;
      if (type === "boolean") return !!raw;
      if (type === "number") return raw === "" ? 0 : Number(raw);
      if (type === "json") {
        try {
          return JSON.parse(raw);
        } catch (err) {
          throw new Error(`Ungültiges JSON: ${err.message}`);
        }
      }
      return raw;
    }

    async _save(rawValue) {
      if (this._state.saving) return;
      let value;
      try {
        value = this._parseFormValue(rawValue);
      } catch (err) {
        this._state = { ...this._state, error: err.message };
        this._render();
        return;
      }
      this._state = { ...this._state, saving: true, error: null };
      this._render();
      try {
        const entryId = this._resolveEntryId();
        await this._hass.callWS(this._saveMessage(entryId, value));
        this._state = { ...this._state, saving: false, value };
      } catch (err) {
        this._state = { ...this._state, saving: false, error: this._wsErrorMessage(err) };
      }
      this._render();
    }

    _styles() {
      return `
        <style>
          ha-card { overflow: hidden; }
          .osc-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 8px;
            padding: 16px 16px 4px;
          }
          .osc-main { display: flex; flex-direction: column; min-width: 0; }
          .osc-title { font-size: 15px; color: var(--primary-text-color); }
          .osc-subtitle {
            font-size: 12px;
            color: var(--secondary-text-color);
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .osc-refresh {
            flex: 0 0 auto;
            background: none;
            border: none;
            color: var(--secondary-text-color);
            cursor: pointer;
            padding: 4px;
            border-radius: 50%;
            display: inline-flex;
          }
          .osc-refresh:hover { background: var(--secondary-background-color); color: var(--primary-color); }
          .osc-refresh:disabled { opacity: 0.4; cursor: default; }
          .osc-body { padding: 4px 16px 16px; }
          .osc-note { font-size: 13px; color: var(--secondary-text-color); margin: 0; }
          .osc-error {
            background: var(--error-color, #db4437);
            color: #fff;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
            margin-bottom: 10px;
          }
          .osc-field-row { display: flex; gap: 8px; align-items: center; }
          .osc-field input[type="text"],
          .osc-field input[type="number"],
          .osc-field textarea {
            width: 100%;
            box-sizing: border-box;
            font: inherit;
            font-size: 14px;
            padding: 8px 10px;
            border-radius: 6px;
            border: 1px solid var(--divider-color);
            background: var(--card-background-color, #fff);
            color: var(--primary-text-color);
          }
          .osc-field textarea { font-family: var(--code-font-family, ui-monospace, monospace); font-size: 12px; resize: vertical; }
          .osc-btn-save {
            flex: 0 0 auto;
            font: inherit;
            font-size: 14px;
            font-weight: 500;
            padding: 8px 14px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            background: var(--primary-color);
            color: var(--text-primary-color, #fff);
          }
          .osc-btn-save:disabled { opacity: 0.5; cursor: default; }
          .osc-switch {
            position: relative;
            display: inline-block;
            width: 36px;
            height: 20px;
          }
          .osc-switch input { opacity: 0; width: 0; height: 0; position: absolute; }
          .osc-switch .osc-slider {
            position: absolute;
            inset: 0;
            background-color: var(--switch-unchecked-track-color, #939393);
            transition: background-color 0.2s;
            border-radius: 20px;
            cursor: pointer;
          }
          .osc-switch .osc-slider::before {
            position: absolute;
            content: "";
            height: 16px;
            width: 16px;
            left: 2px;
            top: 2px;
            background-color: #fff;
            transition: transform 0.2s;
            border-radius: 50%;
          }
          .osc-switch input:checked + .osc-slider {
            background-color: var(--switch-checked-track-color, var(--primary-color));
          }
          .osc-switch input:checked + .osc-slider::before { transform: translateX(16px); }
          .osc-switch input:disabled + .osc-slider { opacity: 0.4; cursor: default; }
        </style>
      `;
    }

    _renderInput() {
      const s = this._state;
      if (s.value === undefined) return "";
      const type = s.fieldType;
      if (type === "boolean") {
        return `
          <div class="osc-field">
            <label class="osc-switch">
              <input type="checkbox" data-value ${s.value ? "checked" : ""} ${s.saving ? "disabled" : ""}>
              <span class="osc-slider"></span>
            </label>
          </div>
        `;
      }
      if (type === "number") {
        return `
          <div class="osc-field osc-field-row">
            <input type="number" step="any" data-value value="${esc(s.value)}" ${s.saving ? "disabled" : ""}>
            <button class="osc-btn-save" data-save ${s.saving ? "disabled" : ""}>${s.saving ? "…" : "Speichern"}</button>
          </div>
        `;
      }
      if (type === "json") {
        return `
          <div class="osc-field">
            <textarea data-value rows="4" ${s.saving ? "disabled" : ""}>${esc(JSON.stringify(s.value, null, 2))}</textarea>
            <button class="osc-btn-save" data-save style="margin-top: 8px;" ${s.saving ? "disabled" : ""}>${s.saving ? "Speichert…" : "Speichern"}</button>
          </div>
        `;
      }
      // string - the common case (path, text, filename_formatting, ...)
      return `
        <div class="osc-field osc-field-row">
          <input type="text" data-value value="${esc(s.value)}" ${s.saving ? "disabled" : ""}>
          <button class="osc-btn-save" data-save ${s.saving ? "disabled" : ""}>${s.saving ? "…" : "Speichern"}</button>
        </div>
      `;
    }

    _render() {
      if (!this._hass) return;
      if (!this._root) {
        this._root = this.attachShadow({ mode: "open" });
      }
      const s = this._state;
      const niceLabel = fieldLabel(s.kind, this._config.field, this._hass);
      const header = this._config.title || niceLabel || this._config.field;
      const kLabel = kindLabel(s.kind, this._hass);
      const contextLine = this._config.filter
        ? `${this._config.source} › ${this._config.filter}`
        : this._config.source;

      let body;
      if (s.loading) {
        body = `<p class="osc-note">Lädt…</p>`;
      } else if (s.error && s.value === undefined) {
        body = `<div class="osc-error">${esc(s.error)}</div>`;
      } else {
        body = `
          ${s.error ? `<div class="osc-error">${esc(s.error)}</div>` : ""}
          ${this._renderInput()}
        `;
      }

      this._root.innerHTML = `
        ${this._styles()}
        <ha-card>
          <div class="osc-header">
            <div class="osc-main">
              <span class="osc-title">${esc(header)}</span>
              <span class="osc-subtitle">${esc(contextLine)}${kLabel ? " · " + esc(kLabel) : ""}</span>
            </div>
            <button class="osc-refresh" data-refresh title="Aktualisieren" ${s.loading || s.saving ? "disabled" : ""}>
              <ha-icon icon="mdi:refresh"></ha-icon>
            </button>
          </div>
          <div class="osc-body">${body}</div>
        </ha-card>
      `;

      const refreshBtn = this._root.querySelector("[data-refresh]");
      if (refreshBtn) {
        refreshBtn.addEventListener("click", () => this._fetchValue());
      }
      const valueEl = this._root.querySelector("[data-value]");
      if (valueEl && s.fieldType === "boolean") {
        valueEl.addEventListener("change", (ev) => this._save(ev.target.checked));
      }
      const saveBtn = this._root.querySelector("[data-save]");
      if (saveBtn && valueEl) {
        saveBtn.addEventListener("click", () => this._save(valueEl.value));
      }
    }
  }

  customElements.define("obs-setting-card", ObsSettingCard);

  window.customCards.push({
    type: "obs-setting-card",
    name: "OBS Einstellung",
    description:
      "Eine einzelne OBS-Quellen-/Filter-Einstellung (z. B. Aufnahmepfad) als eigene Karte (OBS Stream Monitor).",
  });
})();
