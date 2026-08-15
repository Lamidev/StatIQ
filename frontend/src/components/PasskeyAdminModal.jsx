import React, { useState, useEffect } from "react";
import {
  Key,
  Users,
  Plus,
  Copy,
  Check,
  Trash2,
  Power,
  Shield,
  X,
  ExternalLink,
  Sparkles,
  CheckCircle2,
  RefreshCw,
  LogOut
} from "lucide-react";
import {
  fetchAdminPasskeys,
  createPasskeyApi,
  togglePasskeyApi,
  deletePasskeyApi,
  getUserProfileId
} from "../api/client";

export default function PasskeyAdminModal({ isOpen, onClose }) {
  const [passkeys, setPasskeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [testerName, setTesterName] = useState("");
  const [testerRole, setTesterRole] = useState("BETA_TESTER");
  const [creating, setCreating] = useState(false);
  const [copiedKey, setCopiedKey] = useState(null);
  const [copiedLink, setCopiedLink] = useState(null);
  const [activeUserKey, setActiveUserKey] = useState("");

  const [keyToDelete, setKeyToDelete] = useState(null);
  const [deletingKey, setDeletingKey] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  const currentProfile = getUserProfileId();

  const loadKeys = async () => {
    setLoading(true);
    try {
      const data = await fetchAdminPasskeys();
      setPasskeys(data.passkeys || []);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      setActiveUserKey(getUserProfileId());
      loadKeys();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const baseUrl = typeof window !== "undefined" ? window.location.origin : "https://statiq-app.vercel.app";

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!testerName.trim()) return;

    setCreating(true);
    try {
      const res = await createPasskeyApi({
        label: testerName.trim(),
        role: testerRole
      });
      if (res && res.success) {
        setTesterName("");
        await loadKeys();
      }
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  const handleToggle = async (key, currentStatus) => {
    await togglePasskeyApi(key, !currentStatus);
    await loadKeys();
  };

  const confirmDeleteKey = async () => {
    if (!keyToDelete) return;
    setDeletingKey(true);
    try {
      await deletePasskeyApi(keyToDelete.key);
      await loadKeys();
    } catch (e) {
      console.error(e);
    } finally {
      setDeletingKey(false);
      setKeyToDelete(null);
    }
  };

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(id);
    setTimeout(() => setCopiedKey(null), 2500);
  };

  const handleCopyLink = (key, id) => {
    const fullUrl = `${baseUrl}?code=${encodeURIComponent(key)}`;
    navigator.clipboard.writeText(fullUrl);
    setCopiedLink(id);
    setTimeout(() => setCopiedLink(null), 2500);
  };

  const confirmLogout = () => {
    localStorage.removeItem("statiq_passkey");
    localStorage.removeItem("statiq_profile_id");
    const cleanUrl = window.location.origin + window.location.pathname;
    window.history.replaceState({}, document.title, cleanUrl);
    window.location.href = cleanUrl;
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/75 backdrop-blur-xs animate-in fade-in duration-150">
      <div 
        className="bg-white rounded-3xl max-w-2xl w-full p-6 sm:p-7 shadow-2xl border border-slate-200 space-y-6 relative max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-4">
          <div className="flex items-center space-x-3">
            <div className="w-11 h-11 rounded-2xl bg-slate-900 text-white flex items-center justify-center shadow-md">
              <Key className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-black text-slate-900">
                  Passkey & Access Manager
                </h3>
                <span className="bg-emerald-100 text-emerald-800 text-[10px] font-extrabold px-2 py-0.5 rounded-full">
                  Admin Control
                </span>
              </div>
              <p className="text-xs text-slate-500 font-medium">
                Create and manage unique passkeys for your beta testers and devices
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowLogoutConfirm(true)}
              className="text-xs font-extrabold text-slate-700 hover:bg-slate-100 border border-slate-200 px-3 py-1.5 rounded-xl transition-all flex items-center gap-1.5 cursor-pointer"
              title="Logout from this device"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Logout</span>
            </button>

            <button
              onClick={onClose}
              className="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 flex items-center justify-center transition-all cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Create New Passkey Section */}
        <div className="bg-slate-900 rounded-2xl p-5 text-white space-y-3 shadow-sm border border-slate-800">
          <div className="flex items-center justify-between">
            <span className="text-xs font-black uppercase tracking-wider text-white flex items-center gap-1.5">
              <Plus className="w-4 h-4 text-emerald-400" />
              Generate New Passkey for a Tester
            </span>
            <span className="text-[11px] text-slate-400 font-semibold hidden sm:inline">
              Instant Profile Isolation
            </span>
          </div>

          <form onSubmit={handleCreate} className="flex flex-col sm:flex-row items-center gap-2.5">
            <input
              type="text"
              placeholder="Tester Name / Label (e.g. Okey, Alex)"
              value={testerName}
              onChange={(e) => setTesterName(e.target.value)}
              className="flex-1 bg-slate-950/80 border border-slate-700 rounded-xl px-3.5 py-2.5 text-xs font-bold text-white placeholder:text-slate-500 focus:outline-hidden focus:border-emerald-500 w-full"
            />

            <select
              value={testerRole}
              onChange={(e) => setTesterRole(e.target.value)}
              className="bg-slate-950 border border-slate-700 rounded-xl px-3 py-2.5 text-xs font-bold text-white focus:outline-hidden w-full sm:w-auto"
            >
              <option value="BETA_TESTER">Beta Tester</option>
              <option value="ADMIN">Co-Admin</option>
            </select>

            <button
              type="submit"
              disabled={creating || !testerName.trim()}
              className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-black px-4 py-2.5 rounded-xl text-xs flex items-center gap-1.5 transition-all shadow-md disabled:opacity-50 w-full sm:w-auto justify-center cursor-pointer"
            >
              {creating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              <span>Create Key</span>
            </button>
          </form>
        </div>

        {/* Issued Passkeys Table */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-black text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
              <Users className="w-4 h-4 text-slate-500" />
              Issued Passkeys ({passkeys.length})
            </h4>
            <button
              onClick={loadKeys}
              className="text-[11px] font-bold text-slate-500 hover:text-slate-900 flex items-center gap-1 cursor-pointer"
            >
              <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>

          <div className="border border-slate-200 rounded-2xl overflow-hidden divide-y divide-slate-100">
            {passkeys.map((p, idx) => {
              const isCurrent = p.key === activeUserKey;
              const isMaster = p.key === "THISSLAMI1805";

              return (
                <div 
                  key={idx}
                  className={`p-3.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 transition-all ${
                    isCurrent ? "bg-emerald-50/50" : "bg-white hover:bg-slate-50"
                  }`}
                >
                  <div className="space-y-0.5 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs font-black text-slate-900 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200">
                        {p.key}
                      </span>

                      <span className="text-xs font-extrabold text-slate-800">
                        {p.label}
                      </span>

                      {p.role === "ADMIN" ? (
                        <span className="text-[10px] font-black bg-slate-900 text-white px-2 py-0.2 rounded-md uppercase">
                          Admin
                        </span>
                      ) : (
                        <span className="text-[10px] font-black bg-slate-100 text-slate-700 border border-slate-200 px-2 py-0.2 rounded-md uppercase">
                          Tester
                        </span>
                      )}

                      {isCurrent && (
                        <span className="text-[10px] font-black bg-emerald-100 text-emerald-800 px-2 py-0.2 rounded-md flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                          This Device
                        </span>
                      )}

                      {!p.is_active && (
                        <span className="text-[10px] font-black bg-rose-100 text-rose-800 px-2 py-0.2 rounded-md">
                          Revoked / Paused
                        </span>
                      )}
                    </div>

                    <div className="text-[11px] text-slate-400 flex items-center gap-3">
                      <span>Created: {p.created_at}</span>
                      <span>|</span>
                      <span>Last Used: {p.last_used_at}</span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1.5 self-end sm:self-auto">
                    {/* Copy Passkey Code */}
                    <button
                      onClick={() => handleCopy(p.key, `key-${idx}`)}
                      className="px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-extrabold flex items-center gap-1 transition-all cursor-pointer"
                      title="Copy Passkey code"
                    >
                      {copiedKey === `key-${idx}` ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                      <span>{copiedKey === `key-${idx}` ? "Copied" : "Code"}</span>
                    </button>

                    {/* Copy Direct Auto-Login Link */}
                    <button
                      onClick={() => handleCopyLink(p.key, `link-${idx}`)}
                      className="px-2.5 py-1.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-xs font-extrabold flex items-center gap-1 transition-all shadow-2xs cursor-pointer"
                      title="Copy direct one-click link"
                    >
                      {copiedLink === `link-${idx}` ? <Check className="w-3 h-3 text-emerald-400" /> : <ExternalLink className="w-3 h-3 text-slate-300" />}
                      <span>{copiedLink === `link-${idx}` ? "Link Copied" : "Link"}</span>
                    </button>

                    {/* Toggle Active / Paused */}
                    {!isMaster && (
                      <button
                        onClick={() => handleToggle(p.key, p.is_active)}
                        className={`p-1.5 rounded-lg border text-xs transition-all cursor-pointer ${
                          p.is_active
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100"
                            : "bg-slate-100 text-slate-400 border-slate-200 hover:bg-slate-200"
                        }`}
                        title={p.is_active ? "Pause access" : "Activate access"}
                      >
                        <Power className="w-3.5 h-3.5" />
                      </button>
                    )}

                    {/* Delete Passkey */}
                    {!isMaster && (
                      <button
                        onClick={() => setKeyToDelete(p)}
                        className="p-1.5 rounded-lg bg-rose-50 hover:bg-rose-100 text-rose-600 transition-all cursor-pointer"
                        title="Delete passkey"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {keyToDelete && (
        <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xs animate-in fade-in duration-150">
          <div 
            className="bg-white rounded-3xl max-w-sm w-full p-6 shadow-2xl border border-slate-200 space-y-5 text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-12 h-12 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center mx-auto shadow-xs">
              <Trash2 className="w-6 h-6" />
            </div>

            <div className="space-y-1.5">
              <h3 className="text-base font-black text-slate-900">
                Delete Access Passkey?
              </h3>
              <p className="text-xs text-slate-500 font-medium leading-relaxed">
                Permanently delete passkey <span className="font-mono font-black text-slate-900 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">{keyToDelete.key}</span> for <span className="font-extrabold text-slate-800">{keyToDelete.label}</span>?
              </p>
            </div>

            <div className="flex items-center gap-2.5 pt-2">
              <button
                onClick={() => setKeyToDelete(null)}
                disabled={deletingKey}
                className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold py-2.5 rounded-xl text-xs transition-all cursor-pointer"
              >
                Cancel
              </button>

              <button
                onClick={confirmDeleteKey}
                disabled={deletingKey}
                className="flex-1 bg-rose-600 hover:bg-rose-700 text-white font-black py-2.5 rounded-xl text-xs transition-all shadow-md cursor-pointer flex items-center justify-center gap-1.5"
              >
                {deletingKey ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                <span>{deletingKey ? "Deleting..." : "Delete Key"}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Logout Confirmation Modal */}
      {showLogoutConfirm && (
        <div className="fixed inset-0 z-60 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-xs animate-in fade-in duration-150">
          <div 
            className="bg-white rounded-3xl max-w-sm w-full p-6 shadow-2xl border border-slate-200 space-y-5 text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-800 flex items-center justify-center mx-auto shadow-xs">
              <LogOut className="w-6 h-6" />
            </div>

            <div className="space-y-1">
              <h3 className="text-base font-black text-slate-900">
                Log Out of StatIQ?
              </h3>
              <p className="text-xs text-slate-500 font-medium leading-relaxed">
                You will be returned to the Passkey access gate. You can log back in anytime with your passkey.
              </p>
            </div>

            <div className="flex items-center gap-2.5 pt-2">
              <button
                onClick={() => setShowLogoutConfirm(false)}
                className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold py-2.5 rounded-xl text-xs transition-all cursor-pointer"
              >
                Cancel
              </button>

              <button
                onClick={confirmLogout}
                className="flex-1 bg-slate-900 hover:bg-slate-800 text-white font-black py-2.5 rounded-xl text-xs transition-all shadow-md cursor-pointer"
              >
                Log Out
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
