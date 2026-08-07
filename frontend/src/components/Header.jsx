import React from "react";
import { Activity, Calendar, Target, Search, FlaskConical, CheckCircle2, Receipt } from "lucide-react";

export default function Header({ activeTab, setActiveTab }) {
  const tabs = [
    { id: "fixtures", label: "1. Match Fixtures", icon: Calendar },
    { id: "builder", label: "2. AI Ticket Builder", icon: Target },
    { id: "auditor", label: "3. Ticket Auditor & Re-Editor", icon: Search },
    { id: "history", label: "4. Tickets / Bet History", icon: Receipt },
    { id: "backtester", label: "5. Backtest Simulator", icon: FlaskConical },
  ];

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-slate-900 flex items-center justify-center text-white">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <span className="text-lg font-extrabold text-slate-900 tracking-tight">
                StatIQ
              </span>
              <span className="text-xs text-slate-500 block -mt-1 font-medium">
                AI Football Prediction Engine
              </span>
            </div>
          </div>

          {/* System Status Pill */}
          <div className="flex items-center space-x-2 bg-emerald-50 text-emerald-700 border border-emerald-200 px-3 py-1 rounded-full text-xs font-semibold">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>AI Brain Ready</span>
          </div>
        </div>

        {/* 4 Clean Categorized Navigation Tabs */}
        <div className="flex space-x-2 overflow-x-auto py-2 border-t border-slate-100">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-xs font-extrabold whitespace-nowrap transition-all ${
                  isActive
                    ? "bg-slate-900 text-white shadow-sm"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? "text-white" : "text-slate-500"}`} />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </header>
  );
}
