/**
 * OBS Szenen-Baum - a custom Lovelace card bundled with the OBS Stream
 * Monitor integration (custom_components/obs_stream_monitor/).
 *
 * Shows OBS's scenes -> sources -> filters as a click-through tree, with
 * toggles for source visibility (the "eye" icon in OBS) and filter
 * enable/disable. It never talks to OBS directly - it just reads/writes
 * the switch.* and sensor.* entities the integration creates once
 * "Szenen-Baum aktivieren" is turned on in the integration's Configure
 * dialog, discovering them via their obs_role/scene/source/filter
 * attributes (set in switch.py / sensor.py) rather than by entity_id, so
 * it keeps working even if entities get renamed.
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
 * custom element so it can be served as-is.
 */
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
    }

    set hass(hass) {
      this._hass = hass;
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
            font-family: var(--code-font-family, ui-monospace, "SFMono-Regular", Consolas, monospace);
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
        </style>
      `;
    }

    _renderEntityId(entity) {
      return `
        <span class="otc-entity-id" data-copy-entity="${esc(entity.entity_id)}" title="Klicken zum Kopieren">
          <ha-icon icon="mdi:content-copy"></ha-icon>
          ${esc(entity.entity_id)}
        </span>
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
              ${this._renderToggle(entity)}
            </div>
          `;
        })
        .join("");
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
})();
