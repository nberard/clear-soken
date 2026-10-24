<script lang="ts">
	import { onMount } from 'svelte';

	// Invite à installer l'appli sur l'écran d'accueil après le scan du QR code.
	type InstallEvent = Event & { prompt: () => Promise<void> };

	let deferred: InstallEvent | null = $state(null);
	let isIos = $state(false);
	let installed = $state(true);

	onMount(() => {
		installed =
			window.matchMedia('(display-mode: standalone)').matches ||
			(navigator as Navigator & { standalone?: boolean }).standalone === true;
		isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
		const onPrompt = (e: Event) => {
			e.preventDefault();
			deferred = e as InstallEvent;
		};
		window.addEventListener('beforeinstallprompt', onPrompt);
		return () => window.removeEventListener('beforeinstallprompt', onPrompt);
	});

	async function install() {
		await deferred?.prompt();
		deferred = null;
	}
</script>

{#if !installed && (deferred || isIos)}
	<div class="card install">
		<strong>Garder Clear Soken sur ton téléphone</strong>
		{#if deferred}
			<p class="muted">Ajoute l’appli à ton écran d’accueil, elle marche même sans réseau.</p>
			<button class="btn" onclick={install}>Installer</button>
		{:else}
			<p class="muted">
				Dans Safari, touche <b>Partager</b> puis <b>« Sur l’écran d’accueil »</b>.
			</p>
		{/if}
	</div>
{/if}

<style>
	.install { background: var(--primary-soft); border-color: transparent; }
	.install .btn { margin-top: 0.5rem; }
</style>
