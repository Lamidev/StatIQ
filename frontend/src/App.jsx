import React, { useState } from "react";
import Header from "./components/Header";
import GameweekFixturesTab from "./components/GameweekFixturesTab";
import TicketBuilderTab from "./components/TicketBuilderTab";
import BetSlipAuditorTab from "./components/BetSlipAuditorTab";
import BetHistoryTab from "./components/BetHistoryTab";
import BacktesterTab from "./components/BacktesterTab";

export default function App() {
  const [activeTab, setActiveTab] = useState("fixtures");

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900 font-sans">
      {/* Clean Categorized Navigation Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
      />

      {/* Main View Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === "fixtures" && <GameweekFixturesTab />}
        {activeTab === "builder" && <TicketBuilderTab />}
        {activeTab === "auditor" && <BetSlipAuditorTab onNavigateHistory={() => setActiveTab("history")} />}
        {activeTab === "history" && <BetHistoryTab />}
        {activeTab === "backtester" && <BacktesterTab />}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-200 py-6 bg-white">
        <div className="max-w-7xl mx-auto px-4 text-center text-xs text-slate-500 flex flex-col sm:flex-row items-center justify-between gap-2 font-medium">
          <span>StatIQ © 2026 — AI Football Prediction & Intelligence Platform</span>
          <div className="flex items-center space-x-4">
            <span className="text-slate-900 font-bold">Weighted Ensemble v1.0.0</span>
            <span>•</span>
            <span>Temperature T = 2.1216</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
