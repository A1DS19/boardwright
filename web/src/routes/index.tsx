import { createFileRoute } from "@tanstack/react-router";
import {
	CircuitBoard,
	Cpu,
	GitFork,
	MessageSquareText,
	Send,
	Sparkles,
	Wand2,
} from "lucide-react";
import { NewsletterForm } from "#/components/newsletter-form";

export const Route = createFileRoute("/")({ component: Landing });

function Landing() {
	return (
		<main>
			<Hero />
			<Benefits />
			<HowItWorks />
			<FinalCta />
		</main>
	);
}

function Hero() {
	return (
		<section className="relative overflow-hidden px-4 pt-20 pb-24 sm:pt-28 sm:pb-32">
			<div className="brand-grid pointer-events-none absolute inset-0 opacity-60" />
			<div className="brand-glow pointer-events-none absolute inset-x-0 top-0 h-[640px]" />

			<div className="page-wrap relative">
				<div className="mx-auto flex max-w-3xl flex-col items-center text-center">
					<span className="chip mb-6 text-xs">
						<Sparkles className="size-3.5 text-brand" aria-hidden="true" />
						Pre-1.0 · open core
					</span>

					<h1 className="display-title">
						Describe a board.{" "}
						<span className="text-brand">Watch Claude lay it out.</span>
					</h1>

					<p className="lead mx-auto mt-6 max-w-2xl">
						Boardwright is a local MCP server that gives Claude{" "}
						<span className="text-foreground">41 KiCad tools</span> across the
						full PCB workflow — research, schematic, layout, routing, fab
						outputs. Your KiCad, your libraries, accelerated by an agent that
						designs the way you do.
					</p>

					<NewsletterForm className="mt-8" />

					<p className="mt-4 text-xs text-muted-foreground">
						Local-first. Open core. Bring your own AI key.
					</p>
				</div>
			</div>
		</section>
	);
}

function Benefits() {
	const items = [
		{
			icon: Cpu,
			title: "Local-first",
			body: "Your KiCad install. Your footprint libraries. Your fab presets. Boardwright runs entirely on your machine — files never leave, the network is optional, and offline works once installed.",
		},
		{
			icon: GitFork,
			title: "Open core, MIT licensed",
			body: "The MCP server and the 41-tool catalog are open source. No telemetry, no signup, no lock-in. Audit it, fork it, ship it.",
		},
		{
			icon: CircuitBoard,
			title: "The full PCB workflow",
			body: "Component research, schematic capture, layout, copper pours, routing, ERC and DRC, Gerbers, drill files, BOM, position files. Eight phases. Forty-one tools. One agent.",
		},
	] as const;

	return (
		<section className="px-4 py-20 sm:py-24">
			<div className="page-wrap">
				<div className="mx-auto max-w-2xl text-center">
					<p className="eyebrow">Why Boardwright</p>
					<h2 className="mt-2 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
						Built for KiCad users who already ship boards.
					</h2>
				</div>

				<div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
					{items.map(({ icon: Icon, title, body }) => (
						<article
							key={title}
							className="group relative overflow-hidden rounded-2xl border border-border bg-card p-6 transition-colors hover:border-brand/40"
						>
							<div className="inline-flex items-center justify-center rounded-lg border border-brand/30 bg-brand/10 p-2 text-brand">
								<Icon className="size-5" aria-hidden="true" />
							</div>
							<h3 className="mt-4 text-base font-semibold text-foreground">
								{title}
							</h3>
							<p className="mt-2 text-sm leading-relaxed text-muted-foreground">
								{body}
							</p>
						</article>
					))}
				</div>
			</div>
		</section>
	);
}

function HowItWorks() {
	const steps = [
		{
			icon: MessageSquareText,
			label: "Describe",
			title: "Tell Claude what you're building.",
			body: 'In plain English. "USB-C rechargeable LED controller, 4 RGB channels, BLE." Or paste a datasheet. Or point Claude at an existing project to extend.',
		},
		{
			icon: Wand2,
			label: "Drive",
			title: "Claude drives your KiCad.",
			body: "Schematic capture, footprint placement, copper pours, routing, ERC and DRC. You watch the design happen in pcbnew. Stop, steer, or rewind at any moment.",
		},
		{
			icon: Send,
			label: "Ship",
			title: "Get fab-ready outputs.",
			body: "Gerbers, drill files, BOM, position files, 3D model — all generated via kicad-cli. Hand them straight to JLCPCB, PCBWay, Aisler, or your fab of choice.",
		},
	] as const;

	return (
		<section className="px-4 py-20 sm:py-24">
			<div className="page-wrap">
				<div className="mx-auto max-w-2xl text-center">
					<p className="eyebrow">How it works</p>
					<h2 className="mt-2 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
						From prompt to Gerbers, in your editor.
					</h2>
				</div>

				<ol className="mt-12 grid gap-4 lg:grid-cols-3">
					{steps.map(({ icon: Icon, label, title, body }, index) => (
						<li
							key={label}
							className="relative rounded-2xl border border-border bg-card p-6"
						>
							<div className="flex items-center gap-3">
								<span className="flex size-8 items-center justify-center rounded-lg bg-brand/15 font-mono text-sm font-semibold text-brand">
									{String(index + 1).padStart(2, "0")}
								</span>
								<span className="eyebrow">{label}</span>
								<Icon
									className="ml-auto size-4 text-muted-foreground"
									aria-hidden="true"
								/>
							</div>
							<h3 className="mt-4 text-base font-semibold text-foreground">
								{title}
							</h3>
							<p className="mt-2 text-sm leading-relaxed text-muted-foreground">
								{body}
							</p>
						</li>
					))}
				</ol>
			</div>
		</section>
	);
}

function FinalCta() {
	return (
		<section className="px-4 py-20 sm:py-28">
			<div className="page-wrap">
				<div className="relative mx-auto max-w-3xl overflow-hidden rounded-3xl border border-border bg-card p-10 text-center sm:p-14">
					<div className="brand-glow pointer-events-none absolute inset-0 opacity-80" />
					<div className="relative">
						<p className="eyebrow">Get on the waitlist</p>
						<h2 className="mt-2 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
							AI-native KiCad. Coming to PyPI soon.
						</h2>
						<p className="lead mx-auto mt-4 max-w-xl">
							Boardwright is in pre-1.0 and used daily on real boards. The PyPI
							release, a 60-second demo, and the public launch land in the next
							four weeks. Get notified.
						</p>
						<div className="mt-8 flex justify-center">
							<NewsletterForm />
						</div>
					</div>
				</div>
			</div>
		</section>
	);
}
