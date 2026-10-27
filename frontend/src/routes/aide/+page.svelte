<script lang="ts">
	import { wipeAll } from '#lib/storage.ts';

	let wiped = $state(false);

	function wipe() {
		if (confirm('Effacer toutes tes notes, tes mémos vocaux et tes échelons de ce téléphone ?')) {
			wipeAll();
			wiped = true;
		}
	}
</script>

<h1>Besoin d’aide</h1>
<p class="lead">Tu n’es pas seul·e. Parler, c’est déjà prendre soin de toi.</p>

<div class="card first">
	<strong>Dans le service</strong>
	<p>Va voir un·e soignant·e ou utilise la sonnette de ta chambre. L’équipe est là pour ça, de jour comme de nuit.</p>
</div>

<a class="card call" href="tel:3114">
	<span class="num">3114</span>
	<span><strong>Numéro national de prévention du suicide</strong><br /><span class="muted">Gratuit, 24 h/24, 7 j/7</span></span>
</a>
<a class="card call" href="tel:15">
	<span class="num">15</span>
	<span><strong>SAMU</strong><br /><span class="muted">Urgence médicale</span></span>
</a>
<a class="card call" href="tel:112">
	<span class="num">112</span>
	<span><strong>Urgences</strong><br /><span class="muted">Depuis n’importe quel téléphone</span></span>
</a>
<a class="card call" href="sms:114">
	<span class="num">114</span>
	<span><strong>Urgence par SMS</strong><br /><span class="muted">Si tu ne peux pas parler</span></span>
</a>

<h2>Mes données</h2>
<div class="card">
	<p class="muted">Tes notes d’humeur, tes mémos vocaux et tes échelons sont seulement sur ce téléphone. Personne d’autre n’y a accès.</p>
	{#if wiped}
		<p><strong>C’est effacé.</strong></p>
	{:else}
		<button class="btn secondary" onclick={wipe}>Tout effacer</button>
	{/if}
</div>

<style>
	.first { background: var(--primary-soft); border-color: transparent; }
	.call { display: flex; align-items: center; gap: 1rem; color: inherit; text-decoration: none; }
	.num {
		min-width: 72px;
		text-align: center;
		font-size: 1.4rem;
		font-weight: 800;
		color: #fff;
		background: var(--danger);
		border-radius: var(--radius-sm);
		padding: 0.4rem 0.6rem;
	}
</style>
