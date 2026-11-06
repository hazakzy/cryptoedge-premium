/* Official TradingView display embed. No scraping, API key or server storage. */
(function () {
  'use strict';
  var sections = document.querySelectorAll('[data-economic-calendar]');
  if (!sections.length) return;
  var mounted = new Set();

  function mount(section) {
    var host = section.querySelector('[data-calendar-widget]');
    var widget = host.querySelector('.tradingview-widget-container__widget');
    var status = section.querySelector('[data-calendar-status]');
    if (host._calendarCleanup) host._calendarCleanup();
    widget.replaceChildren();
    host.querySelectorAll('script').forEach(function (script) { script.remove(); });
    status.hidden = false;
    status.textContent = 'Loading economic calendar…';
    var theme = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
    var timer = window.setTimeout(function () {
      status.textContent = 'Calendar taking longer to load? Open it on TradingView below.';
    }, 15000);
    var observer = new MutationObserver(function () {
      var frame = widget.querySelector('iframe') || host.querySelector('iframe');
      if (!frame) return;
      frame.title = 'Economic calendar by TradingView';
      frame.addEventListener('load', function () {
        window.clearTimeout(timer);
        status.hidden = true;
      }, { once: true });
      observer.disconnect();
    });
    observer.observe(host, { childList: true, subtree: true });
    host._calendarCleanup = function () { window.clearTimeout(timer); observer.disconnect(); };
    var script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-events.js';
    script.async = true;
    script.textContent = JSON.stringify({
      colorTheme: theme,
      isTransparent: false,
      locale: 'en',
      countryFilter: 'us,gb,eu,jp,cn',
      importanceFilter: '1',
      width: '100%',
      height: Number(section.getAttribute('data-calendar-height')) || 520
    });
    script.onerror = function () {
      window.clearTimeout(timer);
      status.hidden = false;
      status.textContent = 'Calendar unavailable here. Open it on TradingView below.';
    };
    host.appendChild(script);
    mounted.add(section);
  }

  if ('IntersectionObserver' in window) {
    var visible = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) { visible.unobserve(entry.target); mount(entry.target); }
      });
    }, { rootMargin: '250px' });
    sections.forEach(function (section) { visible.observe(section); });
  } else {
    sections.forEach(mount);
  }
  new MutationObserver(function () { mounted.forEach(mount); }).observe(document.documentElement,
    { attributes: true, attributeFilter: ['data-theme'] });
})();
