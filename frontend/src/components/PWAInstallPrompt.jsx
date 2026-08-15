import React, { useState, useEffect } from "react";
import { Download, X, Activity, Share, PlusSquare } from "lucide-react";

export default function PWAInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [isIOS, setIsIOS] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  const [isDismissed, setIsDismissed] = useState(false);

  useEffect(() => {
    // Check if already in standalone PWA mode
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone;
    if (isStandalone) return;

    // Detect iOS
    const userAgent = window.navigator.userAgent.toLowerCase();
    const isIosDevice = /iphone|ipad|ipod/.test(userAgent);
    setIsIOS(isIosDevice);

    const handleBeforeInstall = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setShowPrompt(true);
    };

    window.addEventListener("beforeinstallprompt", handleBeforeInstall);

    // If iOS and not dismissed, show prompt after 3 seconds
    if (isIosDevice && !localStorage.getItem("statiq_pwa_dismissed")) {
      const timer = setTimeout(() => setShowPrompt(true), 3000);
      return () => clearTimeout(timer);
    }

    return () => {
      window.removeEventListener("beforeinstallprompt", handleBeforeInstall);
    };
  }, []);

  const handleInstallClick = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") {
      setShowPrompt(false);
    }
    setDeferredPrompt(null);
  };

  const handleDismiss = () => {
    setShowPrompt(false);
    setIsDismissed(true);
    localStorage.setItem("statiq_pwa_dismissed", "true");
  };

  if (!showPrompt || isDismissed) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 sm:left-auto sm:right-6 sm:max-w-sm z-50 animate-in fade-in slide-in-from-bottom-5 duration-200">
      <div className="bg-slate-900 text-white p-4 rounded-2xl shadow-2xl border border-slate-800 flex items-start gap-3 relative">
        <div className="w-10 h-10 rounded-xl bg-slate-800 text-emerald-400 flex items-center justify-center shrink-0 border border-slate-700">
          <Activity className="w-5 h-5" />
        </div>

        <div className="flex-1 min-w-0 pr-6">
          <h4 className="text-xs font-black tracking-tight text-white flex items-center gap-1.5">
            <span>Install StatIQ App</span>
            <span className="bg-emerald-500/20 text-emerald-300 text-[9px] px-1.5 py-0.2 rounded font-bold uppercase">
              PWA
            </span>
          </h4>
          <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">
            {isIOS
              ? "Tap the Share button below, then tap 'Add to Home Screen' to install."
              : "Install StatIQ on your mobile home screen for 1-tap launch & live alerts."}
          </p>

          <div className="mt-2.5 flex items-center gap-2">
            {!isIOS && deferredPrompt ? (
              <button
                onClick={handleInstallClick}
                className="bg-emerald-500 hover:bg-emerald-400 text-slate-950 px-3 py-1.5 rounded-xl text-xs font-extrabold flex items-center gap-1.5 transition-all shadow-sm cursor-pointer active:scale-95"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Install Now</span>
              </button>
            ) : isIOS ? (
              <div className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2 py-1 rounded-lg">
                <Share className="w-3 h-3" />
                <span>Share</span>
                <span>→</span>
                <PlusSquare className="w-3 h-3" />
                <span>Add to Home</span>
              </div>
            ) : null}

            <button
              onClick={handleDismiss}
              className="text-[11px] font-bold text-slate-400 hover:text-white px-2 py-1 rounded-lg transition-colors cursor-pointer"
            >
              Maybe Later
            </button>
          </div>
        </div>

        <button
          onClick={handleDismiss}
          className="absolute top-3 right-3 text-slate-400 hover:text-white p-1 rounded-lg transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
