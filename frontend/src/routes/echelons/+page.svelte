<script lang="ts">
	import { onMount } from 'svelte';
	import { load, save, uid, DEFAULT_STEPS, type Step } from '#lib/storage.ts';

	const LEVELS = ['', 'Prendre soin de moi', 'Aller vers les autres', 'Garder le lien', 'Préparer la sortie'];

	let steps: Step[] = $state([]);
	let custom = $state('');
	let customLevel = $state(1);

	onMount(() => (steps = load<Step[]>('steps', DEFAULT_STEPS)));

	function persist() {
		save('steps', steps);
	}

	function toggle(s: Step) {
		s.doneAt = s.doneAt ? null : new Date().toISOString();
		persist();
	}

	function add() {
		const label = custom.trim();
		if (!label) return;
		steps.push({ id: uid(), level: customLevel, label, doneAt: null });
		custom = '';
		persist();
	}

	function remove(id: string) {
		steps = steps.filter((s) => s.id !== id);
		persist();
	}

	let done = $derived(steps.filter((s) => s.doneAt).length);
</script>

<h1>Mes échelons</h1>
<p class="lead">Chaque petit pas compte. Tu peux les faire dans l’ordre que tu veux.</p>

<div class="card progress" aria-label="{done} sur {steps.length} échelons franchis">
	<div class="fill" style:width="{steps.length ? (done / steps.length) * 100 : 0}%"></div>
</div>
<p class="muted">{done} / {steps.length} franchis</p>

{#each [1, 2, 3, 4] as level (level)}
	<h2>{level}. {LEVELS[level]}</h2>
	{#each steps.filter((s) => s.level === level) as s (s.id)}
		<div class="card step" class:done={s.doneAt}>
			<label>
				<input type="checkbox" checked={!!s.doneAt} onchange={() => toggle(s)} />
				<span>{s.label}</span>
			</label>
			<button class="del" aria-label="Retirer cet échelon" onclick={() => remove(s.id)}>✕</button>
		</div>
	{/each}
{/each}

<h2>Ajouter mon propre échelon</h2>
<div class="card">
	<input bind:value={custom} placeholder="Ex. : appeler ma sœur" maxlength="120" />
	<div class="row">
		<select bind:value={customLevel} aria-label="Palier">
			{#each [1, 2, 3, 4] as l (l)}<option value={l}>{l}. {LEVELS[l]}</option>{/each}
		</select>
		<button class="btn" onclick={add} disabled={!custom.trim()}>Ajouter</button>
	</div>
</div>

<style>
	.progress { padding: 0; height: 14px; overflow: hidden; margin-bottom: 0.3rem; }
	.fill { height: 100%; background: var(--accent); transition: width 0.4s; }
	.step { display: flex; align-items: center; justify-content: space-between; padding: 0.6rem 0.9rem; }
	.step label { display: flex; align-items: center; gap: 0.7rem; flex: 1; cursor: pointer; }
	.step input { width: 24px; height: 24px; accent-color: var(--primary); }
	.step.done span { text-decoration: line-through; color: var(--text-soft); }
	.del { background: none; border: none; color: var(--text-soft); cursor: pointer; padding: 0.3rem; }
	.row { display: flex; gap: 0.5rem; margin-top: 0.6rem; }
	select { flex: 1; font: inherit; color: inherit; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0 0.5rem; min-width: 0; }
</style>
