<script>
  import { post, setUnauthorizedHandler } from './lib/api.js';
  import { app, loadMe, showError } from './lib/store.svelte.js';
  import { setLanguage, t } from './lib/i18n.svelte.js';
  import Toast from './components/Toast.svelte';
  import Icon from './components/Icon.svelte';
  import LanguageSwitch from './components/LanguageSwitch.svelte';
  import Login from './pages/Login.svelte';
  import Signup from './pages/Signup.svelte';
  import Privacy from './pages/Privacy.svelte';
  import Home from './pages/Home.svelte';
  import Family from './pages/Family.svelte';
  import Import from './pages/Import.svelte';
  import Links from './pages/Links.svelte';

  const PUBLIC = ['login', 'signup', 'privacy'];
  let status = $state('loading');
  let route = $state(readHash());

  function readHash() {
    const [path, query = ''] = location.hash.replace(/^#\/?/, '').split('?');
    const [name = '', param = ''] = path.split('/');
    return { name, param: decodeURIComponent(param), query: new URLSearchParams(query) };
  }
  $effect(() => {
    const onHash = () => { route = readHash(); window.scrollTo(0, 0); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  });

  const authenticated = $derived(!!app.me?.authenticated);
  const admin = $derived(app.me?.role === 'admin');
  const nav = $derived(['home', 'family', ...(admin ? ['links', 'import'] : [])]);
  const page = $derived.by(() => {
    if (!authenticated) return PUBLIC.includes(route.name) ? route.name : 'login';
    if (route.name === 'privacy') return 'privacy';
    return nav.includes(route.name) ? route.name : 'home';
  });

  setUnauthorizedHandler(() => { if (app.me) app.me = { ...app.me, authenticated: false }; });

  async function start() {
    try {
      const me = await loadMe();
      if (me.authenticated && me.user.language) setLanguage(me.user.language);
      status = 'ready';
    } catch (e) { showError(e); status = 'error'; }
  }
  start();

  async function logout() {
    await post('/logout').catch(() => {});
    await loadMe().catch(() => {});
    location.hash = '#/login';
  }
  const ICONS = { home: 'apps', family: 'family', links: 'link', import: 'imports' };
</script>

{#if status === 'loading'}
  <main class="center"><img class="pulse" src="/icon.svg" alt={t('common.wait')} width="56" height="56" /></main>
{:else if status === 'error'}
  <main class="center"><p class="empty">{t('error.server')}<br /><button class="btn soft" onclick={start}>{t('common.retry')}</button></p></main>
{:else if !authenticated || page === 'privacy'}
  <div class="public-language"><LanguageSwitch /></div>
  {#if page === 'signup'}<Signup ondone={start} external={!!route.query.get('external')} />
  {:else if page === 'privacy'}<Privacy />
  {:else}<Login ondone={start} initialError={route.query.get('error') ?? ''} />{/if}
{:else}
  <div class="shell">
    <nav class="nav" aria-label={t('nav.sections')}>
      <a class="logo" href="#/home"><img src="/icon.svg" alt="" width="28" height="28" /><span>weHub</span></a>
      {#each nav as id (id)}
        <a href="#/{id}" class:on={page === id} aria-current={page === id ? 'page' : undefined}>
          <span class="ico"><Icon name={ICONS[id]} size={22} /></span>
          <span class="lbl">{t('nav.' + id)}</span>
        </a>
      {/each}
      <button class="logout" onclick={logout} title={app.me.user.email}>
        <span class="ico"><Icon name="logout" size={20} /></span><span class="lbl">{t('account.sign_out')}</span>
      </button>
    </nav>
    <main class="main">
      {#key page + ':' + app.me.family?.id}
        {#if page === 'family'}<Family onlogout={logout} />
        {:else if page === 'import'}<Import />
        {:else if page === 'links'}<Links />
        {:else}<Home />{/if}
      {/key}
    </main>
  </div>
{/if}
<Toast />

<style>
  .center { min-height: 100dvh; display: grid; place-items: center; padding: 16px; }
  .pulse { border-radius: 12px; animation: pulse 1s ease-in-out infinite alternate; }
  @keyframes pulse { to { opacity: 0.5; } }
  .public-language { position: absolute; top: 12px; right: 12px; z-index: 5; }
  .main { padding: 20px 16px calc(var(--nav-h) + 40px + env(safe-area-inset-bottom)); max-width: 1000px; margin: 0 auto; }
  .nav { position: fixed; z-index: 50; left: 0; right: 0; bottom: 0; height: calc(var(--nav-h) + env(safe-area-inset-bottom));
    padding: 6px 6px env(safe-area-inset-bottom); display: flex; background: var(--surface); border-top: 1px solid var(--line); }
  .logo { display: none; }
  .nav a:not(.logo), .logout { flex: 1; min-width: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
    text-decoration: none; color: var(--muted); font-weight: 500; font-size: 0.7rem; border-radius: var(--r-sm); border: 0; background: none;
    font-family: inherit; cursor: pointer; -webkit-tap-highlight-color: transparent; }
  .lbl { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ico { width: 22px; height: 22px; display: grid; place-items: center; }
  .nav a.on { color: var(--primary); }
  @media (min-width: 900px) {
    .shell { display: grid; grid-template-columns: 220px 1fr; }
    .nav { position: sticky; top: 0; height: 100dvh; flex-direction: column; gap: 2px; padding: 20px 12px; border-top: 0; border-right: 1px solid var(--line); }
    .logo { display: flex; align-items: center; gap: 10px; padding: 4px 10px 18px; text-decoration: none; color: var(--ink); font-size: 1.15rem; font-weight: 650; }
    .logo img { border-radius: 7px; }
    .nav a:not(.logo), .logout { flex: none; flex-direction: row; justify-content: flex-start; gap: 10px; padding: 9px 12px; font-size: 0.92rem; }
    .nav a:not(.logo) .ico, .logout .ico { width: 18px; height: 18px; }
    .nav a.on { background: var(--primary-soft); }
    .logout { margin-top: auto; }
    .logout:hover { color: var(--ink); background: var(--surface-2); }
    .main { padding: 32px 32px 48px; width: 100%; }
  }
</style>
