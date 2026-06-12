import { useState, useRef, useEffect } from "react";
import { sendMessage, type ChatResponse } from "./api";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Message {
  role: "user" | "assistant";
  content: string;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function App() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "Hello! I'm **Agent Alpha**. How can I help you today?" },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const bottomRef = useRef<HTMLDivElement>(null);

  /* Auto-scroll on new messages */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const data: ChatResponse = await sendMessage(text, sessionId);
      setSessionId(data.session_id ?? undefined);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.reply },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `❌ **Error:** ${msg}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto flex h-dvh max-w-4xl flex-col">
      {/* ---- Header ---- */}
      <header className="flex items-center gap-3 border-b border-gray-800 px-6 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 text-sm font-bold text-white shadow-lg shadow-indigo-500/25">
          α
        </div>
        <div>
          <h1 className="text-lg font-semibold leading-tight tracking-tight">
            Agent Alpha
          </h1>
          <p className="text-xs text-gray-500">powered by pydantic-ai</p>
        </div>
      </header>

      {/* ---- Messages ---- */}
      <div className="flex-1 overflow-y-auto px-6 py-4 scrollbar-thin">
        <div className="space-y-4">
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white"
                    : "bg-gray-800 text-gray-100"
                }`}
              >
                <Markdown content={msg.content} />
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="max-w-[80%] rounded-2xl bg-gray-800 px-4 py-3 text-sm text-gray-400">
                <span className="inline-flex gap-1">
                  <span className="animate-bounce">●</span>
                  <span className="animate-bounce [animation-delay:0.15s]">●</span>
                  <span className="animate-bounce [animation-delay:0.3s]">●</span>
                </span>
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* ---- Input ---- */}
      <form
        onSubmit={handleSubmit}
        className="border-t border-gray-800 px-6 py-4"
      >
        <div className="flex gap-3">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Agent Alpha anything…"
            disabled={loading}
            className="flex-1 rounded-xl border border-gray-700 bg-gray-900 px-4 py-2.5 text-sm text-gray-100 placeholder-gray-500 outline-none transition focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Send
          </button>
        </div>
      </form>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Minimal Markdown renderer (inline only — no deps needed)          */
/* ------------------------------------------------------------------ */

function Markdown({ content }: { content: string }) {
  /* Bold */
  const rendered = content
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/(?<!\*)__(.+?)__(?!\*)/g, "<strong>$1</strong>")
    /* Code blocks */
    .replace(/```(\w*)\n([\s\S]*?)```/g, "<pre class='my-2 overflow-x-auto rounded-lg bg-gray-900 p-3 text-xs'><code>$2</code></pre>")
    /* Inline code */
    .replace(/`([^`]+)`/g, "<code class='rounded bg-gray-900 px-1 py-0.5 text-xs text-indigo-300'>$1</code>")
    /* Line breaks */
    .replace(/\n/g, "<br />");

  return <span dangerouslySetInnerHTML={{ __html: rendered }} />;
}
