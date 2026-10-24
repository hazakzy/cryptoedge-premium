(function(){
  if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  var observer = new IntersectionObserver(function(entries){
    entries.forEach(function(entry){ if(entry.isIntersecting){entry.target.classList.add('is-visible');observer.unobserve(entry.target);} });
  }, {threshold:0.08});
  document.querySelectorAll('.course-card,.bundle,.section-intro').forEach(function(el){
    el.classList.add('reveal-ready');observer.observe(el);
  });
})();
