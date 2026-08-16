import React, { useState, useEffect, useRef } from "react";
import { Bell, Trophy, CheckCheck, Trash2, ChevronRight, X } from "lucide-react";
import { fetchNotificationsList, markNotificationRead, clearAllNotifications } from "../api/client";

export default function NotificationDropdown({ onSelectTicket }) {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const dropdownRef = useRef(null);

  const fetchNotifications = async () => {
    try {
      const data = await fetchNotificationsList();
      setNotifications(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch (e) {
      console.error("Failed to fetch notifications:", e);
    }
  };

  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 15000);
    return () => clearInterval(interval);
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleMarkAllRead = async (e) => {
    e.stopPropagation();
    try {
      const data = await markNotificationRead({ all: true });
      if (data) {
        setNotifications(data.notifications || []);
        setUnreadCount(0);
      }
    } catch (err) {
      console.error("Failed to mark all read:", err);
    }
  };

  const handleClearAll = async (e) => {
    e.stopPropagation();
    try {
      await clearAllNotifications();
      setNotifications([]);
      setUnreadCount(0);
    } catch (err) {
      console.error("Failed to clear notifications:", err);
    }
  };

  const handleItemClick = async (item) => {
    if (!item.read) {
      try {
        await markNotificationRead({ id: item.id });
        setNotifications((prev) =>
          prev.map((n) => (n.id === item.id ? { ...n, read: true } : n))
        );
        setUnreadCount((prev) => Math.max(0, prev - 1));
      } catch (e) {
        // silent catch
      }
    }
    setIsOpen(false);
    if (onSelectTicket && (item.ticket_id || item.code)) {
      onSelectTicket(item.ticket_id || item.code);
    }
  };


  return (
    <div className="relative inline-block text-left" ref={dropdownRef}>
      {/* Bell Trigger Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-all focus:outline-none"
        title="Win Alerts & Ticket Notifications"
      >
        <Bell className="w-5 h-5" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-emerald-600 text-white text-[10px] font-black flex items-center justify-center shadow-sm animate-pulse border border-white">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* Popover Menu */}
      {isOpen && (
        <div className="origin-top-right absolute right-0 mt-2 w-80 sm:w-96 rounded-2xl bg-white shadow-2xl border border-slate-200 z-50 overflow-hidden divide-y divide-slate-100 animate-in fade-in slide-in-from-top-2 duration-200">
          {/* Header Bar */}
          <div className="p-4 bg-slate-900 text-white flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Trophy className="w-5 h-5 text-amber-400" />
              <span className="font-extrabold text-sm tracking-tight">Win Notifications</span>
              {unreadCount > 0 && (
                <span className="bg-emerald-500 text-white text-[10px] font-extrabold px-2 py-0.5 rounded-full">
                  {unreadCount} new
                </span>
              )}
            </div>
            <div className="flex items-center space-x-2">
              {notifications.length > 0 && (
                <>
                  <button
                    onClick={handleMarkAllRead}
                    className="text-slate-300 hover:text-white text-xs font-semibold flex items-center space-x-1 transition-colors"
                    title="Mark all as read"
                  >
                    <CheckCheck className="w-3.5 h-3.5" />
                    <span className="hidden sm:inline">Read all</span>
                  </button>
                  <button
                    onClick={handleClearAll}
                    className="text-slate-400 hover:text-rose-400 text-xs font-semibold p-1 transition-colors"
                    title="Clear all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </>
              )}
              <button
                onClick={() => setIsOpen(false)}
                className="text-slate-400 hover:text-white p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Notifications List */}
          <div className="max-h-80 overflow-y-auto divide-y divide-slate-100 bg-slate-50/50">
            {notifications.length === 0 ? (
              <div className="p-8 text-center text-slate-400 flex flex-col items-center">
                <Bell className="w-8 h-8 mb-2 stroke-1 opacity-50" />
                <p className="text-xs font-semibold">No notifications yet</p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Winning tickets will alert here in real time.
                </p>
              </div>
            ) : (
              notifications.map((item) => (
                <div
                  key={item.id}
                  onClick={() => handleItemClick(item)}
                  className={`p-3.5 flex items-start space-x-3 cursor-pointer transition-all hover:bg-slate-100 ${
                    !item.read ? "bg-emerald-50/60 border-l-4 border-emerald-500" : "bg-white"
                  }`}
                >
                  <div className="p-2 rounded-xl bg-emerald-100 text-emerald-700 flex-shrink-0 mt-0.5">
                    <Trophy className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-900 truncate">
                        {item.title}
                      </span>
                      <span className="text-[10px] text-slate-400 font-medium whitespace-nowrap ml-2">
                        {item.created_at ? item.created_at.split(" ")[1] || item.created_at : ""}
                      </span>
                    </div>
                    <p className="text-[11px] font-semibold text-emerald-700 mt-0.5">
                      {item.message}
                    </p>
                    <div className="flex items-center justify-between mt-1.5 text-[10px] text-slate-500 font-medium">
                      <span className="font-extrabold text-indigo-900 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200 uppercase">
                        Feature: {item.mode || "AUDITOR"} Mode
                      </span>
                      <span className="text-slate-700 font-bold flex items-center space-x-1">
                        <span>Click to view ticket</span>
                        <ChevronRight className="w-3 h-3 text-slate-400" />
                      </span>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
