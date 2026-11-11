<script>
  // Admin: links to other services on the home page, in groups, each for everyone or for chosen members.
  // Icons as in Homepage (jellyfin.png, mdi-logout, an address…); a Homepage services.yaml can be imported.
  import { del, get, post, put } from '../lib/api.js';
  import { loadMe, showError, toast } from '../lib/store.svelte.js';
  import { t } from '../lib/i18n.svelte.js';
  import Icon from './Icon.svelte';
  import LinkIcon from './LinkIcon.svelte';

  let { members } = $props();
  const ICONS = ['link', 'lock', 'home', 'photo', 'film', 'music', 'server', 'chart', 'mail', 'calendar', 'book', 'cloud', 'tool'];
  let links = $state([]);
  let form = $state(null); // { id?, name, url, description, icon, group, everyone, members: [] }
  let importing = $state(null); // the pasted services.yaml while the import box is open
  let report = $state(null);
  const groups = $derived([...new Set(links.map((l) => l.group).filter(Boolean))]);
  // What the icon field means, for the hint under it
  const iconHint = (v) => {
    v = (v || '').trim();
    if (!v || ICONS.includes(v)) return '';
    if (/^https?:\/\//i.test(v)) return t('links.icon_url');
    if (/^mdi-/i.test(v)) return t('links.icon_mdi');
    if (/^si-/i.test(v)) return t('links.icon_si');
    if (/^sh-/i.test(v)) return t('links.icon_selfhst');
    return t('links.icon_dashboard');
  };

  get('/family/shortcuts').then((r) => (links = r)).catch(showError);

  async function act(fn, message) {
    try { links = await fn(); await loadMe(); if (message) toast(message); return true; } catch (e) { showError(e); return false; }
  }
  const startNew = () => { importing = null; form = { name: '', url: '', description: '', icon: 'link', group: groups.at(-1) ?? '', monitor: true, everyone: true, members: [] }; };
  const edit = (l) => { importing = null; form = { ...l, members: [...l.members] }; };
  async function save(e) {
    e.preventDefault();
    const body = { name: form.name, url: form.url, description: form.description, icon: form.icon, group: form.group, monitor: form.monitor, everyone: form.everyone, members: form.members };
    if (await act(() => (form.id ? put(`/family/shortcuts/${form.id}`, body) : post('/family/shortcuts', body)), t('common.saved'))) form = null;
  }
  async function remove(l) {
    if (!confirm(t('links.confirm_delete', { name: l.name }))) return;
    await act(() => del(`/family/shortcuts/${l.id}`));
  }
  const move = (l, direction) => act(() => post(`/family/shortcuts/${l.id}/move`, { direction }));
  async function runImport(e) {
    e.preventDefault();
    try {
      const r = await post('/family/shortcuts/import', { yaml: importing });
      links = r.links; report = r; importing = null;
      await loadMe();
    } catch (err) { showError(err); }
  }
  const toggle = (id) => (form.members = form.members.includes(id) ? form.members.filter((x) => x !== id) : [...form.members, id]);
  const who = (l) => (l.everyone ? t('links.everyone') : members.filter((m) => l.members.includes(m.id)).map((m) => m.name).join(', '));
</script>

<section class="card stack">
  <div class="spread"><h2 class="ic"><Icon name="link" />{t('links.title')}</h2>
    {#if !form && importing === null}<div class="row">
      <button class="btn ghost sm" onclick={() => { report = null; importing = ''; }}><Icon name="upload" size={15} />{t('links.import')}</button>
      <button class="btn soft sm" onclick={startNew}><Icon name="plus" size={15} />{t('links.add')}</button></div>{/if}</div>
  <p class="small muted">{t('links.explain')}</p>

  {#if importing !== null}
    <form class="box stack" onsubmit={runImport}>
      <p class="small">{t('links.import_explain')}</p>
      <textarea class="input mono" rows="12" bind:value={importing} spellcheck="false" placeholder={'- Multimedia:\n    - Jellyfin:\n        icon: jellyfin.png\n        href: https://jellyfin.example.com\n        description: Streaming'} aria-label="services.yaml"></textarea>
      <p class="tiny muted">{t('links.import_note')}</p>
      <div class="row">
        <button class="btn primary" disabled={!importing.trim()}>{t('links.import_go')}</button>
        <button type="button" class="btn ghost" onclick={() => (importing = null)}>{t('common.cancel')}</button>
      </div>
    </form>
  {/if}
  {#if report}
    <div class="box small">
      {t('links.import_done', { added: report.added.length, updated: report.updated.length })}
      {#if report.skipped.length}<br /><span class="muted">{t('links.import_skipped', { names: report.skipped.join(', ') })}</span>{/if}
    </div>
  {/if}

  {#if form}
    <form class="box stack" onsubmit={save}>
      <div class="grid2">
        <input class="input" bind:value={form.name} maxlength="60" placeholder={t('links.name')} aria-label={t('links.name')} required />
        <input class="input" bind:value={form.url} maxlength="500" placeholder="https://vault.example.com" aria-label={t('links.url')} required inputmode="url" />
      </div>
      <div class="grid2">
        <input class="input" bind:value={form.description} maxlength="120" placeholder={t('links.description')} aria-label={t('links.description')} />
        <input class="input" bind:value={form.group} maxlength="60" placeholder={t('links.group')} aria-label={t('links.group')} list="link-groups" />
        <datalist id="link-groups">{#each groups as gr}<option value={gr}></option>{/each}</datalist>
      </div>
      <label class="stack tight">
        <span class="small">{t('links.icon')}</span>
        <input class="input" bind:value={form.icon} maxlength="500" placeholder="jellyfin.png · mdi-logout · https://…" spellcheck="false" autocapitalize="off" />
        <span class="tiny muted">{iconHint(form.icon) || t('links.icon_help')}</span>
      </label>
      <div class="icons" role="radiogroup" aria-label={t('links.icon')}>
        {#each ICONS as i}
          <button type="button" class="ib" class:on={form.icon === i} onclick={() => (form.icon = i)} aria-label={i} role="radio" aria-checked={form.icon === i}>
            <Icon name={i} size={18} /></button>
        {/each}
      </div>
      <label class="check small"><input type="checkbox" bind:checked={form.monitor} /> {t('links.monitor')}</label>
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
        {#if i === 0 || l.group !== links[i - 1].group}<li class="gh">{l.group || t('links.no_group')}</li>{/if}
        <li>
          <span class="lic"><LinkIcon link={l} size={20} /></span>
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
  .gh { font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); padding-top: 14px; }
  .tight { gap: 4px; }
  .check { display: flex; align-items: center; gap: 8px; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 0.85rem; }
  .lic { width: 32px; height: 32px; border-radius: 8px; background: var(--primary-soft); color: var(--primary); display: grid; place-items: center; flex-shrink: 0; }
  .url { overflow-wrap: anywhere; }
</style>
