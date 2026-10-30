<script lang="ts">
	import { onMount } from 'svelte';
	import { load, save, uid } from '#lib/storage.ts';
	import {
		CADRES,
		ENTOURAGES,
		ENVIES,
		PLAN_VIDE,
		decouper,
		finSejour,
		idees,
		lienAide,
		lienAirbnb,
		manques,
		type PlanSortie
	} from '#lib/sortie.ts';

	const DUREES = [
		{ nuits: 7, label: '1 semaine' },
		{ nuits: 14, label: '2 semaines' },
		{ nuits: 30, label: '1 mois' },
		{ nuits: 61, label: '2 mois' },
		{ nuits: 91, label: '3 mois' }
	];

	let plan: PlanSortie = $state(structuredClone(PLAN_VIDE));
	let charge = $state(false);
	let duree = $state(30);
	let nuitsParSejour = $state(7);

	onMount(() => {
		plan = { ...structuredClone(PLAN_VIDE), ...load<PlanSortie>('sortie', PLAN_VIDE) };
		if (!plan.sortieLe) plan.sortieLe = new Date().toISOString().slice(0, 10);
		charge = true;
	});

	// Sauvegarde locale à chaque modification (après le chargement)
	$effect(() => {
		const copie = $state.snapshot(plan);
		if (charge) save('sortie', copie);
	});

	let reste = $derived(manques(plan));

	function generer() {
		if (plan.sejours.length && !confirm('Remplacer les séjours déjà prévus ?')) return;
		plan.sejours = decouper(plan.sortieLe, duree, nuitsParSejour, uid);
	}

	function toggleEnvie(i: number, id: string) {
		const e = plan.sejours[i].envies;
		plan.sejours[i].envies = e.includes(id) ? e.filter((x) => x !== id) : [...e, id];
	}

	const jour = (iso: string) =>
		new Date(iso + 'T12:00:00').toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' });
</script>

<h1>Ma sortie</h1>
<p class="lead">
	Préparer la suite, séjour par séjour : une semaine thérapeutique ou plusieurs mois. À construire avec ton équipe
	soignante, avant de partir.
</p>

<section class="card">
	<h2>1. Le cadre</h2>
	<label>Je sors le <input type="date" bind:value={plan.sortieLe} /></label>
	<label>
		Ce que j’attends de cette période
		<textarea bind:value={plan.objectifs} rows="2" placeholder="Ex. retrouver un rythme de sommeil, reprendre le sport, revoir des gens"></textarea>
	</label>
	<div class="row">
		<label>
			Durée totale
			<select bind:value={duree}>
				{#each DUREES as d (d.nuits)}<option value={d.nuits}>{d.label}</option>{/each}
			</select>
		</label>
		<label>
			Changer de lieu tous les
			<select bind:value={nuitsParSejour}>
				<option value={3}>3 nuits</option>
				<option value={7}>7 nuits</option>
				<option value={14}>14 nuits</option>
				<option value={30}>mois</option>
			</select>
		</label>
	</div>
	<button class="btn full" onclick={generer}>Préparer les séjours</button>
</section>

{#if plan.sejours.length}
	<h2>2. Mes séjours</h2>
	{#each plan.sejours as s, i (s.id)}
		<article class="card sejour" class:reserve={s.reserve}>
			<header>
				<strong>Séjour {i + 1}</strong>
				<span class="muted">{jour(s.debut)} → {jour(finSejour(s))} · {s.nuits} nuit{s.nuits > 1 ? 's' : ''}</span>
			</header>

			<fieldset>
				<legend>Pour</legend>
				<div class="chips">
					{#each ENVIES as e (e.id)}
						<button class="chip" class:on={s.envies.includes(e.id)} aria-pressed={s.envies.includes(e.id)} onclick={() => toggleEnvie(i, e.id)}>
							{e.emoji} {e.label}
						</button>
					{/each}
				</div>
			</fieldset>

			<div class="row">
				<label>
					Cadre
					<select bind:value={s.cadre}>
						{#each CADRES as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
					</select>
				</label>
				<label>
					Avec qui
					<select bind:value={s.entourage}>
						{#each ENTOURAGES as e (e.id)}<option value={e.id}>{e.label}</option>{/each}
					</select>
				</label>
			</div>
			<div class="row">
				<label>Ville ou région <input bind:value={s.lieu} placeholder="Ex. Annecy, Bretagne" /></label>
				<label>Budget max / nuit (€) <input type="number" min="0" inputmode="numeric" bind:value={s.budgetNuit} /></label>
			</div>

			<div class="actions">
				<a class="btn" href={lienAirbnb(s)} target="_blank" rel="noopener noreferrer">Chercher sur Airbnb</a>
				<label class="check"><input type="checkbox" bind:checked={s.reserve} /> Réservé</label>
			</div>
			{#if s.reserve}
				<label>Lien de l’annonce <input type="url" bind:value={s.lien} placeholder="https://www.airbnb.fr/rooms/…" /></label>
			{/if}

			{#if idees(s).length}
				<details>
					<summary>Idées pour ce séjour</summary>
					<ul>{#each idees(s) as idee (idee)}<li>{idee}</li>{/each}</ul>
				</details>
			{/if}
			<p class="muted aide">
				Avant de partir, repère l’aide près de ce lieu :
				<a href={lienAide(s, 'cmp')} target="_blank" rel="noopener noreferrer">CMP</a> ·
				<a href={lienAide(s, 'urgences')} target="_blank" rel="noopener noreferrer">urgences psychiatriques</a> ·
				<a href={'/addictions/?pres=' + encodeURIComponent(s.lieu.trim())}>centre addictions</a>
			</p>
			<textarea bind:value={s.notes} rows="2" placeholder="Notes (adresse, accès, ce que je veux y faire)"></textarea>
		</article>
	{/each}
{/if}

<h2>3. Mon filet de sécurité</h2>
<section class="card">
	<h3>Mes rendez-vous de suivi</h3>
	{#each plan.rdv as r, i (r.id)}
		<div class="rdv">
			<input bind:value={r.qui} placeholder="Psychiatre, psychologue, CMP…" aria-label="Avec qui" />
			<input type="date" bind:value={r.quand} aria-label="Date" />
			<input bind:value={r.comment} placeholder="Sur place, visio, téléphone" aria-label="Comment" />
			<button class="btn secondary" aria-label="Retirer ce rendez-vous" onclick={() => plan.rdv.splice(i, 1)}>✕</button>
		</div>
	{/each}
	<button class="btn secondary" onclick={() => plan.rdv.push({ id: uid(), qui: '', quand: '', comment: '' })}>+ Un rendez-vous</button>

	<h3>Mon traitement</h3>
	<textarea bind:value={plan.traitement} rows="2" placeholder="Ce que je prends, et quand (facultatif)"></textarea>
	<label class="check">
		<input type="checkbox" bind:checked={plan.ordonnance} /> J’ai mon ordonnance et assez de traitement pour toute la durée
	</label>

	<h3>Ma personne de confiance</h3>
	<div class="row">
		<input bind:value={plan.confiance.nom} placeholder="Prénom" aria-label="Prénom de la personne de confiance" />
		<input type="tel" bind:value={plan.confiance.tel} placeholder="Téléphone" aria-label="Téléphone de la personne de confiance" />
	</div>

	<h3>Quand ça ne va pas</h3>
	<label>
		Mes signes d’alerte
		<textarea bind:value={plan.signaux} rows="2" placeholder="Ex. je dors moins de 5 h, je ne réponds plus aux messages"></textarea>
	</label>
	<label>
		Ce qui m’aide
		<textarea bind:value={plan.aides} rows="2" placeholder="Ex. marcher, respirer 2 minutes, appeler ma personne de confiance"></textarea>
	</label>
	<p class="urgence">
		Si ça devient trop lourd, où que tu sois : <a href="tel:3114"><strong>3114</strong></a> (prévention du suicide, 24 h/24) ·
		<a href="tel:15"><strong>15</strong></a> · <a href="tel:112"><strong>112</strong></a>
	</p>
</section>

<h2>4. Pour mon psychologue et mon psychiatre</h2>
<section class="card">
	{#if reste.length}
		<p>Il manque encore : {reste.join(', ')}.</p>
	{:else}
		<p>✓ Le plan est complet.</p>
	{/if}
	<a class="btn full" href="/sortie/export/">Préparer le document à montrer</a>
	<p class="muted">Un document à imprimer ou à enregistrer en PDF. Rien n’est envoyé : c’est toi qui le partages.</p>
</section>

<style>
	label { display: block; margin: 0.6rem 0; font-weight: 600; font-size: 0.95rem; }
	label input, label textarea, label select { margin-top: 0.3rem; font-weight: 400; }
	select { width: 100%; font: inherit; padding: 0.6rem; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--surface); color: inherit; }
	h3 { font-size: 1rem; margin: 1.1rem 0 0.3rem; }
	.row { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; }
	.full { width: 100%; margin-top: 0.6rem; }
	.sejour header { display: flex; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap; }
	.sejour.reserve { border-color: var(--accent); }
	fieldset { border: none; padding: 0; margin: 0.6rem 0; }
	legend { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.3rem; }
	.chips { display: flex; flex-wrap: wrap; gap: 0.4rem; }
	.chip { border: 1px solid var(--border); background: var(--surface); color: inherit; border-radius: 999px; padding: 0.4rem 0.8rem; font: inherit; cursor: pointer; }
	.chip.on { background: var(--accent-soft); border-color: var(--accent); font-weight: 700; }
	.actions { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin: 0.6rem 0; }
	.check { display: flex; align-items: center; gap: 0.5rem; font-weight: 600; }
	.check input { width: auto; margin: 0; }
	.rdv { display: grid; grid-template-columns: 1fr; gap: 0.4rem; margin-bottom: 0.6rem; padding-bottom: 0.6rem; border-bottom: 1px solid var(--border); }
	.aide { margin: 0.6rem 0; }
	details { margin: 0.5rem 0; }
	summary { cursor: pointer; font-weight: 600; }
	.urgence { margin-top: 1rem; padding: 0.7rem; border-radius: var(--radius-sm); background: var(--surface-soft); }
	@media (max-width: 380px) { .row { grid-template-columns: 1fr; } }
</style>
