<script lang="ts">
	// Espace admin : stats Instagram avancées (comptes avec le rôle « admin », sans lien avec l'appli patients).
	// Les données viennent de /api/admin/stats/* (marts dbt de clearmind-tools) ; rien n'est gardé sur l'appareil.
	import { onMount } from 'svelte';
	import {
		CRITERES,
		NIVEAUX,
		argent,
		compterNiveaux,
		date,
		description,
		filtrerComptes,
		LIBELLES_VERDICT,
		libelleGroupe,
		fourchette,
		nombre,
		nomPays,
		pct,
		rechercherPublications,
		resumeAudience,
		titre,
		top,
		valeurCritere,
		type Compte,
		type Critere,
		type FiltreComptes,
		type Sens,
		type Tri,
		type Pays,
		type Publication,
		type Qualite,
		type Verdict,
		type Verdicts
	} from '#lib/admin.ts';

	type Onglet = 'reels' | 'comptes' | 'audience';

	let etat: 'chargement' | 'connexion' | 'ouvert' = $state('chargement');
	let moi = $state('');
	let nom = $state('');
	let motDePasse = $state('');
	let erreurConnexion = $state('');
	let envoi = $state(false);

	let onglet: Onglet = $state('reels');
	let publications: Publication[] = $state([]);
	let comptes: Compte[] = $state([]);
	let qualite: Qualite[] = $state([]);
	let pays: Pays[] = $state([]);
	let erreurs: Partial<Record<string, string>> = $state({});
	let luLe: number | null = $state(null);

	let critere: Critere = $state('likes_authentiques_estimes');
	let sens: Sens = $state('desc');
	/** 2e niveau de tri : départage les égalités du 1er ('' = aucun) */
	let critere2: Critere | '' = $state('');
	let sens2: Sens = $state('desc');
	const tris = $derived<Tri[]>([
		{ critere, sens },
		...(critere2 && critere2 !== critere ? [{ critere: critere2, sens: sens2 }] : [])
	]);
	const critere2Actif = $derived(CRITERES.find((c) => c.id === critere2));
	const libelleSens = (s: Sens) => (s === 'desc' ? 'Décroissant' : 'Croissant');
	let combien = $state(10);
	let reelsSeulement = $state(true);
	let achetesSeulement = $state(false);
	let sansPeriodesAchat = $state(false);
	let recherche = $state('');
	/** Miniatures qui n'ont pas chargé (lien Instagram expiré) : on montre un aperçu neutre */
	let cassees = $state(new Set<string>());
	const aDesPeriodes = $derived(publications.some((p) => p.periode_achat));
	let filtre: FiltreComptes = $state({ niveau: 'probablement faux', population: 'tous', recherche: '', traites: false });
	let verdicts: Verdicts = $state({});
	const nbTraites = $derived(comptes.filter((c) => verdicts[c.compte_id]).length);
	let erreurVerdict = $state('');

	/** Pose (ou retire, si on reclique le même) un verdict ; la carte quitte la liste sauf si « traités » est coché */
	async function poserVerdict(c: Compte, v: Verdict) {
		const avant = verdicts[c.compte_id];
		const nouveau = avant?.verdict === v ? null : v;
		const suivant = { ...verdicts };
		if (nouveau) suivant[c.compte_id] = { verdict: nouveau, nom_compte: c.nom_compte, le: new Date().toISOString().slice(0, 10) };
		else delete suivant[c.compte_id];
		verdicts = suivant;
		erreurVerdict = '';
		const res = await fetch('/api/admin/verdicts', {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({ compte_id: c.compte_id, nom_compte: c.nom_compte, verdict: nouveau })
		}).catch(() => null);
		if (!res?.ok) {
			const remis = { ...verdicts };
			if (avant) remis[c.compte_id] = avant;
			else delete remis[c.compte_id];
			verdicts = remis;
			erreurVerdict = `Verdict non enregistré pour @${c.nom_compte}${res?.status === 401 ? ' (session expirée)' : ''}.`;
		}
	}
	let affiches = $state(50);

	const tousClasses = $derived(
		top(rechercherPublications(publications, recherche), tris, Infinity, reelsSeulement, achetesSeulement, sansPeriodesAchat)
	);
	const classement = $derived(tousClasses.slice(0, combien));
	const critereActif = $derived(CRITERES.find((c) => c.id === critere)!);
	const estGroupe = (c: object | undefined) => !!c && 'groupe' in c && !!c.groupe;
	/** Titres de groupe entre les cartes : dès qu'il y a un 2e niveau (le 1er forme alors des tranches ou des mois),
	 *  ou quand le 1er critère est lui-même un groupe (mois, période d'achat, boosts, tranches) */
	const parGroupes = $derived(estGroupe(critereActif) || (!!critere2Actif && critere2Actif.id !== critereActif.id));
	/** Chiffre mis en avant sur la carte : le 2e critère quand le 1er ne fait que regrouper */
	const critereAffiche = $derived(estGroupe(critereActif) && critere2Actif ? critere2Actif : critereActif);
	/** Critère rappelé sous la date (ni celui mis en avant, ni le groupe, ni la date déjà affichée) */
	const critereRappel = $derived(
		[critereActif, critere2Actif].find((c) => c && c !== critereAffiche && !estGroupe(c) && c.id !== 'published_at')
	);
	const titreGroupe = (p: Publication) => libelleGroupe(p, critere);
	const comptesFiltres = $derived(filtrerComptes(comptes, filtre, verdicts));
	const niveaux = $derived(compterNiveaux(comptes));
	const audience = $derived(resumeAudience(pays));
	const maxPays = $derived(Math.max(1, ...pays.map((p) => p.abonnes)));
	const qAbonnes = $derived(qualite.find((q) => q.population === 'abonnes'));
	const qLikers = $derived(qualite.find((q) => q.population === 'likers'));
	const qSuivis = $derived(qualite.find((q) => q.population === 'suivis'));

	async function charger(vue: string) {
		const res = await fetch(`/api/admin/stats/${vue}`, { credentials: 'same-origin' });
		if (res.status === 401) {
			etat = 'connexion';
			throw new Error('session');
		}
		const json = await res.json().catch(() => ({}));
		if (!res.ok) throw new Error(json.erreur ?? `erreur ${res.status}`);
		luLe = json.lu_le ?? luLe;
		return json.lignes;
	}

	/** Indicateur d'activité : chargement des données, mise à jour de la liste après un changement de tri ou de filtre */
	let chargement = $state(false);
	let calcul = $state(false);
	let minuterie: ReturnType<typeof setTimeout> | undefined;
	let premierPassage = true;
	$effect(() => {
		// relu à chaque changement de tri, de filtre ou de recherche
		void [critere, sens, critere2, sens2, combien, reelsSeulement, achetesSeulement, sansPeriodesAchat, recherche,
			filtre.niveau, filtre.population, filtre.recherche, filtre.traites, affiches];
		if (premierPassage) {
			premierPassage = false;
			return;
		}
		calcul = true;
		clearTimeout(minuterie);
		// la liste se recalcule tout de suite ; le pictogramme reste un instant pour qu'on voie que ça a bougé
		minuterie = setTimeout(() => (calcul = false), 400);
	});
	const erreurOnglet = $derived(
		onglet === 'reels' ? erreurs.publications : onglet === 'comptes' ? (erreurs.comptes ?? erreurs.qualite) : erreurs.pays
	);

	async function toutCharger() {
		chargement = true;
		try {
			await chargerVues();
		} finally {
			chargement = false;
		}
	}

	async function chargerVues() {
		erreurs = {};
		const vues = [
			['publications', (l: Publication[]) => (publications = l)],
			['comptes', (l: Compte[]) => (comptes = l)],
			['qualite', (l: Qualite[]) => (qualite = l)],
			['pays', (l: Pays[]) => (pays = l)]
		] as const;
		const lireVerdicts = fetch('/api/admin/verdicts', { credentials: 'same-origin' })
			.then((r) => (r.ok ? r.json() : {}))
			.then((v) => (verdicts = v))
			.catch(() => {});
		await Promise.all([
			lireVerdicts,
			...vues.map(async ([vue, poser]) => {
				try {
					(poser as (l: unknown) => void)(await charger(vue));
				} catch (e) {
					if ((e as Error).message !== 'session') erreurs[vue] = (e as Error).message;
				}
			})
		]);
	}

	onMount(async () => {
		const res = await fetch('/api/admin/moi', { credentials: 'same-origin' }).catch(() => null);
		if (res?.ok) {
			moi = (await res.json()).nom;
			etat = 'ouvert';
			await toutCharger();
		} else {
			etat = 'connexion';
			if (res?.status === 404) erreurConnexion = 'L’espace admin n’est pas activé sur ce serveur.';
		}
	});

	async function seConnecter(e: SubmitEvent) {
		e.preventDefault();
		envoi = true;
		erreurConnexion = '';
		try {
			const res = await fetch('/api/admin/connexion', {
				method: 'POST',
				headers: { 'content-type': 'application/json' },
				body: JSON.stringify({ nom, mot_de_passe: motDePasse })
			});
			if (res.ok) {
				moi = (await res.json()).nom;
				motDePasse = '';
				etat = 'ouvert';
				await toutCharger();
			} else if (res.status === 429) {
				erreurConnexion = 'Trop d’essais. Réessaie dans 10 minutes.';
			} else if (res.status === 404) {
				erreurConnexion = 'L’espace admin n’est pas activé sur ce serveur.';
			} else {
				erreurConnexion = 'Nom ou mot de passe incorrect, ou compte sans accès admin.';
			}
		} catch {
			erreurConnexion = 'Serveur injoignable.';
		} finally {
			envoi = false;
		}
	}

	async function seDeconnecter() {
		await fetch('/api/admin/deconnexion', { method: 'POST' }).catch(() => null);
		publications = comptes = [];
		qualite = [];
		pays = [];
		moi = '';
		etat = 'connexion';
	}

	const largeur = (part: number, total: number) => `${total ? Math.max(0, Math.min(100, (part / total) * 100)) : 0}%`;
	const classeNiveau = (n: string) => (n === 'probablement faux' ? 'faux' : n === 'à vérifier' ? 'doute' : 'reel');
</script>

<svelte:head>
	<title>Admin · Clear Soken</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="admin">
	<header>
		<div>
			<h1>Stats Instagram</h1>
			<p class="soft">Ce que l’appli Instagram ne montre pas</p>
		</div>
		{#if etat === 'ouvert'}
			<div class="moi">
				<span class="soft">{moi}</span>
				<button class="lien" onclick={seDeconnecter}>Déconnexion</button>
			</div>
		{/if}
	</header>

	{#if etat === 'chargement'}
		<p class="soft">Chargement…</p>
	{:else if etat === 'connexion'}
		<form class="card connexion" onsubmit={seConnecter}>
			<h2>Connexion</h2>
			<p class="soft">Réservé aux comptes avec le rôle admin.</p>
			<label>Nom <input bind:value={nom} autocomplete="username" autocapitalize="none" required /></label>
			<label>
				Mot de passe
				<input type="password" bind:value={motDePasse} autocomplete="current-password" required />
			</label>
			{#if erreurConnexion}<p class="erreur" role="alert">{erreurConnexion}</p>{/if}
			<button class="primaire" disabled={envoi}>{envoi ? 'Vérification…' : 'Se connecter'}</button>
		</form>
	{:else}
		<div class="onglets" role="tablist">
			<button role="tab" aria-selected={onglet === 'reels'} onclick={() => (onglet = 'reels')}>Top réels</button>
			<button role="tab" aria-selected={onglet === 'comptes'} onclick={() => (onglet = 'comptes')}>Faux comptes</button>
			<button role="tab" aria-selected={onglet === 'audience'} onclick={() => (onglet = 'audience')}>Provenance</button>
		</div>

		<div class="barre-statut" role="status" aria-live="polite">
			{#if chargement}
				<span class="roue" aria-hidden="true"></span><span>Chargement des données…</span>
			{:else if erreurOnglet}
				<span class="pic erreur" aria-hidden="true">⚠</span><span class="erreur">Erreur : {erreurOnglet}</span>
			{:else if calcul}
				<span class="roue" aria-hidden="true"></span><span>Mise à jour…</span>
			{:else}
				<span class="pic ok" aria-hidden="true">✓</span>
				<span>
					{#if onglet === 'reels'}{nombre(classement.length)} affichée{classement.length > 1 ? 's' : ''} sur {nombre(tousClasses.length)}
					{:else if onglet === 'comptes'}{nombre(comptesFiltres.length)} compte{comptesFiltres.length > 1 ? 's' : ''}
					{:else}{nombre(pays.length)} pays{/if}
				</span>
			{/if}
			<button class="lien recharger" onclick={toutCharger} disabled={chargement}>Recharger</button>
		</div>

		{#if onglet === 'reels'}
			<section>
				<div class="reglages">
					<label>
						Classer par
						<span class="tri">
							<select bind:value={critere}>
								<optgroup label="Chiffres">
									{#each CRITERES.filter((c) => !estGroupe(c)) as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
								</optgroup>
								<optgroup label="Regrouper par (puis classer avec « Puis par »)">
									{#each CRITERES.filter((c) => estGroupe(c)) as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
								</optgroup>
							</select>
							<button type="button" class="sens" title={libelleSens(sens)} aria-label={libelleSens(sens)}
								onclick={() => (sens = sens === 'desc' ? 'asc' : 'desc')}>{sens === 'desc' ? '↓' : '↑'}</button>
						</span>
					</label>
					<label>
						Puis par
						<span class="tri">
							<select bind:value={critere2}>
								<option value="">—</option>
								{#each CRITERES.filter((c) => !estGroupe(c)) as c (c.id)}{#if c.id !== critere}<option value={c.id}>{c.label}</option>{/if}{/each}
							</select>
							<button type="button" class="sens" title={libelleSens(sens2)} aria-label={libelleSens(sens2)} disabled={!critere2}
								onclick={() => (sens2 = sens2 === 'desc' ? 'asc' : 'desc')}>{sens2 === 'desc' ? '↓' : '↑'}</button>
						</span>
					</label>
					<label>
						Combien
						<select bind:value={combien}>
							<option value={10}>Top 10</option>
							<option value={25}>Top 25</option>
							<option value={1000}>Tout</option>
						</select>
					</label>
					<label class="case"><input type="checkbox" bind:checked={reelsSeulement} /> Réels seulement</label>
					<label class="case"><input type="checkbox" bind:checked={achetesSeulement} /> Likes achetés seulement</label>
					{#if aDesPeriodes}
						<label class="case"><input type="checkbox" bind:checked={sansPeriodesAchat} /> Sans les périodes d’achat</label>
					{/if}
				</div>
				<label class="recherche">
					Chercher dans les titres et descriptions
					<input type="search" bind:value={recherche} placeholder="surf, #recette…" autocapitalize="none" />
				</label>
				<p class="soft petit">
					{#if parGroupes}
						{#if estGroupe(critereActif)}Groupes par {critereActif.label.toLowerCase()}{:else}Tranches de {critereActif.label.toLowerCase()}{critere === 'published_at' ? ' (par mois)' : ''}{/if}{#if critere2Actif && critere2 !== critere}, puis classées par {critere2Actif.label.toLowerCase()} dans chaque {estGroupe(critereActif) ? 'groupe' : 'tranche'}{:else} : choisis un critère dans « Puis par » pour classer dans chaque groupe{/if}.
					{:else}
						{critereActif.label} : {critereActif.aide}. Choisis un critère dans « Puis par » pour regrouper par tranches et classer à l’intérieur.
					{/if}
				</p>

				{#if erreurs.publications}
					<p class="erreur">Publications indisponibles : {erreurs.publications}</p>
				{:else if !classement.length}
					<p class="card soft">
						{recherche.trim() ? `Aucune publication ne correspond à « ${recherche.trim()} ».` : 'Aucune publication pour l’instant.'}
					</p>
				{/if}

				<ol class="classement">
					{#each classement as p, i (p.publication_id)}
						{#if parGroupes && (i === 0 || titreGroupe(classement[i - 1]) !== titreGroupe(p))}
							<li class="groupe" aria-hidden="true">{titreGroupe(p)}</li>
						{/if}
						<li class="card">
							<div class="tete">
								<span class="rang">{i + 1}</span>
								<a class="vignette" href={p.url ?? undefined} target="_blank" rel="noopener noreferrer" tabindex="-1" aria-hidden="true">
									{#if p.miniature && !cassees.has(p.publication_id)}
										<img
											src={p.miniature}
											alt=""
											loading="lazy"
											referrerpolicy="no-referrer"
											onerror={() => (cassees = new Set(cassees).add(p.publication_id))}
										/>
									{:else}
										<span>{p.libelle_format.slice(0, 1)}</span>
									{/if}
								</a>
								<div class="titre">
									{#if p.url}<a href={p.url} target="_blank" rel="noopener noreferrer">{titre(p)}</a>
									{:else}<span class="nom">{titre(p)}</span>{/if}
									<span class="soft petit quand">
										{#if p.texte?.trim()}{p.libelle_format} · {date(p.published_at)}{/if}{#if p.texte?.trim() && critereRappel}{' · '}{/if}{#if critereRappel}{critereRappel.label} : {valeurCritere(p, critereRappel.id)}{/if}
									</span>
									{#if p.boosts}<span class="badge pub">Boosté ×{p.boosts}</span>{/if}
									{#if p.likes_superieurs_aux_vues}<span class="badge achat" title="Plus de likes que de vues">Likes achetés</span>{/if}
									{#if p.periode_achat}<span class="badge periode" title="Publiée pendant une période d’achat de likes ou d’abonnés">Période d’achat</span>{/if}
								</div>
								<strong class="valeur">{valeurCritere(p, critereAffiche.id)}</strong>
							</div>
							{#if description(p)}<p class="soft petit description">{description(p)}</p>{/if}

							<div class="barre-legende">
								<span>Likes {nombre(p.likes)}</span>
								<span><i class="pastille org"></i>organiques {nombre(p.likes_organiques)} · <i class="pastille paye"></i>payés {nombre(p.likes_payes)}</span>
							</div>
							<div class="barre" aria-hidden="true">
								<span class="org" style:width={largeur(p.likes_organiques, p.likes ?? 0)}></span>
								<span class="paye" style:width={largeur(p.likes_payes ?? 0, p.likes ?? 0)}></span>
							</div>

							{#if p.likes_faux_estimes != null}
								<div class="barre-legende">
									<span>{pct(p.part_likes_faux)} de faux{#if p.estimation === 'likes au-delà des vues'}{' · au-delà des vues'}{:else if p.estimation === 'ratio likes/vues'}{' · ratio likes/vues'}{/if}</span>
									<span><i class="pastille vrai"></i>authentiques {nombre(p.likes_authentiques_estimes)} · <i class="pastille faux"></i>faux {nombre(p.likes_faux_estimes)}</span>
								</div>
								<div class="barre" aria-hidden="true">
									<span class="vrai" style:width={largeur(p.likes_authentiques_estimes ?? 0, p.likes ?? 0)}></span>
									<span class="faux" style:width={largeur(p.likes_faux_estimes, p.likes ?? 0)}></span>
								</div>
							{:else if p.likers_analyses > 0}
								<p class="soft petit">
									<span class="badge faible">Échantillon trop petit</span>
									{nombre(p.likers_analyses)} liker{p.likers_analyses > 1 ? 's' : ''} analysé{p.likers_analyses > 1 ? 's' : ''} sur {nombre(p.likes)} likes (il en faut 30) : de {fourchette(p) || '?'} de faux, impossible à trancher.
								</p>
							{:else}
								<p class="soft petit">Likers pas encore analysés, et pas plus de likes que de vues.</p>
							{/if}
							{#if p.likes_faux_estimes != null && p.estimation !== 'likers analysés' && fourchette(p)}
								<p class="soft petit">Likers analysés ({nombre(p.likers_analyses)}) : de {fourchette(p)} de faux, trop peu pour compter.</p>
							{:else if p.likes_faux_estimes != null && p.estimation === 'likers analysés' && fourchette(p)}
								<p class="soft petit">Fourchette à 95 % : {fourchette(p)} de faux (sur {nombre(p.likers_analyses)} likers analysés).</p>
							{/if}
							{#if p.periode_achat && p.ratio_likes_vues != null && p.ratio_reference != null}
								<p class="soft petit">
									Likes / vues : {pct(p.ratio_likes_vues, 1)} · réels hors achat : {pct(p.ratio_reference, 1)}{#if p.likes_au_dela_du_ratio}{' · '}<strong>{nombre(p.likes_au_dela_du_ratio)} likes en trop</strong>{/if}
								</p>
							{/if}

							<dl>
								<div><dt>Vues</dt><dd>{nombre(p.vues)}</dd></div>
								<div><dt>dont payées</dt><dd>{nombre(p.vues_payees)}</dd></div>
								<div><dt>Likers analysés</dt><dd>{nombre(p.likers_analyses)} / {nombre(p.likers_releves)}</dd></div>
								{#if p.boosts}
									<div><dt>Dépense</dt><dd>{argent(p.depense, p.devise)}</dd></div>
									<div><dt>Abonnés payés</dt><dd>{nombre(p.abonnements_payes)}</dd></div>
									<div><dt>Coût / abonné</dt><dd>{argent(p.cout_par_abonne, p.devise)}</dd></div>
								{/if}
								<div><dt>Commentaires suspects</dt><dd>{pct(p.part_commentaires_suspects)}</dd></div>
							</dl>
						</li>
					{/each}
				</ol>
			</section>
		{:else if onglet === 'comptes'}
			<section>
				{#if erreurs.qualite}<p class="erreur">Synthèse indisponible : {erreurs.qualite}</p>{/if}
				<div class="tuiles">
					<div class="card tuile">
						<span class="soft">Abonnés faux estimés</span>
						<strong>{nombre(qAbonnes?.abonnes_faux_estimes)}</strong>
						<span class="soft petit">{pct(qAbonnes?.proba_faux_moyenne)} de {nombre(qAbonnes?.abonnes_total)} · échantillon de {nombre(qAbonnes?.comptes_analyses)}</span>
					</div>
					<div class="card tuile">
						<span class="soft">Likers faux (moyenne)</span>
						<strong>{pct(qLikers?.proba_faux_moyenne)}</strong>
						<span class="soft petit">{nombre(qLikers?.comptes_analyses)} likers analysés</span>
					</div>
					{#if qSuivis}
						<div class="card tuile">
							<span class="soft">Comptes que je suis : faux probables</span>
							<strong>{nombre(qSuivis.probablement_faux)}</strong>
							<span class="soft petit">sur {nombre(qSuivis.comptes_analyses)} analysés · {nombre(qSuivis.a_verifier)} à vérifier</span>
							<button class="lien" onclick={() => { filtre.population = 'suivis'; filtre.niveau = 'probablement faux'; }}>Voir la liste</button>
						</div>
					{/if}
				</div>

				<div class="barre grande" aria-hidden="true">
					<span class="faux" style:width={largeur(niveaux['probablement faux'], comptes.length)}></span>
					<span class="doute" style:width={largeur(niveaux['à vérifier'], comptes.length)}></span>
					<span class="vrai" style:width={largeur(niveaux['plutôt réel'], comptes.length)}></span>
				</div>

				<div class="puces" role="group" aria-label="Niveau">
					<button aria-pressed={filtre.niveau === 'tous'} onclick={() => (filtre.niveau = 'tous')}>Tous {nombre(comptes.length)}</button>
					{#each NIVEAUX as n (n)}
						<button class={classeNiveau(n)} aria-pressed={filtre.niveau === n} onclick={() => (filtre.niveau = n)}>{n} {nombre(niveaux[n])}</button>
					{/each}
				</div>
				<div class="reglages">
					<label>
						Parmi
						<select bind:value={filtre.population}>
							<option value="tous">tous les comptes analysés</option>
							<option value="suivis">comptes que je suis</option>
							<option value="abonnes">abonnés</option>
							<option value="likers">likers des réels</option>
						</select>
					</label>
					<label>Chercher <input type="search" bind:value={filtre.recherche} placeholder="@nom" autocapitalize="none" /></label>
					<label class="case"><input type="checkbox" bind:checked={filtre.traites} /> Afficher les comptes traités ({nombre(nbTraites)})</label>
				</div>
				{#if erreurVerdict}<p class="erreur" role="alert">{erreurVerdict}</p>{/if}

				{#if erreurs.comptes}<p class="erreur">Comptes indisponibles : {erreurs.comptes}</p>{/if}
				<ul class="comptes">
					{#each comptesFiltres.slice(0, affiches) as c (c.compte_id)}
						<li class="card">
							<div class="tete">
								<a class="vignette rond" href={c.url} target="_blank" rel="noopener noreferrer" tabindex="-1" aria-hidden="true"
									title={c.a_une_photo === false ? 'Pas de photo de profil' : undefined}>
									{#if c.photo && !cassees.has('c:' + c.compte_id)}
										<img
											src={c.photo}
											alt=""
											loading="lazy"
											referrerpolicy="no-referrer"
											onerror={() => (cassees = new Set(cassees).add('c:' + c.compte_id))}
										/>
									{:else}
										<span>{c.a_une_photo === false ? '?' : c.nom_compte.slice(0, 1).toUpperCase()}</span>
									{/if}
								</a>
								<span class="pct {classeNiveau(c.niveau)}">{c.pct_faux} %</span>
								<a href={c.url} target="_blank" rel="noopener noreferrer">@{c.nom_compte}</a>
								<span class="soft petit">{[c.est_suivi && 'je le suis', c.est_abonne && 'me suit', c.est_liker && `${c.reels_likes} réel${c.reels_likes > 1 ? 's' : ''} liké${c.reels_likes > 1 ? 's' : ''}`].filter(Boolean).join(' · ')}</span>
							</div>
							{#if c.raisons}<p class="petit">{c.raisons}</p>{/if}
							<p class="soft petit">{nombre(c.abonnes)} abonnés · {nombre(c.abonnements)} abonnements · {nombre(c.publications)} publications</p>
							<div class="verdicts" role="group" aria-label="Verdict pour @{c.nom_compte}">
								<a class="ouvrir" href={c.url} target="_blank" rel="noopener noreferrer">Ouvrir dans Instagram ↗</a>
								{#each (c.est_suivi ? ['retire', 'faux', 'vrai'] : ['faux', 'vrai']) as Verdict[] as v (v)}
									<button class="v-{v}" aria-pressed={verdicts[c.compte_id]?.verdict === v} onclick={() => poserVerdict(c, v)}>
										{LIBELLES_VERDICT[v]}
									</button>
								{/each}
							</div>
						</li>
					{/each}
				</ul>
				{#if comptesFiltres.length > affiches}
					<button class="lien plus" onclick={() => (affiches += 50)}>Voir 50 de plus ({nombre(comptesFiltres.length - affiches)} restants)</button>
				{/if}
				<p class="soft petit">
					Le pourcentage additionne des indices (pas de photo, aucune publication, suit beaucoup plus de comptes qu’il n’a
					d’abonnés, nom généré…). Il classe les comptes, il ne prouve rien : vérifie avant de bloquer.
				</p>
			</section>
		{:else}
			<section>
				{#if erreurs.pays}<p class="erreur">Pays indisponibles : {erreurs.pays}</p>{/if}
				<div class="card tuile">
					<span class="soft">Abonnés hors du marché visé</span>
					<strong>{pct(audience.horsMarche)}</strong>
					{#if audience.inattendus.length}
						<span class="soft petit">surtout {audience.inattendus.map((p) => nomPays(p.pays)).join(', ')}</span>
					{/if}
				</div>
				<ul class="pays">
					{#each pays as p (p.pays)}
						<li>
							<span class="nom">{nomPays(p.pays)}</span>
							<span class="barre fine" aria-hidden="true"><span class={p.pays_attendu ? 'vrai' : 'doute'} style:width={largeur(p.abonnes, maxPays)}></span></span>
							<span class="chiffre">{pct(p.part, 1)}</span>
						</li>
					{/each}
				</ul>
				<p class="soft petit"><i class="pastille vrai"></i>pays visés · <i class="pastille doute"></i>autres pays. Une grosse part hors du marché visé est typique des fermes à abonnés.</p>
			</section>
		{/if}

		{#if luLe}<p class="soft petit pied">Données lues le {new Date(luLe * 1000).toLocaleString('fr-FR')} · mises à jour chaque nuit</p>{/if}
	{/if}
</div>

<style>
	.admin {
		--vrai: var(--primary);
		--faux: var(--danger);
		--doute: var(--accent);
		--paye: #6a7fc1;
		max-width: 760px;
		margin: 0 auto;
		padding: calc(env(safe-area-inset-top) + 1rem) 16px calc(env(safe-area-inset-bottom) + 2rem);
	}
	header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1rem; }
	h1 { margin: 0; font-size: 1.5rem; }
	h2 { margin-top: 0; }
	.soft { color: var(--text-soft); margin: 0; }
	.petit { font-size: 0.85rem; }
	.moi { display: flex; flex-direction: column; align-items: flex-end; gap: 0.2rem; }
	.erreur { color: var(--danger); }
	.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem; box-shadow: var(--shadow); }
	.connexion { display: grid; gap: 0.8rem; max-width: 380px; }
	label { display: grid; gap: 0.25rem; font-size: 0.85rem; color: var(--text-soft); }
	input, select { font: inherit; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.55rem 0.7rem; min-width: 0; }
	button { font: inherit; cursor: pointer; }
	.primaire { background: var(--primary); color: #fff; border: 0; border-radius: 999px; padding: 0.7rem 1rem; font-weight: 700; }
	.primaire:disabled { opacity: 0.6; }
	.lien { background: none; border: 0; color: var(--primary); padding: 0; text-decoration: underline; }
	.plus { display: block; margin: 0.5rem auto 1rem; }

	.onglets { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; background: var(--surface-soft); border-radius: 999px; padding: 4px; margin-bottom: 1rem; }
	.onglets button { border: 0; background: none; border-radius: 999px; padding: 0.55rem 0.3rem; color: var(--text-soft); font-weight: 600; font-size: 0.9rem; }
	.onglets button[aria-selected='true'] { background: var(--surface); color: var(--text); box-shadow: var(--shadow); }

	.reglages { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: end; margin-bottom: 0.5rem; }
	.reglages label { flex: 1 1 140px; }
	.reglages .case { display: flex; align-items: center; gap: 0.4rem; flex: 0 0 auto; padding-bottom: 0.6rem; white-space: nowrap; color: var(--text); }
	.case input { padding: 0; width: 1.1rem; height: 1.1rem; accent-color: var(--primary); }

	.classement, .comptes, .pays { list-style: none; padding: 0; margin: 0.75rem 0; display: grid; gap: 0.6rem; }
	.tete { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
	.rang { font-weight: 800; color: var(--text-soft); width: 1.6rem; text-align: center; }
	.titre { flex: 1; min-width: 0; display: flex; gap: 0.4rem; flex-wrap: wrap; align-items: center; }
	.titre a, .titre .nom, .comptes a { color: var(--text); font-weight: 700; }
	.titre .quand { flex-basis: 100%; }
	.vignette {
		flex: 0 0 auto; width: 56px; height: 56px; border-radius: var(--radius-sm); overflow: hidden;
		background: var(--surface-soft); display: grid; place-items: center; color: var(--text-soft); font-weight: 800;
		text-decoration: none;
	}
	.vignette img { width: 100%; height: 100%; object-fit: cover; display: block; }
	.vignette.rond { width: 44px; height: 44px; border-radius: 50%; }
	.description {
		margin: 0.5rem 0 0; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical;
		overflow: hidden; overflow-wrap: anywhere;
	}
	.recherche { margin: 0.2rem 0 0.5rem; }
	.valeur { font-size: 1.35rem; font-variant-numeric: tabular-nums; }
	.classement .groupe {
		font-weight: 800; font-size: 0.95rem; color: var(--text-soft);
		margin: 0.6rem 0 -0.2rem; padding-left: 0.2rem;
	}
	.classement .groupe::first-letter { text-transform: uppercase; }
	.tri { display: flex; gap: 0.3rem; }
	.tri select { flex: 1; }
	.sens {
		flex: 0 0 auto; width: 2.4rem; border: 1px solid var(--border); background: var(--surface); color: var(--text);
		border-radius: var(--radius-sm); font-weight: 800;
	}
	.sens:disabled { opacity: 0.4; cursor: default; }
	.badge { font-size: 0.72rem; border-radius: 999px; padding: 0.1rem 0.5rem; font-weight: 700; }
	.badge.pub { background: color-mix(in srgb, var(--paye) 20%, transparent); color: var(--paye); }
	.badge.achat { background: color-mix(in srgb, var(--faux) 18%, transparent); color: var(--faux); }
	.badge.periode { background: color-mix(in srgb, var(--doute) 20%, transparent); color: var(--doute); }
	.classement li > p.soft { margin-top: 0.5rem; }
	.badge.faible { background: var(--surface-soft); color: var(--text-soft); margin-right: 0.3rem; }

	.barre-legende { display: flex; justify-content: space-between; gap: 0.5rem; flex-wrap: wrap; font-size: 0.78rem; color: var(--text-soft); margin-top: 0.7rem; }
	.barre { display: flex; height: 10px; border-radius: 999px; overflow: hidden; background: var(--surface-soft); margin-top: 0.25rem; }
	.barre.grande { height: 14px; margin: 0.8rem 0; }
	.barre.fine { height: 8px; margin: 0; flex: 1; }
	.barre span { display: block; height: 100%; }
	.org, .vrai { background: var(--vrai); }
	.paye { background: var(--paye); }
	.faux { background: var(--faux); }
	.doute { background: var(--doute); }
	.pastille { display: inline-block; width: 0.6rem; height: 0.6rem; border-radius: 50%; margin-right: 0.25rem; vertical-align: baseline; }

	dl { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 0.5rem 1rem; margin: 0.8rem 0 0; }
	dl div { display: grid; }
	dt { font-size: 0.75rem; color: var(--text-soft); }
	dd { margin: 0; font-weight: 700; font-variant-numeric: tabular-nums; }

	.tuiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.6rem; }
	.tuile { display: grid; gap: 0.2rem; }
	.tuile strong { font-size: 1.8rem; font-variant-numeric: tabular-nums; }

	.puces { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0 0.8rem; }
	.puces button { border: 1px solid var(--border); background: var(--surface); color: var(--text); border-radius: 999px; padding: 0.35rem 0.75rem; font-size: 0.85rem; }
	.puces button[aria-pressed='true'] { background: var(--text); color: var(--bg); border-color: var(--text); }
	.puces button.faux, .puces button.doute, .puces button.reel { background: var(--surface); }
	.puces button.faux[aria-pressed='true'] { background: var(--faux); color: #fff; border-color: var(--faux); }
	.puces button.doute[aria-pressed='true'] { background: var(--doute); color: #fff; border-color: var(--doute); }
	.puces button.reel[aria-pressed='true'] { background: var(--vrai); color: #fff; border-color: var(--vrai); }

	.comptes p { margin: 0.4rem 0 0; }
	.verdicts { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.7rem; align-items: center; }
	.verdicts .ouvrir {
		font-weight: 700; color: var(--primary); text-decoration: none; margin-right: auto;
		padding: 0.35rem 0; font-size: 0.85rem;
	}
	.verdicts button {
		border: 1px solid var(--border); background: var(--surface); color: var(--text);
		border-radius: 999px; padding: 0.35rem 0.75rem; font-size: 0.82rem;
	}
	.verdicts button.v-retire[aria-pressed='true'] { background: var(--text); color: var(--bg); border-color: var(--text); }
	.verdicts button.v-faux[aria-pressed='true'] { background: var(--faux); color: #fff; border-color: var(--faux); }
	.verdicts button.v-vrai[aria-pressed='true'] { background: var(--vrai); color: #fff; border-color: var(--vrai); }
	.pct { font-weight: 800; border-radius: 999px; padding: 0.15rem 0.55rem; color: #fff; font-size: 0.85rem; font-variant-numeric: tabular-nums; }
	.pct.faux { background: var(--faux); }
	.pct.doute { background: var(--doute); }
	.pct.reel { background: var(--vrai); }

	.pays li { display: grid; grid-template-columns: minmax(90px, 30%) 1fr 4.5rem; align-items: center; gap: 0.6rem; font-size: 0.9rem; }
	.pays .chiffre { text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; }
	.pays .nom { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.pied { margin-top: 1.5rem; text-align: center; }

	.barre-statut {
		position: sticky; top: 0; z-index: 2; display: flex; align-items: center; gap: 0.45rem;
		padding: 0.45rem 0.2rem; margin: -0.4rem 0 0.6rem; background: var(--bg); font-size: 0.85rem; color: var(--text-soft);
	}
	.barre-statut .recharger { margin-left: auto; font-size: 0.85rem; }
	.barre-statut .recharger:disabled { opacity: 0.5; cursor: default; }
	.pic { font-weight: 800; width: 1rem; text-align: center; }
	.pic.ok { color: var(--vrai); }
	.roue {
		width: 0.9rem; height: 0.9rem; border-radius: 50%; border: 2px solid var(--border);
		border-top-color: var(--primary); animation: tourne 0.7s linear infinite; flex: 0 0 auto;
	}
	@keyframes tourne { to { transform: rotate(360deg); } }
	@media (prefers-reduced-motion: reduce) { .roue { animation-duration: 2s; } }
</style>
