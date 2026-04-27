import { cloudflare } from "@cloudflare/vite-plugin";
import tailwindcss from "@tailwindcss/vite";
import { devtools } from "@tanstack/devtools-vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const config = defineConfig({
	resolve: { tsconfigPaths: true },
	plugins: [
		tailwindcss(),
		devtools(),
		cloudflare({ viteEnvironment: { name: "ssr" } }),
		tanstackStart({
			// Pre-render every marketing route to static HTML at build time.
			// Server functions (e.g. waitlist) still run dynamically — only
			// the document shells become static.
			prerender: {
				enabled: true,
				crawlLinks: true,
				autoSubfolderIndex: true,
			},
			pages: [
				{
					path: "/",
					sitemap: { priority: 1.0, changefreq: "weekly" },
				},
			],
			sitemap: {
				enabled: true,
				host: "https://boardwright.dev",
			},
		}),
		viteReact(),
	],
});

export default config;
