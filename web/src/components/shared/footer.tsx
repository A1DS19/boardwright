import { Github } from "lucide-react";

export function Footer() {
	const year = new Date().getFullYear();

	return (
		<footer className="mt-24 border-t border-border px-4 pb-14 pt-10 text-muted-foreground">
			<div className="page-wrap flex flex-col items-center justify-between gap-4 text-center sm:flex-row sm:text-left">
				<p className="m-0 text-sm">
					&copy; {year} Boardwright. MIT licensed.
				</p>
				<p className="eyebrow m-0">Local-first · KiCad-native</p>
			</div>
			<div className="mt-4 flex justify-center gap-2">
				<a
					href="https://github.com/A1DS19/boardwright"
					target="_blank"
					rel="noreferrer"
					className="rounded-xl p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
				>
					<span className="sr-only">Boardwright on GitHub</span>
					<Github className="size-5" aria-hidden="true" />
				</a>
			</div>
		</footer>
	);
}
