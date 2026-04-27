import { useForm } from "@tanstack/react-form";
import { Loader2, Mail } from "lucide-react";
import { useState } from "react";
import { Button } from "#/components/ui/button";
import { Input } from "#/components/ui/input";
import { cn } from "#/lib/utils";
import { joinWaitlist } from "#/server/waitlist";

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface NewsletterFormProps {
	className?: string;
}

export function NewsletterForm({ className }: NewsletterFormProps) {
	const [status, setStatus] = useState<"idle" | "success" | "error">("idle");
	const [message, setMessage] = useState<string>("");

	const form = useForm({
		defaultValues: { email: "" },
		onSubmit: async ({ value }) => {
			try {
				const result = await joinWaitlist({ data: { email: value.email } });
				setStatus("success");
				setMessage(result.message);
			} catch (err) {
				setStatus("error");
				setMessage(
					err instanceof Error
						? err.message
						: "Something went wrong. Try again.",
				);
			} finally {
				form.reset();
			}
		},
	});

	if (status === "success") {
		return (
			<div
				className={cn(
					"rounded-xl border border-brand/30 bg-brand/10 px-4 py-3 text-sm text-foreground",
					className,
				)}
			>
				<p className="m-0 font-medium">{message}</p>
				<p className="m-0 mt-1 text-xs text-muted-foreground">
					Watch your inbox — early access opens soon.
				</p>
			</div>
		);
	}

	return (
		<form
			onSubmit={(e) => {
				e.preventDefault();
				e.stopPropagation();
				form.handleSubmit();
			}}
			className={cn("w-full max-w-md", className)}
			noValidate
		>
			<div className="flex flex-col gap-2 sm:flex-row sm:items-stretch">
				<form.Field
					name="email"
					validators={{
						onChange: ({ value }) => {
							if (!value) return "Email is required.";
							if (!EMAIL_REGEX.test(value.trim()))
								return "Enter a valid email.";
							return undefined;
						},
					}}
				>
					{(field) => (
						<div className="relative flex-1">
							<Mail
								className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
								aria-hidden="true"
							/>
							<Input
								type="email"
								inputMode="email"
								autoComplete="email"
								placeholder="you@company.com"
								value={field.state.value}
								onChange={(e) => {
									field.handleChange(e.target.value);
									if (status === "error") setStatus("idle");
								}}
								onBlur={field.handleBlur}
								aria-invalid={field.state.meta.errors.length > 0}
								aria-describedby="newsletter-error"
								className="h-11 w-full pl-9 pr-3 text-sm"
							/>
						</div>
					)}
				</form.Field>

				<form.Subscribe
					selector={(s) => [s.isSubmitting, s.canSubmit] as const}
				>
					{([isSubmitting, canSubmit]) => (
						<Button
							type="submit"
							size="lg"
							className="h-11 px-5 text-sm font-semibold sm:flex-shrink-0"
							disabled={isSubmitting || !canSubmit}
						>
							{isSubmitting ? (
								<>
									<Loader2 className="size-4 animate-spin" aria-hidden="true" />
									Joining...
								</>
							) : (
								"Get early access"
							)}
						</Button>
					)}
				</form.Subscribe>
			</div>

			<form.Field name="email">
				{(field) => (
					<p
						id="newsletter-error"
						className="mt-2 min-h-4 text-xs text-destructive"
						aria-live="polite"
					>
						{field.state.meta.errors[0] ?? (status === "error" ? message : " ")}
					</p>
				)}
			</form.Field>
		</form>
	);
}
