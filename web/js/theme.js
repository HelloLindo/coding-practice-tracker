// Applied before first paint so the chosen theme never flashes.
(function () {
  'use strict';
  var choice = 'system';
  try { choice = localStorage.getItem('practice-theme') || 'system'; } catch (_) { /* storage unavailable */ }
  if (choice === 'light' || choice === 'dark') document.documentElement.dataset.theme = choice;
})();
