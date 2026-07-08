"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type TraceEvent = {
  kind: string;
  label: string;
  seconds: number;
  [key: string]: unknown;
};

type TurnResponse = {
  reply: string;
  transcript?: string;
  intents: string[];
  seconds?: number;
  total_seconds?: number;
  stt_seconds?: number;
  tts_seconds?: number;
  trace: TraceEvent[];
  reply_audio_b64?: string;
  reply_audio_mime?: string;
};

type Ledger = {
  customers: { name: string; balance_paise: number; balance: string }[];
  transactions: {
    id: number;
    type: string;
    amount: string;
    customer: string | null;
    ts: string;
  }[];
  today: {
    date: string;
    sales: string;
    udhaar_given: string;
    repayments_received: string;
    cash_in: string;
  };
};

type Turn = {
  you: string;
  bahi: string;
  intents: string[];
  timing: string;
  error?: boolean;
};

type Profile = Record<string, string>;

const TYPE_HINDI: Record<string, string> = {
  sale: "बिक्री",
  udhaar: "उधार",
  repayment: "वापसी",
};

function timingLine(body: TurnResponse): string {
  const llm = body.trace
    .filter((e) => e.kind === "llm")
    .reduce((total, e) => total + e.seconds, 0);
  const parts: string[] = [];
  if (body.stt_seconds != null) parts.push(`stt ${body.stt_seconds.toFixed(1)}s`);
  parts.push(`llm ${llm.toFixed(1)}s`);
  if (body.tts_seconds != null) parts.push(`tts ${body.tts_seconds.toFixed(1)}s`);
  parts.push(`total ${(body.total_seconds ?? body.seconds ?? 0).toFixed(1)}s`);
  return parts.join(" · ");
}

export default function Console() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const threadRef = useRef<HTMLDivElement>(null);

  const refreshLedger = useCallback(async () => {
    try {
      const response = await fetch("/api/ledger");
      if (response.ok) setLedger(await response.json());
    } catch {
      /* server not up yet — footer shows the hint */
    }
  }, []);

  useEffect(() => {
    fetch("/health")
      .then((r) => r.json())
      .then((body) => setProfile(body.profile))
      .catch(() => setProfile(null));
    fetch("/api/ledger")
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => body && setLedger(body))
      .catch(() => {});
  }, []);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const pushResult = useCallback(
    (you: string, body: TurnResponse) => {
      setTurns((prev) => [
        ...prev,
        { you, bahi: body.reply || "(chup)", intents: body.intents, timing: timingLine(body) },
      ]);
      if (body.reply_audio_b64) {
        const bytes = Uint8Array.from(atob(body.reply_audio_b64), (c) => c.charCodeAt(0));
        const url = URL.createObjectURL(
          new Blob([bytes], { type: body.reply_audio_mime ?? "audio/wav" })
        );
        const audio = new Audio(url);
        audio.onended = () => URL.revokeObjectURL(url);
        void audio.play();
      }
      void refreshLedger();
    },
    [refreshLedger]
  );

  const pushError = (you: string, message: string) => {
    setTurns((prev) => [
      ...prev,
      { you, bahi: message, intents: [], timing: "", error: true },
    ]);
  };

  const sendAudio = useCallback(
    async (blob: Blob) => {
      setBusy(true);
      const form = new FormData();
      form.append("file", blob, "utterance.webm");
      try {
        const response = await fetch("/api/turn/audio", { method: "POST", body: form });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail ?? response.statusText);
        pushResult(body.transcript ?? "(bola)", body);
      } catch (error) {
        pushError("(bola)", `sun nahi paya — ${String(error)}`);
      } finally {
        setBusy(false);
      }
    },
    [pushResult]
  );

  const toggleMic = useCallback(async () => {
    if (busy) return;
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "audio/mp4";
      const recorder = new MediaRecorder(stream, { mimeType: mime });
      chunksRef.current = [];
      recorder.ondataavailable = (event) => chunksRef.current.push(event.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        void sendAudio(new Blob(chunksRef.current, { type: mime }));
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      pushError("(mic)", "microphone nahi mila — neeche likh ke pucho");
    }
  }, [busy, recording, sendAudio]);

  const sendTyped = useCallback(
    async (event: React.FormEvent) => {
      event.preventDefault();
      const text = typed.trim();
      if (!text || busy) return;
      setTyped("");
      setBusy(true);
      try {
        const response = await fetch("/api/turn", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail ?? response.statusText);
        pushResult(text, body);
      } catch (error) {
        pushError(text, `jawab nahi aaya — ${String(error)}`);
      } finally {
        setBusy(false);
      }
    },
    [typed, busy, pushResult]
  );

  return (
    <div className="book">
      <header className="spine">
        <div className="wordmark">
          <span className="devanagari">बही</span>
          <span>
            <span className="latin">Bahi</span>
            <span className="tagline"> · bol ke likho — the ledger writes itself</span>
          </span>
        </div>
        <div className="stamp">
          {profile ? (
            <>
              stt <b>{profile.stt}</b> · tts <b>{profile.tts}</b>
              <br />
              brain <b>{profile.orchestrator}</b> · routing <b>{profile.routing}</b>
            </>
          ) : (
            <>server offline — make run</>
          )}
        </div>
      </header>

      <main className="page">
        <section className="voice">
          <div className="mic-area">
            <button
              className={`mic ${recording ? "recording" : ""}`}
              onClick={toggleMic}
              disabled={busy}
              aria-label={recording ? "Stop recording" : "Start recording"}
            >
              {recording ? "सुन रहा…" : busy ? "…" : "बोलिए"}
            </button>
            <p className="mic-hint">
              “Ramesh ko 200 rupaye udhaar likh do” · “aaj ka hisaab batao”
              <span className="status">
                {recording ? "recording — tap to finish" : busy ? "soch raha hoon…" : "tap & speak"}
              </span>
            </p>
          </div>

          <div className="thread" ref={threadRef}>
            {turns.length === 0 && (
              <p className="empty">Aaj ki pehli entry boliye…</p>
            )}
            {turns.map((turn, index) => (
              <div className="turn" key={index}>
                <div className="you">{turn.you}</div>
                {turn.error ? (
                  <div className="error-note">{turn.bahi}</div>
                ) : (
                  <div className="bahi">{turn.bahi}</div>
                )}
                {turn.timing && (
                  <div className="meta">
                    {turn.intents.length > 0 && (
                      <>
                        <span className="intent">{turn.intents.join(" + ")}</span>
                        {" — "}
                      </>
                    )}
                    {turn.timing}
                  </div>
                )}
              </div>
            ))}
          </div>

          <form className="ask-form" onSubmit={sendTyped}>
            <input
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
              placeholder="…ya likh ke pucho"
              disabled={busy}
            />
            <button type="submit" disabled={busy || !typed.trim()}>
              likho
            </button>
          </form>
        </section>

        <section className="khata">
          <h2>आज का हिसाब {ledger ? `— ${ledger.today.date}` : ""}</h2>
          {ledger ? (
            <div className="today-row">
              <span className="fig">
                <span className="label">bikri</span>
                <span className="value">{ledger.today.sales}</span>
              </span>
              <span className="fig">
                <span className="label">udhaar diya</span>
                <span className="value owes">{ledger.today.udhaar_given}</span>
              </span>
              <span className="fig">
                <span className="label">wapsi</span>
                <span className="value clear">{ledger.today.repayments_received}</span>
              </span>
              <span className="fig">
                <span className="label">cash in</span>
                <span className="value">{ledger.today.cash_in}</span>
              </span>
            </div>
          ) : (
            <p className="empty">khata khaali hai…</p>
          )}

          <div className="section-label">khata — kaun kitna dena hai</div>
          <table className="ruled">
            <tbody>
              {(ledger?.customers ?? []).map((customer) => (
                <tr key={customer.name}>
                  <td>{customer.name}</td>
                  <td className={`amount ${customer.balance_paise > 0 ? "owes" : "clear"}`}>
                    {customer.balance}
                  </td>
                </tr>
              ))}
              {ledger && ledger.customers.length === 0 && (
                <tr>
                  <td className="empty">koi udhaar nahi — sab saaf</td>
                </tr>
              )}
            </tbody>
          </table>

          <div className="section-label" style={{ marginTop: "var(--line-h)" }}>
            taaza entries
          </div>
          <table className="ruled">
            <tbody>
              {(ledger?.transactions ?? []).slice(0, 8).map((txn) => (
                <tr key={txn.id}>
                  <td>
                    <span className={`txn-type ${txn.type}`}>
                      {TYPE_HINDI[txn.type] ?? txn.type}
                    </span>
                    {txn.customer ? ` — ${txn.customer}` : ""}
                  </td>
                  <td className="amount">{txn.amount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </main>

      <footer className="footer-note">
        provider-blind core · swap the whole stack with one env profile · built with Claude Code
      </footer>
    </div>
  );
}
