<script lang="ts">
	// Espace admin, onglet Stories : ce que l'appli Instagram ne permet pas (classer toutes les stories passées, voir
	// lesquelles mériteraient d'aller à la une, repérer les à la une qu'on n'a plus alimentées depuis longtemps).
	import { date, nombre, pct } from '#lib/admin.ts';
	import {
		CRITERES_STORY,
		TRIS_UNE,
		aMettreALaUne,
		synthese,
		trierALaUne,
		trierStories,
		type AlaUne,
		type CritereStory,
		type FiltreUne,
		type Story,
		type TriUne
	} from '#lib/stories.ts';

	let { stories = [], highlights = [] }: { stories: Story[]; highlights: AlaUne[] } = $props();

	let critere: CritereStory = $state('vues');
	let sens: 'desc' | 'asc' = $state('desc');
	let une: FiltreUne = $state('toutes');
	let combien = $state(20);
	let triUne: TriUne = $state('vues_moyenne');
	let cassees = $state(new Set<string>());

	const resume = $derived(synthese(stories));
	const liste = $derived(trierStories(stories, critere, sens, une).slice(0, combien));
	const suggestions = $derived(aMettreALaUne(stories));
	const alaune = $derived(trierALaUne(highlights, triUne));
	const valeurStory = (s: Story) =>
		critere === 'taux_sortie' ? pct(s.taux_sortie, 1) : critere === 'publiee_le' ? date(s.publiee_le) : nombre(s[critere]);
	const heureTxt = (h: number) => `${h} h – ${h + 1} h`;
	const casse = (id: string) => (cassees = new Set(cassees).add(id));
</script>

<section class="stories">
	{#if !stories.length && !highlights.length}
		<p class="carte soft">
			Pas encore de story mesurée. Instagram ne donne les chiffres d’une story que pendant ses 24 h : lance
			<code>load_bronze.py --seulement-stories</code> plusieurs fois par jour (voir le README de clearmind-tools).
		</p>
	{/if}

	{#if stories.length}
		<div class="tuiles">
			<div class="carte tuile">
				<span class="soft">Stories mesurées</span>
				<strong>{nombre(resume.nb)}</strong>
				<span class="soft petit">du {date(resume.plus_ancienne)} au {date(resume.plus_recente)}</span>
			</div>
			<div class="carte tuile">
				<span class="soft">Vues moyennes</span>
				<strong>{nombre(resume.vues_moyenne)}</strong>
				<span class="soft petit">taux de sortie moyen {pct(resume.taux_sortie_moyen, 1)}</span>
			</div>
			{#if resume.meilleure_heure}
				<div class="carte tuile">
					<span class="soft">Meilleure heure</span>
					<strong>{heureTxt(resume.meilleure_heure.heure)}</strong>
					<span class="soft petit">{nombre(resume.meilleure_heure.vues)} vues en moyenne ({resume.meilleure_heure.nb} stories)</span>
				</div>
			{/if}
		</div>
		{#if resume.par_type.length > 1}
			<p class="soft petit">
				{resume.par_type.map((t) => `${t.type === 'video' ? 'Vidéos' : t.type === 'image' ? 'Photos' : t.type} : ${nombre(t.vues_moyenne)} vues en moyenne (${t.nb})`).join(' · ')}
			</p>
		{/if}

		{#if suggestions.length}
			<h2>À mettre à la une</h2>
			<p class="soft petit">Tes stories les plus vues (au moins 1,5 × la médiane) qui ne sont dans aucune story à la une.</p>
			<ul class="bande">
				{#each suggestions as s (s.story_id)}
					<li>
						<a class="apercu" href={s.url ?? undefined} target="_blank" rel="noopener noreferrer">
							{#if s.miniature && !cassees.has(s.story_id)}
								<img src={s.miniature} alt="" loading="lazy" referrerpolicy="no-referrer" onerror={() => casse(s.story_id)} />
							{:else}<span>{s.type_story === 'video' ? '▶' : '▢'}</span>{/if}
						</a>
						<strong>{nombre(s.vues)}</strong>
						<span class="soft petit">{date(s.publiee_le)}</span>
					</li>
				{/each}
			</ul>
		{/if}

		<h2>Toutes les stories</h2>
		<div class="reglages">
			<label>
				Classer par
				<span class="tri">
					<select bind:value={critere}>
						{#each CRITERES_STORY as c (c.id)}<option value={c.id}>{c.label}</option>{/each}
					</select>
					<button type="button" class="sens" aria-label={sens === 'desc' ? 'Décroissant' : 'Croissant'}
						onclick={() => (sens = sens === 'desc' ? 'asc' : 'desc')}>{sens === 'desc' ? '↓' : '↑'}</button>
				</span>
			</label>
			<label>
				Lesquelles
				<select bind:value={une}>
					<option value="toutes">toutes</option>
					<option value="a_la_une">à la une</option>
					<option value="pas_a_la_une">pas à la une</option>
				</select>
			</label>
			<label>
				Combien
				<select bind:value={combien}>
					<option value={20}>20</option>
					<option value={50}>50</option>
					<option value={5000}>Tout</option>
				</select>
			</label>
		</div>
		<ol class="liste">
			{#each liste as s, i (s.story_id)}
				<li class="carte">
					<span class="rang">{i + 1}</span>
					<a class="apercu petit-apercu" href={s.url ?? undefined} target="_blank" rel="noopener noreferrer" tabindex="-1" aria-hidden="true">
						{#if s.miniature && !cassees.has(s.story_id)}
							<img src={s.miniature} alt="" loading="lazy" referrerpolicy="no-referrer" onerror={() => casse(s.story_id)} />
						{:else}<span>{s.type_story === 'video' ? '▶' : '▢'}</span>{/if}
					</a>
					<div class="infos">
						<span>
							{date(s.publiee_le)}{s.heure != null ? ` · ${s.heure} h` : ''}
							{#if s.a_la_une}<span class="badge une">À la une : {s.a_la_une}</span>{/if}
							{#if s.chiffres_partiels}<span class="badge partiel" title="Relevée moins de 20 h après sa publication">partiel</span>{/if}
						</span>
						<span class="soft petit">
							{nombre(s.vues)} vues · {nombre(s.portee)} portée · {nombre(s.reponses)} réponses · {nombre(s.partages)} partages
							{#if s.abonnements}· {nombre(s.abonnements)} abonnements{/if} · sorties {pct(s.taux_sortie, 1)}
						</span>
					</div>
					<strong class="valeur">{valeurStory(s)}</strong>
				</li>
			{/each}
		</ol>
	{/if}

	{#if highlights.length}
		<h2>Stories à la une</h2>
		<div class="reglages">
			<label>
				Classer par
				<select bind:value={triUne}>
					{#each TRIS_UNE as t (t.id)}<option value={t.id}>{t.label}</option>{/each}
				</select>
			</label>
		</div>
		<ul class="liste">
			{#each alaune as h (h.highlight_id)}
				<li class="carte">
					<span class="apercu rond" aria-hidden="true">
						{#if (h.couverture || h.miniature_exemple) && !cassees.has('h:' + h.highlight_id)}
							<img src={h.couverture ?? h.miniature_exemple} alt="" loading="lazy" referrerpolicy="no-referrer" onerror={() => casse('h:' + h.highlight_id)} />
						{:else}<span>{h.titre.slice(0, 1).toUpperCase()}</span>{/if}
					</span>
					<div class="infos">
						<strong>{h.titre}</strong>
						<span class="soft petit">
							{nombre(h.nb_stories)} stories · du {date(h.plus_ancienne)} au {date(h.plus_recente)}
							{#if h.jours_depuis_ajout != null && h.jours_depuis_ajout > 90}<span class="badge vieux">rien ajouté depuis {nombre(h.jours_depuis_ajout)} jours</span>{/if}
						</span>
						<span class="soft petit">
							{#if h.stories_mesurees}
								{nombre(h.vues_moyenne)} vues en moyenne, max {nombre(h.vues_max)} ({h.stories_mesurees} mesurée{h.stories_mesurees > 1 ? 's' : ''} sur {h.nb_stories})
							{:else}aucune story mesurée (toutes antérieures à la collecte){/if}
						</span>
					</div>
				</li>
			{/each}
		</ul>
	{/if}

	<p class="soft petit">
		Instagram ne donne les chiffres d’une story que pendant ses 24 h en ligne : seules les stories collectées à ce
		moment-là sont mesurées. Les likes de story ne sont disponibles par aucune API.
	</p>
</section>

<style>
	.stories h2 { font-size: 1.05rem; margin: 1.2rem 0 0.3rem; }
	.soft { color: var(--text-soft); margin: 0; }
	.petit { font-size: 0.85rem; }
	.carte { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 0.8rem 1rem; box-shadow: var(--shadow); }
	.tuiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.6rem; margin-bottom: 0.5rem; }
	.tuile { display: grid; gap: 0.2rem; }
	.tuile strong { font-size: 1.6rem; font-variant-numeric: tabular-nums; }
	.reglages { display: flex; flex-wrap: wrap; gap: 0.6rem; align-items: end; margin: 0.4rem 0; }
	.reglages label { flex: 1 1 140px; display: grid; gap: 0.25rem; font-size: 0.85rem; color: var(--text-soft); }
	select { font: inherit; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.55rem 0.7rem; min-width: 0; }
	.tri { display: flex; gap: 0.3rem; }
	.tri select { flex: 1; }
	.sens { width: 2.4rem; border: 1px solid var(--border); background: var(--surface); color: var(--text); border-radius: var(--radius-sm); font-weight: 800; cursor: pointer; }
	.liste { list-style: none; padding: 0; margin: 0.6rem 0; display: grid; gap: 0.5rem; }
	.liste li { display: flex; align-items: center; gap: 0.7rem; }
	.rang { font-weight: 800; color: var(--text-soft); width: 1.6rem; text-align: center; }
	.infos { flex: 1; min-width: 0; display: grid; gap: 0.15rem; }
	.valeur { font-size: 1.2rem; font-variant-numeric: tabular-nums; }
	.apercu {
		flex: 0 0 auto; width: 64px; height: 112px; border-radius: var(--radius-sm); overflow: hidden; display: grid; place-items: center;
		background: var(--surface-soft); color: var(--text-soft); text-decoration: none; font-weight: 800;
	}
	.apercu img { width: 100%; height: 100%; object-fit: cover; display: block; }
	.petit-apercu { width: 40px; height: 70px; }
	.apercu.rond { width: 52px; height: 52px; border-radius: 50%; }
	.bande { list-style: none; padding: 0; margin: 0.5rem 0; display: flex; gap: 0.6rem; overflow-x: auto; }
	.bande li { display: grid; gap: 0.15rem; justify-items: center; }
	.badge { font-size: 0.72rem; border-radius: 999px; padding: 0.1rem 0.5rem; font-weight: 700; margin-left: 0.3rem; }
	.badge.une { background: color-mix(in srgb, var(--primary) 18%, transparent); color: var(--primary); }
	.badge.partiel { background: var(--surface-soft); color: var(--text-soft); }
	.badge.vieux { background: color-mix(in srgb, var(--accent) 20%, transparent); color: var(--accent); }
	code { font-size: 0.85em; }
</style>
