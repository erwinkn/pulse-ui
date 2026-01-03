/**
 * ChatGPT Pro Automation via Playwriter
 *
 * A simple alternative to Oracle's browser mode.
 * Connects to your existing Chrome session via Playwriter's CDP relay.
 *
 * Usage:
 *   import { askChatGPT } from './chatgpt-automation.js'
 *
 *   const result = await askChatGPT({
 *     prompt: 'Your question here',
 *     model: 'pro'
 *   });
 */

import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright-core";
import { getCdpUrl, startPlayWriterCDPRelayServer } from "playwriter";

// Load .env from repo root if it exists
function loadEnvFile() {
	try {
		const envPath = path.join(process.cwd(), ".env");
		if (fs.existsSync(envPath)) {
			const content = fs.readFileSync(envPath, "utf-8");
			for (const line of content.split("\n")) {
				const trimmed = line.trim();
				if (!trimmed || trimmed.startsWith("#")) continue;
				const eqIndex = trimmed.indexOf("=");
				if (eqIndex === -1) continue;
				const key = trimmed.slice(0, eqIndex).trim();
				let value = trimmed.slice(eqIndex + 1).trim();
				if (
					(value.startsWith('"') && value.endsWith('"')) ||
					(value.startsWith("'") && value.endsWith("'"))
				) {
					value = value.slice(1, -1);
				}
				if (!process.env[key]) {
					process.env[key] = value;
				}
			}
		}
	} catch {
		// Ignore errors reading .env
	}
}

loadEnvFile();

const DEFAULT_URL = process.env.CHATGPT_ORACLE_URL || "https://chatgpt.com/";

const MODEL_MAP = {
	auto: "model-switcher-gpt-5-2",
	instant: "model-switcher-gpt-5-2-instant",
	thinking: "model-switcher-gpt-5-2-thinking",
	pro: "model-switcher-gpt-5-2-pro",
};

/**
 * Check if response is complete using multiple signals
 */
async function checkCompletionSignals(page) {
	return page.evaluate(() => {
		const stopBtn = document.querySelector('button[data-testid="stop-button"]');
		const stopVisible = stopBtn !== null && stopBtn.offsetParent !== null;
		const copyBtn = document.querySelector('button[data-testid="copy-turn-action-button"]');
		const thumbsUp = document.querySelector(
			'button[data-testid="good-response-turn-action-button"]',
		);
		const hasActionButtons = copyBtn !== null || thumbsUp !== null;
		return { complete: !stopVisible && hasActionButtons, hasActionButtons, stopVisible };
	});
}

/**
 * Extract assistant's response text
 */
async function extractResponse(page) {
	return page.evaluate(() => {
		const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
		if (msgs.length === 0) return "";
		return msgs[msgs.length - 1].innerText || "";
	});
}

/**
 * Wait for response with stability checking
 */
async function waitForResponse(page, { timeout, log, onProgress }) {
	const startTime = Date.now();
	let lastLogTime = startTime;
	let lastResponseLength = 0;
	let stableCount = 0;

	const SHORT_RESPONSE_THRESHOLD = 16;
	const SHORT_STABILITY_CYCLES = 8;
	const NORMAL_STABILITY_CYCLES = 3;

	while (Date.now() - startTime < timeout) {
		const elapsed = Math.round((Date.now() - startTime) / 1000);

		if (Date.now() - lastLogTime > 30000) {
			log(`Still waiting... ${elapsed}s elapsed`);
			if (onProgress) onProgress(elapsed, "streaming");
			lastLogTime = Date.now();
		}

		const signals = await checkCompletionSignals(page);

		if (signals.complete) {
			const response = await extractResponse(page);
			if (response.length === lastResponseLength && response.length > 0) {
				stableCount++;
				const requiredCycles =
					response.length < SHORT_RESPONSE_THRESHOLD
						? SHORT_STABILITY_CYCLES
						: NORMAL_STABILITY_CYCLES;
				if (stableCount >= requiredCycles) {
					log(`Response complete after ${elapsed}s`);
					return { response, elapsed, timedOut: false };
				}
			} else {
				stableCount = 0;
				lastResponseLength = response.length;
			}
		} else {
			stableCount = 0;
			lastResponseLength = 0;
		}

		await page.waitForTimeout(1000);
	}

	log(`Timeout after ${Math.round((Date.now() - startTime) / 1000)}s`);
	return {
		response: await extractResponse(page),
		elapsed: Math.round((Date.now() - startTime) / 1000),
		timedOut: true,
	};
}

/**
 * Connect to Chrome via Playwriter's CDP relay
 * Tries to connect to existing relay first, starts new one if needed
 */
async function connectToChrome() {
	let server = null;

	// Try connecting to existing relay first
	try {
		const browser = await chromium.connectOverCDP(getCdpUrl(), { timeout: 2000 });
		return { server: null, browser };
	} catch {
		// No existing relay, start a new one
	}

	server = await startPlayWriterCDPRelayServer();
	const browser = await chromium.connectOverCDP(getCdpUrl());
	return { server, browser };
}

/**
 * Send a prompt to ChatGPT and get the response
 *
 * @param {Object} options
 * @param {string} [options.url] - ChatGPT URL (defaults to CHATGPT_ORACLE_URL env var or https://chatgpt.com/)
 * @param {string} options.prompt - The prompt to send
 * @param {Array<{path: string, content: string}>} [options.files=[]] - Files to attach
 * @param {'auto'|'instant'|'thinking'|'pro'} [options.model='pro'] - Model to use
 * @param {number} [options.timeout=900000] - Max wait time in ms (default 15 min)
 * @param {Function} [options.onProgress] - Callback(elapsed, status) called every 30s
 * @returns {Promise<{success: boolean, response: string, url: string, elapsed: number, timedOut: boolean, error?: string}>}
 */
export async function askChatGPT({
	url = DEFAULT_URL,
	prompt,
	files = [],
	model = "pro",
	timeout = 900000,
	onProgress = null,
}) {
	// Build prompt with file contents
	let fullPrompt = prompt;
	if (files.length > 0) {
		fullPrompt += "\n\n---\n\n# Attached Files\n";
		for (const f of files) {
			fullPrompt += `\n## ${f.path}\n\`\`\`\n${f.content}\n\`\`\`\n`;
		}
	}

	const log = (msg) => console.log(`[askChatGPT] ${msg}`);
	const startTime = Date.now();

	let server, browser, page;
	try {
		log("Connecting to Chrome...");
		({ server, browser } = await connectToChrome());

		const context = browser.contexts()[0];
		page = await context.newPage();

		log(`Opening ${url}`);
		await page.goto(url);
		await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});

		// Select model
		const modelTestId = MODEL_MAP[model] || MODEL_MAP["pro"];
		log(`Selecting model: ${model}`);
		await page.locator('button[data-testid="model-switcher-dropdown-button"]').click();
		await page.waitForTimeout(300);
		await page.locator(`[data-testid="${modelTestId}"]`).click();
		await page.waitForTimeout(300);

		// Fill and send
		const editor = page.locator(".ProseMirror");
		await editor.waitFor({ timeout: 10000 });
		await editor.click();
		await editor.fill(fullPrompt);
		log(`Prompt entered (${fullPrompt.length} chars)`);

		const sendBtn = page.locator('button[data-testid="send-button"]');
		await sendBtn.waitFor({ timeout: 5000 });
		await sendBtn.click();
		log("Message sent, waiting for response...");

		// Wait for response
		const result = await waitForResponse(page, { timeout, log, onProgress });
		const finalUrl = page.url();

		log(`Response: ${result.response.slice(0, 100)}${result.response.length > 100 ? "..." : ""}`);
		await page.close();
		await browser.close();
		if (server) server.close();

		return {
			success: true,
			response: result.response,
			url: finalUrl,
			elapsed: result.elapsed,
			timedOut: result.timedOut,
		};
	} catch (err) {
		log(`Error: ${err.message}`);
		if (page) await page.close().catch(() => {});
		if (browser) await browser.close().catch(() => {});
		if (server) server.close();
		return {
			success: false,
			error: err.message,
			response: "",
			url: "",
			elapsed: Math.round((Date.now() - startTime) / 1000),
			timedOut: false,
		};
	}
}

// CLI entry point
if (process.argv[1] === import.meta.filename) {
	const prompt = process.argv[2];
	if (!prompt) {
		console.error('Usage: node chatgpt-automation.js "your prompt"');
		process.exit(1);
	}

	const result = await askChatGPT({ prompt });
	console.log("\n--- Response ---\n");
	console.log(result.response);
	process.exit(result.success ? 0 : 1);
}
