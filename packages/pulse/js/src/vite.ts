import { timingSafeEqual } from "node:crypto";
import type { IncomingMessage, ServerResponse } from "node:http";
import { basename, dirname, isAbsolute, relative, resolve } from "node:path";
import type { EnvironmentModuleNode, Plugin } from "vite";

const HEALTH_PATH = "/__pulse/health";
const COMMIT_PATH = "/__pulse/commit";
const MAX_BODY_BYTES = 64 * 1024;

export interface PulseVitePluginOptions {
	generatedDir?: string;
	stagingDir?: string;
}

interface CommitRequest {
	generation: number;
	files: string[];
}

function sendJson(
	response: ServerResponse,
	statusCode: number,
	body: Record<string, unknown>,
) {
	response.writeHead(statusCode, { "content-type": "application/json" });
	response.end(JSON.stringify(body));
}

function authorized(request: IncomingMessage, secret: string) {
	const authorization = request.headers.authorization;
	if (!authorization?.startsWith("Bearer ")) return false;

	const provided = Buffer.from(authorization.slice("Bearer ".length));
	const expected = Buffer.from(secret);
	return provided.length === expected.length && timingSafeEqual(provided, expected);
}

async function readCommitRequest(request: IncomingMessage): Promise<CommitRequest> {
	const contentLength = Number(request.headers["content-length"]);
	if (Number.isFinite(contentLength) && contentLength > MAX_BODY_BYTES) {
		throw new Error("Request body is too large");
	}

	const chunks: Buffer[] = [];
	let byteLength = 0;
	for await (const chunk of request) {
		const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
		byteLength += buffer.length;
		if (byteLength > MAX_BODY_BYTES) throw new Error("Request body is too large");
		chunks.push(buffer);
	}

	const value: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
	if (
		typeof value !== "object" ||
		value === null ||
		!("generation" in value) ||
		!Number.isSafeInteger(value.generation) ||
		(value.generation as number) <= 0
	) {
		throw new Error("generation must be a positive safe integer");
	}
	const files = "files" in value ? value.files : [];
	if (!Array.isArray(files) || files.some((file) => typeof file !== "string")) {
		throw new Error("files must be an array of paths");
	}
	return { generation: value.generation as number, files };
}

function isWithin(file: string, directory: string) {
	const path = relative(directory, file);
	return path === "" || (!path.startsWith("..") && !isAbsolute(path));
}

export function pulseVitePlugin(options: PulseVitePluginOptions = {}): Plugin {
	const secretValue = process.env.PULSE_VITE_CONTROL_SECRET;
	const enabled = secretValue !== undefined;
	if (enabled && !secretValue) {
		throw new Error("PULSE_VITE_CONTROL_SECRET must not be empty");
	}
	const secret = secretValue ?? "";
	const generatedDirOption =
		options.generatedDir ?? process.env.PULSE_VITE_GENERATED_DIR ?? "app/pulse";
	const stagingDirOption = options.stagingDir ?? process.env.PULSE_VITE_STAGING_DIR;

	let generatedDir = "";
	let stagingDir = "";
	let latestGeneration = 0;
	const pendingFiles = new Set<string>();

	return {
		name: "pulse:reload-coordination",
		apply: "serve",
		configResolved(config) {
			generatedDir = resolve(config.root, generatedDirOption);
			stagingDir = stagingDirOption
				? resolve(config.root, stagingDirOption)
				: resolve(
						dirname(generatedDir),
						`.${basename(generatedDir)}.pulse-reload`,
					);
		},
		hotUpdate: {
			order: "pre",
			handler({ file }) {
				if (
					enabled &&
					(isWithin(file, generatedDir) || isWithin(file, stagingDir))
				) {
					pendingFiles.add(file);
					return [];
				}
			},
		},
		configureServer(viteServer) {
			if (!enabled) return;

			viteServer.middlewares.use(async function pulseReloadMiddleware(
				request,
				response,
				next,
			) {
				const path = new URL(request.url ?? "/", "http://pulse.local").pathname;
				if (path !== HEALTH_PATH && path !== COMMIT_PATH) {
					next();
					return;
				}

				if (!authorized(request, secret)) {
					sendJson(response, 401, { status: "unauthorized" });
					return;
				}

				if (request.method === "GET" && path === HEALTH_PATH) {
					sendJson(response, 200, {
						status: "ready",
						generation: latestGeneration,
					});
					return;
				}
				if (request.method !== "POST" || path !== COMMIT_PATH) {
					sendJson(response, 404, { status: "not_found" });
					return;
				}

				let commit: CommitRequest;
				try {
					commit = await readCommitRequest(request);
				} catch (error) {
					sendJson(response, 400, {
						status: "invalid_request",
						error: error instanceof Error ? error.message : String(error),
					});
					return;
				}
				const publishedFiles = commit.files.map((file) =>
					resolve(generatedDir, file),
				);
				if (publishedFiles.some((file) => !isWithin(file, generatedDir))) {
					sendJson(response, 400, {
						status: "invalid_request",
						error: "files must stay inside the generated directory",
					});
					return;
				}

				if (commit.generation < latestGeneration) {
					sendJson(response, 409, {
						status: "stale",
						generation: latestGeneration,
					});
					return;
				}
				if (commit.generation === latestGeneration) {
					sendJson(response, 200, {
						status: "committed",
						generation: latestGeneration,
					});
					return;
				}

				try {
					const files = new Set([...pendingFiles, ...publishedFiles]);
					for (const environment of Object.values(viteServer.environments)) {
						const invalidated = new Set<EnvironmentModuleNode>();
						for (const file of files) {
							for (const module of
								environment.moduleGraph.getModulesByFile(file) ?? []) {
								environment.moduleGraph.invalidateModule(module, invalidated);
							}
						}
					}
					viteServer.ws.send({ type: "full-reload" });
					latestGeneration = commit.generation;
					pendingFiles.clear();
				} catch (error) {
					const message = error instanceof Error ? error.message : String(error);
					viteServer.config.logger.error(
						`Pulse generation ${commit.generation} commit failed: ${message}`,
					);
					sendJson(response, 500, { status: "error", error: message });
					return;
				}

				sendJson(response, 200, {
					status: "committed",
					generation: latestGeneration,
				});
			});
		},
	};
}
