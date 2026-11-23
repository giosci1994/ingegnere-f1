// Ingegnere F1 — landing page
// One language at a time (English / Italian): every translated element carries
// data-en and data-it. The choice is remembered in this browser.
document.addEventListener('DOMContentLoaded', () => {
  const root = document.documentElement;
  const langBtn = document.getElementById('lang-toggle');
  const texts = document.querySelectorAll('[data-en]');
  const metaDesc = document.querySelector('meta[name="description"]');
  const KEY = 'ingegnere-f1-lang';

  function saved() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function remember(lang) {
    try { localStorage.setItem(KEY, lang); } catch (e) { /* private mode: no memory */ }
  }

  function apply(lang) {
    texts.forEach((el) => {
      const value = el.dataset[lang];
      if (value !== undefined) el.innerHTML = value;
    });
    root.lang = lang;
    if (root.dataset[lang + 'Title']) document.title = root.dataset[lang + 'Title'];
    if (metaDesc && metaDesc.dataset[lang]) metaDesc.content = metaDesc.dataset[lang];
    if (langBtn) {
      langBtn.textContent = lang === 'it' ? 'EN' : 'IT';
      langBtn.setAttribute('aria-label', lang === 'it' ? 'Switch to English' : "Passa all'italiano");
      langBtn.title = langBtn.getAttribute('aria-label');
    }
  }

  // ?lang=it / ?lang=en wins, then the saved choice, then the browser language.
  const fromUrl = new URLSearchParams(location.search).get('lang');
  let lang = ['en', 'it'].includes(fromUrl) ? fromUrl
    : saved() || ((navigator.language || 'en').toLowerCase().startsWith('it') ? 'it' : 'en');
  apply(lang);

  if (langBtn) {
    langBtn.addEventListener('click', () => {
      lang = lang === 'it' ? 'en' : 'it';
      apply(lang);
      remember(lang);
    });
  }

  const year = document.getElementById('year');
  if (year) year.textContent = new Date().getFullYear();

  // Entrance with Motion (motion.dev), optional. The head script hides .reveal only while Motion is
  // expected; it gives up after 1.5 s, and a failed load shows everything at once.
  let started = false;
  window.__startMotion = () => {
    if (started) return;
    started = true;
    const M = window.Motion;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    clearTimeout(window.__revealTimer);
    if (!M || !M.animate || !M.inView || reduceMotion || !root.classList.contains('motion-ready')) {
      root.classList.remove('motion-ready');
      return;
    }
    const ease = [0.22, 1, 0.36, 1];
    const items = Array.from(document.querySelectorAll('.reveal'));
    // Hand the hidden start from the class to inline styles, then fade and rise each block as it enters.
    // Blocks entering together get a small stagger (50 ms, at most six steps).
    items.forEach((el) => { el.style.opacity = '0'; });
    root.classList.remove('motion-ready');
    let batch = 0;
    let batchTimer = null;
    try {
      items.forEach((el) => {
        M.inView(el, () => {
          const delay = Math.min(batch, 5) * 0.05;
          batch += 1;
          clearTimeout(batchTimer);
          batchTimer = setTimeout(() => { batch = 0; }, 120);
          M.animate(el, { opacity: [0, 1], transform: ['translateY(8px)', 'translateY(0px)'] },
            { duration: 0.4, delay, ease });
        }, { amount: 0.2 });
      });
    } catch (e) {
      items.forEach((el) => { el.style.opacity = ''; el.style.transform = ''; });
    }
  };
  if (window.Motion) window.__startMotion();
});
