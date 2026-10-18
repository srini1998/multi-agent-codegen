# Immediate coding practice

All 164 HumanEval exercises include original single/team drafts exported from the actual frozen Qwen 2.5 3B benchmark artifacts. Loading these is explicitly recorded replay; test execution remains real Pyodide in a disposable worker. Code edits invalidate previous results. No model weights are downloaded.

Fresh generation is an optional server API using Groq's quota-limited Free Plan. It is disabled unless GROQ_API_KEY and GROQ_FREE_PLAN_CONFIRMED=true are set in the server environment. No credentials or billing have been configured by this update. Provider failure or exhausted quota returns an error, without canned output or paid fallback. Generation sends task text to the provider; Python checks remain local. Free provider quotas can be exhausted by public use; this is a small portfolio demo, not an authenticated production service.

Validation: TypeScript/Vite build; real Chrome loads both recorded strategies, actual Python positive/negative checks, edits clear passes, English-only/390px, no model-weight requests. See parent delivery/evidence/pairbench-immediate-browser.json. Original backend results and hardened container harness remain unchanged.
