import { createServerFn } from "@tanstack/react-start";

/*
  Waitlist submission handler — Buttondown /v1/subscribers API.

  Auth: BUTTONDOWN_API_KEY (read from .env in dev, wrangler secret in prod).

  Notable headers:
    • X-Buttondown-Bypass-Firewall: true
        Skips Buttondown's Email Firewall (which is otherwise designed for
        browser-form-flow signups). Documented rate limit: 5 requests / hour.
    • X-Buttondown-Collision-Behavior: add
        Treats already-subscribed emails as success (no 400). Defensive code
        for duplicates is still kept below as a fallback.

  Subscribers are tagged "waitlist" so they can be segmented from any future
  newsletter list. The default flow (no `type` field) sends a confirmation
  email — set type: "regular" if you want to skip double opt-in.
*/

declare const process: { env: { BUTTONDOWN_API_KEY?: string } };

const BUTTONDOWN_API_URL = "https://api.buttondown.com/v1/subscribers";
const WAITLIST_TAGS = ["waitlist"];

interface WaitlistInput {
	email: string;
}

interface WaitlistResult {
	ok: true;
	message: string;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const SUCCESS_MESSAGE = "You're on the list. Check your email to confirm.";
const ALREADY_SUBSCRIBED_MESSAGE =
	"You're already on the list. We'll be in touch.";

export const joinWaitlist = createServerFn({ method: "POST" })
	.inputValidator((input: unknown): WaitlistInput => {
		if (!input || typeof input !== "object") {
			throw new Error("Invalid request.");
		}
		const { email } = input as { email?: unknown };
		if (typeof email !== "string") {
			throw new Error("Email is required.");
		}
		const trimmed = email.trim().toLowerCase();
		if (!EMAIL_REGEX.test(trimmed)) {
			throw new Error("Please enter a valid email address.");
		}
		if (trimmed.length > 254) {
			throw new Error("Email is too long.");
		}
		return { email: trimmed };
	})
	.handler(async ({ data }): Promise<WaitlistResult> => {
		const apiKey = process.env.BUTTONDOWN_API_KEY;
		if (!apiKey) {
			console.error("[waitlist] BUTTONDOWN_API_KEY is not configured");
			throw new Error(
				"Subscriptions are temporarily unavailable. Try again soon.",
			);
		}

		let response: Response;
		try {
			response = await fetch(BUTTONDOWN_API_URL, {
				method: "POST",
				headers: {
					Authorization: `Token ${apiKey}`,
					"Content-Type": "application/json",
					"X-Buttondown-Bypass-Firewall": "true",
					"X-Buttondown-Collision-Behavior": "add",
				},
				body: JSON.stringify({
					email_address: data.email,
					tags: WAITLIST_TAGS,
				}),
			});
		} catch (err) {
			console.error("[waitlist] Buttondown network error", err);
			throw new Error("Network error. Try again in a minute.");
		}

		if (response.ok) {
			return { ok: true, message: SUCCESS_MESSAGE };
		}

		const errorBody = await response.text().catch(() => "");
		let parsed: { code?: string; detail?: string } | null = null;
		try {
			parsed = JSON.parse(errorBody) as { code?: string; detail?: string };
		} catch {
			// Body wasn't JSON — fall back to substring matching.
		}
		const code = parsed?.code ?? "";
		const detail = parsed?.detail ?? errorBody;

		console.error("[waitlist] Buttondown error", {
			status: response.status,
			code,
			detail: detail.slice(0, 300),
			email: data.email,
		});

		// Bypass-firewall is rate-limited to 5/hr; the general API allows 100/day.
		if (response.status === 429) {
			throw new Error("Too many signups right now. Try again in a minute.");
		}

		if (
			response.status === 400 &&
			(code === "email_already_exists" || /already/i.test(detail))
		) {
			return { ok: true, message: ALREADY_SUBSCRIBED_MESSAGE };
		}

		if (
			response.status === 400 &&
			(code === "invalid_email" || /invalid/i.test(detail))
		) {
			throw new Error("That email looks invalid.");
		}

		if (response.status === 400) {
			throw new Error("We couldn't add that email. Try again.");
		}

		throw new Error("Something went wrong. Try again in a minute.");
	});
