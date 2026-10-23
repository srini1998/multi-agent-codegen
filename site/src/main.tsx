import { createRoot } from "react-dom/client";
import { useState, useRef, useEffect } from "react";
import { CrtBackground } from "@designcodeio/threeui/components/CrtBackground";
import { Play, ArrowUpRight, TerminalWindow } from "@phosphor-icons/react";
import tasks from "./data/humaneval.json";
import drafts from "./data/drafts.json";
import recorded from "./data/results.json";
import { useModel } from "./ai/useModel";
import { Shell, Trace, ModelControl, useLanguage } from "./ui";
import "./styles.css";
function App() {
  const { ja, t, toggle } = useLanguage(),
    model = useModel();
  const [idx, setIdx] = useState(0),
    [code, setCode] = useState(
      "def has_close_elements(numbers, threshold):\n    # Write your solution here\n    return False\n",
    ),
    [strategy, setStrategy] = useState("team"),
    [busy, setBusy] = useState(""),
    [status, setStatus] = useState(""),
    [entries, setEntries] = useState<unknown[]>([]);
  const agentNote = useRef("");
  const worker = useRef<Worker | null>(null),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const task = tasks[idx];
  const log = (entry: unknown) => setEntries((e) => [...e, entry]);
  function stop() {
    worker.current?.terminate();
    worker.current = null;
    if (timer.current) clearTimeout(timer.current);
    model.stop();
    setBusy("");
    setStatus(
      t("Stopped. No result recorded.", "停止しました。結果は保存されません。"),
    );
  }
  useEffect(
    () => () => {
      worker.current?.terminate();
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );
  async function write() {
    setBusy("agent");
    setStatus(t("Asking the cloud model…", "端末上で生成中…"));
    let context = "";
    let draft = "";
    const calls: { role: string; model?: string; ms: number }[] = [];
    try {
      const roles =
        strategy === "team" ? ["planner", "coder", "reviewer"] : ["coder"];
      for (const role of roles) {
        const instruction =
          role === "planner"
            ? "Write a short plan. No code."
            : role === "reviewer"
              ? "Review the candidate, fix bugs, return the complete Python function in a python code fence."
              : "Return a complete Python function in a python code fence. No explanation.";
        const prompt = `${instruction}\nImplement this exact exercise:\n${task.prompt}\n${context.slice(-6000)}`;
        const result = await model.generate(
          [{ role: "user", content: prompt }],
          undefined,
          512,
        );
        log({ at: new Date().toISOString(), role, prompt, ...result });
        calls.push({ role, model: result.model, ms: result.ms });
        context += `\n${role}: ${result.text}`;
        if (role !== "planner") {
          const text = result.text;
          const match = text.match(/```(?:python)?\s*\n([\s\S]*?)```/);
          const candidate = (
            match?.[1] ?? text.slice(Math.max(0, text.indexOf("def ")))
          ).trim();
          if (!candidate.includes(`def ${task.entry}(`))
            throw new Error(
              t(
                "Model did not return the required function. Inspect its trace and try single-coder mode.",
                "必要な関数が生成されませんでした。記録を確認してください。",
              ),
            );
          setCode(candidate);
          draft = candidate;
        }
      }
      agentNote.current = `(${calls[0]?.model ?? "cloud model"}, ${calls.length} call${calls.length > 1 ? "s" : ""}, ${calls.reduce((n, c) => n + c.ms, 0)} ms: ${calls.map((c) => c.role).join(" → ")}.)`;
      setStatus(
        "Draft written by " + agentNote.current + " Now running the real HumanEval tests on it in Python…",
      );
    } catch (e) {
      setStatus(String(e));
      log({ error: String(e) });
      setBusy("");
      return;
    }
    // The model's claim is not trusted: the draft is executed against the exercise's own tests.
    run(draft, "cloud-draft");
  }
  function run(src: string = code, origin = "editor") {
    setBusy("test");
    setStatus(
      t(
        "Loading Python (~12 MB); code then has 15 seconds.",
        "Python を読込中（約12MB）。実行時間は15秒です。",
      ),
    );
    const w = new Worker("/python-worker.mjs", { type: "module" });
    worker.current = w;
    const finish = (message: string) => {
      setStatus(message);
      setBusy("");
      w.terminate();
      worker.current = null;
      if (timer.current) clearTimeout(timer.current);
    };
    timer.current = setTimeout(
      () =>
        finish(
          t(
            "Python download timed out. Check your connection.",
            "Python の読込がタイムアウトしました。",
          ),
        ),
      90000,
    );
    w.onerror = (e) => {
      finish(e.message);
      log({ error: e.message });
    };
    w.onmessage = ({ data: m }) => {
      if (m.type === "ready") {
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => {
          finish(t("Stopped after 15 seconds.", "15秒で停止しました。"));
          log({ kind: "test", task: task.id, ok: false, reason: "timeout" });
        }, 15000);
        w.postMessage({ code: src, test: task.test, entry: task.entry });
      } else if (m.type === "result") {
        const label = m.ok
          ? t(
              "Exercise checks passed. This is not a security or production audit.",
              "課題のチェックに合格しました。実運用の監査ではありません。",
            )
          : t(
              "Checks failed. Edit your code and try again.",
              "チェックに失敗しました。コードを修正してください。",
            );
        log({ kind: "test", task: task.id, origin, code: src, ...m });
        finish(
          (origin === "cloud-draft"
            ? (m.ok
                ? "Fresh cloud draft PASSED the real tests. "
                : "Fresh cloud draft FAILED the real tests — the model was wrong. ") +
              agentNote.current +
              "\n"
            : "") +
            label +
            (m.output ? "\n" + m.output : ""),
        );
      }
    };
  }
  return (
    <Shell name="PAIR BENCH" number="02" ja={ja} toggle={toggle}>
      <section className="hero">
        <div className="crt" aria-hidden="true">
          <CrtBackground />
        </div>
        <p className="eyebrow reveal">
          {t(
            "THE CODING PRACTICE ROOM",
            "もう一人の相棒。実際のテスト。",
          )}
        </p>
        <h1 className="reveal">
          {t("Can the code", "書く。動かす。")}
          <br />
          <em>{t("pass the test?", "確かめる。")}</em>
        </h1>
        <div className="hero-bottom reveal">
          <p>
            {t(
              "Pick a Python challenge. Try a saved AI solution, change the code and run the real tests. Compare one coder with a team of three—no AI download or account needed.",
              "小さな Python の課題を、動くコードに。端末上のチームに下書きを頼み、テストで確かめましょう。",
            )}
          </p>
          <a className="cta" href="#bench">
            {t("Open the bench", "作業を始める")} <ArrowUpRight size={24} />
          </a>
        </div>
      </section>
      <main id="bench">
        <header className="section-head">
          <h2>
            <TerminalWindow size={28} /> {t("Your workbench", "ワークベンチ")}
          </h2>
          <span>01—164 / HUMAN EVAL</span>
        </header>
        <div className="bench">
          <section className="question">
            <label htmlFor="exercise">
              {t("Choose a real coding exercise", "課題を選ぶ")}
            </label>
            <select
              id="exercise"
              disabled={!!busy}
              value={idx}
              onChange={(e) => {
                const i = Number(e.target.value);
                setIdx(i);
                setCode(tasks[i].prompt + "    pass\n");
                setStatus("");
              }}
            >
              {tasks.map((q, i) => (
                <option key={q.id} value={i}>
                  {q.id} · {q.entry}
                </option>
              ))}
            </select>
            <pre className="spec">{task.prompt}</pre>
            <details>
              <summary>
                {t(
                  "Exercise checks (inspectable in this browser)",
                  "チェック内容（ブラウザで閲覧可能）",
                )}
              </summary>
              <pre>{task.test}</pre>
            </details>
            <p className="note">
              {t(
                "These are public benchmark exercises, not secret tests. Uploaded files and system access are not supported.",
                "公開ベンチマークです。秘密のテストではありません。ファイル操作やシステムアクセスは対象外です。",
              )}
            </p>
          </section>
          <section>
            <label htmlFor="code">
              {t("Your Python function", "Python 関数")}
            </label>
            <textarea
              id="code"
              spellCheck={false}
              value={code}
              onChange={(e) => {
                setCode(e.target.value);
                setStatus(
                  t(
                    "Code changed. Run checks again.",
                    "コードを変更しました。再度チェックしてください。",
                  ),
                );
              }}
              disabled={!!busy}
              maxLength={64000}
            />
            <div className="actions">
              <button className="cta" onClick={() => run()} disabled={!!busy}>
                <Play size={18} />
                {t("Run checks", "チェックを実行")}
              </button>
              <button
                onClick={stop}
                disabled={!busy && model.state.phase === "idle"}
              >
                {t("Stop", "停止")}
              </button>
              <button
                className="quiet"
                onClick={() => {
                  const u = URL.createObjectURL(
                    new Blob([code], { type: "text/x-python" }),
                  );
                  const a = document.createElement("a");
                  a.href = u;
                  a.download = task.entry + ".py";
                  a.click();
                  URL.revokeObjectURL(u);
                }}
              >
                {t("Download .py", "保存 .py")}
              </button>
            </div>
            <output role="status">
              {status ||
                t(
                  "Write a solution or load a recorded AI draft. Nothing runs until you click Run checks.",
                  "コードを書くか、下のエージェントを利用してください。",
                )}
            </output>
            <div className="ai-box"><h3>Start with a real AI attempt</h3><p>These drafts were generated by Qwen 2.5 3B during the saved 164-task experiment. Load either approach instantly, then judge it with the actual tests. Loading a draft is a replay, not a new generation.</p><div className="actions">{(['single','team'] as const).map(mode=><button key={mode} disabled={!!busy} onClick={()=>{const d=(drafts as Record<string,Record<string,{code:string;model:string}>>)[task.id]?.[mode];if(!d){setStatus('No recorded draft for this task.');return;}setCode(d.code);setStatus('Recorded '+mode+' draft loaded. Run checks to see whether it works.');log({action:'load-recorded-draft',task:task.id,strategy:mode,model:d.model});}}>{mode==='single'?'Try one coder':'Try a coding team'} ↗</button>)}</div></div>
            <details className="ai-box"><summary>Want a fresh AI attempt?</summary>
            <div className="ai-box">
              <h3>{t("Generate a new draft (optional cloud)", "下書きを依頼する")}</h3>
              <p>
                {t(
                  "One coder, or a planner → coder → reviewer, on Groq’s free plan (openai/gpt-oss-20b). The new draft is then executed against the exercise’s real tests in your browser — the model’s own claim is never trusted. More roles can make the answer worse.",
                  "単独の作成者、または計画→作成→レビュー。同じモデルでも役割を増やすと結果が悪くなることがあります。",
                )}
              </p>
              <ModelControl
                state={model.state}
                load={model.load}
                stop={stop}
                ja={ja}
              />
              <select
                aria-label={t("Agent strategy", "エージェントの構成")}
                value={strategy}
                disabled={!!busy}
                onChange={(e) => setStrategy(e.target.value)}
              >
                <option value="single">
                  {t("Single coder", "単独の作成者")}
                </option>
                <option value="team">
                  {t("Planner → Coder → Reviewer", "計画 → 作成 → レビュー")}
                </option>
              </select>
              <button
                onClick={write}
                disabled={!!busy || model.state.phase !== "ready"}
              >
                {busy === "agent"
                  ? t("Generating…", "生成中…")
                  : t("Generate a new cloud draft", "下書きを生成")}
              </button>
            </div></details>
          </section>
        </div>
        <section className="results">
          <div>
            <p className="eyebrow">
              {t(
                "WHAT THE EXPERIMENT ACTUALLY FOUND",
                "実験で実際に分かったこと",
              )}
            </p>
            <h2>
              {t(
                "A team isn’t always better.",
                "チームが優れているとは限らない。",
              )}
            </h2>
            <p>
              {t(
                "164 HumanEval tasks. A local Qwen 2.5 3B model. Saved solutions regraded in an offline Python container. These are recorded results, not your current browser session.",
                "HumanEval 164問、ローカルの Qwen 2.5 3B。オフラインの Python コンテナで再評価した保存済みの結果です。",
              )}
            </p>
          </div>
          <div>
            {Object.entries(recorded.strategies).map(([name, s]) => (
              <div className="bar-row" key={name}>
                <span>{name}</span>
                <strong>{(s.solve_rate * 100).toFixed(1)}%</strong>
                <div className="bar">
                  <i style={{ width: s.solve_rate * 100 + "%" }} />
                </div>
                <small>
                  {s.solved}/164 · {s.mean_llm_calls}{" "}
                  {t("calls / task", "回 / 問")}
                </small>
              </div>
            ))}
            <p className="note">
              {t(
                "Final-solution solve rates; unequal call budgets. This browser uses Gemma 3 1B, a different model. Its output is unmeasured until you run checks.",
                "最終解答の成功率。呼び出し回数は同じではありません。ブラウザは別モデルの Gemma 3 1B を使用します。",
              )}
            </p>
          </div>
        </section>
        <section id="how" className="how">
          <h2>
            {t(
              "From an exercise to an answer you can check.",
              "課題から、検証できる答えへ。",
            )}
          </h2>
          <ol>
            <li>
              {t(
                "Pick a function-sized task. For example, find two measurements closer than a tolerance. Useful for data cleanup and small utilities.",
                "関数サイズの課題を選ぶ。例：許容値より近い2つの測定値を探す。データ整理に役立ちます。",
              )}
            </li>
            <li>
              {t(
                "Write Python yourself or explicitly download the free browser model and generate a draft. Your text stays on your device.",
                "自分で Python を書くか、無料のモデルをダウンロードして下書きを生成します。入力は端末に留まります。",
              )}
            </li>
            <li>
              {t(
                "Run actual Python in a disposable WebAssembly worker. Checks use a separate namespace. A 15-second limit stops loops.",
                "使い捨ての WebAssembly ワーカーで Python を実行。チェックは別の名前空間で実行し、15秒で停止します。",
              )}
            </li>
          </ol>
          <p className="note">
            {t(
              "A worker keeps the interface responsive; it is not a hardened sandbox for hostile code. No confidential data, host files or credentials are provided. Browser tests do not certify correctness beyond these cases.",
              "ワーカーは画面を応答可能に保ちますが、悪意のあるコードに対する完全な隔離ではありません。テストは記載のケースだけを確認します。",
            )}
          </p>
          <a href="https://github.com/srini1998/multi-agent-codegen">
            {t(
              "Source, methodology & MIT dataset license",
              "ソース・評価方法・MIT ライセンス",
            )}{" "}
            ↗
          </a>
        </section>
      </main>
      <Trace ja={ja} entries={entries} />
    </Shell>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
