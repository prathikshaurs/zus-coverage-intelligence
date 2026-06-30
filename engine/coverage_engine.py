"""
Coverage Intelligence Engine:
Turns raw retrieval facts into the metrics, anomalies, and narratives
  - coverage by geography, network, data type, and customer
  - gap + anomaly detection with root-cause hypotheses
  - regular "coverage intelligence" a customer can read and act on
"""

from __future__ import annotations
import json
import numpy as np
import pandas as pd


class CoverageEngine:
    def __init__(self, coverage: pd.DataFrame, adt: pd.DataFrame | None = None,
                 meta: dict | None = None):
        self.cov = coverage.copy()
        self.adt = adt.copy() if adt is not None else None
        self.meta = meta or {}

    # core metric: coverage rate = share of (upid x net x type) retrieved
    def _rate(self, df):
        if len(df) == 0:
            return 0.0
        return round(100 * df["retrieved"].mean(), 1)

    def overall(self) -> dict:
        c = self.cov
        retrieved = c[c["retrieved"]]
        return {
            "humans": int(c["upid"].nunique()),
            "coverage_rate": self._rate(c),
            "median_latency_min": int(retrieved["latency_min"].median()),
            "p90_latency_min": int(retrieved["latency_min"].quantile(0.90)),
            "timeout_rate": round(100 * c["timed_out"].mean(), 1),
            "thin_payload_rate": round(100 * c["thin_payload"].mean(), 2),
            "total_pulls": int(len(c)),
        }

    def by(self, dimension: str) -> pd.DataFrame:
        # Coverage broken out by a single dimension
        c = self.cov
        g = c.groupby(dimension)
        out = pd.DataFrame({
            "coverage_rate": g.apply(lambda d: self._rate(d), include_groups=False),
            "pulls": g.size(),
            "timeout_rate": (100 * g["timed_out"].mean()).round(1),
            "median_latency_min": g.apply(
                lambda d: d.loc[d["retrieved"], "latency_min"].median()
                if d["retrieved"].any() else np.nan, include_groups=False),
            "avg_resources": g.apply(
                lambda d: d.loc[d["retrieved"], "n_resources"].mean()
                if d["retrieved"].any() else 0, include_groups=False).round(1),
        }).reset_index().sort_values("coverage_rate")
        return out

    def matrix(self, row: str, col: str, value: str = "coverage_rate") -> pd.DataFrame:
        # Pivot coverage across two dimensions (eg: state x network)
        c = self.cov
        if value == "coverage_rate":
            piv = c.pivot_table(index=row, columns=col, values="retrieved",
                                aggfunc="mean")
            return (piv * 100).round(1)
        piv = c.pivot_table(index=row, columns=col, values=value, aggfunc="mean")
        return piv.round(1)

    # anomaly detection: where is coverage materially below expectation?
    def detect_anomalies(self, dimension_pair=("state", "network"),
                         min_pulls=150, z_threshold=2.0) -> pd.DataFrame:
        """
        For each cell in a 2-D breakout, comparing its coverage rate to the
        expected rate for that network (the network's own mean across cells), and 
        flag cells that fall a meaningful number of std-devs below expectation
        """
        row, col = dimension_pair
        c = self.cov
        cells = (c.groupby([row, col])
                   .agg(coverage_rate=("retrieved", "mean"),
                        pulls=("retrieved", "size"),
                        timeout_rate=("timed_out", "mean"),
                        thin_rate=("thin_payload", "mean"))
                   .reset_index())
        cells["coverage_rate"] *= 100
        cells["timeout_rate"] *= 100
        cells["thin_rate"] *= 100

        # expected = mean coverage for that column value (e.g. that network)
        col_stats = cells.groupby(col)["coverage_rate"].agg(["mean", "std"]).rename(
            columns={"mean": "expected_rate", "std": "col_std"})
        cells = cells.merge(col_stats, on=col, how="left")
        cells["col_std"] = cells["col_std"].replace(0, np.nan).fillna(
            cells["coverage_rate"].std())
        cells["delta"] = (cells["coverage_rate"] - cells["expected_rate"]).round(1)
        cells["z"] = ((cells["coverage_rate"] - cells["expected_rate"])
                      / cells["col_std"]).round(2)

        flagged = cells[(cells["pulls"] >= min_pulls) &
                        (cells["z"] <= -z_threshold)].copy()
        flagged = flagged.sort_values("z")
        return flagged

    # root cause narrative generation
    def narrate(self, anomalies: pd.DataFrame,
                dimension_pair=("state", "network")) -> list[dict]:
        """
        Translating each flagged anomaly into a plain-English narrative with a
        hypothesis and a recommended operational action
        """
        row, col = dimension_pair
        out = []
        for _, a in anomalies.iterrows():
            cell = self.cov[(self.cov[row] == a[row]) & (self.cov[col] == a[col])]
            timeout = a["timeout_rate"]
            thin = a["thin_rate"]

            # hypothesis selection
            if timeout > 12:
                hypo = (f"Elevated timeouts ({timeout:.0f}% vs network norm) point to a "
                        f"connectivity or responder-latency problem at {a[col]} in {a[row]}, "
                        f"not a data-availability problem.")
                action = (f"Escalate to the network team to check {a[col]} responder health "
                          f"in {a[row]}; confirm endpoint is live and within SLA.")
                cat = "connectivity"
            elif thin > 5:
                hypo = (f"Records are being retrieved but arrive thin "
                        f"({thin:.1f}% near-empty payloads), which usually signals a "
                        f"document-format or configuration issue at the source EHR.")
                action = ("Sample 10 thin DocumentReferences, confirm vendor, and open a "
                          "config ticket; add a parsing playbook entry.")
                cat = "configuration"
            else:
                hypo = (f"Coverage in {a[row]} via {a[col]} runs {abs(a['delta']):.0f} pts "
                        f"below the {a[col]} norm with normal latency, suggesting genuine "
                        f"network participation gaps for this geography or cohort.")
                action = (f"Flag {a[row]} coverage to the customer's solutions contact; "
                          f"evaluate adding a regional HIE to backfill {a[col]} gaps.")
                cat = "participation_gap"

            out.append({
                "scope": f"{a[row]} | {a[col]}",
                "coverage_rate": round(a["coverage_rate"], 1),
                "expected_rate": round(a["expected_rate"], 1),
                "delta_pts": round(a["delta"], 1),
                "z_score": round(a["z"], 2),
                "pulls": int(a["pulls"]),
                "category": cat,
                "hypothesis": hypo,
                "recommended_action": action,
            })
        return out

    # data-quality anomalies (non-geographic)
    def detect_quality_issues(self, thin_threshold=5.0, latency_mult=1.8) -> list[dict]:
        """
        Catch problems a geographic scan misses: data-type/network combinations
        that retrieve records but deliver poor quality (thin payloads) or run
        far slower than peers. Shows the same data investigated from a second angle.
        """
        c = self.cov
        out = []

        # 1) thin-payload hot spots by (network, data_type)
        retrieved = c[c["retrieved"]]
        thin = (retrieved.groupby(["network", "data_type"])
                .agg(thin_rate=("thin_payload", "mean"),
                     pulls=("thin_payload", "size"),
                     avg_resources=("n_resources", "mean"))
                .reset_index())
        thin["thin_rate"] *= 100
        for _, r in thin[thin["thin_rate"] >= thin_threshold].sort_values(
                "thin_rate", ascending=False).iterrows():
            out.append({
                "type": "thin_payload",
                "scope": f"{r['network']} | {r['data_type']}",
                "metric": f"{r['thin_rate']:.1f}% near-empty payloads",
                "pulls": int(r["pulls"]),
                "hypothesis": (f"{r['data_type']} records from {r['network']} are retrieved "
                               f"but {r['thin_rate']:.0f}% come back near-empty, a hallmark of a "
                               f"source EHR emitting malformed or stub documents."),
                "recommended_action": ("Pull a 10-record sample, identify the source vendor, "
                                       "open a configuration ticket, and codify a parsing "
                                       "playbook so the issue is caught at onboarding."),
            })

        # 2) latency outliers by network
        lat = (retrieved.groupby("network")["latency_min"].median()
               .reset_index(name="median_latency"))
        global_med = retrieved["latency_min"].median()
        for _, r in lat[lat["median_latency"] >= latency_mult * global_med].iterrows():
            out.append({
                "type": "latency_outlier",
                "scope": r["network"],
                "metric": f"median {int(r['median_latency'])}m vs {int(global_med)}m network-wide",
                "pulls": int((self.cov["network"] == r["network"]).sum()),
                "hypothesis": (f"{r['network']} responds far slower than peer networks, which "
                               f"delays chart-prep and time-sensitive workflows even when "
                               f"coverage is adequate."),
                "recommended_action": ("Confirm whether slow responders sit behind a single "
                                       "repository; consider pre-fetching for this network on "
                                       "high-priority cohorts."),
            })
        return out

    # ADT noise-to-signal summary
    def adt_signal(self) -> dict:
        if self.adt is None or len(self.adt) == 0:
            return {}
        a = self.adt
        total = len(a)
        dups = int(a["is_duplicate"].sum())
        missing_ctx = int(a["missing_clinical_context"].sum())
        actionable = a[(~a["is_duplicate"]) &
                       (a["event_type"].isin(["A01-Admit", "A03-Discharge"])) &
                       (~a["missing_clinical_context"])]
        return {
            "total_alerts": total,
            "duplicate_alerts": dups,
            "duplicate_rate": round(100 * dups / total, 1),
            "missing_context_rate": round(100 * missing_ctx / total, 1),
            "actionable_alerts": int(len(actionable)),
            "actionable_rate": round(100 * len(actionable) / total, 1),
            "noise_reduction_pts": round(100 * (1 - len(actionable) / total), 1),
        }

    # full report bundle (what a dashboard / API would consume)
    def build_report(self) -> dict:
        anomalies = self.detect_anomalies()
        report = {
            "overall": self.overall(),
            "by_customer": self.by("customer").to_dict(orient="records"),
            "by_network": self.by("network").to_dict(orient="records"),
            "by_data_type": self.by("data_type").to_dict(orient="records"),
            "by_state": self.by("state").to_dict(orient="records"),
            "by_age_band": self.by("age_band").to_dict(orient="records"),
            "state_network_matrix": self.matrix("state", "network").reset_index().to_dict(orient="records"),
            "datatype_network_matrix": self.matrix("data_type", "network").reset_index().to_dict(orient="records"),
            "anomalies": self.narrate(anomalies),
            "quality_issues": self.detect_quality_issues(),
            "adt_signal": self.adt_signal(),
            "meta": self.meta,
        }
        return report


def run(data_dir="data", out="dashboard/coverage_report.json"):
    cov = pd.read_csv(f"{data_dir}/coverage_facts.csv")
    adt = pd.read_csv(f"{data_dir}/adt_events.csv")
    with open(f"{data_dir}/meta.json") as f:
        meta = json.load(f)
    eng = CoverageEngine(cov, adt, meta)
    report = eng.build_report()
    with open(out, "w") as f:
        json.dump(report, f, indent=2, default=str)
    return report


if __name__ == "__main__":
    rep = run()
    o = rep["overall"]
    print(f"Coverage rate: {o['coverage_rate']}%  | median latency {o['median_latency_min']}m"
          f"  | timeouts {o['timeout_rate']}%")
    print(f"Anomalies flagged: {len(rep['anomalies'])}")
    for a in rep["anomalies"][:5]:
        print(f"  - {a['scope']}: {a['coverage_rate']}% (exp {a['expected_rate']}%, "
              f"{a['delta_pts']} pts, z={a['z_score']}) [{a['category']}]")
    print(f"Quality issues: {len(rep['quality_issues'])}")
    for q in rep["quality_issues"][:5]:
        print(f"  - [{q['type']}] {q['scope']}: {q['metric']}")
    s = rep["adt_signal"]
    print(f"ADT: {s['total_alerts']} alerts -> {s['actionable_alerts']} actionable "
          f"({s['noise_reduction_pts']}% noise removed)")
