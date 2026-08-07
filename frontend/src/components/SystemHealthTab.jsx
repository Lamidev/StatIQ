import React, { useState } from "react";
import { triggerReconciliation } from "../api/client";
import { CheckCircle2, RefreshCw } from "lucide-react";

export default function SystemHealthTab({ healthStatus, driftReport, onRefresh }) {
  const [reconciling, setReconciling] = useState(false);
  const [reconRes, setReconRes] = useState(null);

  const handleReconcile = async () => {
    setReconciling(true);
    const data = await triggerReconciliation();
    setReconRes(data);
    setReconciling(false);
    if (onRefresh) onRefresh();
  };

  return (
    <div className="space-y-6">
      {/* Title Header */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-slate-900">
            System Reliability & Match Reconciliation
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            Audits database health and reconciles completed match scores against pre-kickoff predictions.
          </p>
        </div>

        <button
          onClick={handleReconcile}
          disabled={reconciling}
          className="px-4 py-2 rounded-xl btn-black text-xs font-bold flex items-center justify-center space-x-2 self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${reconciling ? "animate-spin" : ""}`} />
          <span>{reconciling ? "Reconciling..." : "Run Reconciliation"}</span>
        </button>
      </div>

      {reconRes && (
        <div className="bg-emerald-50 border border-emerald-200 p-4 rounded-2xl flex items-center justify-between text-xs text-emerald-800 font-bold">
          <div className="flex items-center space-x-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>Reconciled {reconRes.reconciled_count} finished match outcomes!</span>
          </div>
          <span>Accuracy: {reconRes.accuracy_pct}%</span>
        </div>
      )}

      {/* Metrics Summary */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-2">
          <span className="text-xs text-slate-400 font-semibold block">Pipeline Status</span>
          <span className="text-xl font-extrabold text-emerald-600 uppercase">
            {healthStatus?.pipeline_status || "HEALTHY"}
          </span>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-2">
          <span className="text-xs text-slate-400 font-semibold block">Rolling 30-Day Status</span>
          <span className="text-xl font-extrabold text-slate-900 uppercase">
            {driftReport?.rolling_30_days?.status || "STABLE"}
          </span>
        </div>

        <div className="bg-white p-6 rounded-2xl border border-slate-200 space-y-2">
          <span className="text-xs text-slate-400 font-semibold block">Rolling 90-Day Status</span>
          <span className="text-xl font-extrabold text-slate-900 uppercase">
            {driftReport?.rolling_90_days?.status || "STABLE"}
          </span>
        </div>
      </div>
    </div>
  );
}
