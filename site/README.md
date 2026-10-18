# Pair Bench
An end-user Python exercise workbench. `npm ci && npm run dev` in this folder. Vite/React; Gemma 3 1B q4 via transformers.js runs only after explicit download; Python via Pyodide 314.0.7 in a disposable module worker.

164 MIT HumanEval exercises. Visitors can edit, generate, run checks, download code, switch English/Japanese, and inspect a side trace. Checks are shipped to the client and are inspectable; they are not secret. A separate checker namespace reduces accidental helper contamination but is not a hostile-code boundary. Worker deadline is 15 seconds after Python readiness (90s CDN initialization deadline). Stop terminates workers. Code is never sent to an inference server.

Recorded Qwen 2.5 3B results are separate from live Gemma browser sessions. Dataset license is in src/data/HUMANEVAL-LICENSE.txt. ThreeUI Community CRT component is MIT. Fonts are self-hosted SIL OFL. GSAP entrance animation respects reduced motion. No paid integrations or telemetry.

Verification: delivery/evidence/pairbench-browser.json in the delivery workspace records actual passing/negative Python checks, trace dialog, language and mobile flows. The browser worker's deployment CSP limits network access to the pinned Python CDN. This is not a hardened sandbox for arbitrary hostile code; do not execute untrusted confidential inputs.
