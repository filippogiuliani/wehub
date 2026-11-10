<script>
  // Admin: the other services shown on the home page (the family apps themselves come from the server settings)
  import { get } from '../lib/api.js';
  import { app, showError } from '../lib/store.svelte.js';
  import { t } from '../lib/i18n.svelte.js';
  import Shortcuts from '../components/Shortcuts.svelte';
  import AppIcon from '../components/AppIcon.svelte';
  let members = $state(null);
  get('/family').then((f) => (members = f.members)).catch(showError);
</script>

<header class="head"><h1>{t('links.title')}</h1><p class="muted">{t('links.page_subtitle')}</p></header>

<div class="stack big">
  {#if members}<Shortcuts {members} />{/if}

  <section class="card stack">
    <h2>{t('links.family_apps')}</h2>
    <p class="small muted">{t('links.family_apps_note')}</p>
    <ul class="list">
      {#each app.me.all_apps as a (a.id)}
        <li><AppIcon id={a.id} size={32} /><span class="grow"><b>{a.name}</b> <span class="tiny muted">{a.url || t('links.no_url')}</span></span></li>
      {/each}
    </ul>
  </section>
</div>

<style>
  .head { margin-bottom: 18px; }
  .big { gap: 14px; }
  .list { list-style: none; margin: 0; padding: 0; }
  .list li { display: flex; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--line); }
  .list li:last-child { border: 0; }
</style>
