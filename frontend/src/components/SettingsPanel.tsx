// ---------------------------------------------------------------------------
// System Link — Settings Panel
// License key activation, tier display, and subscription management.
// ---------------------------------------------------------------------------

import { useState, useEffect } from "react";
import { X, Check, Loader, ExternalLink, Zap, Crown } from "lucide-react";
import { useFluxStore } from "../store";
import { validateLicenseKey, getLicensePortal } from "../api/client";
import type { LicensePortalResponse } from "../api/client";

interface Props {
  onClose: () => void;
}

const S = {
  overlay: {
    position: "fixed" as const,
    inset: 0,
    background: "rgba(0,0,0,0.65)",
    zIndex: 1000,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  panel: {
    background: "#151722",
    border: "1px solid #2d3148",
    borderRadius: 12,
    width: 460,
    maxWidth: "calc(100vw - 32px)",
    boxShadow: "0 24px 64px rgba(0,0,0,0.6)",
    overflow: "hidden",
  },
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 20px",
    borderBottom: "1px solid #2d3148",
  },
  title: {
    fontWeight: 700,
    fontSize: 15,
    color: "#e2e8f0",
  },
  closeBtn: {
    background: "none",
    border: "none",
    color: "#64748b",
    cursor: "pointer",
    padding: 4,
    lineHeight: 1,
    display: "flex",
    alignItems: "center",
  },
  body: {
    padding: "20px",
    display: "flex",
    flexDirection: "column" as const,
    gap: 20,
  },
  tierCard: (pro: boolean) => ({
    background: pro
      ? "linear-gradient(135deg, rgba(99,102,241,0.12) 0%, rgba(139,92,246,0.08) 100%)"
      : "rgba(15,23,42,0.8)",
    border: pro ? "1px solid rgba(99,102,241,0.4)" : "1px solid #1e293b",
    borderRadius: 10,
    padding: "14px 16px",
    display: "flex",
    alignItems: "center",
    gap: 12,
  }),
  tierIcon: (pro: boolean) => ({
    width: 36,
    height: 36,
    borderRadius: 8,
    background: pro ? "rgba(99,102,241,0.2)" : "rgba(71,85,105,0.3)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0 as const,
  }),
  tierLabel: {
    fontWeight: 700,
    fontSize: 13,
    color: "#e2e8f0",
  },
  tierSub: {
    fontSize: 11,
    color: "#64748b",
    marginTop: 2,
  },
  tierBadge: (pro: boolean) => ({
    marginLeft: "auto",
    padding: "3px 10px",
    borderRadius: 20,
    fontSize: 11,
    fontWeight: 700,
    background: pro ? "rgba(99,102,241,0.2)" : "rgba(71,85,105,0.2)",
    color: pro ? "#818cf8" : "#64748b",
    border: pro ? "1px solid rgba(99,102,241,0.3)" : "1px solid #1e293b",
  }),
  label: {
    fontSize: 12,
    fontWeight: 600,
    color: "#94a3b8",
    marginBottom: 6,
  },
  inputRow: {
    display: "flex",
    gap: 8,
  },
  input: {
    flex: 1,
    background: "#0f172a",
    border: "1px solid #2d3148",
    borderRadius: 6,
    padding: "9px 12px",
    color: "#e2e8f0",
    fontSize: 13,
    fontFamily: "monospace",
    outline: "none",
  },
  btn: (variant: "primary" | "secondary" | "danger") => ({
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "9px 14px",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    background:
      variant === "primary"
        ? "rgba(99,102,241,0.8)"
        : variant === "danger"
        ? "rgba(239,68,68,0.15)"
        : "rgba(51,65,85,0.6)",
    color:
      variant === "primary"
        ? "#fff"
        : variant === "danger"
        ? "#fca5a5"
        : "#94a3b8",
    border:
      variant === "danger" ? "1px solid rgba(239,68,68,0.3)" : "none",
    whiteSpace: "nowrap" as const,
  }),
  statusMsg: (ok: boolean) => ({
    fontSize: 12,
    color: ok ? "#4ade80" : "#f87171",
    marginTop: 6,
  }),
  divider: {
    borderTop: "1px solid #1e293b",
    margin: "4px 0",
  },
  linkBtn: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "9px 14px",
    borderRadius: 6,
    border: "1px solid #2d3148",
    cursor: "pointer",
    fontSize: 12,
    fontWeight: 600,
    background: "transparent",
    color: "#94a3b8",
    textDecoration: "none",
  },
};

export function SettingsPanel({ onClose }: Props) {
  const store = useFluxStore();
  const isPro = store.license.tier === "pro";

  const [keyInput, setKeyInput] = useState(store.license.key ?? "");
  const [validating, setValidating] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ text: string; ok: boolean } | null>(null);
  const [portal, setPortal] = useState<LicensePortalResponse | null>(null);

  // Load portal URLs once
  useEffect(() => {
    getLicensePortal().then(setPortal).catch(() => null);
  }, []);

  const handleActivate = async () => {
    const key = keyInput.trim();
    if (!key) return;
    setValidating(true);
    setStatusMsg(null);
    try {
      const res = await validateLicenseKey(key);
      if (res.valid) {
        store.activateLicense(key);
        setStatusMsg({ text: res.message, ok: true });
      } else {
        setStatusMsg({ text: res.message, ok: false });
      }
    } catch {
      setStatusMsg({ text: "Could not reach license server. Please check your connection.", ok: false });
    } finally {
      setValidating(false);
    }
  };

  const handleDeactivate = () => {
    store.deactivateLicense();
    setKeyInput("");
    setStatusMsg({ text: "License deactivated. Now running in Free mode.", ok: true });
  };

  return (
    <div style={S.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={S.panel}>
        {/* Header */}
        <div style={S.header}>
          <span style={S.title}>Settings</span>
          <button style={S.closeBtn} onClick={onClose} aria-label="Close settings">
            <X size={18} />
          </button>
        </div>

        <div style={S.body}>
          {/* Tier card */}
          <div style={S.tierCard(isPro)}>
            <div style={S.tierIcon(isPro)}>
              {isPro ? <Crown size={18} color="#818cf8" /> : <Zap size={18} color="#64748b" />}
            </div>
            <div>
              <div style={S.tierLabel}>
                {isPro ? "System Link Pro" : "System Link Free"}
              </div>
              <div style={S.tierSub}>
                {isPro
                  ? "Cloud AI enabled — your subscription is active."
                  : "Self-hosted mode. Provide your own API key in .env."}
              </div>
            </div>
            <span style={S.tierBadge(isPro)}>{isPro ? "PRO" : "FREE"}</span>
          </div>

          {/* License key section */}
          {isPro ? (
            <div>
              <div style={S.label}>Pro License Key</div>
              <div style={S.inputRow}>
                <input
                  type="password"
                  value={keyInput}
                  readOnly
                  style={{ ...S.input, color: "#475569" }}
                  placeholder="••••••••••••••••"
                />
                <button style={S.btn("danger")} onClick={handleDeactivate}>
                  Deactivate
                </button>
              </div>
              {statusMsg && <div style={S.statusMsg(statusMsg.ok)}>{statusMsg.text}</div>}
            </div>
          ) : (
            <div>
              <div style={S.label}>Activate Pro License</div>
              <div style={S.inputRow}>
                <input
                  type="text"
                  value={keyInput}
                  onChange={(e) => setKeyInput(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleActivate()}
                  placeholder="Paste your license key here…"
                  style={S.input}
                  autoComplete="off"
                  spellCheck={false}
                />
                <button
                  style={S.btn("primary")}
                  onClick={handleActivate}
                  disabled={validating || !keyInput.trim()}
                >
                  {validating ? <Loader size={13} style={{ animation: "flux-spin 1s linear infinite" }} /> : <Check size={13} />}
                  {validating ? "Checking…" : "Activate"}
                </button>
              </div>
              {statusMsg && <div style={S.statusMsg(statusMsg.ok)}>{statusMsg.text}</div>}
            </div>
          )}

          <div style={S.divider} />

          {/* Subscription links */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={S.label}>Subscription</div>

            {!isPro && (
              <a
                href={portal?.purchase_url ?? "https://usayeed.gumroad.com"}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  ...S.linkBtn,
                  background: "rgba(99,102,241,0.08)",
                  border: "1px solid rgba(99,102,241,0.3)",
                  color: "#818cf8",
                }}
              >
                <Crown size={13} />
                Upgrade to Pro — $14.99 / month
                <ExternalLink size={11} style={{ marginLeft: "auto" }} />
              </a>
            )}

            <a
              href={portal?.manage_url ?? "https://app.gumroad.com/subscriptions"}
              target="_blank"
              rel="noopener noreferrer"
              style={S.linkBtn}
            >
              <ExternalLink size={13} />
              Manage / Cancel Subscription
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
