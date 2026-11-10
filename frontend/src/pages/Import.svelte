<script>
  // Bring into weHub the members, people and children the apps already have. Nothing is deleted in the apps:
  // each one then recognises its own family and people (and keeps all their data).
  import { get, post } from '../lib/api.js';
  import { showError, toast } from '../lib/store.svelte.js';
  import { t } from '../lib/i18n.svelte.js';
  import Icon from '../components/Icon.svelte';

  let data = $state(null);
  let loading = $state(false);
  let members = $state([]); // chosen emails
  let groups = $state([]);
  let done = $state(null);

  async function load(selection = null) {
    loading = true;
    try {
      const q = selection ? '?' + new URLSearchParams(Object.entries(selection).map(([k, v]) => [k, v ?? 'none'])) : '';
      data = await get('/import/preview' + q);
      members = data.members.filter((m) => !m.exists).map((m) => m.email);
      groups = data.groups.map((g) => ({ ...g, target: g.target ?? '' }));
    } catch (e) { showError(e); } finally { loading = false; }
  }
  load();

  const selected = () => Object.fromEntries(data.apps.filter((a) => a.ok).map((a) => [a.id, a.selected]));
  function choose(appId, value) {
    load({ ...selected(), [appId]: value === '' ? null : Number(value) });
  }
  async function apply() {
    try {
      done = await post('/import/apply', {
        selected: selected(),
        members: data.members.filter((m) => members.includes(m.email)),
        groups: groups.map((g) => ({ ...g, target: g.target === '' ? null : g.target })),
      });
      toast(t('import.done'));
      await load();
    } catch (e) { showError(e); }
  }
</script>

<header class="head"><h1>{t('nav.import')}</h1><p class="muted">{t('import.subtitle')}</p></header>

{#if !data}
  <p class="muted">{loading ? t('common.wait') : ''}</p>
{:else}
  <div class="stack big">
    <section class="card stack">
      <h2>{t('import.step_families')}</h2>
      <ul class="list">
        {#each data.apps as a (a.id)}
          <li>
            <span class="ic"><Icon name={a.id} size={20} /></span>
            <div class="grow">
              <b>{a.name}</b>
              {#if !a.ok}<div class="small err">{t('import.unreachable', { reason: a.error })}</div>
              {:else if !a.families.length}<div class="small muted">{t('import.no_families')}</div>{/if}
            </div>
            {#if a.ok && a.families.length}
              <select class="input sel" value={a.selected ?? ''} onchange={(e) => choose(a.id, e.currentTarget.value)} aria-label={a.name}>
                <option value="">{t('import.skip_app')}</option>
                {#each a.families as f (f.local_id)}
                  <option value={f.local_id}>{f.name} – {f.members.join(', ')}</option>
                {/each}
              </select>
            {/if}
          </li>
        {/each}
      </ul>
    </section>

    {#if data.members.length}
      <section class="card stack">
        <h2>{t('import.step_members')}</h2>
        <p class="small muted">{t('import.members_note')}</p>
        <ul class="list">
          {#each data.members as m (m.email)}
            <li>
              <label class="row grow">
                <input type="checkbox" checked={m.exists || members.includes(m.email)} disabled={m.exists}
                       onchange={() => (members = members.includes(m.email) ? members.filter((x) => x !== m.email) : [...members, m.email])} />
                <span class="grow"><b>{m.name}</b> <span class="tiny muted">{m.email} · {m.apps.join(', ')}</span></span>
              </label>
              <span class="tiny muted">{m.exists ? t('import.already') : m.role === 'admin' ? t('members.role_admin') : t('members.role_member')}</span>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    {#if groups.length}
      <section class="card stack">
        <h2>{t('import.step_people')}</h2>
        <p class="small muted">{t('import.people_note')}</p>
        <ul class="list">
          {#each groups as g, i (g.key)}
            <li class="group">
              <div class="grow stack small-gap">
                <div class="row wrap">
                  <input class="input name" bind:value={groups[i].name} maxlength="60" aria-label={t('common.name')} disabled={!!g.target && g.target !== 'skip'} />
                  <select class="input sel" bind:value={groups[i].kind} aria-label={t('people.kind')}>
                    <option value="child">{t('people.child')}</option><option value="adult">{t('people.adult')}</option>
                  </select>
                  <input class="input date" type="date" bind:value={groups[i].birth_date} aria-label={t('people.birth_date')} />
                </div>
                <div class="chips">
                  {#each g.sources as s (s.app + s.local_id)}<span class="chip tiny">{s.app}: {s.name}</span>{/each}
                </div>
              </div>
              <select class="input sel" bind:value={groups[i].target} aria-label={t('import.target')}>
                <option value="">{t('import.new_person')}</option>
                {#each data.hub_people as h (h.id)}<option value={h.id}>{t('import.same_as', { name: h.name })}</option>{/each}
                <option value="skip">{t('import.dont_import')}</option>
              </select>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <div class="row wrap">
      <button class="btn primary" onclick={apply} disabled={loading}><Icon name="check" size={16} />{t('import.apply')}</button>
      <button class="btn ghost" onclick={() => load()} disabled={loading}><Icon name="refresh" size={15} />{t('import.reload')}</button>
    </div>
    {#if done}<p class="small">{t('import.result', done)}</p>{/if}
    <p class="tiny muted">{t('import.after')}</p>
  </div>
{/if}

<style>
  .head { margin-bottom: 18px; }
  .big { gap: 14px; }
  .list { list-style: none; margin: 0; padding: 0; }
  .list li { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--line); }
  .list li:last-child { border: 0; }
  .group { align-items: flex-start !important; flex-wrap: wrap; }
  .ic { width: 34px; height: 34px; border-radius: 9px; background: var(--primary); color: var(--primary-ink); display: grid; place-items: center; }
  .sel { width: auto; min-height: 36px; max-width: 100%; }
  .name { width: 180px; min-height: 36px; }
  .date { width: auto; min-height: 36px; }
  .small-gap { gap: 6px; }
  .err { color: var(--danger); }
</style>
