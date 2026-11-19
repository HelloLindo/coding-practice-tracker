// Entry point: load platforms and problems, then hand over to the router.

import {problemHref} from './dom.js';
import {state, loadPlatforms, refreshProblems, notice, followJob} from './state.js';
import {initSidebar, renderList} from './sidebar.js';
import {register, start, onRender, navigate, flash} from './router.js';
import {newView} from './views/new.js';
import {problemView} from './views/problem.js';
import {reviewView} from './views/review.js';

function initTheme() {
  const apply = choice => {
    if (choice === 'light' || choice === 'dark') document.documentElement.dataset.theme = choice;
    else delete document.documentElement.dataset.theme;
    document.querySelectorAll('[data-theme-choice]').forEach(button => {
      const active = button.dataset.themeChoice === choice;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  };
  let choice = 'system';
  try { choice = localStorage.getItem('practice-theme') || 'system'; } catch (_) { /* unavailable */ }
  apply(choice);
  document.querySelectorAll('[data-theme-choice]').forEach(button => button.addEventListener('click', () => {
    try { localStorage.setItem('practice-theme', button.dataset.themeChoice); } catch (_) { /* unavailable */ }
    apply(button.dataset.themeChoice);
  }));
}

function resumeJob() {
  let id = null;
  try { id = sessionStorage.getItem('practice-job'); } catch (_) { return; }
  if (!id) return;
  const view = state.view;
  if (view?.resume) { view.resume(id); return; }
  if (view?.follow) { view.follow(id); return; }
  followJob(id, {onDone: async job => {
    await refreshProblems().catch(() => {});
    if (job.key) { flash(job.message, job.state === 'ready' ? 'success' : 'error'); navigate(problemHref(job.key), {force: true, draft: job.draft}); }
  }});
}

(async () => {
  initTheme();
  register('new', newView);
  register('problem', problemView);
  register('review', reviewView);
  onRender(() => renderList());
  try {
    await loadPlatforms();
    initSidebar();
    await refreshProblems();
  } catch (error) {
    notice(error.message, 'error');
  }
  await start();
  resumeJob();
})();
