import { useCallback, useState } from "react";

/**
 * FunctionTester - A component that accepts a synchronous function prop
 * and demonstrates client-side execution of transpiled Python functions.
 */

interface FunctionTesterProps {
	/** The synchronous function to test */
	fn: (...args: unknown[]) => unknown;
	/** Label to display for this function */
	label?: string;
	/** Initial value for testing */
	initialValue?: number;
	/** Whether to show the function's string representation */
	showCode?: boolean;
}

export function FunctionTester({
	fn,
	label = "Function Tester",
	initialValue = 5,
	showCode = false,
}: FunctionTesterProps) {
	const [value, setValue] = useState(initialValue);
	const [result, setResult] = useState<string>(() => {
		try {
			return String(fn(initialValue));
		} catch (e) {
			return `Error: ${e}`;
		}
	});

	const handleChange = useCallback(
		(e: React.ChangeEvent<HTMLInputElement>) => {
			const newValue = Number(e.target.value);
			setValue(newValue);
			try {
				setResult(String(fn(newValue)));
			} catch (e) {
				setResult(`Error: ${e}`);
			}
		},
		[fn],
	);

	return (
		<div className="rounded-lg border border-slate-700 bg-slate-800 p-4 space-y-3">
			<h3 className="text-lg font-semibold text-slate-200">{label}</h3>

			{showCode && (
				<pre className="text-xs text-slate-400 bg-slate-900 p-2 rounded overflow-x-auto">
					{fn.toString()}
				</pre>
			)}

			<div className="flex items-center gap-3">
				<label className="text-slate-300">
					Input:
					<input
						type="number"
						value={value}
						onChange={handleChange}
						className="ml-2 w-24 px-2 py-1 bg-slate-900 border border-slate-600 rounded text-white"
					/>
				</label>
			</div>

			<div className="flex items-center gap-2">
				<span className="text-slate-400">Result:</span>
				<span className="font-mono text-emerald-400 font-semibold">{result}</span>
			</div>
		</div>
	);
}

/**
 * MultiArgFunctionTester - Tests functions with multiple arguments
 */
interface MultiArgTesterProps {
	fn: (...args: number[]) => unknown;
	label?: string;
	argLabels?: string[];
	initialValues?: number[];
	showCode?: boolean;
}

export function MultiArgFunctionTester({
	fn,
	label = "Multi-Arg Function",
	argLabels = ["a", "b"],
	initialValues = [5, 3],
	showCode = false,
}: MultiArgTesterProps) {
	const [values, setValues] = useState(initialValues);
	const [result, setResult] = useState<string>(() => {
		try {
			return String(fn(...initialValues));
		} catch (e) {
			return `Error: ${e}`;
		}
	});

	const handleChange = useCallback(
		(index: number, newValue: number) => {
			const newValues = [...values];
			newValues[index] = newValue;
			setValues(newValues);
			try {
				setResult(String(fn(...newValues)));
			} catch (e) {
				setResult(`Error: ${e}`);
			}
		},
		[fn, values],
	);

	return (
		<div className="rounded-lg border border-slate-700 bg-slate-800 p-4 space-y-3">
			<h3 className="text-lg font-semibold text-slate-200">{label}</h3>

			{showCode && (
				<pre className="text-xs text-slate-400 bg-slate-900 p-2 rounded overflow-x-auto">
					{fn.toString()}
				</pre>
			)}

			<div className="flex flex-wrap items-center gap-3">
				{values.map((val, i) => (
					<label key={argLabels[i] || i} className="text-slate-300">
						{argLabels[i] || `arg${i}`}:
						<input
							type="number"
							value={val}
							onChange={(e) => handleChange(i, Number(e.target.value))}
							className="ml-2 w-20 px-2 py-1 bg-slate-900 border border-slate-600 rounded text-white"
						/>
					</label>
				))}
			</div>

			<div className="flex items-center gap-2">
				<span className="text-slate-400">Result:</span>
				<span className="font-mono text-emerald-400 font-semibold">{result}</span>
			</div>
		</div>
	);
}

/**
 * StringFunctionTester - Tests functions that accept a string
 */
interface StringTesterProps {
	fn: (s: string) => unknown;
	label?: string;
	initialValue?: string;
	showCode?: boolean;
}

export function StringFunctionTester({
	fn,
	label = "String Function",
	initialValue = "hello world",
	showCode = false,
}: StringTesterProps) {
	const [value, setValue] = useState(initialValue);
	const [result, setResult] = useState<string>(() => {
		try {
			return String(fn(initialValue));
		} catch (e) {
			return `Error: ${e}`;
		}
	});

	const handleChange = useCallback(
		(e: React.ChangeEvent<HTMLInputElement>) => {
			const newValue = e.target.value;
			setValue(newValue);
			try {
				setResult(String(fn(newValue)));
			} catch (e) {
				setResult(`Error: ${e}`);
			}
		},
		[fn],
	);

	return (
		<div className="rounded-lg border border-slate-700 bg-slate-800 p-4 space-y-3">
			<h3 className="text-lg font-semibold text-slate-200">{label}</h3>

			{showCode && (
				<pre className="text-xs text-slate-400 bg-slate-900 p-2 rounded overflow-x-auto">
					{fn.toString()}
				</pre>
			)}

			<div className="flex items-center gap-3">
				<label className="text-slate-300 flex-1">
					Input:
					<input
						type="text"
						value={value}
						onChange={handleChange}
						className="ml-2 w-full max-w-md px-2 py-1 bg-slate-900 border border-slate-600 rounded text-white"
					/>
				</label>
			</div>

			<div className="flex items-center gap-2">
				<span className="text-slate-400">Result:</span>
				<span className="font-mono text-emerald-400 font-semibold break-all">{result}</span>
			</div>
		</div>
	);
}

/**
 * ArrayFunctionTester - Tests functions that accept an array
 */
interface ArrayTesterProps {
	fn: (arr: number[]) => unknown;
	label?: string;
	initialValue?: string;
	showCode?: boolean;
}

export function ArrayFunctionTester({
	fn,
	label = "Array Function",
	initialValue = "1, 2, 3, 4, 5",
	showCode = false,
}: ArrayTesterProps) {
	const [value, setValue] = useState(initialValue);
	const [result, setResult] = useState<string>(() => {
		try {
			const arr = value
				.split(",")
				.map((s) => Number(s.trim()))
				.filter((n) => !Number.isNaN(n));
			return JSON.stringify(fn(arr));
		} catch (e) {
			return `Error: ${e}`;
		}
	});

	const handleChange = useCallback(
		(e: React.ChangeEvent<HTMLInputElement>) => {
			const newValue = e.target.value;
			setValue(newValue);
			try {
				const arr = newValue
					.split(",")
					.map((s) => Number(s.trim()))
					.filter((n) => !Number.isNaN(n));
				setResult(JSON.stringify(fn(arr)));
			} catch (e) {
				setResult(`Error: ${e}`);
			}
		},
		[fn],
	);

	return (
		<div className="rounded-lg border border-slate-700 bg-slate-800 p-4 space-y-3">
			<h3 className="text-lg font-semibold text-slate-200">{label}</h3>

			{showCode && (
				<pre className="text-xs text-slate-400 bg-slate-900 p-2 rounded overflow-x-auto">
					{fn.toString()}
				</pre>
			)}

			<div className="flex items-center gap-3">
				<label className="text-slate-300 flex-1">
					Array (comma-separated):
					<input
						type="text"
						value={value}
						onChange={handleChange}
						className="ml-2 w-full max-w-md px-2 py-1 bg-slate-900 border border-slate-600 rounded text-white"
					/>
				</label>
			</div>

			<div className="flex items-center gap-2">
				<span className="text-slate-400">Result:</span>
				<span className="font-mono text-emerald-400 font-semibold break-all">{result}</span>
			</div>
		</div>
	);
}
