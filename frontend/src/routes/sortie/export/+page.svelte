<script lang="ts">
	import { onMount } from 'svelte';
	import { load, MOODS, type MoodEntry } from '#lib/storage.ts';
	import { CADRES, ENTOURAGES, ENVIES, PLAN_VIDE, finSejour, manques, type PlanSortie } from '#lib/sortie.ts';

	let plan: PlanSortie = $state(structuredClone(PLAN_VIDE));
	let humeurs: MoodEntry[] = $state([]);
	let avecHumeur = $state(true);
	let avecNotes = $state(false);
	let avecTraitement = $state(true);

	onMount(() => {
		plan = { ...structuredClone(PLAN_VIDE), ...load<PlanSortie>('sortie', PLAN_VIDE) };
		humeurs = load<MoodEntry[]>('moods', []);
	});

	const jour = (iso: string) =>
		iso ? new Date(iso.length === 10 ? iso + 'T12:00:00' : iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' }) : '—';
	const court = (iso: string) => new Date(iso + 'T12:00:00').toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
	const libelle = (liste: readonly { id: string; label: string }[], id: string) => liste.find((x) => x.id === id)?.label ?? id;

	// Humeur des 30 derniers jours : nombre de notes par niveau et moyenne
	let recentes = $derived(humeurs.filter((h) => Date.now() - new Date(h.at).getTime() < 30 * 864e5));
	let moyenne = $derived(recentes.length ? recentes.reduce((s, h) => s + h.mood, 0) / recentes.length : null);
	let reste = $derived(manques(plan));
</script>

<div class="no-print card options">
	<p><strong>Ce que le document contient</strong> (rien n’est envoyé : imprime-le ou enregistre-le en PDF, puis partage-le toi-même)</p>
	<label><input type="checkbox" bind:checked={avecTraitement} /> Mon traitement</label>
	<label><input type="checkbox" bind:checked={avecHumeur} /> Mon humeur des 30 derniers jours</label>
	{#if avecHumeur}<label class="sub"><input type="checkbox" bind:checked={avecNotes} /> avec mes notes écrites</label>{/if}
	<button class="btn" onclick={() => window.print()}>Imprimer ou enregistrer en PDF</button>
	<a class="btn secondary" href="/sortie/">Modifier le plan</a>
</div>

<article class="doc">
	<h1>Plan de sortie</h1>
	<p class="muted">Sortie le {jour(plan.sortieLe)} · document préparé le {jour(new Date().toISOString())} avec Clear Soken</p>
	{#if reste.length}<p class="alerte">À compléter : {reste.join(', ')}.</p>{/if}

	{#if plan.objectifs}
		<h2>Ce que j’attends de cette période</h2>
		<p>{plan.objectifs}</p>
	{/if}

	<h2>Séjours</h2>
	{#if plan.sejours.length}
		<div class="scroll"><table>
			<thead><tr><th>Dates</th><th>Lieu</th><th>Pour</th><th>Avec qui</th><th>Réservé</th></tr></thead>
			<tbody>
				{#each plan.sejours as s (s.id)}
					<tr>
						<td class="dates">{court(s.debut)} → {court(finSejour(s))}</td>
						<td>{s.lieu || libelle(CADRES, s.cadre)}</td>
						<td>{s.envies.map((e) => libelle(ENVIES, e)).join(', ')}</td>
						<td>{libelle(ENTOURAGES, s.entourage)}</td>
						<td>{s.reserve ? 'oui' : 'non'}</td>
					</tr>
				{/each}
			</tbody>
		</table></div>
	{:else}
		<p class="muted">Aucun séjour prévu.</p>
	{/if}

	<h2>Suivi</h2>
	{#if plan.rdv.length}
		<ul>{#each plan.rdv as r (r.id)}<li>{r.qui || 'Rendez-vous'}{r.quand ? ` — ${jour(r.quand)}` : ' — date à fixer'}{r.comment ? ` (${r.comment})` : ''}</li>{/each}</ul>
	{:else}
		<p class="muted">Aucun rendez-vous noté.</p>
	{/if}
	<p>Personne de confiance : {plan.confiance.nom || '—'} {plan.confiance.tel ? `· ${plan.confiance.tel}` : ''}</p>
	{#if avecTraitement}
		<p>Traitement : {plan.traitement || '—'} · ordonnance pour toute la durée : {plan.ordonnance ? 'oui' : 'non'}</p>
	{/if}

	<h2>Quand ça ne va pas</h2>
	<p><strong>Mes signes d’alerte :</strong> {plan.signaux || '—'}</p>
	<p><strong>Ce qui m’aide :</strong> {plan.aides || '—'}</p>
	<p><strong>Numéros :</strong> 3114 (prévention du suicide, 24 h/24) · 15 · 112</p>

	{#if avecHumeur}
		<h2>Humeur des 30 derniers jours</h2>
		{#if recentes.length}
			<p>{recentes.length} notes · moyenne {moyenne?.toFixed(1)} / 5</p>
			<ul class="niveaux">
				{#each MOODS as m (m.value)}<li>{m.emoji} {m.label} : {recentes.filter((h) => h.mood === m.value).length}</li>{/each}
			</ul>
			{#if avecNotes}
				<ul>
					{#each recentes.filter((h) => h.note) as h (h.id)}<li>{jour(h.at)} — {MOODS[h.mood - 1].label} : {h.note}</li>{/each}
				</ul>
			{/if}
		{:else}
			<p class="muted">Aucune note d’humeur sur cette période.</p>
		{/if}
	{/if}
</article>

<style>
	.options label { display: flex; gap: 0.5rem; align-items: center; margin: 0.4rem 0; }
	.options label input { width: auto; }
	.options .sub { margin-left: 1.6rem; }
	.options .btn { margin: 0.6rem 0.4rem 0 0; }
	.doc h2 { font-size: 1.05rem; margin-top: 1.2rem; }
	.alerte { padding: 0.5rem 0.7rem; border-radius: var(--radius-sm); background: var(--accent-soft); }
	.scroll { overflow-x: auto; }
	.dates { white-space: nowrap; }
	table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
	th, td { text-align: left; padding: 0.35rem 0.4rem; border-bottom: 1px solid var(--border); vertical-align: top; }
	.niveaux { list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: 0.3rem 1rem; }
	@media print {
		.no-print, :global(nav), :global(.help) { display: none !important; }
		:global(main) { padding: 0 !important; max-width: none !important; }
		:global(body) { background: #fff !important; color: #000 !important; }
		.doc { font-size: 11pt; }
	}
</style>
