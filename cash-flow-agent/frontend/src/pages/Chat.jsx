import { Send, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { sendChatMessage } from "../api/endpoints";
import PageHeader from "../components/PageHeader";

export default function Chat() {
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Hi! Ask me anything about your cash flow and liquidity — e.g. \"Which month might I run into a cash shortage?\"" },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(e) {
    e.preventDefault();
    const question = input.trim();
    if (!question) return;
    setMessages((m) => [...m, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    try {
      const { data } = await sendChatMessage({ question, horizon: 12, scenario: "expected" });
      setMessages((m) => [...m, { role: "assistant", text: data.answer }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Sorry, something went wrong answering that." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto flex flex-col h-[calc(100vh-9.5rem)]">
      <PageHeader title="AI Chat" subtitle="Ask questions about your forecast in plain language." />
      <div className="flex-1 overflow-y-auto card p-4 space-y-3 mb-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            {m.role === "assistant" && (
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 mr-2"
                style={{ background: "var(--brand-100)", color: "var(--brand-700)" }}
              >
                <Sparkles size={14} />
              </div>
            )}
            <div
              className="max-w-[80%] rounded-2xl px-3.5 py-2.5 text-sm whitespace-pre-wrap"
              style={
                m.role === "user"
                  ? { background: "var(--brand-600)", color: "#fff", borderBottomRightRadius: 4 }
                  : { background: "#f1f5f9", color: "var(--ink-900)", borderBottomLeftRadius: 4 }
              }
            >
              {m.text}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex items-center gap-2 text-sm" style={{ color: "var(--ink-400)" }}>
            <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: "var(--ink-400)" }} />
            <span className="w-1.5 h-1.5 rounded-full animate-bounce [animation-delay:0.1s]" style={{ background: "var(--ink-400)" }} />
            <span className="w-1.5 h-1.5 rounded-full animate-bounce [animation-delay:0.2s]" style={{ background: "var(--ink-400)" }} />
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <form onSubmit={handleSend} className="flex gap-2">
        <input
          className="input"
          placeholder="Type your question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" disabled={loading} className="btn-primary">
          <Send size={16} />
        </button>
      </form>
    </div>
  );
}
