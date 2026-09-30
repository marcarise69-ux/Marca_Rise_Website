import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Sparkles, X, Send, ShieldCheck, Users, Briefcase, Info } from "lucide-react";
import { API } from "@/lib/mjApi";
import { mascotFor } from "@/lib/mascots";
import { CertificateVerificationCard } from "./CertificateVerificationCard";
import logo from "@/assets/marca_logo.jpg";

type Msg = {
  id: string;
  role: "user" | "assistant";
  text: string;
  mascot?: string;
  certificate?: Record<string, string> | null;
  certStatus?: "verified" | "revoked" | "not_found";
};

const SUGGESTIONS = [
  "Verify your certificate here",
  "Get to know more about Marca Rise",
  "Do you know who the founders of Marca Rise are?",
  "Meet the founders",
  "Check your internship certificate",
];

const QUICK_ACTIONS = [
  { icon: ShieldCheck, label: "Verify My Certificate", prompt: "I want to verify a certificate" },
  { icon: Briefcase, label: "Our Services ✨", prompt: "What services does Marca Rise offer?" },
  { icon: Users, label: "Meet Founder", prompt: "Who are the founders of Marca Rise?" },
  { icon: Info, label: "About Marca Rise", prompt: "Tell me about Marca Rise" },
];

const WELCOME =
  "Hey! I'm MJ. ✦ I can help you verify your internship certificate, learn about Marca Rise, explore our services, or meet our founders.";

const CERT_RE = /[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+/;
const URL_RE = /(https?:\/\/[^\s)]+)/g;

function renderInline(text: string) {
  const tokens = text.split(
    /(\*\*[^*]+\*\*|https?:\/\/[^\s)]+|\*[^*]+\*)/g
  );

  return tokens.map((token, index) => {
    if (!token) return null;

    // Bold
    if (token.startsWith("**") && token.endsWith("**")) {
      return (
        <strong
          key={index}
          className="font-bold text-slate-900"
        >
          {token.slice(2, -2)}
        </strong>
      );
    }

    // Italic
    if (token.startsWith("*") && token.endsWith("*")) {
      return (
        <em key={index} className="italic">
          {token.slice(1, -1)}
        </em>
      );
    }

    // URL
    if (/^https?:\/\//.test(token)) {
      return (
        <a
          key={index}
          href={token}
          target="_blank"
          rel="noreferrer"
          className="font-semibold text-purple-600 underline underline-offset-2 break-all hover:text-purple-800"
        >
          {token}
        </a>
      );
    }

    return <span key={index}>{token}</span>;
  });
}

function renderText(text: string) {
  const lines = text.replace(/\r\n/g, "\n").split("\n");

  const elements: React.ReactNode[] = [];

  let bulletItems: string[] = [];

  const flushBullets = () => {
    if (!bulletItems.length) return;

    elements.push(
      <ul
        key={`bullets-${elements.length}`}
        className="my-2.5 space-y-2 pl-5 list-disc marker:text-purple-500"
      >
        {bulletItems.map((item, index) => (
          <li
            key={index}
            className="pl-1 leading-6"
          >
            {renderInline(item)}
          </li>
        ))}
      </ul>
    );

    bulletItems = [];
  };

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim();

    // Empty line = paragraph spacing
    if (!line) {
      flushBullets();

      elements.push(
        <div
          key={`space-${index}`}
          className="h-2"
        />
      );

      return;
    }

    // Markdown heading
    if (/^#{1,3}\s+/.test(line)) {
      flushBullets();

      const heading = line.replace(/^#{1,3}\s+/, "");

      elements.push(
        <div
          key={`heading-${index}`}
          className="mt-1 mb-2 text-[15px] font-bold text-slate-900"
        >
          {renderInline(heading)}
        </div>
      );

      return;
    }

    // Bullet: -, •, *
    if (/^[-•*]\s+/.test(line)) {
      bulletItems.push(line.replace(/^[-•*]\s+/, ""));
      return;
    }

    // Numbered list
    if (/^\d+\.\s+/.test(line)) {
      flushBullets();

      const match = line.match(/^(\d+)\.\s+(.*)$/);

      elements.push(
        <div
          key={`number-${index}`}
          className="flex gap-2 my-1.5 leading-6"
        >
          <span className="font-bold text-purple-600 shrink-0">
            {match?.[1]}.
          </span>

          <span>
            {renderInline(match?.[2] || line)}
          </span>
        </div>
      );

      return;
    }

    // Normal paragraph
    flushBullets();

    elements.push(
      <p
        key={`paragraph-${index}`}
        className="leading-6 mb-2"
      >
        {renderInline(line)}
      </p>
    );
  });

  flushBullets();

  return <div className="space-y-0.5">{elements}</div>;
}

const uid = () => Math.random().toString(36).slice(2);

export default function MarcaAIChat() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [mascot, setMascot] = useState("hello");
  const [bubbleIdx, setBubbleIdx] = useState(0);
  const [showBubble, setShowBubble] = useState(false);
  const [lastCert, setLastCert] = useState<Record<string, string> | null>(null);
  const [loadingText, setLoadingText] = useState("Thinking…");

  const sessionId = useRef(uid());
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // rotating suggestion bubbles (paused while chat open)
  useEffect(() => {
    if (open) {
      setShowBubble(false);
      return;
    }
    let mounted = true;
    const cycle = () => {
      if (!mounted) return;
      setShowBubble(true);
      setTimeout(() => mounted && setShowBubble(false), 4200);
    };
    const first = setTimeout(cycle, 2500);
    const interval = setInterval(() => {
      setBubbleIdx((i) => (i + 1) % SUGGESTIONS.length);
      cycle();
    }, 7000);
    return () => {
      mounted = false;
      clearTimeout(first);
      clearInterval(interval);
    };
  }, [open]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, loading]);

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || loading) return;
      const userMsg: Msg = { id: uid(), role: "user", text };
      setMessages((m) => [...m, userMsg]);
      setInput("");
      setLoading(true);
      setMascot("working");
      setLoadingText(
        CERT_RE.test(text) || /verify|certificate/i.test(text)
          ? "Give me a moment — I'm checking that certificate…"
          : "Thinking…"
      );

      const history = messages.slice(-6).map((m) => ({ role: m.role, content: m.text }));

      try {
        const res = await fetch(`${API}/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: text,
            session_id: sessionId.current,
            context_certificate: lastCert,
            history,
          }),
        });
        if (!res.ok) throw new Error("bad");
        const data = await res.json();
        const asst: Msg = {
          id: uid(),
          role: "assistant",
          text: data.reply || "",
          mascot: data.mascot,
          certificate: data.certificate,
          certStatus: data.status,
        };
        setMessages((m) => [...m, asst]);
        setMascot(data.mascot || "explaining");
        if (data.type === "certificate" && data.status === "verified" && data.certificate) {
          setLastCert(data.certificate);
        }
      } catch {
        setMessages((m) => [
          ...m,
          {
            id: uid(),
            role: "assistant",
            text: "Sorry, I couldn't reach the Marca Rise assistant just now. Please try again in a moment.",
            mascot: "error",
          },
        ]);
        setMascot("error");
      } finally {
        setLoading(false);
      }
    },
    [loading, messages, lastCert]
  );

  const openChat = useCallback(() => {
    setOpen(true);
    setMessages((m) => {
      if (m.length === 0) {
        return [{ id: uid(), role: "assistant", mascot: "hello", text: WELCOME }];
      }
      return m;
    });
    setMascot((prev) => prev);
  }, []);

  // external trigger (e.g. from the first-open popup CTA)
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail || {};
      openChat();
      if (detail.prefill) setInput(detail.prefill);
      setTimeout(() => inputRef.current?.focus(), 350);
    };
    window.addEventListener("mj:open", handler as EventListener);
    return () => window.removeEventListener("mj:open", handler as EventListener);
  }, [openChat]);

  // focus input whenever panel opens
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 350);
  }, [open]);

  return (
    <>
      {/* ================= FLOATING ICON (fixed anchor; icon never moves) ================= */}
      <div
        className="fixed z-[99998] w-16 h-16 left-4 top-[75vh] -translate-y-1/2 sm:left-6 sm:top-auto sm:bottom-6 sm:translate-y-0"
        style={{ pointerEvents: open ? "none" : "auto" }}
      >
        {/* suggestion bubble — absolutely anchored to the icon, does NOT affect its position */}
        <AnimatePresence mode="wait">
          {showBubble && !open && (
            <motion.button
              key={bubbleIdx}
              initial={{ opacity: 0, y: -8, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -4, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 300, damping: 24 }}
              onClick={openChat}
              data-testid="mj-suggestion-bubble"
              className="absolute left-0 top-full mt-3 sm:top-auto sm:bottom-full sm:mt-0 sm:mb-3 w-[280px] max-w-[calc(100vw-32px)] text-left rounded-2xl bg-white border border-purple-200 px-4 py-2.5 text-[13px] font-semibold text-slate-700"
              style={{ boxShadow: "0 0 0 1px rgba(168,85,247,0.15),0 10px 30px rgba(124,12,231,0.18)" }}
            >
              {SUGGESTIONS[bubbleIdx]}
              {/* arrow: points UP toward icon on mobile, DOWN on desktop */}
              <span className="absolute left-6 w-3 h-3 rotate-45 bg-white -top-1.5 border-t border-l sm:top-auto sm:-bottom-1.5 sm:border-t-0 sm:border-l-0 sm:border-b sm:border-r border-purple-200" />
            </motion.button>
          )}
        </AnimatePresence>

        {/* orb — fills the fixed wrapper */}
        <AnimatePresence>
          {!open && (
            <motion.button
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0, opacity: 0 }}
              whileHover={{ scale: 1.08 }}
              whileTap={{ scale: 0.92 }}
              onClick={openChat}
              aria-label="Open MJ, the Marca Rise AI assistant"
              data-testid="mj-launcher"
              className="absolute inset-0 w-16 h-16 rounded-full flex items-center justify-center"
              style={{ pointerEvents: "auto" }}
            >
              {/* pulsing glow */}
              <motion.span
                className="absolute inset-0 rounded-full"
                style={{ background: "radial-gradient(circle,#A855F7,transparent 70%)" }}
                animate={{ scale: [1, 1.5, 1], opacity: [0.5, 0, 0.5] }}
                transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
              />
              {/* rotating ring */}
              <motion.span
                className="absolute inset-[-3px] rounded-full"
                style={{
                  background: "conic-gradient(from 0deg,#A855F7,#6D28D9,#4C1D95,#A855F7)",
                  padding: 2,
                  WebkitMask: "radial-gradient(farthest-side,transparent calc(100% - 3px),#000 0)",
                }}
                animate={{ rotate: 360 }}
                transition={{ duration: 6, repeat: Infinity, ease: "linear" }}
              />
              {/* core with Marca Rise logo (subtle idle float only — position stays fixed) */}
              <motion.span
                className="relative w-16 h-16 rounded-full flex items-center justify-center overflow-hidden shadow-[0_10px_30px_rgba(76,29,149,0.5)]"
                style={{ background: "#0B0B0D" }}
                animate={{ y: [0, -5, 0] }}
                transition={{ duration: 3.5, repeat: Infinity, ease: "easeInOut" }}
              >
                <img
                  src={logo}
                  alt="Marca Rise"
                  className="w-full h-full object-cover"
                />
                <span className="absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full bg-green-400 border-2 border-white" />
              </motion.span>
            </motion.button>
          )}
        </AnimatePresence>
      </div>

      {/* ================= PANEL ================= */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 40, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 40, scale: 0.95 }}
            transition={{ type: "spring", stiffness: 260, damping: 26 }}
            data-testid="mj-panel"
            className="fixed z-[99999] bottom-4 left-4 sm:bottom-6 sm:left-6 flex flex-col overflow-hidden rounded-[24px] border border-purple-200/60 bg-white/80 backdrop-blur-2xl shadow-[0_30px_80px_rgba(76,29,149,0.35)]"
            style={{
              width: "min(calc(100vw - 32px), 410px)",
              height: "min(80vh, 660px)",
            }}
          >
            {/* header */}
            <div
              className="relative flex items-center gap-3 px-4 py-3 text-white"
              style={{ background: "linear-gradient(135deg,#4C1D95,#6D28D9)" }}
            >
              <div className="relative">
                <img
                  src={mascotFor(mascot)}
                  alt="MJ"
                  className="w-11 h-11 rounded-full object-cover bg-white/10 border border-white/20"
                />
                <motion.span
                  className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-green-400 border-2 border-[#4C1D95]"
                  animate={{ scale: [1, 1.25, 1] }}
                  transition={{ duration: 1.8, repeat: Infinity }}
                />
              </div>
              <div className="flex-1 leading-tight">
                <div className="flex items-center gap-1.5 font-black tracking-wide">
                  <Sparkles size={14} className="text-purple-200" /> MJ
                </div>
                <div className="text-[11px] text-purple-100/80">
                  Marca Rise AI Assistant
                </div>
              </div>
              <div className="flex items-center gap-1 text-[11px] text-purple-100/90 mr-1">
                <span className="w-2 h-2 rounded-full bg-green-400" /> Online
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close chat"
                data-testid="mj-close"
                className="w-8 h-8 rounded-full hover:bg-white/15 flex items-center justify-center transition"
              >
                <X size={18} />
              </button>
            </div>

            {/* messages */}
            <div
              ref={scrollRef}
              className="flex-1 overflow-y-auto px-3 py-4 space-y-3"
              style={{
                background:
                  "linear-gradient(180deg,#faf8ff 0%,#f3eeff 100%)",
              }}
            >
              {messages.map((m) => (
                <MessageRow key={m.id} m={m} />
              ))}

              {/* quick actions on first open */}
              {messages.length <= 1 && !loading && (
                <div className="grid grid-cols-2 gap-2 pt-1" data-testid="mj-quick-actions">
                  {QUICK_ACTIONS.map((qa) => (
                    <button
                      key={qa.label}
                      onClick={() => send(qa.prompt)}
                      className="flex items-center gap-2 rounded-xl border border-purple-200 bg-white/80 px-3 py-2.5 text-[12px] font-semibold text-purple-800 hover:bg-purple-600 hover:text-white hover:border-purple-600 transition-all"
                    >
                      <qa.icon size={15} />
                      {qa.label}
                    </button>
                  ))}
                </div>
              )}

              {loading && (
                <div className="flex items-end gap-2">
                  <img
                    src={mascotFor("working")}
                    alt=""
                    className="w-8 h-8 rounded-full object-cover"
                  />
                  <div className="rounded-2xl rounded-bl-sm bg-white border border-purple-100 px-4 py-3 shadow-sm">
                    <div className="text-xs text-slate-500 mb-1.5">{loadingText}</div>
                    <div className="flex items-center gap-1.5">
                      {[0, 1, 2].map((i) => (
                        <motion.span
                          key={i}
                          className="w-1.5 h-1.5 rounded-full bg-purple-500"
                          animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }}
                          transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* input */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="flex items-center gap-2 border-t border-purple-100 bg-white/90 px-3 py-3"
            >
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask MJ or paste a Certificate ID…"
                data-testid="mj-input"
                aria-label="Message MJ"
                className="flex-1 rounded-full border border-purple-200 bg-purple-50/40 px-4 py-2.5 text-sm text-slate-800 outline-none focus:border-purple-500 focus:bg-white transition"
              />
              <button
                type="submit"
                disabled={!input.trim() || loading}
                data-testid="mj-send"
                aria-label="Send message"
                className="w-10 h-10 shrink-0 rounded-full flex items-center justify-center text-white disabled:opacity-40 transition-all hover:scale-105"
                style={{ background: "linear-gradient(135deg,#6D28D9,#4C1D95)" }}
              >
                <Send size={16} />
              </button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function MessageRow({ m }: { m: Msg }) {
  const isUser = m.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex items-end gap-2 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && (
        <img
          src={mascotFor(m.mascot)}
          alt="MJ"
          className="w-8 h-8 rounded-full object-cover shrink-0 bg-white border border-purple-100"
        />
      )}
      <div className={`max-w-[88%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-2`}>
        {m.text && (
          <div
            className={
              isUser
                ? "rounded-2xl rounded-br-sm px-4 py-2.5 text-sm text-white shadow-sm"
                : "rounded-2xl rounded-bl-sm px-4 py-3 text-[14px] leading-6 text-slate-800 bg-white border border-purple-100 shadow-sm"
            }
            style={
              isUser
                ? { background: "linear-gradient(135deg,#6D28D9,#4C1D95)" }
                : undefined
            }
          >
            {renderText(m.text)}
          </div>
        )}
        {m.certificate !== undefined && m.certStatus && (
          <CertificateVerificationCard
            status={m.certStatus}
            certificate={m.certificate ?? null}
          />
        )}
      </div>
    </motion.div>
  );
}
