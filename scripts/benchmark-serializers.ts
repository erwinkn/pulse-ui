import { performance } from "node:perf_hooks";
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

import {
  serialize as serializeV2,
  deserialize as deserializeV2,
} from "../packages/pulse-ui-client/src/serialize/v2";
import {
  serialize as serializeV3,
  deserialize as deserializeV3,
} from "../packages/pulse-ui-client/src/serialize/v3";

const WARMUP_RUNS = 5;
const MEASURED_RUNS = Number.parseInt(process.argv[2] ?? "20", 10);

if (Number.isNaN(MEASURED_RUNS) || MEASURED_RUNS <= 0) {
  throw new Error("Iteration count must be a positive integer");
}

function createLargeDefaultPayload(targetSerializedBytes = 500_000) {
  const textTarget = Math.max(10_000, Math.floor(targetSerializedBytes * 0.3));
  const baseChunk = "0123456789abcdef";
  const repeats = Math.ceil(textTarget / baseChunk.length);
  const largeText = baseChunk.repeat(repeats).slice(0, textTarget);

  const root: Record<string, any> = {
    id: "generated-benchmark-payload",
    createdAt: new Date(),
    metadata: {
      version: "v3",
      featureFlags: new Set([
        "deep",
        "large",
        "circular",
        "dates",
        "sets",
        "maps",
      ]),
      stats: new Map([
        ["targetSerializedBytes", targetSerializedBytes],
        ["largeTextBytes", textTarget],
      ]),
    },
    summaries: new Map([
      ["recordTypes", new Set(["baseline", "derived", "archived"])],
      ["generatedAt", new Date()],
    ]),
    uniqueVisitors: new Set(
      Array.from(
        { length: 500 },
        (_, index) => `visitor-${index.toString().padStart(4, "0")}`
      )
    ),
    preferences: new Map([
      ["theme", "dark"],
      ["layout", "wide"],
      [
        "limits",
        new Map([
          ["maxItems", 1_000],
          ["timeoutMs", 2_500],
        ]),
      ],
    ]),
  };

  const deepChain: Record<string, any> = {
    depth: 0,
    label: "root",
    timestamps: [new Date(), new Date(Date.now() + 1_000)],
    attributes: new Map([
      ["priority", "high"],
      ["checksum", baseChunk.slice(0, 16)],
    ]),
    flags: new Set(["root"]),
  };

  let current = deepChain;
  for (let level = 1; level <= 12; level += 1) {
    const child = {
      depth: level,
      label: `node-${level}`,
      createdAt: new Date(Date.now() + level * 10_000),
      attributes: new Map<string, number | string>([
        ["iteration", level],
        ["randomSeed", (level * 42).toString(16)],
      ]),
      flags: new Set([`level-${level}`, level % 2 === 0 ? "even" : "odd"]),
      history: new Set([
        new Date(Date.now() - level * 5_000),
        new Date(Date.now() - level * 2_500),
      ]),
    };
    current.child = child;
    current.self = current;
    current = child;  
  }

  current.largeText = largeText;
  current.largeTextSummary = new Map([
    ["chunks", Math.ceil(largeText.length / 1_024)],
    ["approxBytes", largeText.length],
  ]);
  current.flagSet = new Set(["leaf", "contains-large-text"]);

  root.deep = deepChain;

  const payloadBlock = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".repeat(8);
  const recordCount = Math.ceil(targetSerializedBytes / 6_000);
  root.records = [];

  for (let i = 0; i < recordCount; i += 1) {
    const metrics = new Map([
      ["index", i],
      ["blockLength", payloadBlock.length],
      ["timestamp", Date.now() + i * 5_000],
    ]);

    const flags = new Set<string>();
    flags.add(i % 2 === 0 ? "even" : "odd");
    flags.add(i % 3 === 0 ? "multiple-of-three" : "non-multiple-of-three");
    flags.add(i % 5 === 0 ? "multiple-of-five" : "non-multiple-of-five");

    const nestedNode: Record<string, any> = {
      layer: 0,
      label: `record-${i}-layer-0`,
      steps: [],
      occurredAt: new Date(Date.now() - i * 1_000),
    };

    let nestedCurrent = nestedNode;
    for (let layer = 1; layer <= 4; layer += 1) {
      const step = {
        layer,
        label: `record-${i}-layer-${layer}`,
        data: payloadBlock.repeat((layer % 3) + 1),
        observedAt: new Date(Date.now() + layer * 60_000),
        set: new Set([layer, layer + 1, layer + 2]),
        map: new Map([
          ["layer", layer],
          ["combined", `${i}-${layer}`],
        ]),
      };
      nestedCurrent.steps.push(step);
      const nextNode = {
        layer,
        reference: nestedCurrent,
        created: new Date(Date.now() + layer * 10_000),
        steps: [],
      };
      nestedCurrent.next = nextNode;
      nestedCurrent = nextNode;
    }

    root.records.push({
      id: `record-${i}`,
      createdAt: new Date(Date.now() - i * 60_000),
      metrics,
      flags,
      nested: nestedNode,
      payload: payloadBlock.repeat(3 + (i % 5)),
    });
  }

  root.recordsById = new Map(
    root.records.map((record: any) => [record.id, record])
  );
  root.recordSet = new Set(
    root.records.slice(0, Math.min(20, root.records.length))
  );

  const circularA: Record<string, any> = {
    name: "circular-A",
    timestamps: [new Date(), new Date(Date.now() + 86_400_000)],
  };
  const circularB: Record<string, any> = {
    name: "circular-B",
    relatedDates: new Set([new Date(Date.now() - 86_400_000), new Date()]),
  };

  circularA.partner = circularB;
  circularB.partner = circularA;
  circularA.self = circularA;

  const circularContainer: Record<string, any> = {
    circularA,
    circularB,
    pairSet: new Set([circularA, circularB]),
    pairMap: new Map([
      ["primary", circularA],
      ["secondary", circularB],
      ["pair", [circularA, circularB]],
    ]),
  };
  circularContainer.self = circularContainer;

  root.circular = circularContainer;

  return root;
}

function loadPayloadFromFile(filePath: string) {
  try {
    const jsonContent = readFileSync(filePath, "utf-8");
    const payload = JSON.parse(jsonContent);
    const payloadSize = Buffer.byteLength(jsonContent);
    const payloadGzipSize = gzipSync(Buffer.from(jsonContent)).length;
    console.log(`Loaded payload from ${filePath}, size: ${payloadSize} bytes`);
    return { payload, payloadSize, payloadGzipSize };
  } catch (error) {
    throw new Error(
      `Failed to load JSON file "${filePath}": ${error instanceof Error ? error.message : String(error)}`
    );
  }
}

function getPayloadInfo() {
  const filePath = process.argv[3];

  if (filePath) {
    const { payload, payloadSize, payloadGzipSize } = loadPayloadFromFile(filePath);
    return {
      payload,
      sizeRows: [
        {
          type: `original JSON (${filePath})`,
          bytes: payloadSize,
          gzipBytes: payloadGzipSize,
        },
      ],
    };
  }

  const payload = createLargeDefaultPayload();
  const approxSerialized = serializeV3(payload);
  const approxSerializedJson = JSON.stringify(approxSerialized);
  const approxBytes = Buffer.byteLength(approxSerializedJson);
  const approxGzipBytes = gzipSync(Buffer.from(approxSerializedJson)).length;

  console.log(
    `Generated default payload with dates, sets, maps, and circular refs (~${approxBytes} bytes, ~${approxGzipBytes} bytes gzipped via v3)`
  );

  return {
    payload,
    sizeRows: [],
  };
}

function benchmarkWithSize<T>(
  label: string,
  fn: () => { result: T; serialized: unknown }
) {
  const timings: number[] = [];
  let last: T | undefined;
  let lastSerialized: unknown;

  for (let warmup = 0; warmup < WARMUP_RUNS; warmup += 1) {
    fn();
  }

  for (let i = 0; i < MEASURED_RUNS; i += 1) {
    const start = performance.now();
    const { result, serialized } = fn();
    const elapsed = performance.now() - start;
    timings.push(elapsed);
    last = result;
    lastSerialized = serialized;
  }

  const serializedJson = JSON.stringify(lastSerialized);
  const serializedSize = Buffer.byteLength(serializedJson);
  const serializedGzipSize = gzipSync(Buffer.from(serializedJson)).length;

  const total = timings.reduce((sum, value) => sum + value, 0);
  const avg = total / timings.length;
  const min = Math.min(...timings);
  const max = Math.max(...timings);

  return {
    label,
    avg,
    min,
    max,
    runs: timings.length,
    last,
    serializedSize,
    serializedGzipSize,
  };
}

function main() {
  const { payload, sizeRows } = getPayloadInfo();

  // V2 roundtrip benchmark (serialize -> deserialize)
  const v2Roundtrip = benchmarkWithSize("v2 roundtrip", () => {
    const serialized = serializeV2(payload, []);
    const deserialized = deserializeV2(serialized, []);
    return { result: deserialized, serialized };
  });

  // V3 roundtrip benchmark (serialize -> deserialize)
  const v3Roundtrip = benchmarkWithSize("v3 roundtrip", () => {
    const serialized = serializeV3(payload);
    const deserialized = deserializeV3(serialized);
    return { result: deserialized, serialized };
  });

  const rows = [v2Roundtrip, v3Roundtrip].map(
    ({ label, avg, min, max, runs }) => ({
      label,
      runs,
      "avg (ms)": avg.toFixed(3),
      "min (ms)": min.toFixed(3),
      "max (ms)": max.toFixed(3),
    })
  );

  console.table(rows);

  console.log("Payload and serialized sizes:");
  console.table([
    ...sizeRows,
    {
      type: "v2 serialized",
      bytes: v2Roundtrip.serializedSize,
      gzipBytes: v2Roundtrip.serializedGzipSize,
    },
    {
      type: "v3 serialized",
      bytes: v3Roundtrip.serializedSize,
      gzipBytes: v3Roundtrip.serializedGzipSize,
    },
  ]);
}

main();
