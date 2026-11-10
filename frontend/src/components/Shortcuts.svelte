<script>
  // Admin: links to other services on the home page, each for everyone or for chosen members.
  import { del, get, post, put } from '../lib/api.js';
  import { loadMe, showError, toast } from '../lib/store.svelte.js';
  import { t } from '../lib/i18n.svelte.js';
  import Icon from './Icon.svelte';

  let { members } = $props();
  const ICONS = ['link', 'lock', 'home', 'photo', 'film', 'music', 'server', 'chart', 'mail', 'calendar', 'book', 'cloud', 'tool'];
  let links = $state([]);
  let form = $state(null); // { id?, name, url, description, icon, everyone, members: [] }

  get('/family/shortcuts').then((r) => (links = r)).catch(showError);

  async function act(fn, message) {
    try { links = await fn(); await loadMe(); if (message) toast(message); return true; } catch (e) { showError(e); return false; }
  }
  const startNew = () => (form = { name: '', url: '', description: '', icon: 'link', everyone: true, members: [] });
  const edit = (l) => (form = { ...l, members: [...l.members] });
  async function save(e) {
    e.preventDefault();
    const body = { name: form.name, url: form.url, description: form.description, icon: form.icon, everyone: form.everyone, members: form.members };
    if (await act(() => (form.id ? put(`/family/shortcuts/${form.id}`, body) : post('/family/shortcuts', body)), t('common.saved'))) form = null;
  }
  async function remove(l) {
    if (!confirm(t('links.confirm_delete', { name: l.name }))) return;
    await act(() => del(`/family/shortcuts/${l.id}`));
  }
  const move = (l, direction) => act(() => post(`/family/shortcuts/${l.id}/move`, { direction }));
  const toggle = (id) => (form.members = form.members.includes(id) ? form.members.filter((x) => x !== id) : [...form.members, id]);
  const who = (l) => (l.everyone ? t('links.everyone') : members.filter((m) => l.members.includes(m.id)).map((m) => m.name).join(', '));
</script>

<section class="card stack">
  <div class="spread"><h2 class="ic"><Icon name="link" />{t('links.title')}</h2>
    {#if !form}<button class="btn soft sm" onclick={startNew}><Icon name="plus" size={15} />{t('links.add')}</button>{/if}</div>
  <p class="small muted">{t('links.explain')}</p>

  {#if form}
    <form class="box stack" onsubmit={save}>
      <div class="grid2">
        <input class="input" bind:value={form.name} maxlength="60" placeholder={t('links.name')} aria-label={t('links.name')} required />
        <input class="input" bind:value={form.url} maxlength="500" placeholder="https://vault.example.com" aria-label={t('links.url')} required inputmode="url" />
      </div>
      <input class="input" bind:value={form.description} maxlength="120" placeholder={t('links.description')} aria-label={t('links.description')} />
      <div class="icons" role="radiogroup" aria-label={t('links.icon')}>
        {#each ICONS as i}
          <button type="button" class="ib" class:on={form.icon === i} onclick={() => (form.icon = i)} aria-label={i} role="radio" aria-checked={form.icon === i}>
            <Icon name={i} size={18} /></button>
        {/each}
      </div>
      <div class="seg">
        <button type="button" class:on={form.everyone} onclick={() => (form.everyone = true)}>{t('links.everyone')}</button>
        <button type="button" class:on={!form.everyone} onclick={() => (form.everyone = false)}>{t('links.only')}</button>
      </div>
      {#if !form.everyone}
        <div class="chips">
          {#each members as m (m.id)}
            <button type="button" class="chip" class:on={form.members.includes(m.id)} onclick={() => toggle(m.id)}>{m.name}</button>
          {/each}
        </div>
      {/if}
      <p class="tiny">{t('links.not_security')}</p>
      <div class="row">
        <button class="btn primary" disabled={!form.name.trim() || !form.url.trim() || (!form.everyone && !form.members.length)}>{t('common.save')}</button>
        <button type="button" class="btn ghost" onclick={() => (form = null)}>{t('common.cancel')}</button>
      </div>
    </form>
  {/if}

  {#if links.length}
    <ul class="list">
      {#each links as l, i (l.id)}
        <li>
          <span class="lic"><Icon name={l.icon} size={17} /></span>
          <div class="grow">
            <b>{l.name}</b> <span class="tiny muted url">{l.url}</span>
            <div class="tiny muted">{t('links.seen_by', { who: who(l) })}</div>
          </div>
          <button class="btn icon sm ghost" onclick={() => move(l, -1)} disabled={i === 0} aria-label={t('links.up')}><Icon name="up" size={14} /></button>
          <button class="btn icon sm ghost" onclick={() => move(l, 1)} disabled={i === links.length - 1} aria-label={t('links.down')}><Icon name="down" size={14} /></button>
          <button class="btn icon sm ghost" onclick={() => edit(l)} aria-label={t('common.edit')}><Icon name="edit" size={15} /></button>
          <button class="btn icon sm ghost" onclick={() => remove(l)} aria-label={t('common.delete')}><Icon name="trash" size={15} /></button>
        </li>
      {/each}
    </ul>
  {:else if !form}
    <p class="small muted">{t('links.none')}</p>
  {/if}
</section>

<style>
  .ic { display: flex; align-items: center; gap: 8px; }
  .box { padding: 12px; border-radius: var(--r-md); background: var(--primary-soft); }
  .grid2 { display: grid; gap: 8px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 520px) { .grid2 { grid-template-columns: minmax(0, 1fr); } }
  .icons { display: flex; flex-wrap: wrap; gap: 6px; }
  .ib { width: 36px; height: 36px; display: grid; place-items: center; border: 1px solid var(--line); border-radius: var(--r-xs);
    background: var(--surface); color: var(--muted); cursor: pointer; }
  .ib.on { border-color: var(--primary); color: var(--primary-ink); background: var(--primary); }
  .list { list-style: none; margin: 0; padding: 0; }
  .list li { display: flex; align-items: center; gap: 6px; padding: 9px 0; border-bottom: 1px solid var(--line); }
  .list li:last-child { border: 0; }
  .lic { width: 32px; height: 32px; border-radius: 8px; background: var(--primary-soft); color: var(--primary); display: grid; place-items: center; flex-shrink: 0; }
  .url { overflow-wrap: anywhere; }
</style>
