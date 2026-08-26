import React, { useState } from "react";
import { Zap, BarChart3, Radio, ShieldAlert, Bot } from "lucide-react";
import VirtualFrontTesting from "./components/VirtualFrontTesting";
import VirtualCockpit from "./components/VirtualCockpit";
import VirtualBacktest from "./components/VirtualBacktest";
import VirtualLiveMonitor from "./components/VirtualLiveMonitor";
import VirtualRiskEngine from "./components/VirtualRiskEngine";

export default function VirtualTraderApp() {
  const [activeTab, setActiveTab] = useState("fronttest");

  const navItems = [
    { id: "fronttest", label: "🤖 24/7 Front-Tester & Telegram", icon: Bot, description: "Automated 2.0x tickets, Telegram signals & win rate audit" },
    { id: "cockpit", label: "⚡ Live Picks & Bankroll", icon: Zap, description: "Upcoming picks, bankroll & active bets" },
    { id: "backtest", label: "📊 Historical Backtest", icon: BarChart3, description: "585 match historical replay & ROI" },
    { id: "monitor", label: "📡 Live vFootball Stream", icon: Radio, description: "Raw upcoming SportyBet odds" },
    { id: "risk", label: "🛡️ Risk Controls & Kelly", icon: ShieldAlert, description: "Drawdown protection & stake limits" },
  ];

  return (
    <div className="space-y-6">
      {/* Streamlined Clean Navigation Bar */}
      <div className="flex items-center space-x-2 border-b border-slate-200 pb-3 overflow-x-auto no-scrollbar">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`flex items-center space-x-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all whitespace-nowrap ${
                isActive
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>

      {/* Clean Tab Views */}
      {activeTab === "fronttest" && <VirtualFrontTesting />}
      {activeTab === "cockpit" && <VirtualCockpit />}
      {activeTab === "backtest" && <VirtualBacktest />}
      {activeTab === "monitor" && <VirtualLiveMonitor />}
      {activeTab === "risk" && <VirtualRiskEngine />}
    </div>
  );
}


