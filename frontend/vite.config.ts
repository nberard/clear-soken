import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// Site 100 % statique, servi par le backend Rust (ou n'importe quel serveur web).
			adapter: adapter({ fallback: '200.html', precompress: true })
		})
	],
	server: {
		// En dev, l'API Rust tourne sur :8080
		proxy: { '/api': 'http://localhost:8080' }
	}
});
