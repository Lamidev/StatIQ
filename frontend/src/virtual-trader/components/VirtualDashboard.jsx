import React from "react";
import { Activity, ShieldCheck, Database, RefreshCw, Cpu, AlertTriangle } from "lucide-react";

export default function VirtualDashboard({ dashboardData, onRefresh, loading }) {
  if (!dashboardData && loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="w-8 h-8 text-emerald-500 animate-spin" />
        <span className="ml-3 text-sm font-bold text-slate-600">Connecting to Virtual Trader Agent...</span>
      </div>
    );
  }

  const {
    agent_mode = "RESEARCH",
    kill_switch_active = false,
    worker_health = {},
    data_warehouse = {},
    bankroll = {},
    recent_logs = []
  } = dashboardData || {};

  const isOnline = worker_health.status === "ONLINE";

  return (
    <div className="space-y-6">
      {/* Top Banner Status Bar */}
      <div className="bg-slate-900 text-white rounded-2xl p-5 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center space-x-3">
            <span className="text-xs font-black uppercase tracking-wider px-2.5 py-1 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              StatIQ Virtual Trader V1.0
            </span>
            <div className="flex items-center space-x-1.5">
              <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? "bg-emerald-400 animate-pulse" : "bg-rose-400"}`} />
              <span className="text-xs font-semibold text-slate-300">
                Agent Status: <strong className="text-white">{agent_mode}</strong>
              </span>
            </div>
          </div>
          <h2 className="text-lg font-black mt-2 tracking-tight">Autonomous Virtual Sports Intelligence Agent</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            SportyBet vFootball data collection, distribution analysis, and zero-leakage simulation engine.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {kill_switch_active && (
            <div className="flex items-center space-x-1.5 bg-rose-500/20 text-rose-300 border border-rose-500/30 px-3 py-1.5 rounded-xl text-xs font-black">
              <AlertTriangle className="w-4 h-4" />
              <span>KILL SWITCH ACTIVE</span>
            </div>
          )}
          <button
            onClick={onRefresh}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-bold text-slate-200 transition-all cursor-pointer border border-slate-700"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-emerald-400" : ""}`} />
            <span>Refresh State</span>
          </button>
        </div>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Data Warehouse */}
        <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Events Collected</span>
            <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <Database className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-black text-slate-900">{data_warehouse.total_events_collected || 0}</span>
            <span className="text-xs font-semibold text-slate-500">matches</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-medium">
            Across {data_warehouse.active_leagues_tracked || 5} virtual leagues
          </p>
        </div>

        {/* Odds Snapshots */}
        <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Odds Snapshots</span>
            <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
              <Activity className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-black text-slate-900">{data_warehouse.total_odds_snapshots || 0}</span>
            <span className="text-xs font-semibold text-slate-500">prices</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-medium">
            Polled every {worker_health.poll_interval_seconds || 10}s
          </p>
        </div>

        {/* Bankroll State */}
        <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Simulated Bankroll</span>
            <div className="w-7 h-7 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center">
              <ShieldCheck className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-black text-slate-900">
              ₦{(bankroll.balance || 100000).toLocaleString()}
            </span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-medium">
            Daily P/L: <strong className={bankroll.daily_profit_loss >= 0 ? "text-emerald-600" : "text-rose-600"}>
              {bankroll.daily_profit_loss >= 0 ? "+" : ""}₦{(bankroll.daily_profit_loss || 0).toLocaleString()}
            </strong>
          </p>
        </div>

        {/* Worker Health */}
        <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">Ingestion Daemon</span>
            <div className="w-7 h-7 rounded-lg bg-teal-50 text-teal-600 flex items-center justify-center">
              <Cpu className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-xl font-black text-emerald-600">{worker_health.status || "ONLINE"}</span>
          </div>
          <p className="text-[11px] text-slate-500 mt-1 font-medium">
            Total sync ticks: <strong>{worker_health.total_runs || 0}</strong>
          </p>
        </div>
      </div>

      {/* Subsystem Health Grid */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-2xs">
        <h3 className="text-sm font-black text-slate-900 tracking-tight mb-4 flex items-center space-x-2">
          <Activity className="w-4 h-4 text-emerald-600" />
          <span>Virtual Trader Subsystem Status</span>
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { name: "Data Ingestion", status: isOnline ? "ONLINE" : "STANDBY", color: "emerald" },
            { name: "Odds Tracker", status: isOnline ? "ONLINE" : "STANDBY", color: "emerald" },
            { name: "Research Engine", status: "RESEARCHING", color: "indigo" },
            { name: "Prediction Engine", status: "PHASE 3", color: "slate" },
            { name: "Paper Trader", status: "PHASE 5", color: "slate" },
            { name: "Live Execution", status: "DISABLED (FLAG)", color: "amber" },
          ].map((sub, idx) => (
            <div key={idx} className="bg-slate-50 rounded-xl p-3 border border-slate-100 flex flex-col justify-between">
              <span className="text-[11px] font-bold text-slate-600">{sub.name}</span>
              <div className="mt-2 flex items-center space-x-1.5">
                <span className={`w-2 h-2 rounded-full bg-${sub.color}-500`} />
                <span className="text-[10px] font-black text-slate-900">{sub.status}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
