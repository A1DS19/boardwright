import { Link } from "@tanstack/react-router";
import { Github } from "lucide-react";
import ThemeToggle from "./ThemeToggle";

export function Header() {
	return (
		<header className="sticky top-0 z-50 border-b border-border bg-background/80 px-4 backdrop-blur-lg">
			<nav className="page-wrap flex flex-wrap items-center gap-x-3 gap-y-2 py-3 sm:py-4">
				<h2 className="m-0 flex-shrink-0 text-base font-semibold tracking-tight">
					<Link
						to="/"
						className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1.5 text-sm text-foreground no-underline transition-colors hover:bg-muted sm:px-4 sm:py-2"
					>
						<span className="inline-block h-2 w-2 rounded-full bg-brand shadow-[0_0_0_3px_color-mix(in_oklch,var(--brand)_25%,transparent)]" />
						Boardwright
					</Link>
				</h2>

				<div className="ml-auto flex items-center gap-1.5 sm:ml-0 sm:gap-2">
					<a
						href="https://github.com/A1DS19/boardwright"
						target="_blank"
						rel="noreferrer"
						className="rounded-xl p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
					>
						<span className="sr-only">Boardwright on GitHub</span>
						<Github className="size-5" aria-hidden="true" />
					</a>
					<ThemeToggle />
				</div>
			</nav>
		</header>
	);
}
