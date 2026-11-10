<script>
  // The entrance: the apps this person may use, one tap away (signed in to each with the same Pocket ID).
  import { app } from '../lib/store.svelte.js';
  import { language, t } from '../lib/i18n.svelte.js';
  import Icon from '../components/Icon.svelte';
  const apps = $derived(app.me.apps ?? []);
  const links = $derived(app.me.shortcuts ?? []);
</script>

<header class="head">
  <h1>{t('home.hello', { name: app.me.user.name.split(' ')[0] })}</h1>
  <p class="muted">{app.me.family?.name}</p>
</header>

{#if apps.length}
  <div class="grid">
    {#each apps as a (a.id)}
      <a class="tile" href={a.url || '#'} aria-disabled={!a.url}>
        <span class="ic"><Icon name={a.id} size={26} /></span>
        <span class="txt">
          <b>{a.name}</b>
          <span class="small muted">{a.description?.[language.id] ?? a.description?.en ?? ''}</span>
          {#if a.level === 'limited'}<span class="badge">{t('access.limited')}</span>{/if}
        </span>
        <Icon name="right" size={18} />
      </a>
    {/each}
  </div>
  <p class="tiny muted note">{t('home.note')}</p>
{:else}
  <p class="empty">{t('home.no_apps')}</p>
{/if}

{#if links.length}
  <h2 class="sub">{t('links.title')}</h2>
  <div class="links">
    {#each links as l (l.id)}
      <a class="link" href={l.url} target="_blank" rel="noopener noreferrer">
        <span class="lic"><Icon name={l.icon} size={20} /></span>
        <span class="txt"><b>{l.name}</b>{#if l.description}<span class="tiny muted">{l.description}</span>{/if}</span>
        <Icon name="external" size={15} />
      </a>
    {/each}
  </div>
{/if}

<style>
  .head { margin-bottom: 20px; display: flex; flex-direction: column; gap: 4px; }
  .grid { display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 700px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .tile { display: flex; align-items: center; gap: 14px; padding: 18px; border: 1px solid var(--line); border-radius: var(--r-lg);
    background: var(--surface); text-decoration: none; color: var(--ink); }
  .tile:hover { border-color: var(--line-strong); background: var(--surface-2); }
  .ic { width: 48px; height: 48px; border-radius: 12px; background: var(--primary); color: var(--primary-ink); display: grid; place-items: center; flex-shrink: 0; }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .txt b { font-size: 1.05rem; }
  .txt .badge { align-self: flex-start; margin-top: 4px; }
  .note { margin-top: 16px; }
  .sub { margin: 28px 0 12px; }
  .links { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
  .link { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid var(--line); border-radius: var(--r-md);
    background: var(--surface); text-decoration: none; color: var(--ink); min-width: 0; }
  .link:hover { border-color: var(--line-strong); background: var(--surface-2); }
  .link :global(svg:last-child) { color: var(--muted); }
  .lic { width: 36px; height: 36px; border-radius: 9px; background: var(--primary-soft); color: var(--primary); display: grid; place-items: center; flex-shrink: 0; }
  .link .txt b { font-size: 0.95rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
