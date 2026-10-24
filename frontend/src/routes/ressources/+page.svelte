<script lang="ts">
	import { onMount } from 'svelte';

	type Resource = {
		id: string;
		name: string;
		kind: string;
		description: string;
		city: string | null;
		phone: string | null;
		url: string | null;
	};

	let all: Resource[] = $state([]);
	let query = $state('');
	let error = $state(false);
	let loading = $state(true);

	onMount(async () => {
		try {
			const res = await fetch('/api/resources');
			if (!res.ok) throw new Error(String(res.status));
			all = await res.json();
		} catch {
			error = true;
		} finally {
			loading = false;
		}
	});

	let list = $derived.by(() => {
		const q = query.trim().toLowerCase();
		if (!q) return all;
		return all.filter((r) =>
			[r.name, r.kind, r.description, r.city ?? ''].some((f) => f.toLowerCase().includes(q))
		);
	});
</script>

<h1>Après la clinique</h1>
<p class="lead">Des lieux et des personnes pour ne pas rester seul·e.</p>

<input bind:value={query} type="search" placeholder="Chercher : ville, GEM, écoute…" aria-label="Chercher une ressource" />

{#if loading}
	<p class="muted">Chargement…</p>
{:else if error}
	<div class="card"><p>Impossible de charger les ressources pour l’instant. Vérifie ta connexion.</p></div>
{:else if list.length === 0}
	<p class="muted">Aucun résultat.</p>
{/if}

<div class="list">
	{#each list as r (r.id)}
		<article class="card">
			<span class="kind">{r.kind}</span>
			<h3>{r.name}</h3>
			<p>{r.description}</p>
			{#if r.city}<p class="muted">📍 {r.city}</p>{/if}
			<div class="actions">
				{#if r.phone}<a class="btn secondary" href="tel:{r.phone.replace(/\s/g, '')}">📞 {r.phone}</a>{/if}
				{#if r.url}<a class="btn secondary" href={r.url} target="_blank" rel="noopener noreferrer">Site</a>{/if}
			</div>
		</article>
	{/each}
</div>

<style>
	input { margin-bottom: 1rem; }
	h3 { margin: 0.2rem 0; font-size: 1.05rem; }
	.kind {
		display: inline-block;
		font-size: 0.75rem;
		font-weight: 700;
		background: var(--accent-soft);
		color: var(--text);
		padding: 0.1rem 0.6rem;
		border-radius: 999px;
	}
	.actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem; }
	.actions .btn { min-height: 40px; font-size: 0.9rem; }
</style>
