<script lang="ts">
	import { onMount } from 'svelte';
	import { load, save, uid } from '#lib/storage.ts';
	import {
		chiffrer, dechiffrer, demarrer, depuisFichier, estSauvegarde, fusionner, lireThemes, nouvelleSeance, parMois,
		PROCHAINE_VIDE, RESSENTIS, rechercher, themes as listeThemes, trier, type Prochaine, type Sauvegarde, type Seance
	} from '#lib/seances.ts';

	let seances: Seance[] = $state([]);
	let prochaine: Prochaine = $state({ ...PROCHAINE_VIDE });
	let nouveauSujet = $state('');
	let ouverte: string | null = $state(null);
	let aSupprimer: string | null = $state(null);
	let q = $state('');
	let filtre: string | null = $state(null);

	// sauvegarde chiffrée
	let mode: 'rien' | 'export' | 'import' = $state('rien');
	let mdp = $state('');
	let mdp2 = $state('');
	let enAttente: Sauvegarde | null = $state(null);
	let message = $state('');

	onMount(() => {
		seances = load<Seance[]>('seances', []);
		prochaine = load<Prochaine>('seances-prochaine', { ...PROCHAINE_VIDE });
	});

	const garder = () => save('seances', seances);
	const garderProchaine = () => save('seances-prochaine', prochaine);
	const aujourdhui = () => new Date().toISOString().slice(0, 10);

	let triees = $derived(trier(seances));
	let visibles = $derived(rechercher(triees, q, filtre));
	let tousThemes = $derived(listeThemes(seances));
	let mois = $derived(parMois(seances).slice(-12));
	let maxMois = $derived(Math.max(1, ...mois.map((m) => m.n)));
	let datees = $derived(seances.filter((s) => s.date).length);

	const fmt = (d: string | null) =>
		d ? new Date(d + 'T12:00').toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' }) : 'Sans date';
	const extrait = (s: Seance) => s.texte.replace(/\s+/g, ' ').trim().slice(0, 90) || 'Pas encore de notes';

	function ajouterSujet(e: SubmitEvent) {
		e.preventDefault();
		const t = nouveauSujet.trim();
		if (!t) return;
		prochaine.sujets = [...prochaine.sujets, { id: uid(), texte: t, fait: false }];
		nouveauSujet = '';
		garderProchaine();
	}
	function basculerSujet(id: string) {
		prochaine.sujets = prochaine.sujets.map((s) => (s.id === id ? { ...s, fait: !s.fait } : s));
		garderProchaine();
	}
	function retirerSujet(id: string) {
		prochaine.sujets = prochaine.sujets.filter((s) => s.id !== id);
		garderProchaine();
	}
	function commencer() {
		const { seance, reste } = demarrer(prochaine, uid(), aujourdhui());
		seances = [seance, ...seances];
		prochaine = reste;
		ouverte = seance.id;
		garder();
		garderProchaine();
	}
	function ajouterVide() {
		const s = nouvelleSeance(uid(), aujourdhui());
		seances = [s, ...seances];
		ouverte = s.id;
		garder();
	}
	function modifier(id: string, champs: Partial<Seance>) {
		seances = seances.map((s) => (s.id === id ? { ...s, ...champs } : s));
		garder();
	}
	function supprimer(id: string) {
		seances = seances.filter((s) => s.id !== id);
		aSupprimer = null;
		ouverte = null;
		garder();
	}

	async function exporter(e: SubmitEvent) {
		e.preventDefault();
		if (mdp.length < 8) return (message = 'Choisis un mot de passe d’au moins 8 caractères.');
		if (mdp !== mdp2) return (message = 'Les deux mots de passe ne sont pas identiques.');
		const fichier = await chiffrer({ seances, prochaine }, mdp);
		const blob = new Blob([JSON.stringify(fichier)], { type: 'application/json' });
		const nom = `mes-seances-${aujourdhui()}.json`;
		const f = new File([blob], nom, { type: 'application/json' });
		if (navigator.canShare?.({ files: [f] })) {
			await navigator.share({ files: [f], title: 'Mes séances (chiffré)' }).catch(() => {});
		} else {
			const a = document.createElement('a');
			a.href = URL.createObjectURL(blob);
			a.download = nom;
			a.click();
			URL.revokeObjectURL(a.href);
		}
		mdp = mdp2 = '';
		mode = 'rien';
		message = 'Sauvegarde chiffrée créée. Garde-la avec son mot de passe : sans lui, elle ne peut pas être ouverte.';
	}

	async function choisirFichier(e: Event) {
		const input = e.target as HTMLInputElement;
		const f = input.files?.[0];
		input.value = '';
		if (!f) return;
		let json: unknown;
		try {
			json = JSON.parse(await f.text());
		} catch {
			return (message = 'Ce fichier n’est pas reconnu.');
		}
		if (estSauvegarde(json)) {
			enAttente = json;
			mode = 'import';
			message = '';
			return;
		}
		importer(json);
	}
	function importer(json: unknown) {
		const lues = depuisFichier(json, uid);
		if (!lues) return (message = 'Ce fichier n’est pas reconnu.');
		const avant = seances.length;
		seances = fusionner(seances, lues);
		const p = (json as { prochaine?: Prochaine })?.prochaine;
		if (p && Array.isArray(p.sujets) && !prochaine.sujets.length) {
			prochaine = p;
			garderProchaine();
		}
		garder();
		message = `${seances.length - avant} séance(s) ajoutée(s).`;
	}
	async function ouvrirSauvegarde(e: SubmitEvent) {
		e.preventDefault();
		if (!enAttente) return;
		const contenu = await dechiffrer(enAttente, mdp);
		if (contenu === null) return (message = 'Mot de passe incorrect, ou fichier abîmé.');
		mdp = '';
		enAttente = null;
		mode = 'rien';
		importer(contenu);
	}
</script>

<h1>Mes séances</h1>
<p class="lead">Prépare tes séances et garde ce qui t’aide. Tout reste sur ton téléphone.</p>

<section class="card" aria-labelledby="t-prochaine">
	<h2 id="t-prochaine" class="titre">Ma prochaine séance</h2>
	<div class="duo">
		<label>Date<input type="date" bind:value={prochaine.date} onchange={garderProchaine} /></label>
		<label>Avec<input type="text" bind:value={prochaine.soignant} onchange={garderProchaine} placeholder="psychologue, prénom…" /></label>
	</div>
	<p class="muted">Ce que je veux aborder :</p>
	{#if prochaine.sujets.length}
		<ul class="sujets">
			{#each prochaine.sujets as s (s.id)}
				<li class:fait={s.fait}>
					<label class="check"><input type="checkbox" checked={s.fait} onchange={() => basculerSujet(s.id)} /><span>{s.texte}</span></label>
					<button class="del" aria-label={'Retirer ' + s.texte} onclick={() => retirerSujet(s.id)}>✕</button>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="muted">Note les sujets au fil de la semaine, quand ils te viennent.</p>
	{/if}
	<form class="ajout" onsubmit={ajouterSujet}>
		<input type="text" bind:value={nouveauSujet} placeholder="Un sujet, une question…" aria-label="Nouveau sujet" />
		<button class="btn secondary" type="submit">Ajouter</button>
	</form>
	<button class="btn full" onclick={commencer}>Je commence la séance</button>
</section>

{#if mois.length}
	<h2>Mes séances, sur les 12 derniers mois</h2>
	<div class="card frise" role="img" aria-label={`${datees} séances datées`}>
		{#each mois as m (m.mois)}
			<div class="mois" title={`${m.mois} : ${m.n} séance(s)`}>
				<div class="barre" style:height={`${(m.n / maxMois) * 70 + (m.n ? 6 : 2)}px`} class:vide={!m.n}></div>
				<span class="muted">{new Date(m.mois + '-15').toLocaleDateString('fr-FR', { month: 'narrow' })}</span>
			</div>
		{/each}
	</div>
{/if}

<h2>Mon carnet</h2>
<div class="outils">
	<input type="search" bind:value={q} placeholder="Rechercher dans mes notes" aria-label="Rechercher" />
	<button class="btn secondary" onclick={ajouterVide}>Ajouter</button>
</div>
{#if tousThemes.length}
	<div class="chips">
		{#each tousThemes as t (t.theme)}
			<button class="chip" aria-pressed={filtre === t.theme} onclick={() => (filtre = filtre === t.theme ? null : t.theme)}>{t.theme} {t.n}</button>
		{/each}
	</div>
{/if}

{#each visibles as s (s.id)}
	<article class="card seance" class:ouverte={ouverte === s.id}>
		<button class="entete" aria-expanded={ouverte === s.id} onclick={() => (ouverte = ouverte === s.id ? null : s.id)}>
			<span class="date">{s.date ? fmt(s.date) : s.intitule || 'Sans date'}</span>
			<span class="muted">
				{[s.soignant, s.ressenti ? RESSENTIS[s.ressenti - 1].label : ''].filter(Boolean).join(' · ')}
			</span>
			{#if ouverte !== s.id}<span class="extrait">{extrait(s)}</span>{/if}
		</button>
		{#if ouverte === s.id}
			<div class="form">
				<div class="duo">
					<label>Date<input type="date" value={s.date ?? ''} onchange={(e) => modifier(s.id, { date: e.currentTarget.value || null })} /></label>
					<label>Avec<input type="text" value={s.soignant} onchange={(e) => modifier(s.id, { soignant: e.currentTarget.value })} /></label>
				</div>
				<p class="muted">Comment s’est passée la séance ?</p>
				<div class="ressentis" role="radiogroup" aria-label="Ressenti de la séance">
					{#each RESSENTIS as r (r.value)}
						<button role="radio" aria-checked={s.ressenti === r.value} onclick={() => modifier(s.id, { ressenti: s.ressenti === r.value ? 0 : r.value })}>
							{r.label}
						</button>
					{/each}
				</div>
				<label>Mes notes<textarea rows="7" value={s.texte} oninput={(e) => modifier(s.id, { texte: e.currentTarget.value })}></textarea></label>
				<label>À essayer d’ici la prochaine fois<textarea rows="3" value={s.essayer} oninput={(e) => modifier(s.id, { essayer: e.currentTarget.value })}></textarea></label>
				<label>Thèmes<input type="text" value={s.themes.join(', ')} placeholder="sommeil, travail, famille…"
					onchange={(e) => modifier(s.id, { themes: lireThemes(e.currentTarget.value) })} /></label>
				{#if aSupprimer === s.id}
					<div class="confirm">
						<span>Supprimer cette séance ?</span>
						<button class="btn danger" onclick={() => supprimer(s.id)}>Supprimer</button>
						<button class="btn secondary" onclick={() => (aSupprimer = null)}>Garder</button>
					</div>
				{:else}
					<button class="lien" onclick={() => (aSupprimer = s.id)}>Supprimer cette séance</button>
				{/if}
			</div>
		{/if}
	</article>
{:else}
	<p class="muted">{seances.length ? 'Aucune séance ne correspond.' : 'Tes séances apparaîtront ici. Commence par noter ce que tu veux aborder la prochaine fois.'}</p>
{/each}

<h2>Sauvegarde</h2>
<div class="card">
	<p class="muted">Tes notes ne quittent pas ce téléphone. Pour les garder si tu le changes, crée une sauvegarde chiffrée : personne ne peut la lire sans ton mot de passe.</p>
	{#if mode === 'export'}
		<form class="pile" onsubmit={exporter}>
			<label>Mot de passe<input type="password" bind:value={mdp} autocomplete="new-password" minlength="8" /></label>
			<label>Le même, encore<input type="password" bind:value={mdp2} autocomplete="new-password" /></label>
			<p class="muted">Sans ce mot de passe, la sauvegarde est perdue : personne ne peut le retrouver.</p>
			<div class="ligne"><button class="btn" type="submit">Créer la sauvegarde</button><button class="btn secondary" type="button" onclick={() => (mode = 'rien')}>Annuler</button></div>
		</form>
	{:else if mode === 'import'}
		<form class="pile" onsubmit={ouvrirSauvegarde}>
			<label>Mot de passe de la sauvegarde<input type="password" bind:value={mdp} autocomplete="current-password" /></label>
			<div class="ligne"><button class="btn" type="submit">Ouvrir</button><button class="btn secondary" type="button" onclick={() => { mode = 'rien'; enAttente = null; }}>Annuler</button></div>
		</form>
	{:else}
		<div class="ligne">
			<button class="btn secondary" onclick={() => { mode = 'export'; message = ''; }} disabled={!seances.length}>Sauvegarder</button>
			<label class="btn secondary">Restaurer / importer<input type="file" accept=".json,application/json" hidden onchange={choisirFichier} /></label>
		</div>
	{/if}
	{#if message}<p class="message" role="status">{message}</p>{/if}
</div>

<style>
	.titre { margin-top: 0; }
	label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.9rem; color: var(--text-soft); }
	label input, label textarea { color: var(--text); font-size: 1rem; }
	.duo { display: grid; grid-template-columns: 1fr 1fr; gap: 0.6rem; margin-bottom: 0.6rem; }
	@media (max-width: 380px) { .duo { grid-template-columns: 1fr; } }
	.sujets { list-style: none; margin: 0.3rem 0; padding: 0; display: flex; flex-direction: column; gap: 0.2rem; }
	.sujets li { display: flex; align-items: center; gap: 0.4rem; }
	.check { flex-direction: row; align-items: center; gap: 0.6rem; flex: 1; color: var(--text); font-size: 1rem; min-height: 40px; }
	.check input { width: 22px; height: 22px; accent-color: var(--primary); }
	.fait span { text-decoration: line-through; color: var(--text-soft); }
	.ajout, .outils, .ligne { display: flex; gap: 0.5rem; align-items: center; margin: 0.6rem 0; flex-wrap: wrap; }
	.ajout input, .outils input { flex: 1; min-width: 0; }
	.full { width: 100%; }
	.del { background: none; border: none; color: var(--text-soft); font-size: 1rem; cursor: pointer; padding: 0.4rem; }
	.frise { display: flex; justify-content: space-between; align-items: flex-end; gap: 4px; height: 120px; }
	.mois { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1; }
	.barre { width: 100%; max-width: 22px; border-radius: 8px; background: var(--primary); }
	.barre.vide { background: var(--border); }
	.chips { display: flex; gap: 0.4rem; flex-wrap: wrap; margin: 0 0 0.8rem; }
	.chip { font: inherit; font-size: 0.85rem; padding: 0.3rem 0.8rem; border-radius: 999px; border: 1px solid var(--border);
		background: var(--surface); color: var(--text); cursor: pointer; }
	.chip[aria-pressed='true'] { background: var(--primary); border-color: var(--primary); color: #fff; }
	.seance { padding: 0; overflow: hidden; }
	.entete { all: unset; box-sizing: border-box; display: flex; flex-direction: column; gap: 0.15rem; width: 100%; padding: 0.9rem 1.1rem; cursor: pointer; }
	.entete:focus-visible { outline: 3px solid var(--accent); outline-offset: -3px; }
	.date { font-weight: 700; }
	.extrait { color: var(--text-soft); font-size: 0.92rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.ouverte { border-color: var(--primary); }
	.form { display: flex; flex-direction: column; gap: 0.7rem; padding: 0 1.1rem 1rem; }
	.ressentis { display: flex; flex-wrap: wrap; gap: 0.4rem; }
	.ressentis button { font: inherit; font-size: 0.85rem; padding: 0.45rem 0.8rem; border-radius: 999px; border: 1px solid var(--border);
		background: var(--surface-soft); color: var(--text); cursor: pointer; }
	.ressentis button[aria-checked='true'] { background: var(--primary); border-color: var(--primary); color: #fff; }
	.lien { background: none; border: none; color: var(--danger); font: inherit; font-size: 0.9rem; cursor: pointer; align-self: flex-start; padding: 0.3rem 0; }
	.confirm { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
	.pile { display: flex; flex-direction: column; gap: 0.6rem; }
	.message { color: var(--text); background: var(--primary-soft); border-radius: var(--radius-sm); padding: 0.6rem 0.8rem; }
</style>
