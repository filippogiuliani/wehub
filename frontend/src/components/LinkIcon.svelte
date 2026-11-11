<script>
  // The icon of a link: one of weHub's line icons, an image (dashboard-icons, an address) or a single-colour SVG
  // (mdi-…, si-…) drawn in the current colour. Images come from weHub itself (/api/icons/…), never from elsewhere.
  import Icon from './Icon.svelte';
  let { link, size = 20 } = $props();
  let failed = $state(false);
  $effect(() => { link.icon_url; failed = false; });
</script>

{#if link.icon_kind === 'image' && link.icon_url && !failed}
  <img class="img" src={link.icon_url} alt="" width={size} height={size} loading="lazy" onerror={() => (failed = true)} />
{:else if link.icon_kind === 'mono' && link.icon_url && !failed}
  <span class="mono" style:width="{size}px" style:height="{size}px" style:mask-image="url({link.icon_url})"
    style:-webkit-mask-image="url({link.icon_url})" aria-hidden="true"></span>
  <img class="probe" src={link.icon_url} alt="" onerror={() => (failed = true)} />
{:else}
  <Icon name={link.icon_kind === 'builtin' ? link.icon : 'link'} {size} />
{/if}

<style>
  .img { object-fit: contain; display: block; }
  .mono { display: block; background: currentColor; mask-size: contain; mask-repeat: no-repeat; mask-position: center;
    -webkit-mask-size: contain; -webkit-mask-repeat: no-repeat; -webkit-mask-position: center; }
  .probe { display: none; }
</style>
