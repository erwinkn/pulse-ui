import { z } from "zod/v4";

const settingsSchema = z.object({
	username: z.string().min(3),
	email: z.email(),
	notifications: z.boolean(),
});

export function SettingsForm() {
	const result = settingsSchema.safeParse({
		username: "testuser",
		email: "test@example.com",
		notifications: true,
	});
	return (
		<div className="settings-form">
			<h2>Settings Form</h2>
			<p>Schema validation: {result.success ? "valid" : "invalid"}</p>
		</div>
	);
}
