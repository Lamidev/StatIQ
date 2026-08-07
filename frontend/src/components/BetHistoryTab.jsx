import React, { useState, useEffect } from "react";
import {
  Receipt,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronRight,
  ArrowLeft,
  Trash2,
  Filter,
  Calendar,
  Layers,
  ChevronLeft,
  RefreshCw,
  Search,
  ExternalLink,
  ShieldCheck,
  MinusCircle,
} from "lucide-react";
import { fetchTrackedTickets, deleteTrackedTicket } from "../api/client";

export default function BetHistoryTab() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState("ALL"); // ALL, SETTLED, UNSETTLED
  const [dateFilter, setDateFilter] = useState("ALL"); // ALL, TODAY, YESTERDAY
  const [searchQuery, setSearchQuery] = useState("");

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;

  // Selected Ticket for Detail View / Modal
  const [selectedTicket, setSelectedTicket] = useState(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchTrackedTickets();
      const ticketList = Array.isArray(data)
        ? data
        : data.tickets || [];
      setTickets(ticketList);
    } catch (err) {
      console.error("Failed to load bet history:", err);
      setError("Failed to connect to StatIQ backend.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // Auto-poll live scores every 15s for active tickets
    const timer = setInterval(() => {
      loadData();
    }, 15000);
    return () => clearInterval(timer);
  }, []);

  const handleDelete = async (ticketId, e) => {
    if (e) e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this tracked ticket?")) return;

    try {
      await deleteTrackedTicket(ticketId);
      if (selectedTicket?.id === ticketId) {
        setSelectedTicket(null);
      }
      loadData();
    } catch (err) {
      alert("Failed to delete ticket: " + err.message);
    }
  };

  // Filter Logic
  const filteredTickets = tickets.filter((t) => {
    const isWon = t.status === "WON";
    const isLost = t.status === "LOST";
    const isSettled = isWon || isLost;
    const isUnsettled = t.status === "RUNNING" || t.status === "PENDING";

    if (statusFilter === "WON" && !isWon) return false;
    if (statusFilter === "LOST" && !isLost) return false;
    if (statusFilter === "SETTLED" && !isSettled) return false;
    if (statusFilter === "UNSETTLED" && !isUnsettled) return false;

    // Date Filter
    if (dateFilter !== "ALL" && t.created_at) {
      const ticketDateStr = t.created_at.split(" ")[0]; // YYYY-MM-DD
      const now = new Date();
      const todayStr = now.toISOString().split("T")[0];

      const yesterday = new Date(now);
      yesterday.setDate(yesterday.getDate() - 1);
      const yesterdayStr = yesterday.toISOString().split("T")[0];

      if (dateFilter === "TODAY" && ticketDateStr !== todayStr) return false;
      if (dateFilter === "YESTERDAY" && ticketDateStr !== yesterdayStr) return false;
    }

    // Search Query (Code, ID, Teams)
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const codeMatch = (t.code || "").toLowerCase().includes(q);
      const idMatch = (t.id || "").toLowerCase().includes(q);
      const teamMatch = (t.selections || []).some(
        (s) =>
          (s.home_team || "").toLowerCase().includes(q) ||
          (s.away_team || "").toLowerCase().includes(q)
      );
      if (!codeMatch && !idMatch && !teamMatch) return false;
    }

    return true;
  });

  // Pagination Logic
  const totalPages = Math.max(1, Math.ceil(filteredTickets.length / itemsPerPage));
  const pageIndex = Math.min(currentPage, totalPages) - 1;
  const paginatedTickets = filteredTickets.slice(
    pageIndex * itemsPerPage,
    (pageIndex + 1) * itemsPerPage
  );

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Top Banner / Header */}
      <div className="bg-slate-900 text-white p-6 rounded-2xl shadow-md flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Receipt className="w-5 h-5 text-emerald-400" />
            <h1 className="text-xl font-extrabold tracking-tight">
              Tickets & Bet History
            </h1>
          </div>
          <p className="text-xs text-slate-400">
            Track live ticket outcomes, win/loss history, and leg-by-leg SportyBet settlement accuracy.
          </p>
        </div>

        <button
          onClick={loadData}
          disabled={loading}
          className="flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-white px-4 py-2 rounded-xl text-xs font-bold transition-all border border-slate-700 shadow-sm"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          <span>Sync History</span>
        </button>
      </div>

      {/* Summary Metrics Cards Bar */}
      {!selectedTicket && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-1">
            <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
              Total Tracked Tickets
            </span>
            <span className="text-xl font-black text-slate-900">{tickets.length}</span>
          </div>

          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-1">
            <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
              Acca Tickets Won
            </span>
            <div className="flex items-center gap-1.5">
              <span className="text-xl font-black text-emerald-600">
                {tickets.filter((t) => t.status === "WON").length} Won
              </span>
              <span className="text-xs text-slate-400 font-extrabold">
                / {tickets.filter((t) => t.status === "LOST").length} Lost
              </span>
            </div>
          </div>

          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-1">
            <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
              Individual Games Won
            </span>
            <div className="flex items-center gap-1.5">
              <span className="text-xl font-black text-emerald-600">
                {tickets.reduce((acc, t) => acc + (t.selections || []).filter((s) => s.leg_status === "WON").length, 0)}
              </span>
              <span className="text-xs text-slate-400 font-extrabold">
                / {tickets.reduce((acc, t) => acc + (t.selections || []).length, 0)} Matches
              </span>
            </div>
          </div>

          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm space-y-1">
            <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
              Individual Game Win Rate
            </span>
            <div className="flex items-center gap-1">
              <span className="text-xl font-black text-slate-900">
                {(() => {
                  const total = tickets.reduce((acc, t) => acc + (t.selections || []).length, 0);
                  const won = tickets.reduce((acc, t) => acc + (t.selections || []).filter((s) => s.leg_status === "WON").length, 0);
                  return total > 0 ? Math.round((won / total) * 100) : 0;
                })()}%
              </span>
              <span className="text-xs font-bold text-emerald-600">Accuracy</span>
            </div>
          </div>
        </div>
      )}

      {/* Main View: List or Detailed Ticket */}
      {selectedTicket ? (
        /* Detailed Ticket View (SportyBet Style) */
        <TicketDetailView
          ticket={selectedTicket}
          onBack={() => setSelectedTicket(null)}
          onDelete={(id) => handleDelete(id)}
        />
      ) : (
        /* Ticket Cards Summary View */
        <div className="space-y-6">
          {/* Controls & Filter Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
            {/* Status Filter Tabs (All / Won / Lost / Settled / Unsettled) */}
            <div className="flex items-center bg-slate-100 p-1 rounded-xl overflow-x-auto gap-1">
              {[
                { id: "ALL", label: "All" },
                { id: "WON", label: "🏆 Won" },
                { id: "LOST", label: "❌ Lost" },
                { id: "SETTLED", label: "Settled" },
                { id: "UNSETTLED", label: "⏳ Unsettled" },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => {
                    setStatusFilter(tab.id);
                    setCurrentPage(1);
                  }}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-extrabold transition-all whitespace-nowrap ${
                    statusFilter === tab.id
                      ? "bg-white text-slate-900 shadow-sm"
                      : "text-slate-500 hover:text-slate-900"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="flex items-center gap-3">
              {/* Search Box */}
              <div className="relative flex-1 md:w-56">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Search code or team..."
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-9 pr-3 py-1.5 text-xs font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900"
                />
              </div>

              {/* Date Filter Dropdown */}
              <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5">
                <Calendar className="w-3.5 h-3.5 text-slate-400" />
                <select
                  value={dateFilter}
                  onChange={(e) => {
                    setDateFilter(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="bg-transparent text-xs font-extrabold text-slate-900 focus:outline-none cursor-pointer"
                >
                  <option value="ALL">All Dates</option>
                  <option value="TODAY">Today</option>
                  <option value="YESTERDAY">Yesterday</option>
                </select>
              </div>
            </div>
          </div>

          {/* Loading State */}
          {loading ? (
            <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
              <RefreshCw className="w-6 h-6 text-slate-400 animate-spin mx-auto" />
              <p className="text-xs font-bold text-slate-500">Loading bet history...</p>
            </div>
          ) : error ? (
            <div className="bg-rose-50 border border-rose-200 text-rose-800 p-6 rounded-2xl text-center space-y-2">
              <p className="text-xs font-bold">{error}</p>
              <button
                onClick={loadData}
                className="text-xs font-extrabold underline text-rose-900"
              >
                Try Again
              </button>
            </div>
          ) : filteredTickets.length === 0 ? (
            <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
              <Receipt className="w-10 h-10 text-slate-300 mx-auto" />
              <h3 className="text-sm font-extrabold text-slate-900">No Tickets Found</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No staked or audited tickets match your selected filters. Re-edit a ticket in the Ticket Auditor and click "📌 Lock & Track Staked Ticket" to start tracking!
              </p>
            </div>
          ) : (
            /* Ticket Cards List */
            <div className="space-y-4">
              {paginatedTickets.map((t) => (
                <TicketCard
                  key={t.id || t.code}
                  ticket={t}
                  onClick={() => setSelectedTicket(t)}
                  onDelete={(id, e) => handleDelete(id, e)}
                />
              ))}

              {/* Pagination */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between bg-white p-4 rounded-2xl border border-slate-200 shadow-sm text-xs font-bold text-slate-600">
                  <span>
                    Showing {pageIndex * itemsPerPage + 1} -{" "}
                    {Math.min((pageIndex + 1) * itemsPerPage, filteredTickets.length)} of{" "}
                    {filteredTickets.length} Tickets
                  </span>

                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage === 1}
                      className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </button>

                    {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                      <button
                        key={page}
                        onClick={() => setCurrentPage(page)}
                        className={`w-8 h-8 rounded-lg text-xs font-extrabold transition-all ${
                          currentPage === page
                            ? "bg-slate-900 text-white"
                            : "border border-slate-200 text-slate-700 hover:bg-slate-50"
                        }`}
                      >
                        {page}
                      </button>
                    ))}

                    <button
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage === totalPages}
                      className="p-2 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <ChevronRight className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
 * SportyBet-style Ticket Card Summary
 * ───────────────────────────────────────────────────────────────────────────── */
function TicketCard({ ticket, onClick, onDelete }) {
  const selections = ticket.selections || [];
  const nSel = selections.length;

  // Status Badge Logic
  const status = (ticket.status || "RUNNING").toUpperCase();
  const isWon = status === "WON";
  const isLost = status === "LOST";

  // Match Summary: First 3 games + remaining count
  const first3 = selections.slice(0, 3);
  const remainingCount = Math.max(0, nSel - 3);

  // Formatting Stake & Return
  const stakeVal = Number(ticket.stake || 1000);
  const oddsVal = Number(ticket.total_odds || ticket.target_odds || 1.5);
  const potWinVal = Number(ticket.potential_win || stakeVal * oddsVal);
  const returnVal = isWon ? potWinVal : 0;

  return (
    <div
      onClick={onClick}
      className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:border-slate-300 hover:shadow-md transition-all cursor-pointer space-y-4"
    >
      {/* Top Header: Date, Code, Mode, Status Badge */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-bold text-slate-500">
            {ticket.created_at || "Recent Ticket"}
          </span>
          <span className="text-[11px] font-extrabold bg-slate-100 text-slate-700 px-2.5 py-0.5 rounded-full border border-slate-200 uppercase tracking-wider">
            {ticket.mode || "AUDITOR"} Mode
          </span>
          {ticket.flex_cut && (
            <span className="text-[11px] font-extrabold bg-slate-800 text-emerald-400 px-2.5 py-0.5 rounded-full border border-slate-700 uppercase tracking-wider">
              Flex: {ticket.flex_cut}
            </span>
          )}
          {ticket.code && (
            <span className="text-[11px] font-bold text-slate-400 font-mono">
              Code: {ticket.code}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isWon ? (
            <div className="flex flex-col items-end">
              <span className="bg-emerald-100 text-emerald-800 border border-emerald-300 px-3 py-1 rounded-full text-xs font-extrabold flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Won
              </span>
              {ticket.flex_status_text && (
                <span className="text-[10px] font-extrabold text-emerald-700 mt-0.5">
                  {ticket.flex_status_text}
                </span>
              )}
            </div>
          ) : isLost ? (
            <div className="flex flex-col items-end">
              <span className="bg-rose-100 text-rose-800 border border-rose-300 px-3 py-1 rounded-full text-xs font-extrabold flex items-center gap-1">
                <XCircle className="w-3.5 h-3.5" /> Lost
              </span>
              {ticket.flex_status_text && (
                <span className="text-[10px] font-extrabold text-rose-600 mt-0.5">
                  {ticket.flex_status_text}
                </span>
              )}
            </div>
          ) : (
            <span className="bg-amber-100 text-amber-800 border border-amber-300 px-3 py-1 rounded-full text-xs font-extrabold flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" /> Running
            </span>
          )}

          <button
            onClick={(e) => onDelete(ticket.id, e)}
            className="p-1.5 text-slate-300 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-all"
            title="Delete Ticket"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Fixture Summary (First 3 games + N other matches) */}
      <div className="space-y-1.5">
        <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">
          Multiple ({nSel} Selections)
        </div>
        <div className="space-y-1">
          {first3.map((s, idx) => (
            <div key={idx} className="text-xs font-semibold text-slate-800 flex items-center justify-between">
              <span>
                {s.home_team || "Home"} <span className="text-slate-400">v</span> {s.away_team || "Away"}
              </span>
              <span className="text-[11px] font-bold text-slate-500 font-mono">
                {s.score ? `(${s.score})` : s.selection_name || ""}
              </span>
            </div>
          ))}
          {remainingCount > 0 && (
            <div className="text-xs font-extrabold text-indigo-600 pt-0.5">
              ...and {remainingCount} other matches
            </div>
          )}
        </div>
      </div>

      {/* Financial Summary Row (SportyBet Style) */}
      <div className="bg-slate-50 rounded-xl p-3 flex items-center justify-between border border-slate-100 text-xs">
        <div>
          <span className="text-slate-500 font-semibold block text-[10px] uppercase">Total Stake</span>
          <span className="font-extrabold text-slate-900">₦{stakeVal.toLocaleString()}</span>
        </div>

        <div>
          <span className="text-slate-500 font-semibold block text-[10px] uppercase">Total Odds</span>
          <span className="font-extrabold text-slate-900">~{oddsVal.toFixed(2)}x</span>
        </div>

        <div>
          <span className="text-slate-500 font-semibold block text-[10px] uppercase">Total Return</span>
          <span className={`font-extrabold ${isWon ? "text-emerald-600 font-black" : "text-slate-900"}`}>
            ₦{returnVal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </span>
        </div>

        <ChevronRight className="w-4 h-4 text-slate-400 ml-2" />
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
 * SportyBet-style Ticket Details Modal / Full Screen View
 * ───────────────────────────────────────────────────────────────────────────── */
function TicketDetailView({ ticket, onBack, onDelete }) {
  const selections = ticket.selections || [];
  const status = (ticket.status || "RUNNING").toUpperCase();
  const isWon = status === "WON";
  const isLost = status === "LOST";

  const stakeVal = Number(ticket.stake || 1000);
  const oddsVal = Number(ticket.total_odds || ticket.target_odds || 1.5);
  const potWinVal = Number(ticket.potential_win || stakeVal * oddsVal);
  const returnVal = isWon ? potWinVal : 0;

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-md p-6 space-y-6">
      {/* Top Action Bar */}
      <div className="flex items-center justify-between border-b border-slate-100 pb-4">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-xs font-extrabold text-slate-700 hover:text-slate-900 bg-slate-100 px-3.5 py-2 rounded-xl transition-all"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back</span>
        </button>

        <div className="text-center">
          <h2 className="text-sm font-extrabold text-slate-900 uppercase tracking-wider">
            Ticket Details (ID: {ticket.id?.replace("TICK-", "") || ticket.code})
          </h2>
          <span className="text-[11px] font-semibold text-slate-500">
            {ticket.created_at || "Recent"} | Mobile / Web
          </span>
        </div>

        <button
          onClick={() => onDelete(ticket.id)}
          className="flex items-center gap-1.5 text-xs font-extrabold text-rose-600 hover:bg-rose-50 px-3.5 py-2 rounded-xl transition-all"
        >
          <Trash2 className="w-4 h-4" />
          <span>Delete</span>
        </button>
      </div>

      {/* Ticket Overview Card */}
      <div className="bg-slate-900 text-white p-5 rounded-2xl space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <span className="text-xs text-slate-400 block font-semibold">Selection Type</span>
            <span className="text-sm font-extrabold text-white">Multiple ({selections.length} Legs)</span>
          </div>

          <div className="text-right">
            <span className="text-xs text-slate-400 block font-semibold">Status</span>
            {isWon ? (
              <span className="text-emerald-400 font-black text-xs uppercase flex items-center justify-end gap-1">
                <CheckCircle2 className="w-4 h-4" /> Won
              </span>
            ) : isLost ? (
              <span className="text-rose-400 font-black text-xs uppercase flex items-center justify-end gap-1">
                <XCircle className="w-4 h-4" /> Lost
              </span>
            ) : (
              <span className="text-amber-400 font-black text-xs uppercase flex items-center justify-end gap-1">
                <Clock className="w-4 h-4" /> Running / Unsettled
              </span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <span className="text-[10px] text-slate-400 block uppercase font-bold">Total Stake</span>
            <span className="text-sm font-extrabold text-white">₦{stakeVal.toLocaleString()}</span>
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase font-bold">Total Odds</span>
            <span className="text-sm font-extrabold text-white">~{oddsVal.toFixed(2)}x</span>
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase font-bold">Total Return</span>
            <span className={`text-sm font-black ${isWon ? "text-emerald-400" : "text-white"}`}>
              ₦{returnVal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>
        </div>
      </div>

      {/* Leg-by-Leg Details List (SportyBet Style) */}
      <div className="space-y-4">
        <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">
          Leg Selections & Final Match Outcomes ({selections.length})
        </h3>

        <div className="space-y-3">
          {selections.map((sel, idx) => {
            const legStatus = (sel.leg_status || sel.leg_result || "PENDING").toUpperCase();
            const isLegWon = legStatus === "WON";
            const isLegLost = legStatus === "LOST";

            return (
              <div
                key={idx}
                className="bg-slate-50 border border-slate-200 rounded-2xl p-4 space-y-3 hover:border-slate-300 transition-all"
              >
                {/* Leg Header: Leg #, Kickoff, Game ID, Leg Status */}
                <div className="flex items-center justify-between border-b border-slate-200/60 pb-2.5">
                  <div className="flex items-center gap-3">
                    <span className="w-6 h-6 rounded-full bg-slate-900 text-white font-extrabold text-xs flex items-center justify-center">
                      {idx + 1}
                    </span>
                    <span className="text-xs font-semibold text-slate-500">
                      {sel.kickoff_datetime_str || sel.start_time_ms ? "06/08 18:00" : "Upcoming"}
                    </span>
                    {sel.game_id && (
                      <span className="text-[11px] font-bold text-slate-400 font-mono">
                        Game ID: {sel.game_id}
                      </span>
                    )}
                  </div>

                  <div>
                    {isLegWon ? (
                      <span className="bg-emerald-100 text-emerald-800 border border-emerald-300 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold flex items-center gap-1">
                        <CheckCircle2 className="w-3 h-3" /> Won
                      </span>
                    ) : isLegLost ? (
                      <span className="bg-rose-100 text-rose-800 border border-rose-300 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold flex items-center gap-1">
                        <XCircle className="w-3 h-3" /> Lost
                      </span>
                    ) : legStatus === "VOID" || legStatus === "PUSH" ? (
                      <span className="bg-blue-100 text-blue-800 border border-blue-300 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold flex items-center gap-1">
                        <MinusCircle className="w-3 h-3" /> Void / Push (1.00x)
                      </span>
                    ) : (
                      <span className="bg-amber-100 text-amber-800 border border-amber-300 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold flex items-center gap-1">
                        <Clock className="w-3 h-3 animate-pulse" /> Live / Pending
                      </span>
                    )}
                  </div>
                </div>

                {/* Teams & Scores */}
                <div className="flex items-center justify-between py-1">
                  <div className="space-y-0.5">
                    <span className="text-xs font-extrabold text-slate-900 block">
                      {sel.home_team || "Home Team"}
                    </span>
                    <span className="text-xs font-extrabold text-slate-900 block">
                      {sel.away_team || "Away Team"}
                    </span>
                  </div>

                  {sel.score && (
                    <div className="bg-white border border-slate-200 px-3 py-1.5 rounded-xl font-mono text-sm font-black text-slate-900 text-center">
                      {sel.score}
                    </div>
                  )}
                </div>

                {/* Pick, Market & Result Rows (SportyBet Style) */}
                <div className="grid grid-cols-3 gap-2 bg-white p-3 rounded-xl border border-slate-200/80 text-xs">
                  <div>
                    <span className="text-[10px] font-semibold text-slate-400 block uppercase">Pick</span>
                    <span className="font-extrabold text-slate-900">
                      {sel.selection_name || sel.selection || "Pick"} @{sel.odds || sel.estimated_odds || "1.25"}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] font-semibold text-slate-400 block uppercase">Market</span>
                    <span className="font-semibold text-slate-700">
                      {sel.market_name || sel.market || "Market"}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] font-semibold text-slate-400 block uppercase">Result</span>
                    <span className={`font-bold ${isLegWon ? "text-emerald-700 font-extrabold" : isLegLost ? "text-rose-700 font-extrabold" : "text-slate-600"}`}>
                      {sel.score ? (sel.selection_name || "Concluded") : "Pending"}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
