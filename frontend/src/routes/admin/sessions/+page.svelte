<script lang="ts">
	// Espace admin : mes sessions Claude Code (titres, statuts, mes messages et pièces jointes, PR, artifacts, fichiers),
	// pour retrouver où j'ai parlé de quoi. L'index vient de /api/admin/claude ; rien n'est gardé sur l'appareil.
	import { onMount } from 'svelte';
	import {
		ICONES,
		STATUTS,
		compterPieces,
		compterSorties,
		dateCourte,
		dateHeure,
		entreesTrouvees,
		extrait,
		filtrerSessions,
		groupePriorite,
		lireTitre,
		type IndexClaude,
		type SessionClaude,
		type Statut,
		type Tri,
		type TypePiece
	} from '#lib/sessions-claude.ts';

	let etat: 'chargement' | 'connexion' | 'ferme' | 'ouvert' | 'erreur' = $state('chargement');
	let index: IndexClaude = $state({ genere_le: null, sessions: [] });
	let recherche = $state('');
	let statuts: Statut[] = $state([]);
	let piece: TypePiece | '' = $state('');
	let tri: Tri = $state('priorite');
	let ouverte: string | null = $state(null);
	let affiches = $state(30);

	const trouvees = $derived(filtrerSessions(index.sessions, { recherche, statuts, piece, tri }));

	onMount(async () => {
		const res = await fetch('/api/admin/claude', { credentials: 'same-origin' }).catch(() => null);
		if (res?.ok) {
			index = await res.json();
			etat = 'ouvert';
		} else if (res?.status === 401) etat = 'connexion';
		else if (res?.status === 404) etat = 'ferme';
		else etat = 'erreur';
	});

	function basculerStatut(s: Statut) {
		statuts = statuts.includes(s) ? statuts.filter((x) => x !== s) : [...statuts, s];
		affiches = 30;
	}

	const classeStatut = (s: Statut) =>
		s === 'attend ma réponse' ? 'attente' : s === 'en cours' ? 'cours' : s === 'en échec' ? 'echec' : s === 'archivée' ? 'archive' : 'fini';
	const piecesDe = (s: SessionClaude) => Object.entries(compterPieces(s)) as [TypePiece, number][];
	const nomPr = (url: string) => url.replace('https://github.com/', '').replace('/pull/', ' #');
</script>

<svelte:head>
	<title>Sessions Claude · Admin</title>
	<meta name="robots" content="noindex, nofollow" />
</svelte:head>

<div class="admin">
	<header>
		<div>
			<h1>Sessions Claude</h1>
			<p class="soft">
				{#if index.genere_le}Index du {dateHeure(index.genere_le)} · {index.sessions.length} sessions{:else}Ce que j’ai demandé, et ce qui en est sorti{/if}
			</p>
		</div>
		<a class="lien" href="/admin/">Stats Instagram</a>
	</header>

	{#if etat === 'chargement'}
		<p class="soft">Chargement…</p>
	{:else if etat === 'connexion'}
		<p class="card">Connecte-toi d’abord sur <a href="/admin/">l’espace admin</a>, puis reviens ici.</p>
	{:else if etat === 'ferme'}
		<p class="card">L’espace admin n’est pas activé sur ce serveur.</p>
	{:else if etat === 'erreur'}
		<p class="card erreur">Index indisponible pour le moment.</p>
	{:else if !index.sessions.length}
		<p class="card">
			Pas encore d’index. Dans la session « observateur », demande « mets à jour l’index des sessions » : elle le génère
			et l’envoie ici.
		</p>
	{:else}
		<div class="reglages">
			<input class="recherche" type="search" placeholder="Chercher (Spotify, airflow ovh, mint-health…)" bind:value={recherche}
				oninput={() => (affiches = 30)} aria-label="Chercher dans les sessions" />
			<select bind:value={piece} aria-label="Type de pièce jointe">
				<option value="">Toutes les pièces</option>
				{#each ['image', 'son', 'video', 'document'] as t (t)}<option value={t}>{ICONES[t as TypePiece]} {t === 'video' ? 'vidéo' : t}</option>{/each}
			</select>
			<select bind:value={tri} aria-label="Trier">
				<option value="priorite">Par priorité</option>
				<option value="recentes">Activité récente</option>
			</select>
		</div>
		<div class="puces">
			{#each STATUTS as s (s)}
				<button class="puce" aria-pressed={statuts.includes(s)} onclick={() => basculerStatut(s)}>{s}</button>
			{/each}
		</div>
		<p class="soft petit">{trouvees.length} session{trouvees.length > 1 ? 's' : ''}</p>

		<ul class="sessions">
			{#each trouvees.slice(0, affiches) as s, i (s.id)}
				{@const messages = entreesTrouvees(s, recherche)}
				{@const t = lireTitre(s.titre)}
				{#if tri === 'priorite' && (i === 0 || groupePriorite(trouvees[i - 1]) !== groupePriorite(s))}
					<li class="groupe"><h2>{groupePriorite(s)}</h2></li>
				{/if}
				<li class="card">
					<div class="tete">
						{#if t.priorite}<span class="prio" class:range={t.priorite === 'zz'}>{t.priorite}</span>{/if}
						{#if t.projet}<span class="projet">{t.projet}</span>{/if}
						<a class="titre" href={s.url} target="_blank" rel="noopener noreferrer">{t.nom}</a>
						<span class="badge {classeStatut(s.statut)}">{s.statut}</span>
					</div>
					<p class="soft petit">
						{dateCourte(s.cree_le)} → {dateCourte(s.maj_le)} · {s.entrees.length} message{s.entrees.length > 1 ? 's' : ''}
						{#each piecesDe(s) as [t, n] (t)}{' · '}{ICONES[t]} {n}{/each}
						{#if compterSorties(s)}{' · '}{compterSorties(s)} sortie{compterSorties(s) > 1 ? 's' : ''}{/if}
						{#if s.cout_usd != null}{' · '}{Math.round(s.cout_usd)} ${/if}
					</p>
					{#if s.a_faire}<p class="attend">⏳ {s.a_faire}</p>{:else if s.dernier_resultat}<p class="petit">✅ {s.dernier_resultat}</p>{/if}
					{#if messages.length && ouverte !== s.id}
						<ul class="trouves">
							{#each messages.slice(0, 3) as e (e.le)}
								<li><span class="soft">{dateHeure(e.le)}</span> {extrait(e.texte, recherche, 160)}</li>
							{/each}
							{#if messages.length > 3}<li class="soft">… et {messages.length - 3} autre{messages.length > 4 ? 's' : ''}</li>{/if}
						</ul>
					{/if}
					<button class="lien petit" onclick={() => (ouverte = ouverte === s.id ? null : s.id)}>
						{ouverte === s.id ? 'Replier' : 'Détails'}
					</button>

					{#if ouverte === s.id}
						<div class="details">
							{#if s.depots?.length}<p class="petit"><strong>Dépôts :</strong> {s.depots.join(', ')}</p>{/if}
							{#if s.branches?.length}<p class="petit"><strong>Branches :</strong> {s.branches.join(', ')}</p>{/if}

							<h3>Entrées ({s.entrees?.length ?? 0})</h3>
							<ol class="entrees">
								{#each s.entrees ?? [] as e, i (i)}
									<li>
										<span class="soft petit">{dateHeure(e.le)}</span>
										{#if e.texte}<p class="texte">{extrait(e.texte, recherche, 600)}</p>{/if}
										{#each e.pieces ?? [] as p, j (j)}<span class="piece">{ICONES[p.type]} {p.nom}</span>{/each}
									</li>
								{/each}
							</ol>

							<h3>Sorties ({compterSorties(s)})</h3>
							{#if !compterSorties(s)}<p class="soft petit">Aucune PR, artifact ni fichier repéré.</p>{/if}
							<ul class="sorties">
								{#each s.sorties?.prs ?? [] as p, j (j)}
									<li>🔀 <a href={p.url} target="_blank" rel="noopener noreferrer">{nomPr(p.url)}</a>{#if p.titre} · {p.titre}{/if}</li>
								{/each}
								{#each s.sorties?.artifacts ?? [] as a, j (j)}
									<li>✨ <a href={a.url} target="_blank" rel="noopener noreferrer">{a.titre}</a></li>
								{/each}
								{#each s.sorties?.fichiers ?? [] as f, j (j)}
									<li>📦 {f.nom}{#if f.legende} · <span class="soft">{f.legende}</span>{/if}</li>
								{/each}
								{#each s.sorties?.commits ?? [] as c, j (j)}
									<li>💾 <code>{(c.sha ?? '').slice(0, 7)}</code> {c.message}{#if c.depot} <span class="soft">({c.depot})</span>{/if}</li>
								{/each}
							</ul>
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
	header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 1rem; }
	h1 { margin: 0; font-size: 1.5rem; }
	h3 { font-size: 0.95rem; margin: 1rem 0 0.4rem; }
	.soft { color: var(--text-soft); margin: 0; }
	.petit { font-size: 0.85rem; }
	.erreur { color: var(--danger); }
	.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem; box-shadow: var(--shadow); }
	.lien { background: none; border: 0; color: var(--primary); padding: 0; text-decoration: underline; }
	.plus { display: block; margin: 0.5rem auto 1rem; }
	.reglages { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-bottom: 0.5rem; }
	.recherche { flex: 1; min-width: 200px; }
	.puces { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.3rem 0 0.6rem; }
	.puce { border: 1px solid var(--border); background: var(--surface); border-radius: 999px; padding: 0.25rem 0.7rem; font-size: 0.85rem; }
	.puce[aria-pressed='true'] { background: var(--primary); color: #fff; border-color: var(--primary); }
	.sessions { list-style: none; padding: 0; margin: 0.6rem 0; display: grid; gap: 0.6rem; }
	.sessions > li { display: grid; gap: 0.35rem; min-width: 0; }
	.tete { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
	.titre { font-weight: 700; flex: 1; min-width: 0; overflow-wrap: anywhere; }
	.groupe { list-style: none; margin-top: 0.4rem; }
	.groupe h2 { font-size: 0.95rem; margin: 0; color: var(--text-soft); }
	.prio { font-weight: 800; font-variant-numeric: tabular-nums; background: var(--primary); color: #fff; border-radius: 6px; padding: 0 0.4rem; font-size: 0.85rem; }
	.prio.range { background: var(--surface-soft); color: var(--text-soft); }
	.projet { font-size: 0.75rem; border: 1px solid var(--border); border-radius: 999px; padding: 0.05rem 0.5rem; }
	.badge { font-size: 0.72rem; border-radius: 999px; padding: 0.1rem 0.5rem; font-weight: 700; background: var(--surface-soft); }
	.badge.attente { background: #f6c34a; color: #3a2a00; }
	.badge.cours { background: var(--primary); color: #fff; }
	.badge.echec { background: var(--danger); color: #fff; }
	.badge.archive { opacity: 0.7; }
	.attend { margin: 0; font-size: 0.9rem; }
	.trouves { margin: 0; padding-left: 1rem; font-size: 0.85rem; display: grid; gap: 0.2rem; overflow-wrap: anywhere; }
	.details { border-top: 1px solid var(--border); padding-top: 0.5rem; min-width: 0; }
	.details p { margin: 0.2rem 0; overflow-wrap: anywhere; }
	.entrees { padding-left: 1.2rem; display: grid; gap: 0.5rem; margin: 0; }
	.texte { white-space: pre-wrap; overflow-wrap: anywhere; font-size: 0.9rem; }
	.piece { display: inline-block; font-size: 0.8rem; background: var(--surface-soft); border-radius: 6px; padding: 0.1rem 0.4rem; margin: 0.15rem 0.3rem 0 0; overflow-wrap: anywhere; }
	.sorties { list-style: none; padding: 0; margin: 0; display: grid; gap: 0.3rem; font-size: 0.9rem; overflow-wrap: anywhere; }
</style>
