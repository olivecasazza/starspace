/**
 * Star Office UI - Lightweight i18n system
 *
 * Usage in HTML:
 *   <span data-i18n="key">原始中文</span>
 *   <input data-i18n-placeholder="key" placeholder="原始中文">
 *   <div data-i18n-title="key" title="原始中文">...</div>
 *
 * Usage in JS:
 *   const text = t('key');
 *   const text = t('key', { name: 'Star' });  // interpolation: {{name}}
 */

const I18n = (() => {
  let _locale = 'zh';
  let _strings = {};
  let _fallback = {};  // zh strings as fallback
  let _ready = false;
  const _listeners = [];

  /** Detect preferred language from browser or URL param */
  function detectLocale() {
    // URL param takes priority: ?lang=en
    const params = new URLSearchParams(window.location.search);
    const urlLang = params.get('lang');
    if (urlLang && ['zh', 'en', 'ja'].includes(urlLang)) return urlLang;

    // Check localStorage
    const saved = localStorage.getItem('starspace-lang');
    if (saved && ['zh', 'en', 'ja'].includes(saved)) return saved;

    // Browser language
    const nav = navigator.language || navigator.userLanguage || 'zh';
    if (nav.startsWith('ja')) return 'ja';
    if (nav.startsWith('en')) return 'en';
    return 'zh';
  }

  /** Load locale JSON file */
  async function loadLocale(lang) {
    try {
      const resp = await fetch(`/static/locales/${lang}.json?t=${Date.now()}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return await resp.json();
    } catch (e) {
      console.warn(`i18n: failed to load ${lang}.json:`, e);
      return {};
    }
  }

  /** Initialize i18n system */
  async function init(locale) {
    _locale = locale || detectLocale();
    localStorage.setItem('starspace-lang', _locale);

    // Always load zh as fallback
    if (_locale !== 'zh') {
      _fallback = await loadLocale('zh');
      _strings = await loadLocale(_locale);
    } else {
      _strings = await loadLocale('zh');
      _fallback = _strings;
    }

    _ready = true;
    applyDOM();
    _listeners.forEach(fn => fn(_locale));
    return _locale;
  }

  /** Translate a key */
  function t(key, vars) {
    let text = _strings[key] || _fallback[key] || key;
    if (vars && typeof vars === 'object') {
      Object.entries(vars).forEach(([k, v]) => {
        text = text.replace(new RegExp(`{{${k}}}`, 'g'), v);
      });
    }
    return text;
  }

  /** Apply translations to DOM elements with data-i18n attributes */
  function applyDOM(root) {
    const container = root || document;

    container.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      const translated = t(key);
      if (translated && translated !== key) {
        el.textContent = translated;
      }
    });

    container.querySelectorAll('[data-i18n-html]').forEach(el => {
      const key = el.getAttribute('data-i18n-html');
      const translated = t(key);
      if (translated && translated !== key) {
        el.innerHTML = translated;
      }
    });

    container.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      const translated = t(key);
      if (translated && translated !== key) {
        el.placeholder = translated;
      }
    });

    container.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      const translated = t(key);
      if (translated && translated !== key) {
        el.title = translated;
      }
    });
  }

  /** Switch locale at runtime */
  async function setLocale(lang) {
    await init(lang);
    // Update URL without reload
    const url = new URL(window.location);
    url.searchParams.set('lang', lang);
    window.history.replaceState({}, '', url);
  }

  /** Register callback for locale changes */
  function onLocaleChange(fn) {
    _listeners.push(fn);
  }

  return {
    init,
    t,
    applyDOM,
    setLocale,
    onLocaleChange,
    detectLocale,
    get locale() { return _locale; },
    get ready() { return _ready; },
  };
})();

/** Global shorthand */
function t(key, vars) {
  return I18n.t(key, vars);
}
