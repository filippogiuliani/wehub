<script>
  // The entrance: the apps this person may use, one tap away (signed in to each with the same Pocket ID).
  import { app } from '../lib/store.svelte.js';
  import { get } from '../lib/api.js';
  import { language, t } from '../lib/i18n.svelte.js';
  import Icon from '../components/Icon.svelte';
  import AppIcon from '../components/AppIcon.svelte';
  import LinkIcon from '../components/LinkIcon.svelte';
  const apps = $derived(app.me.apps ?? []);
  const links = $derived(app.me.shortcuts ?? []);
  // Is each service up? Asked to weHub (it opens the addresses), again every minute while the page is open
  let status = $state({});
  $effect(() => {
    if (!links.some((l) => l.monitor)) return;
    const load = () => { if (!document.hidden) get('/shortcuts/status').then((r) => (status = r)).catch(() => {}); };
    load();
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
  });
  // A short summary from each app (what is coming up, today's meals, documents to fix): asked to weHub, which asks the apps
  let summary = $state(null); // { apps: { id: data | null } }
  $effect(() => {
    app.me.family?.id;
    const load = () => { if (!document.hidden) get('/home/summary').then((r) => (summary = r)).catch(() => {}); };
    load();
    const timer = setInterval(load, 120000);
    return () => clearInterval(timer);
  });
  const today = new Date().toISOString().slice(0, 10);
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
  function when(d, time) {
    const day = d < today ? t('sum.overdue_on', { date: shortDate(d) }) : d === today ? t('sum.today') : d === tomorrow ? t('sum.tomorrow') : shortDate(d);
    return time ? `${day} ${time}` : day;
  }
  const shortDate = (d) => new Date(d + 'T12:00:00').toLocaleDateString(language.id, { day: 'numeric', month: 'short' });
  const statusText = (st) => !st ? t('links.status_checking')
    : st.up ? t('links.status_up', { ms: st.ms ?? '?' })
    : st.code ? t('links.status_error', { code: st.code })
    : t(st.reason === 'timeout' ? 'links.status_timeout' : 'links.status_down');
  // Links in their groups, in the admin's order (a group sits where its first link is)
  const groups = $derived.by(() => {
    const out = [];
    for (const l of links) {
      let gr = out.find((x) => x.name === (l.group || ''));
      if (!gr) out.push((gr = { name: l.group || '', links: [] }));
      gr.links.push(l);
    }
    return out;
  });
</script>

<header class="head">
  <h1>{t('home.hello', { name: app.me.user.name.split(' ')[0] })}</h1>
  <p class="muted">{app.me.family?.name}</p>
</header>

{#if apps.length}
  <div class="grid">
    {#each apps as a (a.id)}
      {@const sm = summary?.apps?.[a.id]}
      <section class="app-card">
        <a class="tile" href={a.url || '#'} aria-disabled={!a.url}>
          <AppIcon id={a.id} size={44} />
          <span class="txt">
            <b>{a.name}</b>
            <span class="small muted">{a.description?.[language.id] ?? a.description?.en ?? ''}</span>
            {#if a.level === 'limited'}<span class="badge">{t('access.limited')}</span>{/if}
          </span>
          <Icon name="right" size={18} />
        </a>
        <div class="sum">
          {#if !summary}<p class="small muted">…</p>
          {:else if summary.apps[a.id] === undefined}
          {:else if !sm}<p class="small muted">{t('sum.no_answer', { app: a.name })}</p>
          {:else if a.id === 'dotrack'}
            <p class="counts small">
              {#if sm.overdue}<span class="late">{t('sum.n_overdue', { n: sm.overdue })}</span>{/if}
              <span>{t('sum.n_today', { n: sm.today })}</span><span>{t('sum.n_week', { n: sm.week })}</span>
            </p>
            {#each sm.items as it (it.id)}
              <a class="line" href={it.url ?? a.url}><span class="grow ell">{it.title}</span>
                <span class="small" class:late={it.due_date < today}>{when(it.due_date, it.due_time)}</span>
                {#if it.who}<span class="small muted who" class:mine={it.mine}>{it.who}</span>{/if}</a>
            {:else}<p class="small muted">{t('sum.nothing_due')}</p>{/each}
          {:else if a.id === 'eatrack'}
            {#each sm.children as c (c.name)}
              <p class="small"><b>{c.name}</b> · {c.meals_today.length ? c.meals_today.map((m) => t('meal.' + m)).join(', ') : t('sum.no_meals')}</p>
            {:else}<p class="small muted">{t('sum.no_children')}</p>{/each}
            {#if sm.jars_soon}<p class="small late">{t('sum.jars_soon', { n: sm.jars_soon })}</p>{/if}
          {:else if a.id === 'patrack'}
            <p class="counts small">
              {#if sm.to_fix}<span class="late">{t('sum.to_fix', { n: sm.to_fix })}</span>{/if}
              {#if sm.errors}<span class="late">{t('sum.import_errors', { n: sm.errors })}</span>{/if}
              <span>{t('sum.added_week', { n: sm.added_week })}</span>
            </p>
            {#each sm.expiring as d (d.id)}
              <a class="line" href={d.url ?? a.url}><span class="grow ell">{d.title}</span>
                {#if d.person}<span class="small muted">{d.person}</span>{/if}
                <span class="small" class:late={d.expiry_date < today}>{t(d.expiry_date < today ? 'sum.expired_on' : 'sum.expires_on', { date: shortDate(d.expiry_date) })}</span></a>
            {/each}
          {/if}
        </div>
      </section>
    {/each}
  </div>
  <p class="tiny muted note">{t('home.note')}</p>
{:else}
  <p class="empty">{t('home.no_apps')}</p>
{/if}

{#if links.length || app.me.role === 'admin'}
  <div class="spread sub">
    <h2>{t('links.title')}</h2>
    {#if app.me.role === 'admin'}<a class="btn ghost sm" href="#/links"><Icon name="edit" size={14} />{t('links.manage')}</a>{/if}
  </div>
{/if}
{#if !links.length && app.me.role === 'admin'}
  <a class="empty-links" href="#/links">
    <Icon name="plus" size={18} />
    <span><b>{t('links.add_first')}</b><br /><span class="small muted">{t('links.add_first_note')}</span></span>
  </a>
{/if}
{#each groups as gr (gr.name)}
  <section class="group">
    {#if gr.name}<h3>{gr.name}</h3>{/if}
    <div class="links">
      {#each gr.links as l (l.id)}
        <a class="link" href={l.url} target="_blank" rel="noopener noreferrer">
          <span class="lic" class:plain={l.icon_kind === 'image'}><LinkIcon link={l} size={l.icon_kind === 'image' ? 42 : 26} /></span>
          <span class="txt"><b>{l.name}</b>{#if l.description}<span class="small muted desc">{l.description}</span>{/if}</span>
          {#if l.monitor}
            {@const st = status[l.id]}
            <span class="dot" class:up={st?.up} class:down={st && !st.up} title={statusText(st)} aria-label={statusText(st)} role="img"></span>
          {/if}
        </a>
      {/each}
    </div>
  </section>
{/each}

<style>
  .head { margin-bottom: 20px; display: flex; flex-direction: column; gap: 4px; }
  .grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); align-items: start; }
  .app-card { border: 1px solid var(--line); border-radius: var(--r-lg); background: var(--surface); overflow: hidden; }
  .tile { display: flex; align-items: center; gap: 14px; padding: 16px 18px; text-decoration: none; color: var(--ink); }
  .tile:hover { background: var(--surface-2); }
  .sum { display: flex; flex-direction: column; gap: 6px; padding: 0 18px 16px; }
  .sum:empty { display: none; }
  .sum p { margin: 0; }
  .counts { display: flex; flex-wrap: wrap; gap: 4px 12px; color: var(--muted); }
  .line { display: flex; align-items: baseline; gap: 8px; padding: 6px 8px; margin: 0 -8px; border-radius: var(--r-sm, 8px);
    text-decoration: none; color: var(--ink); }
  .line:hover { background: var(--surface-2); }
  .grow { flex: 1; min-width: 0; }
  .ell { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .late { color: var(--danger); }
  .who.mine { color: var(--primary); font-weight: 600; }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .txt b { font-size: 1.05rem; }
  .txt .badge { align-self: flex-start; margin-top: 4px; }
  .note { margin-top: 16px; }
  .sub { margin: 28px 0 12px; }
  .empty-links { display: flex; align-items: center; gap: 12px; padding: 16px; border: 1.5px dashed var(--line-strong); border-radius: var(--r-md);
    text-decoration: none; color: var(--ink); }
  .empty-links:hover { border-color: var(--primary); background: var(--primary-soft); }
  .group + .group { margin-top: 18px; }
  .group h3 { margin: 0 0 8px; font-size: 0.8rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); }
  .links { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
  .link { position: relative; display: flex; align-items: center; gap: 14px; padding: 16px 18px; border: 1px solid var(--line);
    border-radius: var(--r-lg); background: var(--surface); text-decoration: none; color: var(--ink); min-width: 0; min-height: 84px; }
  .link:hover { border-color: var(--line-strong); background: var(--surface-2); }
  .lic { width: 48px; height: 48px; border-radius: 12px; background: var(--primary-soft); color: var(--primary); display: grid;
    place-items: center; flex-shrink: 0; }
  .link .txt b { font-size: 1rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .desc { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.3; }
  .dot { position: absolute; top: 10px; right: 10px; width: 9px; height: 9px; border-radius: 50%; background: var(--line-strong); }
  .dot.up { background: #2f9e44; box-shadow: 0 0 0 3px color-mix(in srgb, #2f9e44 22%, transparent); }
  .dot.down { background: #e03131; box-shadow: 0 0 0 3px color-mix(in srgb, #e03131 22%, transparent); }
  .lic.plain { background: none; }
</style>
