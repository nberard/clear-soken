<script lang="ts">
	import { onMount } from 'svelte';
	import { load, save } from '#lib/storage.ts';
	import type { PlanSortie } from '#lib/sortie.ts';
	import {
		SUBSTANCES,
		TYPES,
		classer,
		formatKm,
		lienItineraire,
		lignesPour,
		lienAnnuaireOfficiel,
		chercherLieu,
		type Centre,
		type Lieu
	} from '#lib/centres.ts';

	type Choix = { substances: string[]; jeune: boolean };

	let centres: Centre[] = $state([]);
	let erreurAnnuaire = $state(false);
	let choix: Choix = $state({ substances: [], jeune: false });
	let mode: 'moi' | 'chezmoi' = $state('moi');

	// Autour de moi (jamais enregistré)
	let position: Lieu | null = $state(null);
	let localisation: 'idle' | 'en-cours' | 'refus' | 'erreur' = $state('idle');

	// Autour de mon futur chez-moi (enregistré sur le téléphone)
	let chezMoi: Lieu | null = $state(null);
	let recherche = $state('');
	let suggestions: Lieu[] = $state([]);
	let rechercheErreur = $state(false);
	let lieuxSortie: string[] = $state([]);
	let saisie: HTMLInputElement | undefined = $state();

	let combien = $state(5);
	let charge = false;

	onMount(async () => {
		choix = load<Choix>('centres:choix', choix);
		chezMoi = load<Lieu | null>('centres:chezmoi', null);
		lieuxSortie = [
			...new Set(load<PlanSortie | null>('sortie', null)?.sejours.map((s) => s.lieu.trim()).filter(Boolean) ?? [])
		];
		const pres = new URLSearchParams(location.search).get('pres');
		if (pres) {
			mode = 'chezmoi';
			recherche = pres;
			chercher();
		} else if (chezMoi) {
			mode = 'chezmoi';
		}
		charge = true;
		try {
			const res = await fetch('/api/centres');
			if (!res.ok) throw new Error(String(res.status));
			centres = await res.json();
		} catch {
			erreurAnnuaire = true;
		}
	});

	$effect(() => {
		const copie = $state.snapshot(choix);
		if (charge) save('centres:choix', copie);
	});

	function basculer(id: string) {
		choix.substances = choix.substances.includes(id)
			? choix.substances.filter((s) => s !== id)
			: [...choix.substances, id];
		combien = 5;
	}

	function meLocaliser() {
		if (!('geolocation' in navigator)) {
			localisation = 'erreur';
			return;
		}
		localisation = 'en-cours';
		navigator.geolocation.getCurrentPosition(
			(p) => {
				position = { label: 'Ma position', lat: p.coords.latitude, lon: p.coords.longitude };
				localisation = 'idle';
			},
			(e) => {
				localisation = e.code === e.PERMISSION_DENIED ? 'refus' : 'erreur';
			},
			{ enableHighAccuracy: false, timeout: 15000, maximumAge: 300000 }
		);
	}

	function choisirMode(m: 'moi' | 'chezmoi') {
		mode = m;
		combien = 5;
		if (m === 'moi' && !position && localisation !== 'en-cours') meLocaliser();
	}

	let minuteur: ReturnType<typeof setTimeout> | undefined;
	let enVol: AbortController | undefined;

	function chercher() {
		clearTimeout(minuteur);
		minuteur = setTimeout(async () => {
			enVol?.abort();
			enVol = new AbortController();
			rechercheErreur = false;
			try {
				suggestions = await chercherLieu(recherche, enVol.signal);
			} catch (e) {
				if ((e as Error).name !== 'AbortError') rechercheErreur = true;
			}
		}, 300);
	}

	function retenir(l: Lieu) {
		chezMoi = l;
		save('centres:chezmoi', l);
		suggestions = [];
		recherche = '';
		combien = 5;
	}

	function changerChezMoi() {
		chezMoi = null;
		save('centres:chezmoi', null);
		setTimeout(() => saisie?.focus());
	}

	function proposer(lieu: string) {
		recherche = lieu;
		chercher();
	}

	let origine = $derived(mode === 'moi' ? position : chezMoi);
	let resultats = $derived(origine ? classer(centres, origine, choix.substances, choix.jeune) : []);
	let meilleur = $derived(resultats[0]);
	let autres = $derived(resultats.slice(1, combien + 1));
	let lignes = $derived(lignesPour(choix.substances));
	let loin = $derived(!!origine && (!meilleur || meilleur.km > 30));

	function tel(t: string) {
		return 'tel:' + t.replace(/[^\d+]/g, '');
	}
</script>

<h1>Trouver un centre</h1>
<p class="lead">Addictions : un lieu près de toi, gratuit et confidentiel.</p>

<h2>Pour quoi&nbsp;?</h2>
<div class="chips" role="group" aria-label="Ce qui me concerne (plusieurs choix possibles)">
	{#each SUBSTANCES as s (s.id)}
		<button class="chip" class:on={choix.substances.includes(s.id)} aria-pressed={choix.substances.includes(s.id)} onclick={() => basculer(s.id)}>
			<span aria-hidden="true">{s.emoji}</span> {s.label}
		</button>
	{/each}
</div>
<label class="check">
	<input type="checkbox" bind:checked={choix.jeune} />
	J’ai moins de 25 ans
</label>
<p class="muted">Plusieurs choix possibles. Rien choisi&nbsp;: tous les centres.</p>

<h2>Autour de…</h2>
<div class="seg" role="radiogroup" aria-label="Chercher autour de">
	<button role="radio" aria-checked={mode === 'moi'} class:on={mode === 'moi'} onclick={() => choisirMode('moi')}>📍 Moi</button>
	<button role="radio" aria-checked={mode === 'chezmoi'} class:on={mode === 'chezmoi'} onclick={() => choisirMode('chezmoi')}>🏠 Futur chez-moi</button>
</div>

{#if mode === 'moi'}
	{#if position}
		<p class="muted">📍 Position trouvée · <button class="lien" onclick={meLocaliser}>actualiser</button></p>
	{:else if localisation === 'en-cours'}
		<p class="muted">Recherche de ta position…</p>
	{:else}
		<button class="btn full" onclick={meLocaliser}>📍 Utiliser ma position</button>
		{#if localisation === 'refus'}
			<p class="muted">La position est bloquée. Autorise-la dans les réglages du navigateur, ou choisis «&nbsp;Mon futur chez-moi&nbsp;» et tape une ville.</p>
		{:else if localisation === 'erreur'}
			<p class="muted">Position introuvable pour l’instant. Réessaie dehors, ou tape une ville dans «&nbsp;Mon futur chez-moi&nbsp;».</p>
		{/if}
	{/if}
{:else if chezMoi}
	<p class="lieu">🏠 <strong>{chezMoi.label}</strong> · <button class="lien" onclick={changerChezMoi}>changer</button></p>
{:else}
	<input
		bind:this={saisie}
		bind:value={recherche}
		oninput={chercher}
		type="search"
		inputmode="search"
		autocomplete="off"
		placeholder="Adresse, ville ou code postal"
		aria-label="Adresse, ville ou code postal de mon futur chez-moi"
	/>
	{#if suggestions.length}
		<ul class="suggestions">
			{#each suggestions as s (s.label + s.lat)}
				<li><button onclick={() => retenir(s)}>{s.label}</button></li>
			{/each}
		</ul>
	{:else if rechercheErreur}
		<p class="muted">Recherche impossible pour l’instant. Vérifie ta connexion.</p>
	{/if}
	{#if lieuxSortie.length && !recherche}
		<p class="muted">Depuis «&nbsp;Ma sortie&nbsp;»&nbsp;:</p>
		<div class="chips">
			{#each lieuxSortie as l (l)}<button class="chip" onclick={() => proposer(l)}>🧳 {l}</button>{/each}
		</div>
	{/if}
{/if}

{#if origine}
	{#if meilleur}
		<h2>Le plus adapté</h2>
		{@render carte(meilleur, true)}
		{#if autres.length}
			<h2>Autres centres proches</h2>
			{#each autres as r (r.centre.id)}{@render carte(r, false)}{/each}
			{#if resultats.length > combien + 1}
				<button class="btn secondary full" onclick={() => (combien += 5)}>Voir plus</button>
			{/if}
		{/if}
		<p class="muted">Suggestion selon ta demande et la distance. Parles-en avec ton équipe soignante&nbsp;: elle connaît les lieux et peut t’orienter.</p>
	{:else if erreurAnnuaire}
		<div class="card"><p>Impossible de charger les centres pour l’instant. Vérifie ta connexion, ou appelle une des lignes ci-dessous.</p></div>
	{/if}
	{#if loin}
		<p class="muted">
			Rien de très proche ici&nbsp;? Cherche aussi dans
			<a href={lienAnnuaireOfficiel(choix.substances)} target="_blank" rel="noopener noreferrer">l’annuaire officiel</a>.
		</p>
	{/if}
{/if}

<h2>Parler à quelqu’un maintenant</h2>
<p class="muted">Gratuit et anonyme, pour toi ou un proche.</p>
{#each lignes as l (l.id)}
	<div class="card ligne">
		<strong>{l.nom}</strong>
		<a class="btn secondary" href={tel(l.tel)}>📞 {l.tel}</a>
	</div>
{/each}

<details class="card">
	<summary>CSAPA, CJC, CAARUD&nbsp;: c’est quoi&nbsp;?</summary>
	{#each Object.entries(TYPES).filter(([t]) => t !== 'autre') as [t, info] (t)}
		<p><strong>{info.label}</strong>&nbsp;: {info.explication}</p>
	{/each}
</details>

<p class="muted privacy">
	🔒 Ta position et tes choix restent sur ton téléphone. Pour situer une adresse tapée, seul ce texte est envoyé au
	service public de l’IGN, sans le motif de ta recherche.
</p>

{#snippet carte(r: (typeof resultats)[number], premier: boolean)}
	<article class="card centre" class:premier>
		<div class="tete">
			<span class="kind">{TYPES[r.centre.type].label}</span>
			<span class="km">{formatKm(r.km)}</span>
		</div>
		<h3>{r.centre.nom}</h3>
		<p class="muted">📍 {r.centre.adresse}, {r.centre.cp} {r.centre.ville}</p>
		<ul class="raisons">{#each r.raisons as x (x)}<li>{x}</li>{/each}</ul>
		{#if r.centre.note}<p class="muted">{r.centre.note}</p>{/if}
		<div class="actions">
			{#if r.centre.tel}<a class="btn" class:secondary={!premier} href={tel(r.centre.tel)}>📞 Appeler</a>{/if}
			<a class="btn secondary" href={lienItineraire(r.centre)} target="_blank" rel="noopener noreferrer">🧭 Y aller</a>
			{#if r.centre.url}<a class="btn secondary" href={r.centre.url} target="_blank" rel="noopener noreferrer">Site</a>{/if}
		</div>
	</article>
{/snippet}

<style>
	h2 { margin-top: 1.25rem; }
	h3 { margin: 0.2rem 0; font-size: 1.05rem; }
	.chips { display: flex; flex-wrap: wrap; gap: 0.45rem; }
	.chip {
		border: 1px solid var(--border);
		background: var(--surface);
		color: inherit;
		border-radius: 999px;
		min-height: 44px;
		padding: 0.4rem 0.85rem;
		font: inherit;
		cursor: pointer;
	}
	.chip.on { background: var(--accent-soft); border-color: var(--accent); font-weight: 700; }
	.check { display: flex; align-items: center; gap: 0.6rem; font-weight: 600; margin: 0.8rem 0 0.2rem; min-height: 44px; }
	.check input { width: 1.3rem; height: 1.3rem; margin: 0; }

	.seg {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 4px;
		padding: 4px;
		background: var(--surface-soft);
		border-radius: 999px;
		margin-bottom: 0.8rem;
	}
	.seg button {
		min-height: 44px;
		border: none;
		border-radius: 999px;
		background: transparent;
		color: inherit;
		font: inherit;
		font-size: 0.95rem;
		cursor: pointer;
	}
	.seg button.on { background: var(--surface); font-weight: 700; box-shadow: var(--shadow); color: var(--primary); }

	.full { width: 100%; }
	.lien { border: none; background: none; padding: 0; color: var(--primary); font: inherit; text-decoration: underline; cursor: pointer; }
	.lieu { margin: 0.4rem 0; }

	.suggestions { list-style: none; margin: 0.3rem 0 0; padding: 0; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); overflow: hidden; }
	.suggestions li + li { border-top: 1px solid var(--border); }
	.suggestions button { width: 100%; min-height: 48px; text-align: left; padding: 0.6rem 0.8rem; border: none; background: none; color: inherit; font: inherit; cursor: pointer; }

	.centre.premier { border: 2px solid var(--primary); }
	.tete { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
	.kind { font-size: 0.75rem; font-weight: 700; background: var(--accent-soft); padding: 0.1rem 0.6rem; border-radius: 999px; }
	.km { font-weight: 700; color: var(--primary); }
	.raisons { list-style: none; display: flex; flex-wrap: wrap; gap: 0.3rem; margin: 0.4rem 0; padding: 0; }
	.raisons li { font-size: 0.8rem; background: var(--primary-soft); padding: 0.1rem 0.55rem; border-radius: 999px; }
	.actions { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.6rem; }
	.actions .btn { flex: 1 1 auto; min-height: 44px; font-size: 0.95rem; }

	.ligne { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; flex-wrap: wrap; }
	.ligne .btn { min-height: 44px; font-size: 0.95rem; }
	details summary { font-weight: 700; cursor: pointer; min-height: 32px; }
	.privacy { text-align: center; margin-top: 1.5rem; }
</style>
