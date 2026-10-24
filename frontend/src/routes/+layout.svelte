<script lang="ts">
	import '#lib/theme.css';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	const nav = [
		{ href: '/', label: 'Accueil', icon: '🏡' },
		{ href: '/humeur/', label: 'Humeur', icon: '🌤️' },
		{ href: '/respirer/', label: 'Respirer', icon: '🫧' },
		{ href: '/echelons/', label: 'Échelons', icon: '🪜' },
		{ href: '/ressources/', label: 'Ressources', icon: '🤝' }
	];
</script>

<svelte:head>
	<title>Clear Soken</title>
</svelte:head>

<a class="help" href="/aide/" aria-label="Besoin d’aide maintenant">Besoin d’aide</a>

<main>
	{@render children()}
</main>

<nav aria-label="Navigation principale">
	{#each nav as item (item.href)}
		<a href={item.href} aria-current={page.url.pathname === item.href ? 'page' : undefined}>
			<span aria-hidden="true">{item.icon}</span>
			{item.label}
		</a>
	{/each}
</nav>

<style>
	main {
		max-width: 560px;
		margin: 0 auto;
		padding: calc(env(safe-area-inset-top) + 3.5rem) 16px
			calc(var(--nav-h) + env(safe-area-inset-bottom) + 1.5rem);
	}

	.help {
		position: fixed;
		top: calc(env(safe-area-inset-top) + 0.75rem);
		right: 16px;
		z-index: 10;
		background: var(--danger);
		color: #fff;
		font-weight: 700;
		font-size: 0.9rem;
		text-decoration: none;
		padding: 0.45rem 0.9rem;
		border-radius: 999px;
	}

	nav {
		position: fixed;
		inset: auto 0 0 0;
		display: grid;
		grid-template-columns: repeat(5, 1fr);
		height: calc(var(--nav-h) + env(safe-area-inset-bottom));
		padding-bottom: env(safe-area-inset-bottom);
		background: var(--surface);
		border-top: 1px solid var(--border);
	}

	nav a {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: 2px;
		font-size: 0.72rem;
		color: var(--text-soft);
		text-decoration: none;
	}
	nav a span { font-size: 1.35rem; }
	nav a[aria-current='page'] { color: var(--primary); font-weight: 700; }
</style>
