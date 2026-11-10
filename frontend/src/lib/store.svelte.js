// Shared state: the session (user, family, apps) and toasts.
import { get } from './api.js';
import { t } from './i18n.svelte.js';

export const app = $state({ toast: null, me: null });

export async function loadMe() {
  app.me = await get('/me');
  return app.me;
}

let toastId = 0;
export function toast(message, kind = 'ok') {
  const id = ++toastId;
  app.toast = { id, message, kind };
  setTimeout(() => { if (app.toast?.id === id) app.toast = null; }, kind === 'error' ? 5000 : 2600);
}
export function showError(e) { toast(e?.message || t('error.generic', { code: '' }), 'error'); }
