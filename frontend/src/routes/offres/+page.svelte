<script lang="ts">
	import { onMount } from 'svelte';

	type Plan = {
		id: string;
		nom: string;
		jour_centimes: number;
		mois_centimes: number;
		an_centimes: number;
		essai_jours: number;
		sur_invitation: boolean;
	};
	type Pricing = { devise: string; plans: Plan[] };

	// Ce que contient chaque plan (les prix, eux, viennent de l'API : PRIX_JOUR_CENTIMES dans .env)
	const details: Record<string, string[]> = {
		free: ['Imports manuels (fichiers)', '1 rapport par mois', '6 derniers mois'],
		premium: [
			'Connecteurs YouTube, Twitch, Instagram',
			'Rapports illimités, tout l’historique',
			'Versions par lecteur, comparaison de phases',
			'Partage avec un soignant'
		],
		dev: ['Tout Premium + fonctions en test', 'Badge Beta testeur', 'Communauté Discord']
	};

	let pricing: Pricing | null = $state(null);
	let error = $state(false);

	onMount(async () => {
		try {
			const res = await fetch('/api/plans');
			if (!res.ok) throw new Error(String(res.status));
			pricing = await res.json();
		} catch {
			error = true;
		}
	});

	const euros = (c: number) =>
		(c / 100).toLocaleString('fr-FR', { style: 'currency', currency: 'EUR' });
</script>

<h1>Offres</h1>
<p class="lead">Supprimer, exporter tes données et retirer un accès reste gratuit, quel que soit le plan.</p>

{#if error}
	<div class="card"><p>Impossible de charger les offres pour l’instant. Vérifie ta connexion.</p></div>
{:else if !pricing}
	<p class="muted">Chargement…</p>
{:else}
	<div class="list">
		{#each pricing.plans as plan (plan.id)}
			<article class="card" class:main={plan.id === 'premium'}>
				<h3>{plan.nom}</h3>
				{#if plan.mois_centimes > 0}
					<p class="price">{euros(plan.mois_centimes)} <span class="muted">/ mois</span></p>
					<p class="muted">
						ou {euros(plan.an_centimes)} / an · soit {euros(plan.jour_centimes)} par jour
					</p>
					{#if plan.essai_jours > 0}<p class="trial">{plan.essai_jours} jours gratuits, sans carte</p>{/if}
				{:else}
					<p class="price">Gratuit</p>
					{#if plan.sur_invitation}<p class="muted">Sur invitation</p>{/if}
				{/if}
				<ul>
					{#each details[plan.id] ?? [] as line (line)}<li>{line}</li>{/each}
				</ul>
			</article>
		{/each}
	</div>
{/if}

<style>
	h3 { margin: 0.2rem 0; font-size: 1.1rem; }
	.price { font-size: 1.5rem; font-weight: 700; margin: 0.3rem 0 0; }
	.price .muted { font-size: 0.95rem; font-weight: 400; }
	.trial {
		display: inline-block;
		font-size: 0.8rem;
		font-weight: 700;
		background: var(--accent-soft);
		color: var(--text);
		padding: 0.1rem 0.6rem;
		border-radius: 999px;
	}
	.main { outline: 2px solid var(--accent); }
	ul { margin: 0.6rem 0 0; padding-left: 1.2rem; }
	.list { display: grid; gap: 0.75rem; }
</style>
