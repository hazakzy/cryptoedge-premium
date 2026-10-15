(function(){
  var KEY = 'ce-theme';
  var root = document.documentElement;
  function current(){ return root.getAttribute('data-theme') === 'light' ? 'light' : 'dark'; }
  function sync(btn){
    var light = current() === 'light';
    btn.setAttribute('aria-pressed', light ? 'true' : 'false');
    btn.setAttribute('aria-label', light ? 'Switch to dark theme' : 'Switch to light theme');
    btn.title = btn.getAttribute('aria-label');
  }
  document.querySelectorAll('[data-theme-toggle]').forEach(function(btn){
    sync(btn);
    btn.addEventListener('click', function(){
      var next = current() === 'light' ? 'dark' : 'light';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
      var m = document.querySelector('meta[name="theme-color"]');
      if (m) m.setAttribute('content', next === 'light' ? '#f4f7fb' : '#070a0f');
      document.querySelectorAll('[data-theme-toggle]').forEach(sync);
    });
  });
})();
