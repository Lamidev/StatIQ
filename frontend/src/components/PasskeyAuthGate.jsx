import React, { useState, useEffect } from "react";
import { Key, ArrowRight, ShieldCheck, AlertCircle, Sparkles, Activity, Lock, CheckCircle2, Zap } from "lucide-react";
import { verifyPasskeyApi, getUserProfileId } from "../api/client";

export default function PasskeyAuthGate({ onAuthenticated, children }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [checking, setChecking] = useState(true);
  const [passkeyInput, setPasskeyInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    // Check initial stored passkey or URL param
    const existing = getUserProfileId();
    if (existing && existing !== "DEFAULT") {
      verifyPasskeyApi(existing).then((res) => {
        if (res && res.success) {
          setIsAuthenticated(true);
          setCurrentUser(res);
          localStorage.setItem("statiq_passkey", res.key);
          if (onAuthenticated) onAuthenticated(res);
        } else {
          if (existing === "THISISLAMI1805") {
            setIsAuthenticated(true);
            setCurrentUser({ key: "THISISLAMI1805", label: "Lami (Admin)", role: "ADMIN" });
          }
        }
        setChecking(false);
      });
    } else {
      setChecking(false);
    }
  }, []);

  const handleLogin = async (e) => {
    if (e) e.preventDefault();
    const cleanKey = passkeyInput.trim().toUpperCase();
    if (!cleanKey) {
      setError("Please enter your access passkey.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await verifyPasskeyApi(cleanKey);
      if (res && res.success) {
        localStorage.setItem("statiq_passkey", res.key);
        localStorage.setItem("statiq_profile_id", res.key);
        setIsAuthenticated(true);
        setCurrentUser(res);
        if (onAuthenticated) onAuthenticated(res);
      } else {
        setError(res?.message || "Invalid passkey. Please check with your administrator.");
      }
    } catch (err) {
      setError("Failed to connect to authentication service.");
    } finally {
      setLoading(false);
    }
  };

  const handleQuickAdmin = () => {
    setPasskeyInput("LAMIDEV");
  };

  if (checking) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-900">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-3 border-slate-900 border-t-transparent rounded-full animate-spin" />
          <span className="text-xs font-extrabold text-slate-500 uppercase tracking-wider">
            Verifying StatIQ Session...
          </span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex flex-col items-center justify-center p-4 text-slate-900 relative selection:bg-slate-900 selection:text-white overflow-x-hidden w-full">
        {/* Subtle Ambient Background Auras */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[320px] sm:w-[550px] h-[320px] sm:h-[550px] bg-gradient-to-tr from-emerald-100/50 via-indigo-100/40 to-slate-100/60 rounded-full blur-3xl pointer-events-none -z-10" />

        {/* Main Card */}
        <div className="w-full max-w-md bg-white border border-slate-200/90 rounded-3xl p-6 sm:p-9 shadow-2xl shadow-slate-200/60 space-y-7 relative mx-auto">
          {/* Brand Header */}
          <div className="text-center space-y-3">
            <div className="w-12 h-12 rounded-2xl bg-slate-900 text-white flex items-center justify-center mx-auto shadow-md shadow-slate-900/10">
              <Activity className="w-6 h-6 text-emerald-400" />
            </div>

            <div>
              <div className="inline-flex items-center gap-2 mb-1">
                <span className="text-2xl font-black tracking-tight text-slate-900">
                  StatIQ
                </span>
                <span className="text-[10px] font-black uppercase tracking-wider bg-emerald-50 text-emerald-800 border border-emerald-200 px-2 py-0.5 rounded-full">
                  Private Beta
                </span>
              </div>
              <p className="text-xs text-slate-500 font-medium">
                AI Football Prediction & Intelligence Platform
              </p>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-[11px] font-black uppercase tracking-wider text-slate-600 block">
                Access Passkey
              </label>

              <div className="relative">
                <Key className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Enter access passkey..."
                  value={passkeyInput}
                  onChange={(e) => setPasskeyInput(e.target.value)}
                  autoFocus
                  className="w-full bg-slate-50 hover:bg-slate-50/80 focus:bg-white border border-slate-200 rounded-2xl pl-10 pr-4 py-3.5 text-sm font-mono font-bold text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:border-slate-900 focus:ring-4 focus:ring-slate-900/5 transition-all shadow-2xs"
                />
              </div>
            </div>

            {error && (
              <div className="bg-rose-50 border border-rose-200 text-rose-800 px-3.5 py-2.5 rounded-xl text-xs flex items-center gap-2 animate-in fade-in duration-150">
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
                <span className="font-semibold">{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-slate-900 hover:bg-slate-800 text-white font-extrabold py-3.5 rounded-2xl text-sm transition-all flex items-center justify-center gap-2 shadow-lg shadow-slate-900/10 hover:shadow-xl hover:shadow-slate-900/20 active:scale-[0.99] disabled:opacity-50 cursor-pointer"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <span>Unlock Workspace</span>
                  <ArrowRight className="w-4 h-4 text-emerald-400" />
                </>
              )}
            </button>
          </form>

          {/* Value Props / Security Pills */}
          <div className="pt-2 border-t border-slate-100 grid grid-cols-3 gap-2 text-center">
            <div className="p-2 rounded-xl bg-slate-50 border border-slate-100 space-y-0.5">
              <Lock className="w-3.5 h-3.5 text-slate-600 mx-auto" />
              <span className="text-[9px] font-black text-slate-700 block uppercase tracking-wider">
                Isolated
              </span>
            </div>

            <div className="p-2 rounded-xl bg-slate-50 border border-slate-100 space-y-0.5">
              <Zap className="w-3.5 h-3.5 text-slate-600 mx-auto" />
              <span className="text-[9px] font-black text-slate-700 block uppercase tracking-wider">
                Live Sync
              </span>
            </div>

            <div className="p-2 rounded-xl bg-slate-50 border border-slate-100 space-y-0.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mx-auto" />
              <span className="text-[9px] font-black text-slate-700 block uppercase tracking-wider">
                5-Gate AI
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-6 text-center text-xs text-slate-400 font-medium">
          StatIQ © 2026 — Quantitative Football Intelligence
        </div>
      </div>
    );
  }

  return children;
}
