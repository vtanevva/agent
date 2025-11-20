import { useEffect, useState, useRef } from "react";

export default function EmailReplyModal({ open, onClose, userId, threadId, to }) {
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState(null);
  const [original, setOriginal] = useState({ subject: "", from: "", date: "", body: "" });
  const textareaRef = useRef(null);
  const containerRef = useRef(null);

  useEffect(() => {
    async function fetchDraft() {
      if (!open || !userId || !threadId || !to) return;
      setLoading(true);
      setError(null);
      try {
        // Fetch original message detail
        const d = await fetch("/api/gmail/thread-detail", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, thread_id: threadId }),
        });
        const detail = await d.json();
        if (detail && detail.success) {
          setOriginal({
            subject: detail.subject || "",
            from: detail.from || "",
            date: detail.date || "",
            body: detail.body || "",
          });
        }

        const r = await fetch("/api/gmail/draft-reply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ user_id: userId, thread_id: threadId, to }),
        });
        const data = await r.json();
        if (data && data.success && data.body) {
          setDraft(data.body);
        } else if (data && data.action === "connect_google") {
          // Pass-through auth flow from server
          window.open(data.connect_url, "_blank", "noopener,noreferrer");
        } else {
          setError(data?.error || "Failed to generate draft.");
        }
      } catch (e) {
        setError(e?.message || "Network error.");
      } finally {
        setLoading(false);
      }
    }
    fetchDraft();
  }, [open, userId, threadId, to]);

  // Focus and ensure visibility when modal opens or when loading finishes
  useEffect(() => {
    if (!open) return;
    const focusAndScroll = () => {
      try {
        if (textareaRef.current) {
          textareaRef.current.focus();
          // Scroll textarea into view
          textareaRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
        // Allow window to adjust for mobile keyboard
        if (typeof window !== 'undefined') {
          setTimeout(() => {
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
          }, 50);
        }
      } catch {}
    };
    // Small timeout allows layout to settle
    const t = setTimeout(focusAndScroll, 50);
    return () => clearTimeout(t);
  }, [open, loading]);

  async function handleSend() {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/gmail/reply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, thread_id: threadId, to, body: draft }),
      });
      const data = await r.json();
      if (data && data.success) {
        onClose(true);
      } else if (data && data.action === "connect_google") {
        window.open(data.connect_url, "_blank", "noopener,noreferrer");
      } else {
        setError(data?.error || "Failed to send reply.");
      }
    } catch (e) {
      setError(e?.message || "Network error.");
    } finally {
      setLoading(false);
    }
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={() => onClose(false)} />
      <div
        ref={containerRef}
        className="relative w-[92%] max-w-3xl bg-white rounded-2xl shadow-2xl border border-dark-500/10 p-4"
        style={{ maxHeight: '90dvh', overflow: 'auto' }}
      >
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold text-primary-900">Reply to {to}</h3>
          <button onClick={() => onClose(false)} className="text-gray-600 hover:text-gray-800">✕</button>
        </div>
        <div className="text-xs text-primary-900/60 mb-2">Thread: {String(threadId).slice(-8)}</div>
        {/* Original message preview */}
        <div className="mb-3 p-3 rounded-xl bg-primary-100/40 border border-dark-500/10">
          <div className="text-sm text-primary-900 font-semibold mb-1">{original.subject || "(No subject)"}</div>
          <div className="text-xs text-primary-900/60 mb-2">{original.from} • {original.date}</div>
          <div className="max-h-32 overflow-y-auto custom-scrollbar text-sm text-primary-900 whitespace-pre-wrap">{original.body}</div>
        </div>
        <div className="h-64">
          {loading ? (
            <div className="w-full h-full flex items-center justify-center text-secondary-700">Preparing draft...</div>
          ) : (
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onFocus={(e) => {
                try {
                  e.target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                  if (typeof window !== 'undefined') {
                    setTimeout(() => {
                      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
                    }, 30);
                  }
                } catch {}
              }}
              className="w-full h-full p-3 rounded-lg bg-primary-100/50 text-primary-900 border-0 focus:ring-0 resize-none"
              placeholder="Draft will appear here..."
            />
          )}
        </div>
        {error && <div className="mt-2 text-xs text-red-600">{error}</div>}
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={() => onClose(false)}
            className="px-4 py-2 rounded-lg bg-dark-500/10 text-dark-700 hover:bg-dark-500/20"
          >
            Cancel
          </button>
          <button
            onClick={handleSend}
            disabled={loading || !draft.trim()}
            className="px-4 py-2 rounded-lg bg-gradient-to-r from-accent-500 to-accent-600 text-primary-50 disabled:opacity-50"
          >
            {loading ? "Sending..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}


