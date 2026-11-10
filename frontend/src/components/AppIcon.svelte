<script>
  // The app's own icon (the same one it shows in its tab and on the phone), a generic one for other apps
  import Icon from './Icon.svelte';
  let { id, size = 48 } = $props();
  const KNOWN = ['dotrack', 'eatrack', 'patrack'];
</script>

{#if KNOWN.includes(id)}
  <img src="/apps/{id}.svg" alt="" width={size} height={size} style="border-radius: {Math.round(size * 0.22)}px" />
{:else}
  <span class="generic" style="width: {size}px; height: {size}px; border-radius: {Math.round(size * 0.22)}px"><Icon name="apps" size={Math.round(size / 2)} /></span>
{/if}

<style>
  img { display: block; flex-shrink: 0; }
  .generic { display: grid; place-items: center; flex-shrink: 0; background: var(--primary); color: var(--primary-ink); }
</style>
