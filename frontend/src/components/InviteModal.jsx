import React, { useState, useEffect } from "react";
import {
  Share2,
  Copy,
  Check,
  Smartphone,
  Users,
  Shield,
  Key,
  Sparkles,
  X,
  ExternalLink
} from "lucide-react";
import { getUserProfileId } from "../api/client";

export default function InviteModal({ isOpen, onClose }) {
  const [currentProfile, setCurrentProfile] = useState("DEFAULT");
  const [testerName, setTesterName] = useState("");
  const [copiedMobile, setCopiedMobile] = useState(false);
  const [copiedInvite, setCopiedInvite] = useState(false);
  const [customKeyInput, setCustomKeyInput] = useState("");

  useEffect(() => {
    if (isOpen) {
      const pid = getUserProfileId();
      setCurrentProfile(pid);
      setCustomKeyInput(pid);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const baseUrl = typeof window !== "undefined" ? window.location.origin : "https://statiq-app.vercel.app";
  const myMobileUrl = `${baseUrl}?code=${encodeURIComponent(currentProfile)}`;
  
  const generatedTesterKey = testerName.trim() ? `BETA-${testerName.trim().toUpperCase().replace(/\s+/g, "_")}` : "BETA-FRIEND";
  const testerInviteUrl = `${baseUrl}?code=${encodeURIComponent(generatedTesterKey)}`;

  const handleCopyMobile = () => {
    navigator.clipboard.writeText(myMobileUrl);
    setCopiedMobile(true);
    setTimeout(() => setCopiedMobile(false), 2500);
  };

  const handleCopyInvite = () => {
    navigator.clipboard.writeText(testerInviteUrl);
    setCopiedInvite(true);
    setTimeout(() => setCopiedInvite(false), 2500);
  };

  const handleSwitchKey = () => {
    if (customKeyInput.trim()) {
      const newKey = customKeyInput.trim().toUpperCase();
      localStorage.setItem("statiq_profile_id", newKey);
      setCurrentProfile(newKey);
      window.location.href = `${window.location.pathname}?code=${encodeURIComponent(newKey)}`;
    }
  };

  const generateRandomKey = () => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let rand = "";
    for (let i = 0; i < 6; i++) {
      rand += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    setTesterName(rand);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/70 backdrop-blur-xs animate-in fade-in duration-150">
      <div 
        className="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl border border-slate-200 space-y-6 relative overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-2xl bg-indigo-600 text-white flex items-center justify-center shadow-md shadow-indigo-100">
              <Share2 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-black text-slate-900">
                Multi-Device Sync & Invite Keys
              </h3>
              <p className="text-xs text-slate-500 font-semibold">
                Access from your phone or share isolated beta links with friends
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 flex items-center justify-center transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Section 1: Your Personal Phone Sync Link */}
        <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-black text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
              <Smartphone className="w-4 h-4 text-emerald-600" />
              1. Your Personal Phone Link
            </span>
            <span className="text-[11px] font-extrabold bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full">
              Key: {currentProfile}
            </span>
          </div>

          <p className="text-xs text-slate-600">
            Open this exact link on your mobile phone to view all your active slips and history:
          </p>

          <div className="flex items-center gap-2">
            <input
              type="text"
              readOnly
              value={myMobileUrl}
              className="flex-1 bg-white border border-slate-200 rounded-xl px-3 py-2 text-xs font-mono text-slate-800 select-all"
            />
            <button
              onClick={handleCopyMobile}
              className={`px-4 py-2 rounded-xl text-xs font-extrabold flex items-center gap-1.5 transition-all shadow-sm ${
                copiedMobile
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-900 hover:bg-slate-800 text-white"
              }`}
            >
              {copiedMobile ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copiedMobile ? "Copied!" : "Copy Link"}</span>
            </button>
          </div>
        </div>

        {/* Section 2: Generate Invite Link for Beta Testers */}
        <div className="bg-indigo-50/70 rounded-2xl p-4 border border-indigo-100 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-black text-indigo-950 uppercase tracking-wider flex items-center gap-1.5">
              <Users className="w-4 h-4 text-indigo-600" />
              2. Generate Beta Tester Link
            </span>
            <button
              onClick={generateRandomKey}
              className="text-[11px] font-extrabold text-indigo-700 hover:text-indigo-900 flex items-center gap-1 bg-indigo-100 hover:bg-indigo-200 px-2 py-0.5 rounded-lg transition-all"
            >
              <Sparkles className="w-3 h-3" />
              Random Key
            </button>
          </div>

          <p className="text-xs text-slate-600">
            Each tester gets their own separate workspace. They will <b>never</b> see your private slips.
          </p>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Tester Name / Identifier (e.g. Alex)"
                value={testerName}
                onChange={(e) => setTesterName(e.target.value)}
                className="flex-1 bg-white border border-indigo-200 rounded-xl px-3 py-2 text-xs font-bold text-slate-900 placeholder:text-slate-400 focus:outline-hidden focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={testerInviteUrl}
                className="flex-1 bg-white border border-indigo-200 rounded-xl px-3 py-2 text-xs font-mono text-slate-800 select-all"
              />
              <button
                onClick={handleCopyInvite}
                className={`px-4 py-2 rounded-xl text-xs font-extrabold flex items-center gap-1.5 transition-all shadow-sm ${
                  copiedInvite
                    ? "bg-emerald-600 text-white"
                    : "bg-indigo-600 hover:bg-indigo-700 text-white"
                }`}
              >
                {copiedInvite ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedInvite ? "Copied!" : "Copy Invite"}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Section 3: Switch Active Profile Key */}
        <div className="border-t border-slate-100 pt-4 flex items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2 flex-1">
            <Key className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <input
              type="text"
              placeholder="Switch Profile Key..."
              value={customKeyInput}
              onChange={(e) => setCustomKeyInput(e.target.value)}
              className="bg-slate-100 border border-slate-200 rounded-lg px-2.5 py-1 text-xs font-bold text-slate-800 w-36"
            />
            <button
              onClick={handleSwitchKey}
              className="bg-slate-200 hover:bg-slate-300 text-slate-800 font-bold px-2.5 py-1 rounded-lg text-xs transition-all"
            >
              Switch
            </button>
          </div>

          <div className="flex items-center gap-1 text-[11px] font-bold text-slate-400">
            <Shield className="w-3.5 h-3.5 text-emerald-600" />
            <span>Profile-Isolated Database</span>
          </div>
        </div>
      </div>
    </div>
  );
}
