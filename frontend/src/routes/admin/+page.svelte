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
		filtrerComptes,
		nombre,
		nomPays,
		pct,
		resumeAudience,
		top,
		valeurCritere,
		type Compte,
		type Critere,
		type FiltreComptes,
		type Pays,
		type Publication,
		type Qualite
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
	let combien = $state(10);
	let reelsSeulement = $state(true);
	let achetesSeulement = $state(false);
	let filtre: FiltreComptes = $state({ niveau: 'probablement faux', population: 'tous', recherche: '' });
	let affiches = $state(50);

	const classement = $derived(top(publications, critere, combien, reelsSeulement, achetesSeulement));
	const critereActif = $derived(CRITERES.find((c) => c.id === critere)!);
	const comptesFiltres = $derived(filtrerComptes(comptes, filtre));
	const niveaux = $derived(compterNiveaux(comptes));
	const audience = $derived(resumeAudience(pays));
	const maxPays = $derived(Math.max(1, ...pays.map((p) => p.abonnes)));
	const qAbonnes = $derived(qualite.find((q) => q.population === 'abonnes'));
	const qLikers = $derived(qualite.find((q) => q.population === 'likers'));

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

	async function toutCharger() {
		erreurs = {};
		const vues = [
			['publications', (l: Publication[]) => (publications = l)],
			['comptes', (l: Compte[]) => (comptes = l)],
			['qualite', (l: Qualite[]) => (qualite = l)],
			['pays', (l: Pays[]) => (pays = l)]
		] as const;
		await Promise.all(
			vues.map(async ([vue, poser]) => {
				try {
					(poser as (l: unknown) => void)(await charger(vue));
				} catch (e) {
					if ((e as Error).message !== 'session') erreurs[vue] = (e as Error).message;
				}
			})
		);
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

		{#if onglet === 'reels'}
			<section>
				<div class="reglages">
					<label>
						Classer par
						<select bind:value={critere}>
							{#each CRITERES as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
						</select>
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
				</div>
				<p class="soft petit">{critereActif.label} : {critereActif.aide}.</p>

				{#if erreurs.publications}
					<p class="erreur">Publications indisponibles : {erreurs.publications}</p>
				{:else if !classement.length}
					<p class="card soft">Aucune publication pour l’instant.</p>
				{/if}

				<ol class="classement">
					{#each classement as p, i (p.publication_id)}
						<li class="card">
							<div class="tete">
								<span class="rang">{i + 1}</span>
								<div class="titre">
									{#if p.url}<a href={p.url} target="_blank" rel="noopener noreferrer">{p.libelle_format} du {date(p.published_at)}</a>
									{:else}{p.libelle_format} du {date(p.published_at)}{/if}
									{#if p.boosts}<span class="badge pub">Boosté ×{p.boosts}</span>{/if}
									{#if p.likes_superieurs_aux_vues}<span class="badge achat" title="Plus de likes que de vues">Likes achetés</span>{/if}
								</div>
								<strong class="valeur">{valeurCritere(p, critere)}</strong>
							</div>

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
									<span>{pct(p.part_likes_faux)} de faux{#if p.estimation === 'likes au-delà des vues'}{' · au-delà des vues'}{/if}</span>
									<span><i class="pastille vrai"></i>authentiques {nombre(p.likes_authentiques_estimes)} · <i class="pastille faux"></i>faux {nombre(p.likes_faux_estimes)}</span>
								</div>
								<div class="barre" aria-hidden="true">
									<span class="vrai" style:width={largeur(p.likes_authentiques_estimes ?? 0, p.likes ?? 0)}></span>
									<span class="faux" style:width={largeur(p.likes_faux_estimes, p.likes ?? 0)}></span>
								</div>
							{:else}
								<p class="soft petit">Likers pas encore analysés, et pas plus de likes que de vues.</p>
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
							<option value="tous">abonnés et likers</option>
							<option value="abonnes">abonnés</option>
							<option value="likers">likers des réels</option>
						</select>
					</label>
					<label>Chercher <input type="search" bind:value={filtre.recherche} placeholder="@nom" autocapitalize="none" /></label>
				</div>

				{#if erreurs.comptes}<p class="erreur">Comptes indisponibles : {erreurs.comptes}</p>{/if}
				<ul class="comptes">
					{#each comptesFiltres.slice(0, affiches) as c (c.compte_id)}
						<li class="card">
							<div class="tete">
								<span class="pct {classeNiveau(c.niveau)}">{c.pct_faux} %</span>
								<a href={c.url} target="_blank" rel="noopener noreferrer">@{c.nom_compte}</a>
								<span class="soft petit">{[c.est_abonne && 'abonné', c.est_liker && `${c.reels_likes} réel${c.reels_likes > 1 ? 's' : ''} liké${c.reels_likes > 1 ? 's' : ''}`].filter(Boolean).join(' · ')}</span>
							</div>
							{#if c.raisons}<p class="petit">{c.raisons}</p>{/if}
							<p class="soft petit">{nombre(c.abonnes)} abonnés · {nombre(c.abonnements)} abonnements · {nombre(c.publications)} publications</p>
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
	.titre a, .comptes a { color: var(--text); font-weight: 700; }
	.valeur { font-size: 1.35rem; font-variant-numeric: tabular-nums; }
	.badge { font-size: 0.72rem; border-radius: 999px; padding: 0.1rem 0.5rem; font-weight: 700; }
	.badge.pub { background: color-mix(in srgb, var(--paye) 20%, transparent); color: var(--paye); }
	.badge.achat { background: color-mix(in srgb, var(--faux) 18%, transparent); color: var(--faux); }

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
	.pct { font-weight: 800; border-radius: 999px; padding: 0.15rem 0.55rem; color: #fff; font-size: 0.85rem; font-variant-numeric: tabular-nums; }
	.pct.faux { background: var(--faux); }
	.pct.doute { background: var(--doute); }
	.pct.reel { background: var(--vrai); }

	.pays li { display: grid; grid-template-columns: minmax(90px, 30%) 1fr 4.5rem; align-items: center; gap: 0.6rem; font-size: 0.9rem; }
	.pays .chiffre { text-align: right; font-variant-numeric: tabular-nums; font-weight: 700; }
	.pays .nom { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
	.pied { margin-top: 1.5rem; text-align: center; }
</style>
