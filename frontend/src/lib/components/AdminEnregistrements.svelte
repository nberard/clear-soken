<script lang="ts">
	// Espace admin, onglet Enregistrements : tout voir et retrouver ce qu'Instagram cache (publications rangées nulle
	// part, rangées dans plusieurs collections, recherche par auteur ou texte). Lecture seule : rien n'est modifié.
	import { date, nombre, pct } from '#lib/admin.ts';
	import {
		TRIS_ENR,
		filtrerEnregistrements,
		nomsCollections,
		topAuteurs,
		trierEnregistrements,
		type Collection,
		type Enregistrement,
		type FiltreEnr,
		type TriEnr
	} from '#lib/enregistrements.ts';

	let { enregistrements = [], collections = [] }: { enregistrements: Enregistrement[]; collections: Collection[] } = $props();

	let filtre: FiltreEnr = $state({ collection: '', dansPlusieurs: false, type: '', recherche: '' });
	let tri: TriEnr = $state('enregistrement');
	let affiches = $state(60);
	let cassees = $state(new Set<string>());

	const vraies = $derived(collections.filter((c) => c.type_collection !== 'TOUT'));
	const tout = $derived(collections.find((c) => c.type_collection === 'TOUT'));
	const nulle = $derived(enregistrements.filter((e) => e.rangee_nulle_part).length);
	const plusieurs = $derived(enregistrements.filter((e) => e.dans_plusieurs).length);
	const liste = $derived(trierEnregistrements(filtrerEnregistrements(enregistrements, filtre), tri));
	const auteurs = $derived(topAuteurs(filtrerEnregistrements(enregistrements, { ...filtre, recherche: '' }), 8));
	const types = $derived([...new Set(enregistrements.map((e) => e.type_publication).filter(Boolean))] as string[]);
	const voir = (f: Partial<FiltreEnr>) => {
		filtre = { collection: '', dansPlusieurs: false, type: '', recherche: '', ...f };
		affiches = 60;
	};
</script>

<section class="enr">
	{#if !enregistrements.length}
		<p class="carte soft">
			Pas encore d’enregistrements. Sur le PC : <code>python social_analytics/collections_instagram.py --charger</code>
			puis <code>dbt build</code> (compte principal, lecture seule ; voir le README de clearmind-tools).
		</p>
	{:else}
		<div class="tuiles">
			<button class="carte tuile" onclick={() => voir({})}>
				<span class="soft">Publications enregistrées</span>
				<strong>{nombre(tout?.publications ?? enregistrements.length)}</strong>
				<span class="soft petit">{nombre(vraies.length)} collections · relevé du {date(tout?.releve_le ?? null)}</span>
			</button>
			<button class="carte tuile" onclick={() => voir({ collection: '__aucune__' })}>
				<span class="soft">Rangées nulle part</span>
				<strong>{nombre(nulle)}</strong>
				<span class="soft petit">dans aucune collection · voir la liste</span>
			</button>
			<button class="carte tuile" onclick={() => voir({ dansPlusieurs: true })}>
				<span class="soft">Dans plusieurs collections</span>
				<strong>{nombre(plusieurs)}</strong>
				<span class="soft petit">voir la liste</span>
			</button>
		</div>

		<h2>Collections</h2>
		<ul class="cols">
			{#each vraies as c (c.collection_id)}
				<li>
					<button class="carte col" aria-pressed={filtre.collection === c.nom} onclick={() => voir({ collection: c.nom })}>
						<strong>{c.nom}</strong>
						<span class="soft petit">
							{nombre(c.publications)} publications · {nombre(c.auteurs)} auteurs · {pct(c.part_reels)} de réels
							{#if c.doublons} · {nombre(c.doublons)} aussi ailleurs{/if}
						</span>
						<span class="soft petit">publiées du {date(c.plus_ancienne)} au {date(c.plus_recente)}</span>
					</button>
				</li>
			{/each}
		</ul>

		<h2>Publications</h2>
		<div class="reglages">
			<label>
				Collection
				<select bind:value={filtre.collection}>
					<option value="">toutes</option>
					<option value="__aucune__">rangées nulle part</option>
					{#each vraies as c (c.collection_id)}<option value={c.nom}>{c.nom}</option>{/each}
				</select>
			</label>
			<label>
				Type
				<select bind:value={filtre.type}>
					<option value="">tous</option>
					{#each types as t (t)}<option value={t}>{t}</option>{/each}
				</select>
			</label>
			<label>
				Classer par
				<select bind:value={tri}>
					{#each TRIS_ENR as t (t.id)}<option value={t.id}>{t.label}</option>{/each}
				</select>
			</label>
			<label class="large">Chercher <input type="search" bind:value={filtre.recherche} placeholder="@auteur ou texte" autocapitalize="none" /></label>
			<label class="case"><input type="checkbox" bind:checked={filtre.dansPlusieurs} /> Dans plusieurs collections</label>
		</div>
		{#if auteurs.length}
			<p class="soft petit">
				Auteurs les plus enregistrés :
				{#each auteurs as a, i (a.auteur)}<button class="lien" onclick={() => (filtre.recherche = a.auteur)}>@{a.auteur}</button> ({a.nb}){i < auteurs.length - 1 ? ', ' : ''}{/each}
			</p>
		{/if}
		<p class="soft petit">{nombre(liste.length)} publication{liste.length > 1 ? 's' : ''}</p>

		<ul class="grille">
			{#each liste.slice(0, affiches) as e (e.media_pk)}
				<li class="carte pub">
					<a class="apercu" href={e.url ?? undefined} target="_blank" rel="noopener noreferrer">
						{#if e.miniature && !cassees.has(e.media_pk)}
							<img src={e.miniature} alt="" loading="lazy" referrerpolicy="no-referrer"
								onerror={() => (cassees = new Set(cassees).add(e.media_pk))} />
						{:else}<span>{e.type_publication === 'reel' ? '▶' : '▢'}</span>{/if}
					</a>
					<div class="infos">
						<a href={e.url ?? undefined} target="_blank" rel="noopener noreferrer">@{e.auteur ?? '?'}</a>
						<span class="soft petit">{e.type_publication} · {date(e.publiee_le)}{e.vues ? ` · ${nombre(e.vues)} vues` : ''}</span>
						{#if e.texte}<span class="texte petit">{e.texte}</span>{/if}
						<span class="badges">
							{#each nomsCollections(e) as n (n)}<span class="badge">{n}</span>{/each}
							{#if e.rangee_nulle_part}<span class="badge aucune">rangée nulle part</span>{/if}
						</span>
					</div>
				</li>
			{/each}
		</ul>
		{#if liste.length > affiches}
			<button class="lien plus" onclick={() => (affiches += 60)}>Voir 60 de plus ({nombre(liste.length - affiches)} restantes)</button>
		{/if}
		<p class="soft petit">
			Lecture seule : pour ranger une publication, ouvre-la (lien) et utilise l’enregistrement d’Instagram. Instagram ne
			donne pas la date d’enregistrement : « Enregistrées récemment » suit l’ordre de « Tout ».
		</p>
	{/if}
</section>

<style>
	.enr h2 { font-size: 1.05rem; margin: 1.2rem 0 0.3rem; }
	.soft { color: var(--text-soft); margin: 0; }
	.petit { font-size: 0.85rem; }
	.carte { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.8rem 1rem; box-shadow: var(--shadow); }
	button.carte { font: inherit; color: var(--text); text-align: left; cursor: pointer; width: 100%; }
	button.carte[aria-pressed='true'] { border-color: var(--primary); box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary) 30%, transparent); }
	.tuiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.6rem; }
	.tuile { display: grid; gap: 0.2rem; }
	.tuile strong { font-size: 1.6rem; font-variant-numeric: tabular-nums; }
	.cols { list-style: none; padding: 0; margin: 0.4rem 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.5rem; }
	.col { display: grid; gap: 0.15rem; }
	.reglages { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: end; margin: 0.4rem 0; }
	.reglages label { flex: 1 1 130px; display: grid; gap: 0.25rem; font-size: 0.85rem; color: var(--text-soft); }
	.reglages label.large { flex-basis: 200px; }
	.reglages .case { display: flex; align-items: center; gap: 0.4rem; flex: 0 0 auto; color: var(--text); white-space: nowrap; padding-bottom: 0.6rem; }
	.case input { width: 1.1rem; height: 1.1rem; accent-color: var(--primary); padding: 0; }
	select, input { font: inherit; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.55rem 0.7rem; min-width: 0; }
	.lien { background: none; border: 0; color: var(--primary); padding: 0; text-decoration: underline; cursor: pointer; font: inherit; }
	.plus { display: block; margin: 0.5rem auto 1rem; }
	.grille { list-style: none; padding: 0; margin: 0.5rem 0; display: grid; gap: 0.5rem; }
	.pub { display: flex; gap: 0.7rem; align-items: flex-start; }
	.apercu {
		flex: 0 0 auto; width: 64px; height: 80px; border-radius: var(--radius-sm); overflow: hidden; display: grid; place-items: center;
		background: var(--surface-soft); color: var(--text-soft); text-decoration: none; font-weight: 800;
	}
	.apercu img { width: 100%; height: 100%; object-fit: cover; display: block; }
	.infos { flex: 1; min-width: 0; display: grid; gap: 0.2rem; }
	.infos a { color: var(--text); font-weight: 700; }
	.texte { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
	.badges { display: flex; flex-wrap: wrap; gap: 0.3rem; }
	.badge { font-size: 0.72rem; border-radius: 999px; padding: 0.1rem 0.5rem; font-weight: 700; background: color-mix(in srgb, var(--primary) 16%, transparent); color: var(--primary); }
	.badge.aucune { background: color-mix(in srgb, var(--accent) 20%, transparent); color: var(--accent); }
	code { font-size: 0.85em; }
</style>
