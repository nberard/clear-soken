<script lang="ts">
	import { onMount } from 'svelte';
	import { load, save, uid, MOODS, type MoodEntry } from '#lib/storage.ts';

	let entries: MoodEntry[] = $state([]);
	let mood: number | null = $state(null);
	let note = $state('');

	onMount(() => (entries = load<MoodEntry[]>('moods', [])));

	function add() {
		if (!mood) return;
		entries = [{ id: uid(), at: new Date().toISOString(), mood, note: note.trim() }, ...entries];
		save('moods', entries);
		mood = null;
		note = '';
	}

	function remove(id: string) {
		entries = entries.filter((e) => e.id !== id);
		save('moods', entries);
	}

	const fmt = (iso: string) =>
		new Date(iso).toLocaleString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

	// 7 derniers jours : moyenne par jour, pour la mini frise
	let week = $derived.by(() => {
		const days: { label: string; avg: number | null }[] = [];
		for (let i = 6; i >= 0; i--) {
			const d = new Date();
			d.setDate(d.getDate() - i);
			const key = d.toDateString();
			const of = entries.filter((e) => new Date(e.at).toDateString() === key);
			days.push({
				label: d.toLocaleDateString('fr-FR', { weekday: 'narrow' }),
				avg: of.length ? of.reduce((s, e) => s + e.mood, 0) / of.length : null
			});
		}
		return days;
	});
</script>

<h1>Mon humeur</h1>
<p class="lead">Pas de bonne ou de mauvaise réponse.</p>

<div class="card">
	<div class="moods" role="radiogroup" aria-label="Mon humeur">
		{#each MOODS as m (m.value)}
			<button
				role="radio"
				aria-checked={mood === m.value}
				aria-label={m.label}
				class:active={mood === m.value}
				onclick={() => (mood = m.value)}>{m.emoji}</button
			>
		{/each}
	</div>
	{#if mood}<p class="muted center">{MOODS[mood - 1].label}</p>{/if}
	<textarea bind:value={note} rows="2" placeholder="Un mot, une pensée (facultatif)"></textarea>
	<button class="btn full" disabled={!mood} onclick={add}>Enregistrer</button>
</div>

<h2>Ma semaine</h2>
<div class="card week" aria-label="Humeur des 7 derniers jours">
	{#each week as d, i (i)}
		<div class="day">
			<div class="bar" style:height={d.avg ? `${d.avg * 16}px` : '4px'} class:empty={!d.avg}></div>
			<span class="muted">{d.label}</span>
		</div>
	{/each}
</div>

{#if entries.length}
	<h2>Mes notes</h2>
	{#each entries as e (e.id)}
		<div class="card entry">
			<span class="emoji" aria-hidden="true">{MOODS[e.mood - 1].emoji}</span>
			<div class="grow">
				<div class="muted">{fmt(e.at)}</div>
				{#if e.note}<p>{e.note}</p>{/if}
			</div>
			<button class="del" aria-label="Supprimer cette note" onclick={() => remove(e.id)}>✕</button>
		</div>
	{/each}
	<p class="muted">Tu peux montrer ces notes à ton équipe soignante si tu le souhaites.</p>
{/if}

<style>
	.moods { display: flex; justify-content: space-between; margin-bottom: 0.3rem; }
	.moods button {
		font-size: 2rem;
		width: 56px;
		height: 56px;
		border-radius: 50%;
		border: 2px solid transparent;
		background: var(--surface-soft);
		cursor: pointer;
	}
	.moods button.active { border-color: var(--primary); background: var(--primary-soft); }
	.center { text-align: center; }
	textarea { margin: 0.6rem 0; }
	.full { width: 100%; }
	.week { display: flex; justify-content: space-between; align-items: flex-end; height: 120px; }
	.day { display: flex; flex-direction: column; align-items: center; gap: 4px; }
	.bar { width: 22px; border-radius: 8px; background: var(--primary); }
	.bar.empty { background: var(--border); }
	.entry { display: flex; gap: 0.8rem; align-items: flex-start; }
	.emoji { font-size: 1.6rem; }
	.grow { flex: 1; }
	.del { background: none; border: none; color: var(--text-soft); font-size: 1rem; cursor: pointer; padding: 0.3rem; }
</style>
