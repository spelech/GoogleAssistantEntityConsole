if (!customElements.get('google-assistant-entity-console-panel')) {
  class GoogleAssistantEntityConsolePanel extends HTMLElement {
    constructor() {
      super();
      this._lastToken = null;
      this._iframe = null;
      this._hass = null;
      this._messageListener = (event) => {
        if (event.data && event.data.type === 'REQUEST_HA_TOKEN') {
          if (this._iframe && this._iframe.contentWindow && this._hass && this._hass.auth && this._hass.auth.accessToken) {
            this._iframe.contentWindow.postMessage({
              type: 'HA_TOKEN_UPDATE',
              token: this._hass.auth.accessToken
            }, '*');
          }
        }
      };
    }

    connectedCallback() {
      this.style.display = 'block';
      this.style.position = 'relative';
      this.style.width = '100%';
      this.style.maxWidth = '100%';
      this.style.height = 'calc(100vh - var(--safe-area-inset-top, 0px) - var(--safe-area-inset-bottom, 0px))';
      this.style.overflow = 'hidden';
      this.style.boxSizing = 'border-box';
      this.style.isolation = 'isolate';
      this.style.zIndex = '1';
      this.style.contain = 'layout paint';
      window.addEventListener('message', this._messageListener);
    }

    disconnectedCallback() {
      window.removeEventListener('message', this._messageListener);
    }

    setConfig(config) {
      this._config = config;
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._iframe) {
        this._iframe = document.createElement('iframe');
        this._iframe.style.width = '100%';
        this._iframe.style.height = '100%';
        this._iframe.style.border = '0';
        this._iframe.style.display = 'block';
        this._iframe.style.overflow = 'hidden';
        this.appendChild(this._iframe);
      }
      // Update the src only once
      if (!this._iframe.src) {
        const token = hass.auth && hass.auth.accessToken ? hass.auth.accessToken : '';
        this._lastToken = token;
        const ver = (this._config && this._config.version) || Date.now();
        this._iframe.src = `/google_assistant_entity_console/static/index.html?token=${encodeURIComponent(token)}&v=${ver}`;
      } else if (hass.auth && hass.auth.accessToken && hass.auth.accessToken !== this._lastToken) {
        this._lastToken = hass.auth.accessToken;
        if (this._iframe.contentWindow) {
          this._iframe.contentWindow.postMessage({
            type: 'HA_TOKEN_UPDATE',
            token: this._lastToken
          }, '*');
        }
      }
    }
  }
  customElements.define('google-assistant-entity-console-panel', GoogleAssistantEntityConsolePanel);
}
