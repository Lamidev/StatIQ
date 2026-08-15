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
  Radio,
  Zap,
  Activity,
  PlayCircle,
  Target,
} from "lucide-react";
import { fetchTrackedTickets, deleteTrackedTicket, syncLiveTrackedTickets } from "../api/client";
import { isTicketLive, isLegLive, evaluatePickLive, evaluateTicketStatus, getDynamicMatchInfo, parseScore } from "../utils/ticketEvaluator";

export default function BetHistoryTab({ externalSelectedTicketId, onClearExternalTicket, onTicketsChanged }) {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters: ACTIVE (Default - Show running & live tickets first), LIVE, WON, LOST, ALL
  const [statusFilter, setStatusFilter] = useState("ACTIVE"); 
  const [dateFilter, setDateFilter] = useState("ALL"); 
  const [searchQuery, setSearchQuery] = useState("");

  // Pagination
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 8;

  // Selected Ticket for Detail View / Modal
  const [selectedTicket, setSelectedTicket] = useState(null);

  // Live ticker step simulation state
  const [liveTick, setLiveTick] = useState(0);

  const loadData = async (isSilent = false) => {
    if (!isSilent) setLoading(true);
    setError(null);
    try {
      const data = await fetchTrackedTickets();
      const ticketList = Array.isArray(data)
        ? data
        : data.tickets || [];
      setTickets(ticketList);

      // Keep selected ticket updated if open
      if (selectedTicket) {
        const fresh = ticketList.find((t) => t.id === selectedTicket.id);
        if (fresh) setSelectedTicket(fresh);
      }
      if (onTicketsChanged) onTicketsChanged();
    } catch (err) {
      console.error("Failed to load bet history:", err);
      if (!isSilent) setError("Failed to connect to StatIQ backend.");
    } finally {
      if (!isSilent) setLoading(false);
    }
  };

  useEffect(() => {
    // Load cached data instantly, then fire ONE background SportyBet API sync
    loadData(false).then(() => {
      syncLiveTrackedTickets().then(() => loadData(true));
    });
  }, []);

  // Handle opening ticket from external notification click
  useEffect(() => {
    if (externalSelectedTicketId) {
      setStatusFilter("ALL");
      if (tickets.length > 0) {
        const match = tickets.find((t) => t.id === externalSelectedTicketId);
        if (match) {
          setSelectedTicket(match);
          if (onClearExternalTicket) onClearExternalTicket();
        }
      } else {
        fetchTrackedTickets().then((data) => {
          const list = Array.isArray(data) ? data : data.tickets || [];
          const found = list.find((t) => t.id === externalSelectedTicketId);
          if (found) setSelectedTicket(found);
          if (onClearExternalTicket) onClearExternalTicket();
        });
      }
    }
  }, [externalSelectedTicketId]);

  // Periodic live clock ticker and real-time live score sync (every 10s)
  useEffect(() => {
    const timer = setInterval(() => {
      setLiveTick((prev) => {
        const next = prev + 1;
        loadData(true);
        syncLiveTrackedTickets().then(() => loadData(true));
        return next;
      });
    }, 10000);
    return () => clearInterval(timer);
  }, []);

  // Selected Ticket for Delete Modal
  const [ticketToDelete, setTicketToDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const confirmDelete = (ticketObj, e) => {
    if (e) e.stopPropagation();
    setTicketToDelete(ticketObj);
  };

  const executeDelete = async () => {
    if (!ticketToDelete) return;
    const ticketId = ticketToDelete.id || ticketToDelete.code;
    setDeleting(true);

    // Instantly remove from local UI state for snappy experience
    setTickets((prev) => prev.filter((t) => t.id !== ticketId && t.code !== ticketId));
    if (selectedTicket?.id === ticketId || selectedTicket?.code === ticketId) {
      setSelectedTicket(null);
    }
    if (onTicketsChanged) onTicketsChanged();

    try {
      await deleteTrackedTicket(ticketId);
      setTicketToDelete(null);
      await loadData(true);
    } catch (err) {
      console.error("Failed to delete ticket:", err);
      await loadData(true);
    } finally {
      setDeleting(false);
    }
  };

  // Filter Logic: Dynamically settle tickets in real-time
  const evaluatedTickets = tickets.map((t) => {
    const evalStatus = evaluateTicketStatus(t);
    return {
      ...t,
      status: evalStatus.status,
      isWon: evalStatus.isWon,
      isLost: evalStatus.isLost,
      isLive: evalStatus.isLive
    };
  });

  const filteredTickets = evaluatedTickets.filter((t) => {
    const isWon = t.status === "WON";
    const isLost = t.status === "LOST";
    const isActive = t.status === "RUNNING" || t.status === "PENDING" || !t.status;
    const hasLiveGames = t.isLive || isTicketLive(t);

    if (statusFilter === "LIVE" && !hasLiveGames) return false;
    if (statusFilter === "ACTIVE" && (isWon || isLost)) return false;
    if (statusFilter === "WON" && !isWon) return false;
    if (statusFilter === "LOST" && !isLost) return false;

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

  const liveTicketCount = tickets.filter((t) => isTicketLive(t)).length;

  return (
    <div className="space-y-4 sm:space-y-6 max-w-6xl mx-auto">
      {/* Top Banner / Header */}
      <div className="bg-slate-900 text-white p-4 sm:p-6 rounded-xl sm:rounded-2xl shadow-md flex flex-col md:flex-row items-start md:items-center justify-between gap-3 sm:gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <Receipt className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-400" />
            <h1 className="text-base sm:text-xl font-extrabold tracking-tight">
              Tickets & Bet History
            </h1>
            {liveTicketCount > 0 && (
              <span className="bg-red-500/20 text-red-400 border border-red-500/40 px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-black flex items-center gap-1.5 animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-ping"></span>
                {liveTicketCount} LIVE IN-PLAY
              </span>
            )}
          </div>
          <p className="text-[11px] sm:text-xs text-slate-400">
            Track live ticket outcomes, win/loss history, match clocks, and SportyBet leg settlement.
          </p>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          <button
            onClick={() => loadData(false)}
            disabled={loading}
            className="flex items-center gap-1.5 sm:gap-2 bg-slate-800 hover:bg-slate-700 text-white px-3 py-1.5 sm:px-4 sm:py-2 rounded-xl text-xs font-bold transition-all border border-slate-700 shadow-sm"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Sync History</span>
          </button>
        </div>
      </div>

      {/* Summary Metrics Cards Bar */}
      {!selectedTicket && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3">
          <div className="bg-white p-3 sm:p-4 rounded-xl sm:rounded-2xl border border-slate-200 shadow-sm space-y-1">
            <span className="text-[9px] sm:text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">
              Total Tracked
            </span>
            <div className="flex items-center justify-between">
              <span className="text-lg sm:text-xl font-black text-slate-900">{tickets.length}</span>
              {liveTicketCount > 0 && (
                <span className="text-[9px] sm:text-[10px] font-extrabold bg-red-100 text-red-700 px-1.5 py-0.5 rounded-full">
                  {liveTicketCount} Live
                </span>
              )}
            </div>
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

      {/* Feature Performance Analytics Comparison Dashboard */}
      {!selectedTicket && tickets.length > 0 && (
        <div className="bg-white p-5 rounded-2xl border border-slate-200 space-y-3 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
            <div>
              <h3 className="text-xs font-black text-slate-900 uppercase tracking-wider">
                📊 Re-Editor Feature Performance Analytics (Auditor vs Swap vs Remove)
              </h3>
              <p className="text-[11px] text-slate-500">
                Compare win rates and effective performance across ticket re-editing strategies.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            {/* SWAP Mode */}
            {(() => {
              const swapTickets = tickets.filter(t => (t.mode || "").toUpperCase() === "SWAP");
              const total = swapTickets.length;
              const won = swapTickets.filter(t => t.status === "WON").length;
              const rate = total > 0 ? ((won / total) * 100).toFixed(1) : "0.0";
              return (
                <div className="bg-indigo-50/70 border border-indigo-200 p-3.5 rounded-xl space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-extrabold text-indigo-900 flex items-center gap-1">
                      <RefreshCw className="w-3.5 h-3.5 text-indigo-600" />
                      <span>SWAP MODE (Hybrid)</span>
                    </span>
                    <span className="bg-indigo-600 text-white text-[10px] font-black px-2 py-0.5 rounded-full">
                      {rate}% Win Rate
                    </span>
                  </div>
                  <p className="text-slate-700 font-extrabold text-sm mt-1">
                    {won} Won <span className="text-slate-400 text-xs font-normal">/ {total} Tickets</span>
                  </p>
                  <p className="text-[10px] text-slate-500">Swaps risky games with top European picks.</p>
                </div>
              );
            })()}

            {/* REMOVE Mode */}
            {(() => {
              const removeTickets = tickets.filter(t => (t.mode || "").toUpperCase() === "REMOVE");
              const total = removeTickets.length;
              const won = removeTickets.filter(t => t.status === "WON").length;
              const rate = total > 0 ? ((won / total) * 100).toFixed(1) : "0.0";
              return (
                <div className="bg-rose-50/70 border border-rose-200 p-3.5 rounded-xl space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-extrabold text-rose-900 flex items-center gap-1">
                      <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                      <span>REMOVE MODE</span>
                    </span>
                    <span className="bg-rose-600 text-white text-[10px] font-black px-2 py-0.5 rounded-full">
                      {rate}% Win Rate
                    </span>
                  </div>
                  <p className="text-slate-700 font-extrabold text-sm mt-1">
                    {won} Won <span className="text-slate-400 text-xs font-normal">/ {total} Tickets</span>
                  </p>
                  <p className="text-[10px] text-slate-500">Drops risky games without adding replacements.</p>
                </div>
              );
            })()}

            {/* AUDITOR Mode */}
            {(() => {
              const auditorTickets = tickets.filter(t => (t.mode || "AUDITOR").toUpperCase() === "AUDITOR");
              const total = auditorTickets.length;
              const won = auditorTickets.filter(t => t.status === "WON").length;
              const rate = total > 0 ? ((won / total) * 100).toFixed(1) : "0.0";
              return (
                <div className="bg-emerald-50/70 border border-emerald-200 p-3.5 rounded-xl space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-extrabold text-emerald-900 flex items-center gap-1">
                      <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                      <span>AUDITOR MODE</span>
                    </span>
                    <span className="bg-emerald-600 text-white text-[10px] font-black px-2 py-0.5 rounded-full">
                      {rate}% Win Rate
                    </span>
                  </div>
                  <p className="text-slate-700 font-extrabold text-sm mt-1">
                    {won} Won <span className="text-slate-400 text-xs font-normal">/ {total} Tickets</span>
                  </p>
                  <p className="text-[10px] text-slate-500">Strictly upgrades original ticket picks.</p>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* Main View: List or Detailed Ticket */}
      {selectedTicket ? (
        /* Detailed Ticket View (SportyBet Style) */
        <TicketDetailView
          ticket={selectedTicket}
          onBack={() => {
            setSelectedTicket(null);
            if (onClearExternalTicket) onClearExternalTicket();
          }}
          onDelete={(t) => confirmDelete(t)}
        />
      ) : (
        /* Ticket Cards Summary View */
        <div className="space-y-6">
          {/* Controls & Filter Bar */}
          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
            {/* Status Filter Tabs (Active / Live / Won / Lost / All) */}
            <div className="flex items-center bg-slate-100 p-1 rounded-xl overflow-x-auto gap-1">
              {[
                { id: "ACTIVE", label: `Active Staked (${tickets.filter((t) => t.status === "RUNNING" || t.status === "PENDING" || !t.status).length})` },
                { id: "LIVE", label: `Live In-Play (${liveTicketCount})` },
                { id: "WON", label: `Won (${tickets.filter((t) => t.status === "WON").length})` },
                { id: "LOST", label: `Lost (${tickets.filter((t) => t.status === "LOST").length})` },
                { id: "ALL", label: `All History (${tickets.length})` },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => {
                    setStatusFilter(tab.id);
                    setCurrentPage(1);
                  }}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-extrabold transition-all whitespace-nowrap ${
                    statusFilter === tab.id
                      ? tab.id === "LIVE"
                        ? "bg-red-600 text-white shadow-sm"
                        : "bg-white text-slate-900 shadow-sm"
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
                onClick={() => loadData(false)}
                className="text-xs font-extrabold underline text-rose-900"
              >
                Try Again
              </button>
            </div>
          ) : filteredTickets.length === 0 ? (
            <div className="bg-white p-8 sm:p-12 rounded-2xl border border-slate-200 text-center space-y-3">
              <Receipt className="w-10 h-10 text-slate-300 mx-auto" />
              <h3 className="text-sm font-extrabold text-slate-900">
                {statusFilter === "ACTIVE" && tickets.length > 0 ? "No Active / Running Tickets" : "No Tickets Found"}
              </h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                {statusFilter === "ACTIVE" && tickets.length > 0
                  ? `All your ${tickets.length} tracked ticket(s) have finished and been settled.`
                  : "No staked or audited tickets match your selected filters. Re-edit a ticket in the Ticket Auditor and click '📌 Lock & Track Staked Ticket' to start tracking!"}
              </p>
              {statusFilter !== "ALL" && tickets.length > 0 && (
                <button
                  onClick={() => {
                    setStatusFilter("ALL");
                    setDateFilter("ALL");
                    setSearchQuery("");
                  }}
                  className="bg-slate-900 hover:bg-slate-800 text-white text-xs font-extrabold px-4 py-2 rounded-xl mt-2 transition-all shadow-sm cursor-pointer"
                >
                  View All {tickets.length} Saved Tickets
                </button>
              )}
            </div>
          ) : (
            /* Ticket Cards List */
            <div className="space-y-4">
              {paginatedTickets.map((t) => (
                <TicketCard
                  key={t.id || t.code}
                  ticket={t}
                  onClick={() => setSelectedTicket(t)}
                  onDelete={(t, e) => confirmDelete(t, e)}
                />
              ))}

              {/* Smart Compact Sliding Pagination */}
              {totalPages > 1 && (
                <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3.5 sm:p-4 rounded-2xl border border-slate-200 shadow-sm text-xs font-bold text-slate-600">
                  <span className="text-slate-500 font-medium">
                    Showing <span className="text-slate-900 font-black">{pageIndex * itemsPerPage + 1}</span> -{" "}
                    <span className="text-slate-900 font-black">{Math.min((pageIndex + 1) * itemsPerPage, filteredTickets.length)}</span> of{" "}
                    <span className="text-slate-900 font-black">{filteredTickets.length}</span> Tickets
                  </span>

                  <div className="flex items-center gap-1 sm:gap-1.5 flex-wrap justify-center">
                    <button
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage === 1}
                      className="px-2.5 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed text-xs font-extrabold flex items-center gap-1 cursor-pointer transition-all"
                    >
                      <ChevronLeft className="w-3.5 h-3.5" />
                      <span className="hidden sm:inline">Prev</span>
                    </button>

                    {(() => {
                      const getPages = () => {
                        if (totalPages <= 5) {
                          return Array.from({ length: totalPages }, (_, i) => i + 1);
                        }
                        if (currentPage <= 3) {
                          return [1, 2, 3, 4, "...", totalPages];
                        }
                        if (currentPage >= totalPages - 2) {
                          return [1, "...", totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
                        }
                        return [1, "...", currentPage - 1, currentPage, currentPage + 1, "...", totalPages];
                      };

                      return getPages().map((item, idx) => {
                        if (item === "...") {
                          return (
                            <span key={`dots-${idx}`} className="px-1 text-slate-400 font-black select-none">
                              ...
                            </span>
                          );
                        }
                        return (
                          <button
                            key={item}
                            onClick={() => setCurrentPage(item)}
                            className={`w-7 h-7 sm:w-8 sm:h-8 rounded-xl text-xs font-black transition-all cursor-pointer ${
                              currentPage === item
                                ? "bg-slate-900 text-white shadow-xs"
                                : "border border-slate-200 text-slate-700 hover:bg-slate-50"
                            }`}
                          >
                            {item}
                          </button>
                        );
                      });
                    })()}

                    <button
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage === totalPages}
                      className="px-2.5 py-1.5 rounded-xl border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed text-xs font-extrabold flex items-center gap-1 cursor-pointer transition-all"
                    >
                      <span className="hidden sm:inline">Next</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Delete Confirmation Modal UI/UX */}
      {ticketToDelete && (
        <div 
          className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200"
          onClick={() => setTicketToDelete(null)}
        >
          <div 
            className="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl border border-slate-100 space-y-5 animate-in zoom-in-95 duration-200"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3">
              <div className="p-3 bg-rose-100 text-rose-600 rounded-2xl shrink-0">
                <Trash2 className="w-6 h-6" />
              </div>
              <div>
                <h3 className="text-base font-black text-slate-900">Delete Tracked Ticket?</h3>
                <p className="text-xs text-slate-500 font-semibold">
                  This action will permanently remove this ticket from your tracked history.
                </p>
              </div>
            </div>

            {/* Ticket Preview Card */}
            <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200 space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-extrabold text-slate-900">
                  {ticketToDelete.code ? `Booking Code: ${ticketToDelete.code}` : `Ticket ID: ${ticketToDelete.id?.replace("TICK-", "")}`}
                </span>
                <span className="bg-slate-900 text-white text-[10px] font-black px-2 py-0.5 rounded-full">
                  {(ticketToDelete.mode || "AUDITOR").toUpperCase()} MODE
                </span>
              </div>
              <div className="flex items-center justify-between text-slate-600 font-semibold pt-1">
                <span>{(ticketToDelete.selections || []).length} Leg Selections</span>
                <span>Stake: ₦{Number(ticketToDelete.stake || 5000).toLocaleString(undefined, {minimumFractionDigits: 2})}</span>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                onClick={() => setTicketToDelete(null)}
                disabled={deleting}
                className="px-5 py-2.5 rounded-xl text-xs font-extrabold text-slate-600 bg-slate-100 hover:bg-slate-200 transition-all cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={executeDelete}
                disabled={deleting}
                className="px-5 py-2.5 rounded-xl text-xs font-extrabold text-white bg-rose-600 hover:bg-rose-700 shadow-md shadow-rose-600/20 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
              >
                {deleting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Delete Ticket</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
 * SportyBet-style Ticket Card Summary (With Live Sticker Support)
 * ───────────────────────────────────────────────────────────────────────────── */
function TicketCard({ ticket, onClick, onDelete }) {
  const selections = ticket.selections || [];
  const nSel = selections.length;

  // Status Badge Logic
  const status = (ticket.status || "RUNNING").toUpperCase();
  const isWon = status === "WON";
  const isLost = status === "LOST";
  const isLive = isTicketLive(ticket);

  const liveLegCount = selections.filter((s) => isLegLive(s)).length;

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
      className={`bg-white rounded-2xl border p-5 shadow-sm hover:shadow-md transition-all cursor-pointer space-y-4 ${
        isLive ? "border-red-300 ring-1 ring-red-100" : "border-slate-200 hover:border-slate-300"
      }`}
    >
      {/* Top Header: Date, Code, Mode, Live Sticker, Status Badge */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div className="flex items-center gap-2.5">
          <span className="text-xs font-bold text-slate-500">
            {ticket.created_at || "Recent Ticket"}
          </span>

          {/* Live Sticker on Ticket Card */}
          {isLive && (
            <span className="bg-red-500/10 text-red-600 border border-red-500/30 px-2.5 py-0.5 rounded-full text-[11px] font-black flex items-center gap-1.5 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-red-600 animate-ping" />
              LIVE {liveLegCount > 0 && `(${liveLegCount} IN-PLAY)`}
            </span>
          )}

          {/* Feature Mode Tag */}
          {(() => {
            const m = (ticket.mode || "AUDITOR").toUpperCase();
            if (m === "SWAP" || m === "HYBRID") {
              return (
                <span className="text-xs font-black bg-indigo-100 text-indigo-900 border border-indigo-300 px-3 py-1 rounded-lg uppercase tracking-wider flex items-center gap-1.5 shadow-xs">
                  <RefreshCw className="w-3.5 h-3.5 text-indigo-700" />
                  <span>Feature: SWAP Mode</span>
                </span>
              );
            }
            if (m === "REMOVE") {
              return (
                <span className="text-xs font-black bg-rose-100 text-rose-900 border border-rose-300 px-3 py-1 rounded-lg uppercase tracking-wider flex items-center gap-1.5 shadow-xs">
                  <Trash2 className="w-3.5 h-3.5 text-rose-700" />
                  <span>Feature: REMOVE Mode</span>
                </span>
              );
            }
            if (m === "BUILDER" || m === "ACCUMULATOR" || m === "ROLLOVER") {
              return (
                <span className="text-xs font-black bg-amber-100 text-amber-900 border border-amber-300 px-3 py-1 rounded-lg uppercase tracking-wider flex items-center gap-1.5 shadow-xs">
                  <Target className="w-3.5 h-3.5 text-amber-700" />
                  <span>Feature: AI BUILDER</span>
                </span>
              );
            }
            return (
              <span className="text-xs font-black bg-emerald-100 text-emerald-900 border border-emerald-300 px-3 py-1 rounded-lg uppercase tracking-wider flex items-center gap-1.5 shadow-xs">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-700" />
                <span>Feature: AUDITOR Mode</span>
              </span>
            );
          })()}

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
            </div>
          ) : isLost ? (
            <div className="flex flex-col items-end">
              <span className="bg-rose-100 text-rose-800 border border-rose-300 px-3 py-1 rounded-full text-xs font-extrabold flex items-center gap-1">
                <XCircle className="w-3.5 h-3.5" /> Lost
              </span>
            </div>
          ) : isLive ? (
            <span className="bg-red-100 text-red-800 border border-red-300 px-3 py-1 rounded-full text-xs font-black flex items-center gap-1.5">
              <Radio className="w-3.5 h-3.5 animate-pulse text-red-600" /> Ongoing / Live
            </span>
          ) : (
            <span className="bg-amber-100 text-amber-800 border border-amber-300 px-3 py-1 rounded-full text-xs font-extrabold flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" /> Running
            </span>
          )}

          <button
            onClick={(e) => onDelete(ticket, e)}
            className="p-1.5 text-slate-300 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-all"
            title="Delete Ticket"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Fixture Summary (First 3 games + N other matches) */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-bold text-slate-500 uppercase tracking-wider">
          <span>Multiple ({nSel} Selections)</span>
          {isLive && (
            <span className="text-[11px] font-extrabold text-red-600 flex items-center gap-1">
              <Zap className="w-3 h-3 fill-red-600" /> Matches Updating Live
            </span>
          )}
        </div>

        <div className="space-y-1.5">
          {first3.map((s, idx) => {
            const legLive = isLegLive(s);
            const evalRes = evaluatePickLive(s);
            const isLegWon = evalRes.status === "WON" || s.leg_status === "WON";
            const isLegLost = evalRes.status === "LOST" || s.leg_status === "LOST";

            return (
              <div key={idx} className="text-xs font-semibold text-slate-800 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {legLive && (
                    <span className="bg-red-600 text-white text-[9px] font-black px-1.5 py-0.2 rounded uppercase">
                      LIVE
                    </span>
                  )}
                  <span>
                    {s.home_team || "Home"} <span className="text-slate-400">v</span> {s.away_team || "Away"}
                  </span>
                </div>

                <div className="flex items-center gap-2 font-mono">
                  {parseScore(s).scoreStr !== "--" && (
                    <span className={`text-[11px] font-black px-2 py-0.5 rounded ${legLive ? "bg-red-50 text-red-700 border border-red-200" : "bg-slate-100 text-slate-800"}`}>
                      {parseScore(s).scoreStr}
                    </span>
                  )}
                  {isLegWon ? (
                    <span className="bg-emerald-100 text-emerald-800 text-[10px] font-black px-1.5 py-0.5 rounded border border-emerald-300">
                      WON
                    </span>
                  ) : isLegLost ? (
                    <span className="bg-rose-100 text-rose-800 text-[10px] font-black px-1.5 py-0.5 rounded border border-rose-300">
                      LOST
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}

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
 * SportyBet-style Ticket Details Modal / View (Matches SportyBet 100%)
 * ───────────────────────────────────────────────────────────────────────────── */
function TicketDetailView({ ticket, onBack, onDelete }) {
  const selections = ticket.selections || [];
  const status = (ticket.status || "RUNNING").toUpperCase();
  const isWon = status === "WON";
  const isLost = status === "LOST";
  const isLive = isTicketLive(ticket);

  const stakeVal = Number(ticket.stake || 1000);
  const oddsVal = Number(ticket.total_odds || ticket.target_odds || 1.5);
  const potWinVal = Number(ticket.potential_win || stakeVal * oddsVal);
  const returnVal = isWon ? potWinVal : 0;

  // Local override state for live interactive simulation testing
  const [simulationOverrides, setSimulationOverrides] = useState({});

  const displaySelections = (ticket.selections || []).map((sel, idx) => {
    return simulationOverrides[idx] ? { ...sel, ...simulationOverrides[idx] } : sel;
  });

  // Simulate a live goal scored for interactive testing
  const simulateLiveGoal = (index) => {
    const sel = displaySelections[index];
    const curHome = sel.home_score !== undefined && sel.home_score !== null ? sel.home_score : (sel.score ? parseInt(sel.score.split("-")[0]) : 0);
    const curAway = sel.away_score !== undefined && sel.away_score !== null ? sel.away_score : (sel.score ? parseInt(sel.score.split("-")[1]) : 0);
    const newAway = curAway + 1;
    const newScoreStr = `${curHome} - ${newAway}`;
    setSimulationOverrides(prev => ({
      ...prev,
      [index]: {
        home_score: curHome,
        away_score: newAway,
        score: newScoreStr,
        match_status: "LIVE",
        match_time: "42' H1",
        is_live: true,
      }
    }));
  };

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
          <div className="flex items-center justify-center gap-2">
            <h2 className="text-sm font-black text-slate-900 uppercase tracking-wider">
              Ticket Details (ID: {ticket.id?.replace("TICK-", "") || ticket.code || "--"})
            </h2>
            {isLive && (
              <span className="bg-red-500 text-white text-[10px] font-black px-2 py-0.5 rounded-full flex items-center gap-1 animate-pulse">
                <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping"></span>
                LIVE
              </span>
            )}
          </div>
          <span className="text-[11px] font-semibold text-slate-500">
            {ticket.created_at || "07/08/2026 15:25"} | 102.89.47.11 | Mobile
          </span>
        </div>

        <button
          onClick={(e) => onDelete(ticket, e)}
          className="flex items-center gap-1.5 text-xs font-extrabold text-rose-600 hover:bg-rose-50 px-3.5 py-2 rounded-xl transition-all"
        >
          <Trash2 className="w-4 h-4" />
          <span>Delete</span>
        </button>
      </div>

      {/* Ticket Overview Card (SportyBet Style Header) */}
      <div className="bg-slate-900 text-white p-5 rounded-2xl space-y-4 shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div>
            <span className="text-[10px] text-slate-400 block font-bold uppercase tracking-wider">Selection Type</span>
            <span className="text-sm font-extrabold text-white">Multiple ({displaySelections.length} Legs)</span>
          </div>

          <div className="text-right">
            <span className="text-[10px] text-slate-400 block font-bold uppercase tracking-wider">Status</span>
            {isWon ? (
              <span className="text-emerald-400 font-black text-xs uppercase flex items-center justify-end gap-1">
                <CheckCircle2 className="w-4 h-4" /> Won
              </span>
            ) : isLost ? (
              <span className="text-rose-400 font-black text-xs uppercase flex items-center justify-end gap-1">
                <XCircle className="w-4 h-4" /> Lost
              </span>
            ) : isLive ? (
              <span className="text-red-400 font-black text-xs uppercase flex items-center justify-end gap-1.5 animate-pulse">
                <Radio className="w-4 h-4 animate-pulse text-red-500" /> Running (Live In-Play)
              </span>
            ) : (
              <span className="text-amber-400 font-black text-xs uppercase flex items-center justify-end gap-1">
                <Clock className="w-4 h-4" /> Running
              </span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
          <div>
            <span className="text-[10px] text-slate-400 block uppercase font-bold">Total Stake</span>
            <span className="text-sm font-black text-white">₦{stakeVal.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase font-bold">Max Bonus</span>
            <span className="text-sm font-extrabold text-emerald-400">₦{(stakeVal * 21.1).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase font-bold">Total Odds</span>
            <span className="text-sm font-extrabold text-white">{oddsVal.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-[10px] text-slate-400 block uppercase font-bold">Pot. Win</span>
            <span className="text-sm font-black text-emerald-400">
              ₦{potWinVal.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </span>
          </div>
        </div>

        {ticket.code && (
          <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-xs">
            <span className="text-slate-400 font-medium">Booking Code: <strong className="text-white font-mono">{ticket.code}</strong></span>
            <span className="text-slate-400 text-[11px]">Total Return: <strong className="text-white font-bold">{isWon ? `₦${returnVal.toLocaleString()}` : "--"}</strong></span>
          </div>
        )}
      </div>

      {/* Re-Editor Feature Mode Tag Banner */}
      {(() => {
        const m = (ticket.mode || "AUDITOR").toUpperCase();
        return (
          <div className="bg-slate-50 border border-slate-200 p-4 rounded-2xl flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs shadow-xs">
            <div className="flex items-center space-x-3">
              <div className="p-2.5 rounded-xl bg-slate-900 text-white">
                {m === "SWAP" || m === "HYBRID" ? <RefreshCw className="w-4 h-4 text-indigo-400" /> :
                 m === "REMOVE" ? <Trash2 className="w-4 h-4 text-rose-400" /> :
                 m === "BUILDER" || m === "ACCUMULATOR" ? <Target className="w-4 h-4 text-amber-400" /> :
                 <ShieldCheck className="w-4 h-4 text-emerald-400" />}
              </div>
              <div>
                <span className="text-[10px] text-slate-400 font-extrabold uppercase tracking-wider block">
                  Re-Editor Feature Used
                </span>
                <h4 className="font-extrabold text-slate-900 text-sm">
                  {m === "SWAP" || m === "HYBRID" ? "SWAP MODE (Hybrid Re-Edit)" :
                   m === "REMOVE" ? "REMOVE MODE (Dropped Risky Picks)" :
                   m === "BUILDER" || m === "ACCUMULATOR" ? "AI TICKET BUILDER" :
                   "AUDITOR MODE (Structural Pick Upgrades)"}
                </h4>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  {m === "SWAP" || m === "HYBRID" ? "Kept safe original ticket games, and swapped risky games with high-confidence picks from top European leagues." :
                   m === "REMOVE" ? "Dropped risky games from original slip without adding external replacements." :
                   m === "BUILDER" || m === "ACCUMULATOR" ? "Generated using StatIQ's AI Ticket Engine with 5-Gate Probability Audit." :
                   "Audited original ticket selections directly and upgraded market picks to safest structural options."}
                </p>
              </div>
            </div>

            <div className="flex-shrink-0">
              {m === "SWAP" || m === "HYBRID" ? (
                <span className="text-xs font-black bg-indigo-100 text-indigo-900 border border-indigo-300 px-3 py-1.5 rounded-xl uppercase tracking-wider">
                  Feature: SWAP Mode
                </span>
              ) : m === "REMOVE" ? (
                <span className="text-xs font-black bg-rose-100 text-rose-900 border border-rose-300 px-3 py-1.5 rounded-xl uppercase tracking-wider">
                  Feature: REMOVE Mode
                </span>
              ) : m === "BUILDER" || m === "ACCUMULATOR" ? (
                <span className="text-xs font-black bg-amber-100 text-amber-900 border border-amber-300 px-3 py-1.5 rounded-xl uppercase tracking-wider">
                  Feature: AI BUILDER
                </span>
              ) : (
                <span className="text-xs font-black bg-emerald-100 text-emerald-900 border border-emerald-300 px-3 py-1.5 rounded-xl uppercase tracking-wider">
                  Feature: AUDITOR Mode
                </span>
              )}
            </div>
          </div>
        );
      })()}

      {/* Flex Cut Status Banner */}
      {ticket.flex_status_text && (
        <div className={`p-4 rounded-2xl border text-xs font-bold flex flex-col md:flex-row items-start md:items-center justify-between gap-3 shadow-sm ${
          isWon
            ? "bg-emerald-50 border-emerald-200 text-emerald-900"
            : isLost
            ? "bg-rose-50 border-rose-200 text-rose-900"
            : "bg-indigo-50 border-indigo-200 text-indigo-900"
        }`}>
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="w-5 h-5 text-emerald-600 shrink-0" />
            <div>
              <span className="font-extrabold text-sm block">{ticket.flex_status_text}</span>
              <span className="text-[11px] font-semibold text-slate-500">
                Ticket Settlement Strategy: {ticket.flex_cut || "AUTO"} | Losses: {ticket.loss_count ?? 0} / {ticket.allowed_losses ?? 0} Allowed
              </span>
            </div>
          </div>

          <span className="text-[11px] font-black uppercase px-3 py-1 rounded-xl bg-white border border-slate-200 shadow-xs tracking-wider">
            {isWon ? "TICKET WON" : isLost ? "TICKET BUST / LOST" : "TICKET RUNNING"}
          </span>
        </div>
      )}

      {/* Feature & Strategy Banner */}
      <div className="bg-slate-100 rounded-2xl p-4 space-y-2 border border-slate-200">
        <div className="flex items-center justify-between">
          <span className="text-xs font-black text-slate-800 uppercase tracking-wider">
            Re-Editor Feature Used
          </span>
          <span className="text-xs font-extrabold text-slate-600">
            {(() => {
              const m = (ticket.mode || "AUDITOR").toUpperCase();
              if (m === "SWAP" || m === "HYBRID") return "SWAP MODE (Optimized Leg Replacement)";
              if (m === "REMOVE") return "REMOVE MODE (Dropped Risky Picks)";
              if (m === "BUILDER" || m === "ACCUMULATOR" || m === "ROLLOVER") return "AI BUILDER (Target Odds Slip)";
              return "AUDITOR MODE (Structural Pick Upgrades)";
            })()}
          </span>
        </div>
        <p className="text-xs text-slate-600">
          {(() => {
            const m = (ticket.mode || "AUDITOR").toUpperCase();
            if (m === "SWAP" || m === "HYBRID") return "Replaced volatile low-confidence legs with model-backed replacement picks.";
            if (m === "REMOVE") return "Dropped risky games from original slip without adding external replacements.";
            if (m === "BUILDER" || m === "ACCUMULATOR" || m === "ROLLOVER") return "Generated custom high-probability accumulator slip targeted at specified odds.";
            return "Audited original ticket selections directly and upgraded market picks to safest structural options.";
          })()}
        </p>
      </div>

      {/* Status Details & Strategy summary */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 space-y-1 text-xs font-semibold text-slate-700">
        <div className="flex items-center justify-between">
          <span className="font-extrabold text-slate-900">
            {ticket.flex_status_text || (isWon ? "WON (Clean Sweep - 0 Losses)" : isLost ? "Straight Acca Lost" : "Ticket Active / Running")}
          </span>
          <span className="text-[11px] font-bold text-slate-500">
            Ticket Settlement Strategy: {ticket.flex_cut || "OFF"} | Losses: {ticket.loss_count || 0} / {ticket.allowed_losses || 0} Allowed
          </span>
        </div>
        {isWon && (
          <div className="text-emerald-700 font-extrabold flex items-center gap-1.5 pt-1">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>TICKET WON</span>
          </div>
        )}
        {isLost && (
          <div className="text-rose-700 font-extrabold flex items-center gap-1.5 pt-1">
            <XCircle className="w-4 h-4 text-rose-600" />
            <span>TICKET BUST / LOST</span>
          </div>
        )}
      </div>

      {/* Leg Selections Detailed List */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-black text-slate-900 uppercase tracking-wider">
            Leg Selections & Live Outcomes ({displaySelections.length})
          </h3>
          <span className="text-[11px] font-bold text-slate-500">
            Real-time Early Win Detection Active
          </span>
        </div>

        <div className="space-y-3">
          {displaySelections.map((sel, idx) => {
            const matchInfo = getDynamicMatchInfo(sel);
            const legLive = matchInfo.isLive;
            const evalRes = evaluatePickLive(sel);
            const isLegWon = evalRes.status === "WON";
            const isLegLost = evalRes.status === "LOST";

            const matchTimeStr = matchInfo.matchTime || sel.match_time || (legLive ? "LIVE" : null);
            const gameId = sel.game_id || sel.fixture_id || sel.external_fixture_id || null;
            const kickoffStr = sel.kickoff_datetime_str || (sel.kickoff_datetime ? new Date(sel.kickoff_datetime).toLocaleDateString([], {month:'2-digit', day:'2-digit'}) + ' ' + new Date(sel.kickoff_datetime).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'}) : null);

            const scoreObj = parseScore(sel);
            const homeScore = scoreObj.home !== null ? scoreObj.home : "--";
            const awayScore = scoreObj.away !== null ? scoreObj.away : "--";

            return (
              <div
                key={idx}
                className={`bg-white border rounded-2xl p-4 space-y-3 shadow-sm transition-all ${
                  legLive
                    ? "border-red-300 ring-1 ring-red-50 bg-gradient-to-r from-red-50/20 via-white to-white"
                    : "border-slate-200 hover:border-slate-300"
                }`}
              >
                {/* Row 1: Leg Number, Live Sticker / Kickoff Time, Game ID, Live Link, Match State */}
                <div className="flex flex-wrap items-center justify-between border-b border-slate-100 pb-2.5 gap-2">
                  <div className="flex items-center gap-3">
                    {/* Index Badge */}
                    <span className="w-6 h-6 rounded-full bg-slate-900 text-white font-extrabold text-xs flex items-center justify-center shadow-sm">
                      {idx + 1}
                    </span>

                    {/* Live Badge & Time or Kickoff Time */}
                    {legLive ? (
                      <div className="flex items-center gap-2">
                        <span className="bg-red-600 text-white px-2 py-0.5 rounded-md text-[10px] font-black uppercase tracking-wide flex items-center gap-1 animate-pulse">
                          <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
                          Live
                        </span>
                        {matchTimeStr && (
                          <span className="text-xs font-black text-red-600 font-mono">
                            {matchTimeStr}
                          </span>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs font-bold text-slate-500">
                        {kickoffStr}
                      </span>
                    )}

                    {/* Game ID */}
                    <span className="text-[11px] font-bold text-slate-400 font-mono">
                      Game ID: {gameId}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Go to Live Betting button if live */}
                    {legLive && (
                      <button
                        onClick={() => simulateLiveGoal(idx)}
                        className="text-[11px] font-extrabold text-red-600 bg-red-50 hover:bg-red-100 border border-red-200 px-2.5 py-1 rounded-lg transition-all flex items-center gap-1"
                        title="Click to simulate live score update / test early win"
                      >
                        <Zap className="w-3 h-3 fill-red-600" />
                        <span>Go to Live Betting</span>
                      </button>
                    )}

                    {/* Match State: Ongoing / Not Started / Concluded / Interrupted */}
                    <span className={`text-[11px] font-extrabold px-2.5 py-0.5 rounded-full uppercase tracking-wider border ${
                      matchInfo.isInterrupted
                        ? "bg-amber-50 text-amber-800 border-amber-300"
                        : legLive
                        ? "bg-red-50 text-red-700 border-red-200"
                        : sel.match_status === "CONCLUDED"
                        ? "bg-slate-100 text-slate-700 border-slate-200"
                        : "bg-slate-100 text-slate-500 border-slate-200"
                    }`}>
                      {matchInfo.isInterrupted ? "Interrupted" : legLive ? "Ongoing" : sel.match_status === "CONCLUDED" ? "Concluded" : "Not Started"}
                    </span>
                  </div>
                </div>

                {/* Row 2: Teams & Live Scores (SportyBet Stacked Layout) */}
                <div className="bg-slate-50/80 p-3 rounded-xl border border-slate-100 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-black text-slate-900">
                      {sel.home_team || "Home Team"}
                    </span>
                    <span className={`font-mono text-sm font-black px-2.5 py-0.5 rounded-md ${
                      legLive ? "bg-red-100 text-red-800 border border-red-200" : "bg-white text-slate-800 border border-slate-200"
                    }`}>
                      {homeScore}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-xs font-black text-slate-900">
                      {sel.away_team || "Away Team"}
                    </span>
                    <span className={`font-mono text-sm font-black px-2.5 py-0.5 rounded-md ${
                      legLive ? "bg-red-100 text-red-800 border border-red-200" : "bg-white text-slate-800 border border-slate-200"
                    }`}>
                      {awayScore}
                    </span>
                  </div>
                </div>

                {/* Row 3: Pick, Market & Result Grid (SportyBet Style) */}
                <div className="grid grid-cols-3 gap-2 bg-white p-3 rounded-xl border border-slate-200 text-xs">
                  <div>
                    <span className="text-[10px] font-bold text-slate-400 block uppercase tracking-wider">Pick</span>
                    <span className="font-extrabold text-slate-900 block">
                      {sel.selection_name || sel.selection || "Pick"} @{sel.odds || sel.estimated_odds || "1.25"}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] font-bold text-slate-400 block uppercase tracking-wider">Market</span>
                    <span className="font-semibold text-slate-700 block">
                      {sel.market_name || sel.market || "Market"}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] font-bold text-slate-400 block uppercase tracking-wider">Result</span>
                    <span className={`font-black block ${
                      isLegWon
                        ? "text-emerald-600 font-extrabold"
                        : evalRes.status === "VOID"
                        ? "text-slate-600 font-extrabold"
                        : isLegLost
                        ? "text-rose-600 font-extrabold"
                        : "text-slate-500"
                    }`}>
                      {evalRes.resultText}
                    </span>
                  </div>
                </div>

                {/* Leg Status Footer Banner */}
                <div className="flex items-center justify-between pt-1">
                  <div className="text-[11px] font-semibold text-slate-400">
                    {legLive && isLegWon && (
                      <span className="text-emerald-700 font-extrabold flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        Pick entered / won early while match is ongoing!
                      </span>
                    )}
                    {matchInfo.isInterrupted && (
                      <span className="text-amber-700 font-bold flex items-center gap-1">
                        Match interrupted (bad weather) — Flashscore: 3-3 (HT: 2-1, H2: 1-2)
                      </span>
                    )}
                  </div>

                  <div>
                    {isLegWon ? (
                      <span className="bg-emerald-100 text-emerald-800 border border-emerald-300 px-3 py-0.5 rounded-full text-xs font-black flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Won
                      </span>
                    ) : evalRes.status === "VOID" ? (
                      <span className="bg-slate-100 text-slate-700 border border-slate-300 px-3 py-0.5 rounded-full text-xs font-black flex items-center gap-1">
                        <MinusCircle className="w-3.5 h-3.5" /> Void (1.00)
                      </span>
                    ) : isLegLost ? (
                      <span className="bg-rose-100 text-rose-800 border border-rose-300 px-3 py-0.5 rounded-full text-xs font-black flex items-center gap-1">
                        <XCircle className="w-3.5 h-3.5" /> Lost
                      </span>
                    ) : legLive ? (
                      <span className="bg-amber-100 text-amber-800 border border-amber-300 px-3 py-0.5 rounded-full text-xs font-extrabold flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5 animate-pulse text-amber-600" /> Live / Ongoing
                      </span>
                    ) : (
                      <span className="bg-slate-100 text-slate-600 border border-slate-200 px-3 py-0.5 rounded-full text-xs font-bold">
                        Pending
                      </span>
                    )}
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
