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
  ExternalLink,
  Sparkles,
  CheckCircle2,
  RefreshCw,
  LogOut,
  Search,
  Lock,
} from "lucide-react";
import {
  fetchAdminPasskeys,
  createPasskeyApi,
  togglePasskeyApi,
  deletePasskeyApi,
  getUserProfileId
} from "../api/client";

export default function AccessControlTab({ currentUser }) {
  const [passkeys, setPasskeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [testerName, setTesterName] = useState("");
  const [customKey, setCustomKey] = useState("");
  const [testerRole, setTesterRole] = useState("BETA_TESTER");
  const [notes, setNotes] = useState("");
  const [creating, setCreating] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL"); // ALL, ACTIVE, PAUSED
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  const [copiedKey, setCopiedKey] = useState(null);
  const [copiedLink, setCopiedLink] = useState(null);

  const activeUserKey = currentUser?.key || getUserProfileId();
  const baseUrl = typeof window !== "undefined" ? window.location.origin : "https://statiq-app.vercel.app";

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
    loadKeys();
  }, []);

  const [toast, setToast] = useState(null);

  const showToast = (title, message, key = null) => {
    setToast({ title, message, key });
    setTimeout(() => setToast(null), 4500);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!testerName.trim()) return;

    setCreating(true);
    try {
      const res = await createPasskeyApi({
        label: testerName.trim(),
        custom_key: customKey.trim() || undefined,
        role: testerRole,
        notes: notes.trim() || undefined,
      });
      if (res && res.success) {
        setTesterName("");
        setCustomKey("");
        setNotes("");
        await loadKeys();
        showToast("Passkey Created Successfully", `Key "${res.key}" generated for ${res.label}`, res.key);
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
    showToast(currentStatus ? "Passkey Paused" : "Passkey Activated", `Updated status for ${key}`);
  };

  const [passkeyToDelete, setPasskeyToDelete] = useState(null);
  const [deletingKey, setDeletingKey] = useState(false);

  const confirmDeletePasskey = async () => {
    if (!passkeyToDelete) return;
    setDeletingKey(true);
    try {
      await deletePasskeyApi(passkeyToDelete.key);
      await loadKeys();
      showToast("Passkey Deleted", `Removed passkey "${passkeyToDelete.key}"`);
    } catch (e) {
      console.error(e);
    } finally {
      setDeletingKey(false);
      setPasskeyToDelete(null);
    }
  };

  const handleDelete = (passkeyObj) => {
    setPasskeyToDelete(passkeyObj);
  };

  const handleCopy = (text, id) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(id);
    showToast("Passkey Code Copied", `Copied "${text}" to clipboard`);
    setTimeout(() => setCopiedKey(null), 2500);
  };

  const handleCopyLink = (key, id) => {
    const fullUrl = `${baseUrl}?code=${encodeURIComponent(key)}`;
    navigator.clipboard.writeText(fullUrl);
    setCopiedLink(id);
    showToast("1-Click Link Copied", `Direct login link for "${key}" copied to clipboard`);
    setTimeout(() => setCopiedLink(null), 2500);
  };

  const handleLogout = () => {
    setShowLogoutConfirm(true);
  };

  const confirmLogout = () => {
    localStorage.removeItem("statiq_passkey");
    localStorage.removeItem("statiq_profile_id");
    const cleanUrl = window.location.origin + window.location.pathname;
    window.history.replaceState({}, document.title, cleanUrl);
    window.location.href = cleanUrl;
  };

  // Filter passkeys
  const filteredPasskeys = passkeys.filter((p) => {
    if (statusFilter === "ACTIVE" && !p.is_active) return false;
    if (statusFilter === "PAUSED" && p.is_active) return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchKey = (p.key || "").toLowerCase().includes(q);
      const matchLabel = (p.label || "").toLowerCase().includes(q);
      if (!matchKey && !matchLabel) return false;
    }
    return true;
  });

  const totalKeys = passkeys.length;
  const activeKeys = passkeys.filter((p) => p.is_active).length;
  const pausedKeys = passkeys.filter((p) => !p.is_active).length;

  return (
    <div className="space-y-4 sm:space-y-6 max-w-6xl mx-auto px-1 sm:px-0">
      {/* Top Banner / Hero */}
      <div className="bg-slate-900 text-white rounded-2xl sm:rounded-3xl p-4 sm:p-8 shadow-xl border border-slate-800 space-y-4 relative overflow-hidden">
        <div className="absolute -top-24 -right-24 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 sm:gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2 sm:gap-2.5">
              <div className="w-9 h-9 sm:w-10 sm:h-10 rounded-xl sm:rounded-2xl bg-emerald-500 text-slate-950 flex items-center justify-center font-black shadow-md shrink-0">
                <Key className="w-4 h-4 sm:w-5 sm:h-5" />
              </div>
              <h1 className="text-lg sm:text-2xl font-black tracking-tight text-white">
                Access Control & Passkeys
              </h1>
            </div>
            <p className="text-xs sm:text-sm text-slate-400 font-medium">
              Manage beta tester passkeys, grant instant isolated access, and control mobile sync.
            </p>
          </div>

          {/* Current User Pill & Logout */}
          <div className="flex items-center gap-2 bg-slate-800/90 border border-slate-700 p-1.5 pl-3 rounded-xl sm:rounded-2xl w-full sm:w-auto justify-between sm:justify-start">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-emerald-400 shrink-0" />
              <div className="text-left">
                <span className="text-[9px] text-slate-400 font-bold block uppercase tracking-wider">Device Key</span>
                <span className="text-xs font-mono font-black text-white">{activeUserKey}</span>
              </div>
            </div>

            <button
              onClick={handleLogout}
              className="bg-slate-700 hover:bg-slate-600 text-white text-xs font-black px-3 py-1.5 rounded-lg sm:rounded-xl transition-all flex items-center gap-1.5 cursor-pointer shadow-xs"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Logout</span>
            </button>
          </div>
        </div>

        {/* Metrics Summary Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-3 pt-1 sm:pt-2">
          <div className="bg-slate-950/60 p-3 sm:p-4 rounded-xl sm:rounded-2xl border border-slate-800 space-y-0.5">
            <span className="text-[9px] sm:text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
              Total Keys
            </span>
            <span className="text-lg sm:text-xl font-black text-white">{totalKeys}</span>
          </div>

          <div className="bg-slate-950/60 p-3 sm:p-4 rounded-xl sm:rounded-2xl border border-slate-800 space-y-0.5">
            <span className="text-[9px] sm:text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
              Active Users
            </span>
            <span className="text-lg sm:text-xl font-black text-emerald-400">{activeKeys}</span>
          </div>

          <div className="bg-slate-950/60 p-3 sm:p-4 rounded-xl sm:rounded-2xl border border-slate-800 space-y-0.5">
            <span className="text-[9px] sm:text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
              Paused Keys
            </span>
            <span className="text-lg sm:text-xl font-black text-amber-400">{pausedKeys}</span>
          </div>

          <div className="bg-slate-950/60 p-3 sm:p-4 rounded-xl sm:rounded-2xl border border-slate-800 space-y-0.5">
            <span className="text-[9px] sm:text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
              Isolation Engine
            </span>
            <span className="text-[11px] sm:text-xs font-extrabold text-emerald-300 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              100% Partitioned
            </span>
          </div>
        </div>
      </div>

      {/* Generate New Passkey Form Card */}
      <div className="bg-white rounded-2xl sm:rounded-3xl p-4 sm:p-7 shadow-sm border border-slate-200 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Plus className="w-4 h-4 sm:w-5 sm:h-5 text-slate-900" />
            <h3 className="text-xs sm:text-sm font-black text-slate-900 uppercase tracking-wider">
              Issue New Passkey for a Tester
            </h3>
          </div>
          <span className="text-xs font-semibold text-slate-500 hidden sm:inline">
            Each key grants an isolated slip workspace
          </span>
        </div>

        <form onSubmit={handleCreate} className="space-y-3 sm:space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] sm:text-[11px] font-extrabold text-slate-500 uppercase tracking-wider block">
                Tester Name / Label <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Okey, Alex"
                value={testerName}
                onChange={(e) => setTesterName(e.target.value)}
                required
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-xs font-bold text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-slate-900"
              />
            </div>

            <div className="space-y-1">
              <label className="text-[10px] sm:text-[11px] font-extrabold text-slate-500 uppercase tracking-wider block">
                Role & Permissions
              </label>
              <select
                value={testerRole}
                onChange={(e) => setTesterRole(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-xs font-bold text-slate-900 focus:outline-hidden"
              >
                <option value="BETA_TESTER">Beta Tester (Own Slips Only)</option>
                <option value="ADMIN">Co-Admin (Full Access + Manager)</option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-[10px] sm:text-[11px] font-extrabold text-slate-500 uppercase tracking-wider block">
                Custom Passkey (Optional)
              </label>
              <input
                type="text"
                placeholder="Auto-generated if empty"
                value={customKey}
                onChange={(e) => setCustomKey(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-xs font-mono font-bold text-slate-900 uppercase focus:outline-hidden"
              />
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 pt-1">
            <p className="text-[11px] sm:text-xs text-slate-500">
              Keys can be entered directly or opened with a 1-click auto-login link.
            </p>

            <button
              type="submit"
              disabled={creating || !testerName.trim()}
              className="bg-slate-900 hover:bg-slate-800 text-white font-extrabold px-6 py-2.5 rounded-xl text-xs flex items-center gap-2 transition-all shadow-md disabled:opacity-50 cursor-pointer justify-center"
            >
              {creating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5 text-emerald-400" />}
              <span>Generate Access Key</span>
            </button>
          </div>
        </form>
      </div>

      {/* Issued Passkeys Management Table */}
      <div className="bg-white rounded-2xl sm:rounded-3xl p-4 sm:p-6 shadow-sm border border-slate-200 space-y-4">
        {/* Controls Bar: Filters & Search */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 border-b border-slate-100 pb-3 sm:pb-4">
          {/* Status Tabs */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl gap-1 overflow-x-auto no-scrollbar">
            {[
              { id: "ALL", label: `All (${totalKeys})` },
              { id: "ACTIVE", label: `Active (${activeKeys})` },
              { id: "PAUSED", label: `Paused (${pausedKeys})` },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setStatusFilter(tab.id)}
                className={`px-2.5 sm:px-3 py-1.5 rounded-lg text-xs font-extrabold transition-all whitespace-nowrap cursor-pointer ${
                  statusFilter === tab.id
                    ? "bg-white text-slate-900 shadow-xs"
                    : "text-slate-500 hover:text-slate-900"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="flex items-center gap-2">
            <div className="relative flex-1 sm:w-64">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                placeholder="Search tester or key..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3 py-1.5 text-xs font-bold text-slate-900 placeholder:text-slate-400 focus:outline-hidden"
              />
            </div>

            <button
              onClick={loadKeys}
              className="p-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-600 transition-all cursor-pointer shrink-0"
              title="Refresh passkeys list"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
          </div>
        </div>

        {/* Passkeys List / Grid */}
        {filteredPasskeys.length === 0 ? (
          <div className="p-8 text-center space-y-2 text-slate-400">
            <Users className="w-8 h-8 mx-auto stroke-1" />
            <p className="text-xs font-bold">No passkeys found matching your filter.</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {filteredPasskeys.map((p, idx) => {
              const isCurrent = p.key === activeUserKey;
              const isMaster = p.key === "THISISLAMI1805";

              return (
                <div
                  key={idx}
                  className={`py-3.5 sm:py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4 transition-all ${
                    isCurrent ? "bg-emerald-50/40 -mx-4 sm:-mx-6 px-4 sm:px-6 rounded-xl sm:rounded-2xl" : ""
                  }`}
                >
                  <div className="space-y-1 flex-1 w-full">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono text-xs font-black text-slate-900 bg-slate-100 px-2.5 py-0.5 rounded-md border border-slate-200 shadow-2xs">
                        {p.key}
                      </span>

                      <span className="text-xs sm:text-sm font-extrabold text-slate-900">
                        {p.label}
                      </span>

                      {p.role === "ADMIN" ? (
                        <span className="text-[9px] font-black bg-slate-900 text-white px-2 py-0.5 rounded-full uppercase tracking-wider">
                          Admin
                        </span>
                      ) : (
                        <span className="text-[9px] font-black bg-slate-100 text-slate-700 border border-slate-200 px-2 py-0.5 rounded-full uppercase tracking-wider">
                          Beta Tester
                        </span>
                      )}

                      {isCurrent && (
                        <span className="text-[9px] font-black bg-emerald-100 text-emerald-800 border border-emerald-300 px-2 py-0.5 rounded-full flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                          This Device
                        </span>
                      )}

                      {!p.is_active && (
                        <span className="text-[9px] font-black bg-rose-100 text-rose-800 border border-rose-300 px-2 py-0.5 rounded-full">
                          Revoked / Paused
                        </span>
                      )}
                    </div>

                    <div className="text-[10px] sm:text-[11px] text-slate-400 flex items-center gap-2 sm:gap-3 font-semibold flex-wrap">
                      <span>Created: {p.created_at}</span>
                      <span>|</span>
                      <span>Last Used: {p.last_used_at}</span>
                      {p.notes && (
                        <>
                          <span>|</span>
                          <span className="text-slate-500 italic">{p.notes}</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Actions Bar */}
                  <div className="flex items-center gap-1.5 sm:gap-2 w-full sm:w-auto justify-end pt-1 sm:pt-0">
                    {/* Copy Passkey Button */}
                    <button
                      onClick={() => handleCopy(p.key, `code-${idx}`)}
                      className="flex-1 sm:flex-initial px-2.5 sm:px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-extrabold flex items-center justify-center gap-1 transition-all cursor-pointer"
                      title="Copy passkey string"
                    >
                      {copiedKey === `code-${idx}` ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copiedKey === `code-${idx}` ? "Copied" : "Copy Code"}</span>
                    </button>

                    {/* Copy Direct Auto-Login Link */}
                    <button
                      onClick={() => handleCopyLink(p.key, `link-${idx}`)}
                      className="flex-1 sm:flex-initial px-2.5 sm:px-3 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-extrabold flex items-center justify-center gap-1 transition-all shadow-xs cursor-pointer"
                      title="Copy one-click auto-login URL"
                    >
                      {copiedLink === `link-${idx}` ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <ExternalLink className="w-3.5 h-3.5 text-slate-300" />}
                      <span>{copiedLink === `link-${idx}` ? "Link Copied" : "1-Click Link"}</span>
                    </button>

                    {/* Toggle Active / Paused */}
                    {!isMaster && (
                      <button
                        onClick={() => handleToggle(p.key, p.is_active)}
                        className={`p-1.5 sm:p-2 rounded-xl border transition-all cursor-pointer shrink-0 ${
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
                        onClick={() => handleDelete(p)}
                        className="p-1.5 sm:p-2 rounded-xl bg-rose-50 hover:bg-rose-100 text-rose-600 transition-all cursor-pointer shrink-0"
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
        )}
      </div>

      {/* Custom Delete Passkey Confirmation Modal */}
      {passkeyToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/80 backdrop-blur-xs animate-in fade-in duration-150">
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
                Are you sure you want to permanently delete passkey <span className="font-mono font-black text-slate-900 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">{passkeyToDelete.key}</span> for <span className="font-extrabold text-slate-800">{passkeyToDelete.label}</span>? They will lose access immediately.
              </p>
            </div>

            <div className="flex items-center gap-2.5 pt-2">
              <button
                onClick={() => setPasskeyToDelete(null)}
                disabled={deletingKey}
                className="flex-1 bg-slate-100 hover:bg-slate-200 text-slate-800 font-bold py-2.5 rounded-xl text-xs transition-all cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>

              <button
                onClick={confirmDeletePasskey}
                disabled={deletingKey}
                className="flex-1 bg-rose-600 hover:bg-rose-700 text-white font-black py-2.5 rounded-xl text-xs transition-all shadow-md cursor-pointer flex items-center justify-center gap-1.5 disabled:opacity-50"
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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/80 backdrop-blur-xs animate-in fade-in duration-150">
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

      {/* Sonner-style Floating Toast Notification */}
      {toast && (
        <div className="fixed bottom-5 right-5 z-50 animate-in slide-in-from-bottom-5 fade-in duration-200">
          <div className="bg-slate-900 text-white rounded-2xl p-4 shadow-2xl border border-slate-800 flex items-start gap-3 max-w-sm w-full">
            <div className="p-1 rounded-lg bg-emerald-500/20 text-emerald-400 mt-0.5 shrink-0">
              <CheckCircle2 className="w-4 h-4" />
            </div>
            <div className="flex-1 space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-black text-white">{toast.title}</span>
                <button
                  onClick={() => setToast(null)}
                  className="text-slate-400 hover:text-white text-xs cursor-pointer ml-2"
                >
                  ✕
                </button>
              </div>
              <p className="text-[11px] text-slate-300 font-medium leading-relaxed">
                {toast.message}
              </p>
              {toast.key && (
                <div className="pt-1.5 flex items-center gap-2">
                  <button
                    onClick={() => {
                      const fullUrl = `${baseUrl}?code=${encodeURIComponent(toast.key)}`;
                      navigator.clipboard.writeText(fullUrl);
                      showToast("1-Click Link Copied", "Direct auto-login link copied to clipboard");
                    }}
                    className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 text-[10px] font-black px-2.5 py-1 rounded-lg transition-all flex items-center gap-1 cursor-pointer"
                  >
                    <ExternalLink className="w-3 h-3" />
                    <span>Copy 1-Click Link</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
