<script lang="ts">
	// Espace admin : opportunités pro relevées dans Gmail (contacts recruteurs, alertes, démarches).
	// Le classement, la localisation et la fraîcheur sont déduits ici (#lib/opportunites.ts) ; seul mon suivi
	// (statut, note) est envoyé au serveur. Rien n'est gardé sur l'appareil.
	import { onMount } from 'svelte';
	import {
		LIBELLES_STATUT,
		ageLisible,
		analyser,
		compter,
		filtrer,
		lienGmail,
		regrouperDoublons,
		statutDe,
		type Fraicheur,
		type Releve,
		type Serieux,
		type StatutSuivi,
		type Suivi,
		type Type,
		type Zone
	} from '#lib/opportunites.ts';

	let etat: 'chargement' | 'connexion' | 'ferme' | 'ouvert' | 'erreur' = $state('chargement');
	let releve: Releve = $state({ genere_le: null, mails: [] });
	let suivi: Record<string, Suivi> = $state({});
	let recherche = $state('');
	let types: Type[] = $state(['recruteur']);
	let serieux: Serieux[] = $state([]);
	let fraicheurs: Fraicheur[] = $state([]);
	let zones: Zone[] = $state([]);
	let statuts: (StatutSuivi | 'nouveau')[] = $state([]);
	let ouverte: string | null = $state(null);
	let notes: Record<string, string> = $state({});
	let affiches = $state(30);
	let message = $state('');

	const maintenant = new Date();
	const toutes = $derived(releve.mails.map((m) => analyser(m, maintenant, releve.zone_proche ?? [])));
	const trouvees = $derived(regrouperDoublons(filtrer(toutes, { recherche, types, serieux, fraicheurs, zones, statuts }, suivi)));
	const parType = $derived(compter(toutes, (o) => o.type));
	const parFraicheur = $derived(compter(toutes.filter((o) => types.length === 0 || types.includes(o.type)), (o) => o.fraicheur));

	onMount(async () => {
		const res = await fetch('/api/admin/opportunites', { credentials: 'same-origin' }).catch(() => null);
		if (res?.ok) {
			const corps = await res.json();
			releve = corps.releve;
			suivi = corps.suivi ?? {};
			etat = 'ouvert';
		} else if (res?.status === 401) etat = 'connexion';
		else if (res?.status === 404) etat = 'ferme';
		else etat = 'erreur';
	});

	function basculer<T>(liste: T[], v: T): T[] {
		affiches = 30;
		return liste.includes(v) ? liste.filter((x) => x !== v) : [...liste, v];
	}

	async function poser(id: string, statut: StatutSuivi | null) {
		const note = (notes[id] ?? suivi[id]?.note ?? '').trim();
		const res = await fetch('/api/admin/opportunites/suivi', {
			method: 'POST',
			credentials: 'same-origin',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ id, statut, note })
		}).catch(() => null);
		if (!res?.ok) {
			message = 'Suivi non enregistré, réessaie.';
			return;
		}
		message = '';
		if (statut) suivi = { ...suivi, [id]: { statut, note, le: new Date().toISOString().slice(0, 10) } };
		else {
			const { [id]: _, ...reste } = suivi;
			suivi = reste;
		}
	}

	const TYPES: [Type, string][] = [['recruteur', 'Recruteurs'], ['alerte', 'Alertes'], ['demarche', 'Démarches'], ['autre', 'Autres']];
	const SERIEUX: Serieux[] = ['sérieux', 'à creuser', 'vague'];
	const FRAICHEURS: Fraicheur[] = ['frais', 'tiède', 'périmé'];
	const ZONES: Zone[] = ['proche', 'à distance', 'loin', 'inconnue'];
	const STATUTS = Object.keys(LIBELLES_STATUT) as (StatutSuivi | 'nouveau')[];
	const dateCourte = (iso: string) => new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: '2-digit' });
	const classe = (s: string) => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z]/gi, '');
</script>

<svelte:head>
	<title>Opportunités · Admin</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="admin">
	<header>
		<div>
			<h1>Opportunités</h1>
			<p class="soft">
				{#if releve.genere_le}Relevé Gmail du {dateCourte(releve.genere_le)} · {releve.mails.length} mails{:else}Recruteurs, alertes et démarches tirés de Gmail{/if}
			</p>
		</div>
		<a class="lien" href="/admin/">Admin</a>
	</header>

	{#if etat === 'chargement'}
		<p class="soft">Chargement…</p>
	{:else if etat === 'connexion'}
		<p class="card">Connecte-toi d’abord sur <a href="/admin/">l’espace admin</a>, puis reviens ici.</p>
	{:else if etat === 'ferme'}
		<p class="card">L’espace admin n’est pas activé sur ce serveur.</p>
	{:else if etat === 'erreur'}
		<p class="card erreur">Relevé indisponible pour le moment.</p>
	{:else if !releve.mails.length}
		<p class="card">
			Pas encore de relevé. Dans une session Claude reliée à Gmail, demande « mets à jour les opportunités de l’espace
			admin » : elle relève les mails et les envoie ici.
		</p>
	{:else}
		{#if releve.stats}
			<p class="soft petit">
				{#each Object.entries(releve.stats) as [k, v], i (k)}{i ? ' · ' : ''}{k} : {v}{/each}
			</p>
		{/if}

		<div class="puces">
			{#each TYPES as [t, nom] (t)}
				<button class="puce" aria-pressed={types.includes(t)} onclick={() => (types = basculer(types, t))}>{nom} {parType[t] ?? 0}</button>
			{/each}
		</div>
		<div class="puces">
			{#each FRAICHEURS as f (f)}
				<button class="puce {classe(f)}" aria-pressed={fraicheurs.includes(f)} onclick={() => (fraicheurs = basculer(fraicheurs, f))}>
					{f} {parFraicheur[f] ?? 0}
				</button>
			{/each}
			{#each SERIEUX as s (s)}
				<button class="puce" aria-pressed={serieux.includes(s)} onclick={() => (serieux = basculer(serieux, s))}>{s}</button>
			{/each}
		</div>
		<details class="plus-filtres">
			<summary class="soft petit">Lieu, suivi, recherche</summary>
			<div class="puces">
				{#each ZONES as z (z)}
					<button class="puce" aria-pressed={zones.includes(z)} onclick={() => (zones = basculer(zones, z))}>📍 {z}</button>
				{/each}
			</div>
			<div class="puces">
				{#each STATUTS as s (s)}
					<button class="puce" aria-pressed={statuts.includes(s)} onclick={() => (statuts = basculer(statuts, s))}>{LIBELLES_STATUT[s]}</button>
				{/each}
			</div>
			<input class="recherche" type="search" placeholder="Chercher (WeWard, Python, Montpellier…)" bind:value={recherche}
				oninput={() => (affiches = 30)} aria-label="Chercher dans les opportunités" />
		</details>

		<p class="soft petit">
			{trouvees.length} résultat{trouvees.length > 1 ? 's' : ''}{#if !statuts.length}{' · '}écartés et archivés masqués{/if}
		</p>
		{#if message}<p class="erreur petit">{message}</p>{/if}

		<ul class="liste">
			{#each trouvees.slice(0, affiches) as o (o.id)}
				{@const st = statutDe(o, suivi)}
				<li class="card">
					<div class="tete">
						<span class="badge {classe(o.fraicheur)}" title="{o.age_jours} jours">{o.fraicheur}</span>
						{#if o.type === 'recruteur'}<span class="badge {classe(o.serieux)}">{o.serieux}</span>{/if}
						{#if st !== 'nouveau'}<span class="badge suivi">{LIBELLES_STATUT[st]}</span>{/if}
						{#if o.non_lu}<span class="point" title="Non lu"></span>{/if}
					</div>
					<a class="titre" href={lienGmail(o.id)} target="_blank" rel="noopener noreferrer">
						{#if o.entreprise}<strong>{o.entreprise}</strong> · {o.poste ?? o.sujet}{:else}{o.sujet}{/if}
					</a>
					<p class="soft petit">
						{ageLisible(o.age_jours)} ({dateCourte(o.le)})
						{#if o.nom} · {o.nom}{/if}
						{#if o.intermediaire !== 'inconnu'} · {o.intermediaire}{/if}
						{#if o.echange} · 💬 échange{/if}
						{#if o.doublons} · +{o.doublons} mail{o.doublons > 1 ? 's' : ''} pour la même offre{/if}
					</p>
					<p class="petit infos">
						📍 {o.lieux.length ? o.lieux.join(', ') : 'lieu inconnu'}
						{#if o.salaire} · 💶 {o.salaire}{/if}
					</p>
					{#if o.extrait && ouverte !== o.id}<p class="petit extrait">{o.extrait}</p>{/if}
					{#if suivi[o.id]?.note && ouverte !== o.id}<p class="petit note">📝 {suivi[o.id].note}</p>{/if}

					<button class="lien petit" onclick={() => (ouverte = ouverte === o.id ? null : o.id)}>
						{ouverte === o.id ? 'Replier' : 'Suivre'}
					</button>
					{#if ouverte === o.id}
						<div class="details">
							{#if o.indices.length}<p class="petit soft">Indices : {o.indices.join(', ')}</p>{/if}
							{#if o.role}<p class="petit soft">{o.role}</p>{/if}
							{#if o.extrait}<p class="petit extrait">{o.extrait}</p>{/if}
							<textarea rows="2" placeholder="Note (rappel, salaire, contact…)" value={notes[o.id] ?? suivi[o.id]?.note ?? ''}
								oninput={(e) => (notes[o.id] = e.currentTarget.value)} aria-label="Note"></textarea>
							<div class="actions">
								{#each STATUTS.filter((s) => s !== 'nouveau') as s (s)}
									<button class="action" aria-pressed={st === s} onclick={() => poser(o.id, s as StatutSuivi)}>{LIBELLES_STATUT[s]}</button>
								{/each}
								{#if st !== 'nouveau'}<button class="lien petit" onclick={() => poser(o.id, null)}>Remettre à « nouveau »</button>{/if}
							</div>
						</div>
					{/if}
				</li>
			{/each}
		</ul>
		{#if trouvees.length > affiches}
			<button class="lien plus" onclick={() => (affiches += 30)}>Afficher plus</button>
		{/if}
	{/if}
</div>

<style>
	.admin { max-width: 860px; margin: 0 auto; padding: 1rem; }
	header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 0.8rem; }
	h1 { margin: 0; font-size: 1.5rem; }
	.soft { color: var(--text-soft); margin: 0; }
	.petit { font-size: 0.85rem; margin: 0; }
	.erreur { color: var(--danger); }
	.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.8rem; box-shadow: var(--shadow); }
	.lien { background: none; border: 0; color: var(--primary); padding: 0; text-decoration: underline; justify-self: start; }
	.plus { display: block; margin: 0.5rem auto 1rem; }
	.puces { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.3rem 0; }
	.puce { border: 1px solid var(--border); background: var(--surface); border-radius: 999px; padding: 0.3rem 0.75rem; font-size: 0.85rem; }
	.puce[aria-pressed='true'] { background: var(--primary); color: #fff; border-color: var(--primary); }
	.plus-filtres { margin: 0.3rem 0 0.5rem; }
	.recherche { width: 100%; margin-top: 0.3rem; }
	.liste { list-style: none; padding: 0; margin: 0.5rem 0; display: grid; gap: 0.6rem; }
	.liste > li { display: grid; gap: 0.3rem; min-width: 0; }
	.tete { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
	.titre { overflow-wrap: anywhere; line-height: 1.3; }
	.badge { font-size: 0.75rem; border-radius: 999px; padding: 0.1rem 0.55rem; border: 1px solid var(--border); }
	.frais { background: #e3f6e8; color: #17653a; border-color: #b9e4c6; }
	.tiede { background: #fff4dc; color: #7a5300; border-color: #f0dba6; }
	.perime { background: #f1f1f1; color: #6b6b6b; }
	.serieux { background: #e6efff; color: #1d4fa8; border-color: #bcd0f5; }
	.acreuser { background: #f4ecff; color: #5b2ea6; border-color: #dccbf7; }
	.vague { color: var(--text-soft); }
	.suivi { background: var(--primary); color: #fff; border-color: var(--primary); }
	.point { width: 0.55rem; height: 0.55rem; border-radius: 50%; background: var(--primary); }
	.infos { color: var(--text); }
	.extrait { white-space: pre-line; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
	.details .extrait { -webkit-line-clamp: unset; line-clamp: unset; }
	.note { font-style: italic; }
	.details { display: grid; gap: 0.5rem; border-top: 1px solid var(--border); padding-top: 0.5rem; }
	textarea { width: 100%; font: inherit; }
	.actions { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; }
	.action { border: 1px solid var(--border); background: var(--surface); border-radius: var(--radius); padding: 0.35rem 0.7rem; font-size: 0.85rem; }
	.action[aria-pressed='true'] { background: var(--primary); color: #fff; border-color: var(--primary); }
	@media (prefers-color-scheme: dark) {
		.frais { background: #183d27; color: #9fe0b5; border-color: #23573a; }
		.tiede { background: #3d3115; color: #f2d58d; border-color: #5a4720; }
		.perime { background: #2a2a2a; color: #a0a0a0; }
		.serieux { background: #1b2c4d; color: #a9c5fb; border-color: #2a4170; }
		.acreuser { background: #2f2146; color: #d2bdf7; border-color: #45306a; }
	}
</style>
