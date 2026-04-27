import { TanStackDevtools } from "@tanstack/react-devtools";
import { createRootRoute, HeadContent, Scripts } from "@tanstack/react-router";
import { TanStackRouterDevtoolsPanel } from "@tanstack/react-router-devtools";
import { Footer, Header } from "../components/shared";

import appCss from "../styles.css?url";

const SITE_URL = "https://boardwright.dev";
const SITE_TITLE = "Boardwright — AI-native KiCad";
const SITE_DESCRIPTION =
	"Local-first AI co-pilot for KiCad. Describe a board; Claude drives your KiCad install through 41 tools across the full PCB workflow — research, schematic, layout, routing, fab outputs.";
const SITE_OG_IMAGE = `${SITE_URL}/og-image.png`;

const ORG_JSON_LD = {
	"@context": "https://schema.org",
	"@type": "Organization",
	name: "Boardwright",
	url: SITE_URL,
	sameAs: [
		"https://github.com/A1DS19/boardwright",
	],
} as const;

const WEBSITE_JSON_LD = {
	"@context": "https://schema.org",
	"@type": "WebSite",
	name: "Boardwright",
	url: SITE_URL,
	description: SITE_DESCRIPTION,
} as const;

const THEME_INIT_SCRIPT = `(function(){try{var stored=window.localStorage.getItem('theme');var mode=(stored==='light'||stored==='dark'||stored==='auto')?stored:'auto';var prefersDark=window.matchMedia('(prefers-color-scheme: dark)').matches;var resolved=mode==='auto'?(prefersDark?'dark':'light'):mode;var root=document.documentElement;root.classList.remove('light','dark');root.classList.add(resolved);if(mode==='auto'){root.removeAttribute('data-theme')}else{root.setAttribute('data-theme',mode)}root.style.colorScheme=resolved;}catch(e){}})();`;

export const Route = createRootRoute({
	head: () => ({
		meta: [
			{ charSet: "utf-8" },
			{ name: "viewport", content: "width=device-width, initial-scale=1" },
			{ title: SITE_TITLE },
			{ name: "description", content: SITE_DESCRIPTION },
			{ name: "theme-color", content: "#1ea861" },
			{ name: "robots", content: "index, follow" },
			{ name: "color-scheme", content: "light dark" },
			{ name: "application-name", content: "Boardwright" },
			{ name: "apple-mobile-web-app-title", content: "Boardwright" },
			{ property: "og:type", content: "website" },
			{ property: "og:site_name", content: "Boardwright" },
			{ property: "og:title", content: SITE_TITLE },
			{ property: "og:description", content: SITE_DESCRIPTION },
			{ property: "og:url", content: SITE_URL },
			{ property: "og:image", content: SITE_OG_IMAGE },
			{ property: "og:image:width", content: "1200" },
			{ property: "og:image:height", content: "630" },
			{
				property: "og:image:alt",
				content: "Boardwright — AI-native KiCad",
			},
			{ property: "og:locale", content: "en_US" },
			{ name: "twitter:card", content: "summary_large_image" },
			{ name: "twitter:title", content: SITE_TITLE },
			{ name: "twitter:description", content: SITE_DESCRIPTION },
			{ name: "twitter:image", content: SITE_OG_IMAGE },
			{ "script:ld+json": ORG_JSON_LD },
			{ "script:ld+json": WEBSITE_JSON_LD },
		],
		links: [
			{ rel: "canonical", href: SITE_URL },
			{ rel: "stylesheet", href: appCss },
			{ rel: "icon", href: "/favicon.ico" },
			{ rel: "manifest", href: "/manifest.json" },
		],
	}),
	shellComponent: RootDocument,
});

function RootDocument({ children }: { children: React.ReactNode }) {
	return (
		<html lang="en" suppressHydrationWarning>
			<head>
				{/* Inline theme script avoids a flash-of-incorrect-theme on first paint.
				    Content is a static constant, no user input — XSS rule does not apply. */}
				{/* biome-ignore lint/security/noDangerouslySetInnerHtml: static theme bootstrap */}
				<script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
				<HeadContent />
			</head>
			<body className="font-sans antialiased [overflow-wrap:anywhere] selection:bg-brand/30 selection:text-foreground">
				<Header />
				{children}
				<Footer />
				<TanStackDevtools
					config={{
						position: "bottom-right",
					}}
					plugins={[
						{
							name: "Tanstack Router",
							render: <TanStackRouterDevtoolsPanel />,
						},
					]}
				/>
				<Scripts />
			</body>
		</html>
	);
}
