<script>
  // The family: members (by email, they sign in with Pocket ID), which apps each may use, people without an account.
  import { del, get, post, put } from '../lib/api.js';
  import { app, loadMe, showError, toast } from '../lib/store.svelte.js';
  import { t } from '../lib/i18n.svelte.js';
  import { fmtDate } from '../lib/date.js';
  import LanguageSwitch from '../components/LanguageSwitch.svelte';
  import Icon from '../components/Icon.svelte';

  let { onlogout } = $props();
  let family = $state(null);
  let familyName = $state('');
  let userName = $state(app.me.user.name);
  const admin = $derived(family?.role === 'admin');

  async function load() {
    try { family = await get('/family'); familyName = family.name; } catch (e) { showError(e); }
  }
  load();
  async function run(fn, message) {
    try { const r = await fn(); if (r?.members) family = r; else await load(); if (message) toast(message); return true; }
    catch (e) { showError(e); return false; }
  }

  // --- Family
  const rename = () => run(() => put('/family', { name: familyName }), t('common.saved'));

  // --- Members
  let adding = $state(null); // { name, email, role, apps: [] }
  function startAdd() { adding = { name: '', email: '', role: 'member', apps: family.apps.map((a) => a.id) }; }
  async function addMember(e) {
    e.preventDefault();
    if (await run(() => post('/family/members', adding), t('members.added', { name: adding.name }))) adding = null;
  }
  async function toggleApp(m, appId) {
    const access = { ...m.access };
    if (access[appId]) delete access[appId]; else access[appId] = 'full';
    await run(() => put(`/family/members/${m.id}`, { apps: access }));
  }
  async function setLevel(m, appId, level) {
    await run(() => put(`/family/members/${m.id}`, { apps: { ...m.access, [appId]: level } }));
  }
  const setRole = (m, role) => run(() => put(`/family/members/${m.id}`, { role }), t('common.saved'));
  async function removeMember(m) {
    if (!confirm(m.me ? t('members.confirm_leave') : t('members.confirm_remove', { name: m.name }))) return;
    if (await run(() => del(`/family/members/${m.id}`)) && m.me) { await loadMe(); location.hash = '#/home'; }
  }

  // --- People
  let editing = $state(null); // { id?, name, birth_date, kind, member }
  async function savePerson(e) {
    e.preventDefault();
    const body = { name: editing.name, birth_date: editing.birth_date || null, kind: editing.kind };
    if (await run(() => (editing.id ? put(`/family/people/${editing.id}`, body) : post('/family/people', body)), t('common.saved'))) editing = null;
  }
  async function removePerson(p) {
    if (!confirm(t('people.confirm_delete', { name: p.name }))) return;
    await run(() => del(`/family/people/${p.id}`));
  }

  // --- Account
  const saveName = async () => { if (await run(() => put('/account', { name: userName }), t('common.saved'))) await loadMe(); };
  const saveLanguage = (l) => run(() => put('/account', { language: l }));
  async function signOutElsewhere() {
    if (!confirm(t('security.confirm_others'))) return;
    try { await post('/account/sessions/revoke'); toast(t('security.others_out')); } catch (e) { showError(e); }
  }
  const seenAt = (s) => (s ? fmtDate(s.slice(0, 10)) + ' ' + s.slice(11, 16) : t('apps.never'));
</script>

<header class="head"><h1>{t('nav.family')}</h1><p class="muted">{t('family.subtitle')}</p></header>

{#if family}
<div class="stack big">
  <section class="card stack">
    <h2>{t('family.family')}</h2>
    {#if admin}
      <form class="row" onsubmit={(e) => { e.preventDefault(); rename(); }}>
        <input class="input grow" bind:value={familyName} maxlength="80" aria-label={t('family.name')} />
        <button class="btn" disabled={!familyName.trim() || familyName === family.name}>{t('common.save')}</button>
      </form>
    {:else}<p><b>{family.name}</b></p>{/if}
  </section>

  <!-- Members and their apps -->
  <section class="card stack">
    <div class="spread"><h2 class="ic"><Icon name="family" />{t('members.title')}</h2>
      {#if admin && !adding}<button class="btn soft sm" onclick={startAdd}><Icon name="plus" size={15} />{t('members.add')}</button>{/if}</div>
    <p class="small muted">{t('members.explain')}</p>
    {#if adding}
      <form class="invite stack" onsubmit={addMember}>
        <div class="grid2">
          <input class="input" bind:value={adding.name} maxlength="80" placeholder={t('common.name')} aria-label={t('common.name')} required />
          <input class="input" type="email" bind:value={adding.email} placeholder={t('members.email')} aria-label={t('members.email')} required />
        </div>
        <div class="chips">
          {#each family.apps as a (a.id)}
            <label class="chip" class:on={adding.apps.includes(a.id)}>
              <input type="checkbox" class="sr-only" checked={adding.apps.includes(a.id)}
                     onchange={() => (adding.apps = adding.apps.includes(a.id) ? adding.apps.filter((x) => x !== a.id) : [...adding.apps, a.id])} />
              {a.name}</label>
          {/each}
          <label class="chip" class:on={adding.role === 'admin'}>
            <input type="checkbox" class="sr-only" checked={adding.role === 'admin'} onchange={() => (adding.role = adding.role === 'admin' ? 'member' : 'admin')} />
            {t('members.role_admin')}</label>
        </div>
        <p class="tiny">{t('members.add_note')}</p>
        <div class="row"><button class="btn primary">{t('members.add')}</button><button type="button" class="btn ghost" onclick={() => (adding = null)}>{t('common.cancel')}</button></div>
      </form>
    {/if}
    <ul class="list">
      {#each family.members as m (m.id)}
        <li class="member">
          <div class="who">
            <b>{m.name}</b>{#if m.me}<span class="muted small">&nbsp;({t('family.you')})</span>{/if}
            <div class="tiny muted email">{m.email} · {m.role === 'admin' ? t('members.role_admin') : t('members.role_member')}
              {#if !m.signed_in} · {t('members.not_signed_in')}{/if}</div>
          </div>
          <div class="apps">
            {#each family.apps as a (a.id)}
              {#if admin}
                <button class="chip" class:on={!!m.access[a.id]} onclick={() => toggleApp(m, a.id)} aria-pressed={!!m.access[a.id]}
                        title={m.access[a.id] ? t('apps.revoke', { app: a.name }) : t('apps.grant', { app: a.name })}>{a.name}</button>
                {#if m.access[a.id] && a.id === 'patrack'}
                  <select class="level" value={m.access[a.id]} onchange={(e) => setLevel(m, a.id, e.currentTarget.value)} aria-label={t('access.level')}>
                    <option value="full">{t('access.full')}</option><option value="limited">{t('access.limited')}</option>
                  </select>
                {/if}
              {:else if m.access[a.id]}<span class="chip">{a.name}</span>{/if}
            {/each}
          </div>
          <div class="acts">
            {#if admin && !m.me}
              <select class="level" value={m.role} onchange={(e) => setRole(m, e.currentTarget.value)} aria-label={t('members.role')}>
                <option value="member">{t('members.role_member')}</option><option value="admin">{t('members.role_admin')}</option>
              </select>
            {/if}
            {#if (admin && !m.me) || (m.me && family.members.length > 1)}
              <button class="btn icon sm ghost" onclick={() => removeMember(m)} aria-label={m.me ? t('members.leave') : t('members.remove', { name: m.name })}>
                <Icon name={m.me ? 'logout' : 'trash'} size={15} /></button>
            {/if}
          </div>
        </li>
      {/each}
    </ul>
    <p class="tiny muted">{t('access.limited_note')}</p>
  </section>

  <!-- People -->
  <section class="card stack">
    <div class="spread"><h2 class="ic"><Icon name="people" />{t('people.title')}</h2>
      {#if !editing}<button class="btn soft sm" onclick={() => (editing = { name: '', birth_date: '', kind: 'child' })}><Icon name="plus" size={15} />{t('people.add')}</button>{/if}</div>
    <p class="small muted">{t('people.explain')}</p>
    {#if editing}
      <form class="invite stack" onsubmit={savePerson}>
        <div class="grid2">
          <input class="input" bind:value={editing.name} maxlength="60" placeholder={t('common.name')} aria-label={t('common.name')}
                 disabled={editing.member} required={!editing.member} />
          <input class="input" type="date" bind:value={editing.birth_date} aria-label={t('people.birth_date')} />
        </div>
        <div class="seg">
          <button type="button" class:on={editing.kind === 'child'} onclick={() => (editing.kind = 'child')}>{t('people.child')}</button>
          <button type="button" class:on={editing.kind === 'adult'} onclick={() => (editing.kind = 'adult')}>{t('people.adult')}</button>
        </div>
        <p class="tiny">{t('people.kind_note')}</p>
        <div class="row"><button class="btn primary">{t('common.save')}</button><button type="button" class="btn ghost" onclick={() => (editing = null)}>{t('common.cancel')}</button></div>
      </form>
    {/if}
    <ul class="list">
      {#each family.people as p (p.id)}
        <li>
          <div class="grow">
            <b>{p.name}</b>
            <div class="tiny muted">{p.user_id ? t('people.member') : p.kind === 'child' ? t('people.child') : t('people.adult')}
              {#if p.birth_date} · {t('people.born', { date: fmtDate(p.birth_date) })}{/if}</div>
          </div>
          <button class="btn icon sm ghost" onclick={() => (editing = { id: p.id, name: p.name, birth_date: p.birth_date ?? '', kind: p.kind, member: !!p.user_id })}
                  aria-label={t('people.edit', { name: p.name })}><Icon name="edit" size={15} /></button>
          {#if !p.user_id}<button class="btn icon sm ghost" onclick={() => removePerson(p)} aria-label={t('people.delete', { name: p.name })}><Icon name="trash" size={15} /></button>{/if}
        </li>
      {/each}
    </ul>
  </section>

  {#if admin}
    <section class="card stack">
      <h2 class="ic"><Icon name="sync" />{t('apps.title')}</h2>
      <ul class="list">
        {#each family.apps as a (a.id)}
          <li><span class="grow"><b>{a.name}</b> <span class="tiny muted">{a.url}</span></span>
            <span class="small muted">{t('apps.last_sync', { when: seenAt(family.seen[a.id]) })}</span></li>
        {/each}
      </ul>
      <p class="tiny muted">{t('apps.explain')}</p>
    </section>
  {/if}

  <!-- Account -->
  <section class="card stack">
    <h2>{t('account.title')}</h2>
    <form class="row" onsubmit={(e) => { e.preventDefault(); saveName(); }}>
      <input class="input grow" bind:value={userName} maxlength="80" aria-label={t('auth.your_name')} />
      <button class="btn" disabled={!userName.trim() || userName === app.me.user.name}>{t('common.save')}</button>
    </form>
    <div class="spread"><span class="small email">{app.me.user.email}</span></div>
    <div class="spread"><span class="small">{t('common.language')}</span><LanguageSwitch onchoose={saveLanguage} /></div>
    <div class="row wrap">
      <button class="btn" onclick={() => onlogout()}>{t('account.sign_out')}</button>
      <button class="btn ghost sm" onclick={signOutElsewhere}>{t('security.sign_out_others')}</button>
    </div>
  </section>
</div>
{/if}

<style>
  .head { margin-bottom: 18px; }
  .big { gap: 14px; }
  .ic { display: flex; align-items: center; gap: 8px; }
  .list { list-style: none; margin: 0; padding: 0; }
  .list li { display: flex; align-items: center; gap: 8px; padding: 10px 0; border-bottom: 1px solid var(--line); }
  .list li:last-child { border: 0; }
  .member { flex-wrap: wrap; }
  .who { flex: 1 1 200px; min-width: 0; }
  .apps { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .acts { display: flex; gap: 4px; align-items: center; }
  .level { width: auto; max-width: 150px; min-height: 30px; border: 1px solid var(--line-strong); border-radius: var(--r-xs); background: var(--surface); font-size: 0.8rem; padding: 0 6px; }
  .email { overflow-wrap: anywhere; }
  .invite { padding: 12px; border-radius: var(--r-md); background: var(--primary-soft); }
  .grid2 { display: grid; gap: 8px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  @media (max-width: 520px) { .grid2 { grid-template-columns: minmax(0, 1fr); } }
  label.chip { cursor: pointer; background: var(--surface); }
  label.chip.on { background: var(--primary); color: var(--primary-ink); border-color: var(--primary); }
</style>
