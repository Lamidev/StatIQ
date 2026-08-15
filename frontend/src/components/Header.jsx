import React, { useState } from "react";
import { Activity, Calendar, Target, Search, FlaskConical, CheckCircle2, Receipt, Key } from "lucide-react";
import NotificationDropdown from "./NotificationDropdown";
import PasskeyAdminModal from "./PasskeyAdminModal";
import { getUserProfileId } from "../api/client";

export default function Header({ activeTab, setActiveTab, activeTicketCount = 0, activeGameCount = 0, onSelectTicket, currentUser }) {
  const [isPasskeyModalOpen, setIsPasskeyModalOpen] = useState(false);
  const currentPid = currentUser?.key || getUserProfileId();
  const userRole = currentUser?.role || "ADMIN";

  const tabs = [
    { id: "fixtures", label: "1. Match Fixtures", icon: Calendar },
    { id: "builder", label: "2. AI Ticket Builder", icon: Target },
    { id: "auditor", label: "3. Ticket Auditor & Re-Editor", icon: Search },
    { id: "history", label: "4. Tickets / Bet History", icon: Receipt },
    { id: "backtester", label: "5. Backtest Simulator", icon: FlaskConical },
    { id: "access", label: "6. Access Control & Keys", icon: Key },
  ];

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center space-x-2.5 sm:space-x-3">
            <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-slate-900 flex items-center justify-center text-white shrink-0 shadow-sm">
              <Activity className="w-4 h-4 sm:w-5 sm:h-5 text-emerald-400" />
            </div>
            <div>
              <span className="text-base sm:text-lg font-black text-slate-900 tracking-tight leading-none block">
                StatIQ
              </span>
              <span className="text-[10px] sm:text-xs text-slate-500 font-medium block mt-0.5">
                AI Football Engine
              </span>
            </div>
          </div>

          {/* Right Header Actions: Status Pill & Notifications */}
          <div className="flex items-center space-x-2">
            <div className="hidden sm:flex items-center space-x-1.5 bg-emerald-50 text-emerald-800 border border-emerald-200 px-3 py-1 rounded-full text-xs font-bold shadow-2xs">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span>AI Brain Ready</span>
            </div>

            {/* Notification Bell Dropdown */}
            <NotificationDropdown onSelectTicket={onSelectTicket} />
          </div>
        </div>

        {/* Passkey & Access Manager Modal */}
        <PasskeyAdminModal isOpen={isPasskeyModalOpen} onClose={() => setIsPasskeyModalOpen(false)} />

        {/* Navigation Tabs Bar */}
        <div className="flex space-x-1.5 sm:space-x-2 overflow-x-auto py-2 border-t border-slate-100 no-scrollbar touch-pan-x">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center space-x-1.5 px-3 py-1.5 sm:px-4 sm:py-2 rounded-xl text-[11px] sm:text-xs font-extrabold whitespace-nowrap transition-all relative flex-shrink-0 ${
                  isActive
                    ? "bg-slate-900 text-white shadow-sm"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                <Icon className={`w-3.5 h-3.5 sm:w-4 sm:h-4 ${isActive ? "text-white" : "text-slate-500"}`} />
                <span>{tab.label}</span>

                {tab.id === "history" && activeTicketCount > 0 && (
                  <span className="min-w-[18px] h-4.5 px-1 rounded-full bg-emerald-600 text-white text-[10px] font-black flex items-center justify-center shadow-sm">
                    {activeTicketCount}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </header>

  );
}
