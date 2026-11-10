<script>
  // Bring into weHub the members, people and children the apps already have. Nothing is deleted in the apps:
  // each one then recognises its own family and people (and keeps all their data).
  import { get, post } from '../lib/api.js';
  import { showError, toast } from '../lib/store.svelte.js';
  import { t } from '../lib/i18n.svelte.js';
  import Icon from '../components/Icon.svelte';
  import AppIcon from '../components/AppIcon.svelte';

  let data = $state(null);
  let loading = $state(false);
  let members = $state([]); // chosen emails
  let groups = $state([]);
  let done = $state(null);

  async function load(selection = null, merges = null) {
    loading = true;
    try {
      const params = new URLSearchParams();
      if (selection) for (const [k, v] of Object.entries(selection)) params.set(k, v ?? 'none');
      if (merges) for (const [k, v] of Object.entries(merges)) if (v.length) params.set('merge_' + k, v.join(','));
      const q = params.toString() ? '?' + params : '';
      data = await get('/import/preview' + q);
      members = data.members.filter((m) => !m.exists).map((m) => m.email);
      groups = data.groups.map((g) => ({ ...g, target: g.target ?? '' }));
    } catch (e) { showError(e); } finally { loading = false; }
  }
  load();

  const selected = () => Object.fromEntries(data.apps.filter((a) => a.ok).map((a) => [a.id, a.selected]));
  const merging = () => Object.fromEntries(data.apps.filter((a) => a.ok).map((a) => [a.id, a.merge ?? []]));
  function choose(appId, value) {
    load({ ...selected(), [appId]: value === '' ? null : Number(value) }, { ...merging(), [appId]: [] });
  }
  function toggleMerge(appId, id) {
    const cur = merging()[appId];
    load(selected(), { ...merging(), [appId]: cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id] });
  }
  const familyName = (a, id) => a.families.find((f) => f.local_id === id);
  async function apply() {
    try {
      done = await post('/import/apply', {
        selected: selected(),
        merge: merging(),
        members: data.members.filter((m) => members.includes(m.email)),
        groups: groups.map((g) => ({ ...g, target: g.target === '' ? null : g.target })),
      });
      toast(t('import.done'));
      await load();
    } catch (e) { showError(e); }
  }
  const mergeErrors = $derived(done ? Object.entries(done.merges ?? {}).filter(([, r]) => r.error) : []);
  const mergeDone = $derived(done ? Object.entries(done.merges ?? {}).filter(([, r]) => !r.error) : []);
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
            <AppIcon id={a.id} size={34} />
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
          {#if a.ok && a.merge_candidates?.length}
            <li class="merge">
              <div class="grow stack small-gap">
                <span class="small">{t('import.merge_intro')}</span>
                {#each a.merge_candidates as id (id)}
                  {@const f = familyName(a, id)}
                  <label class="row">
                    <input type="checkbox" checked={a.merge.includes(id)} onchange={() => toggleMerge(a.id, id)} disabled={loading} />
                    <span>{t('import.merge_into', { name: f.name, members: f.members.join(', ') })}</span>
                  </label>
                {/each}
                <span class="tiny muted">{t('import.merge_note')}</span>
              </div>
            </li>
          {/if}
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
    {#if done}<p class="small">{t('import.result', done)}</p>
      {#each mergeDone as [appId, r] (appId)}<p class="small">{t('import.merged', { app: appId, n: r.families ?? 0 })}</p>{/each}
      {#each mergeErrors as [appId, r] (appId)}<p class="small err">{t('import.merge_failed', { app: appId, error: r.error })}</p>{/each}
    {/if}
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
  .merge { padding-left: 44px !important; background: var(--surface-2); border-radius: var(--r-sm); }
  .merge label { gap: 8px; align-items: flex-start; }
</style>
