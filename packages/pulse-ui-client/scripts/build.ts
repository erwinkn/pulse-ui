import { $ } from "bun";
import { minify } from "terser";
import { readFile, writeFile } from "node:fs/promises";

const entry = "./src/index.ts";
const outdir = "dist";
const prodDefine = {
  "process.env.NODE_ENV": '"production"',
  __DEV__: "false",
};
const devDefine = {
  "process.env.NODE_ENV": '"development"',
  __DEV__: "true",
};
const external = ["react", "react-dom", "react-router", "socket.io-client"];

async function clean() {
  await $`rm -rf ${outdir}`;
}

async function buildBrowser() {
  const result = await Bun.build({
    entrypoints: [entry],
    outdir,
    target: "browser",
    format: "esm",
    minify: {
      whitespace: true,
      identifiers: true,
      syntax: true,
    },
    sourcemap: "external",
    external,
    define: prodDefine,
  });
  if (!result.success) throw new Error("Browser build failed");
  
  await minifyWithTerser(`${outdir}/index.js`, `${outdir}/index.js.map`);
}

async function buildBrowserDev() {
  const result = await Bun.build({
    entrypoints: [entry],
    outdir,
    naming: { entry: "index.development.js" },
    target: "browser",
    format: "esm",
    minify: false,
    sourcemap: "inline",
    external,
    define: devDefine,
  });
  if (!result.success) throw new Error("Browser dev build failed");
}

async function buildNode() {
  const result = await Bun.build({
    entrypoints: [entry],
    outdir,
    naming: { entry: "index.node.js" },
    target: "node",
    format: "esm",
    minify: {
      whitespace: true,
      identifiers: true,
      syntax: true,
    },
    sourcemap: "inline",
    external,
    define: prodDefine,
  });
  if (!result.success) throw new Error("Node build failed");
  
  await minifyWithTerser(`${outdir}/index.node.js`);
}

async function buildBun() {
  const result = await Bun.build({
    entrypoints: [entry],
    outdir,
    naming: { entry: "index.bun.js" },
    target: "bun",
    format: "esm",
    minify: {
      whitespace: true,
      identifiers: true,
      syntax: true,
    },
    sourcemap: "inline",
    external,
    define: prodDefine,
  });
  if (!result.success) throw new Error("Bun build failed");
  
  await minifyWithTerser(`${outdir}/index.bun.js`);
}

async function minifyWithTerser(filePath: string, sourceMapPath?: string) {
  const code = await readFile(filePath, "utf-8");
  const sourceMap = sourceMapPath ? await readFile(sourceMapPath, "utf-8") : undefined;
  
  const publicApiProps = [
    "connect", "disconnect", "isConnected", "onConnectionChange",
    "navigate", "leave", "invokeCallback", "mountView",
    "renderNode", "applyUpdates", "RenderLazy",
    "usePulseClient", "usePulseChannel", "PulseProvider", "PulseView", "PulseForm",
    "serialize", "deserialize", "extractEvent", "extractServerRouteInfo",
    "type", "path", "vdom", "callbacks", "render_props", "css_refs", "ops",
    "onInit", "onUpdate", "routeInfo",
    "children", "props", "key", "tag", "ref",
    "then", "catch", "finally",
    "length", "name", "message", "stack",
    "value", "done",
    "id", "url", "method", "headers", "body", "credentials", "status", "ok",
    "hash", "pathname", "query", "queryParams", "pathParams", "catchall",
    "phase", "error",
    "default",
  ];
  
  const result = await minify(code, {
    sourceMap: sourceMapPath ? {
      content: sourceMap,
      url: `${filePath.split('/').pop()}.map`,
    } : false,
    compress: {
      passes: 3,
      pure_getters: true,
      unsafe: true,
      unsafe_comps: true,
      unsafe_Function: true,
      unsafe_math: true,
      unsafe_methods: true,
      unsafe_proto: true,
      unsafe_regexp: true,
      unsafe_undefined: true,
    },
    mangle: {
      properties: {
        regex: /.*/,
        reserved: publicApiProps,
      },
    },
    format: {
      comments: false,
    },
  });
  
  if (!result.code) throw new Error(`Terser minification failed for ${filePath}`);
  
  await writeFile(filePath, result.code);
  if (result.map && sourceMapPath) {
    await writeFile(sourceMapPath, result.map);
  }
}

async function main() {
  await clean();
  // build sequentially for clearer logs
  await buildBrowser();
  await buildBrowserDev();
  await buildNode();
  await buildBun();
}

await main();
