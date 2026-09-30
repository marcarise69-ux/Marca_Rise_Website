import { useState } from "react";
import { useLocation } from "wouter";
import { motion, AnimatePresence } from "framer-motion";
import { X, ShieldCheck, ArrowRight } from "lucide-react";
import mjHello from "@/assets/MJ_MOSCOT/MJ_HELLO.png";

const STEPS = [
  { num: "01", text: "Find your Certificate ID" },
  { num: "02", text: "Open the MJ Chat Assistant" },
  { num: "03", text: "Enter: VERIFY MR00-XX-00000" },
];

export default function CertificatePopup() {
  // IMPORTANT:
  // Popup is visible immediately on every fresh website load / refresh.
  const [open, setOpen] = useState(true);

  const [location] = useLocation();

  // Never show on admin panel
  if (location.startsWith("/admin")) return null;

  const dismiss = () => {
    setOpen(false);
  };

  const verifyWithMj = () => {
    // Close popup immediately
    setOpen(false);

    // Open MJ immediately
    window.dispatchEvent(
      new CustomEvent("mj:open", {
        detail: {
          prefill: "VERIFY ",
        },
      })
    );
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          data-testid="cert-popup-overlay"
          className="fixed inset-0 z-[100001] flex items-center justify-center p-4"
          style={{
            background: "rgba(11,11,13,0.55)",
            backdropFilter: "blur(6px)",
          }}
          onClick={dismiss}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{
              type: "spring",
              stiffness: 240,
              damping: 24,
            }}
            onClick={(e) => e.stopPropagation()}
            data-testid="cert-popup"
            className="relative w-full max-w-[480px] max-h-[90vh] overflow-y-auto rounded-[28px] border border-purple-300/40 shadow-[0_30px_90px_rgba(76,29,149,0.45)]"
            style={{
              background:
                "linear-gradient(160deg, rgba(255,255,255,0.97), rgba(243,238,255,0.97))",
            }}
          >
            {/* Glow */}
            <div
              className="pointer-events-none absolute -top-16 -right-16 w-48 h-48 rounded-full blur-3xl"
              style={{
                background: "rgba(168,85,247,0.35)",
              }}
            />

            {/* Close */}
            <button
              onClick={dismiss}
              aria-label="Close"
              data-testid="cert-popup-close"
              className="absolute top-4 right-4 w-9 h-9 rounded-full bg-black/5 hover:bg-black/10 flex items-center justify-center text-slate-600 transition z-10"
            >
              <X size={18} />
            </button>

            <div className="relative p-7 sm:p-9">

              {/* Header */}
              <div className="flex items-center gap-4 mb-5">
                <div className="relative shrink-0">
                  <div
                    className="absolute inset-0 rounded-2xl blur-md"
                    style={{
                      background: "rgba(124,12,231,0.35)",
                    }}
                  />

                  <img
                    src={mjHello}
                    alt="MJ"
                    className="relative w-16 h-16 rounded-2xl object-cover border border-purple-200 bg-white"
                  />
                </div>

                <div>
                  <p className="text-[11px] uppercase tracking-[0.25em] font-black text-purple-700 flex items-center gap-1.5">
                    <span>✦</span>
                    Verify Your Internship Certificate
                  </p>

                  <h3 className="text-xl sm:text-2xl font-black text-[#0B0B0D] leading-tight mt-1">
                    Verify with{" "}
                    <span className="text-purple-700">MJ</span>
                  </h3>
                </div>
              </div>

              <p className="text-slate-600 text-sm sm:text-base mb-6">
                Verify your Marca Rise internship certificate instantly with
                MJ.
              </p>

              {/* Steps */}
              <div className="space-y-3 mb-7">
                {STEPS.map((s) => (
                  <div
                    key={s.num}
                    className="flex items-center gap-3 rounded-2xl border border-purple-100 bg-white/70 px-4 py-3"
                  >
                    <span
                      className="shrink-0 w-9 h-9 rounded-xl flex items-center justify-center text-white font-black text-sm"
                      style={{
                        background:
                          "linear-gradient(135deg,#6D28D9,#4C1D95)",
                      }}
                    >
                      {s.num}
                    </span>

                    <span className="text-sm font-semibold text-slate-700">
                      {s.num === "03" ? (
                        <>
                          Enter:{" "}
                          <span className="font-mono text-purple-700">
                            VERIFY MR00-XX-00000
                          </span>
                        </>
                      ) : (
                        s.text
                      )}
                    </span>
                  </div>
                ))}
              </div>

              {/* Verify Button */}
              <button
                onClick={verifyWithMj}
                data-testid="cert-popup-cta"
                className="w-full flex items-center justify-center gap-2 rounded-2xl py-3.5 text-white font-bold text-base shadow-lg transition-all hover:scale-[1.02]"
                style={{
                  background:
                    "linear-gradient(135deg,#6D28D9,#4C1D95)",
                  boxShadow:
                    "0 12px 30px rgba(124,12,231,0.4)",
                }}
              >
                <ShieldCheck size={18} />
                Verify with MJ
                <ArrowRight size={18} />
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}