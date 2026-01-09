import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const DIST_ASSETS = join(import.meta.dir, "..", "dist", "assets");

function analyzeBundle(): void {
	let files: string[];
	try {
		files = readdirSync(DIST_ASSETS);
	} catch {
		console.error("Error: dist/assets directory not found. Run 'bun run build' first.");
		process.exit(1);
	}

	const jsFiles = files.filter((f) => f.endsWith(".js"));

	console.log("\nBundle Analysis:");
	console.log("================");

	for (const file of jsFiles) {
		const filePath = join(DIST_ASSETS, file);
		const stats = statSync(filePath);
		const sizeKB = (stats.size / 1024).toFixed(2);
		console.log(`  ${file}: ${sizeKB} KB`);
	}

	console.log(`\nTotal JS chunks: ${jsFiles.length}`);

	if (jsFiles.length < 3) {
		console.error("\nFAIL: Expected at least 3 JS chunks for code splitting.");
		console.error(`      Found only ${jsFiles.length} chunk(s).`);
		process.exit(1);
	}

	console.log("\nPASS: Code splitting is working (3+ chunks detected).");
}

analyzeBundle();
