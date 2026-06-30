"""
investigation.py -  a worked coverage investigation

This walks one real investigation end to end
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

import pandas as pd
from coverage_engine import CoverageEngine

pd.set_option("display.width", 120)
pd.set_option("display.max_columns", 20)

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def rule(title):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def main():
    cov = pd.read_csv(f"{DATA}/coverage_facts.csv")
    adt = pd.read_csv(f"{DATA}/adt_events.csv")
    eng = CoverageEngine(cov, adt)

    rule("STEP 1 - Start with the headline number")
    o = eng.overall()
    print(f"Network-wide coverage is {o['coverage_rate']}% across {o['humans']:,} humans.")
    print(f"Median latency {o['median_latency_min']}m, timeout rate {o['timeout_rate']}%.")
    print("A single headline never tells you where the problem is. Break it down.")

    rule("STEP 2 - Break coverage down by network")
    by_net = eng.by("network")[["network", "coverage_rate", "median_latency_min", "timeout_rate"]]
    print(by_net.to_string(index=False))
    worst = by_net.iloc[0]
    print(f"\n-> {worst['network']} is the weakest network at {worst['coverage_rate']}%, "
          f"and its latency is high too. Worth a closer look, but network-level")
    print("   averages can hide a geographic problem. Pivot against geography.")

    rule("STEP 3 - Pivot network x geography to localize it")
    m = eng.matrix("state", "network")
    print(m.to_string())
    print("\n-> Scan the QHIN-eHX column. One cell is dramatically lower than the rest.")

    rule("STEP 4 - Let the anomaly engine confirm what the eye caught")
    anomalies = eng.detect_anomalies()
    print(anomalies[["state", "network", "coverage_rate", "expected_rate",
                     "delta", "z", "timeout_rate", "pulls"]].to_string(index=False))
    top = anomalies.iloc[0]
    print(f"\n-> {top['state']} on {top['network']}: {top['coverage_rate']:.1f}% against an "
          f"expected {top['expected_rate']:.1f}% (z = {top['z']}).")
    print("   That is not noise. That is a real, localized shortfall.")

    rule("STEP 5 - Separate the 'why': availability vs connectivity vs config")
    narrated = eng.narrate(anomalies.head(1))
    n = narrated[0]
    print(f"Scope:    {n['scope']}")
    print(f"Category: {n['category']}")
    print(f"Why:      {n['hypothesis']}")
    print(f"Action:   {n['recommended_action']}")

    rule("STEP 6 - Check a second failure mode the geographic scan can miss")
    print("Coverage can look fine while the records that DO come back are unusable.")
    for q in eng.detect_quality_issues():
        print(f"  [{q['type']:15s}] {q['scope']:30s}  {q['metric']}")
    print("\n-> Thin-payload DocumentReferences across multiple networks point at a")
    print("   source-side document/config issue, not a Zus-side retrieval issue.")

    rule("STEP 7 - Quantify the ADT noise the same population generates")
    s = eng.adt_signal()
    print(f"Raw alerts:        {s['total_alerts']:,}")
    print(f"Duplicates (<6h):  {s['duplicate_alerts']:,}  ({s['duplicate_rate']}%)")
    print(f"Missing context:   {s['missing_context_rate']}% of alerts")
    print(f"Actionable:        {s['actionable_alerts']:,}  ({s['actionable_rate']}%)")
    print(f"-> Filtering removes {s['noise_reduction_pts']}% of alerts before a care team sees them.")

    rule("OUTCOME")
    print("From one headline number to three concrete, routable findings:")
    print("  1. TX/QHIN participation gap   -> solutions team + regional HIE eval")
    print("  2. Thin DocumentReference docs -> config ticket + parsing playbook")
    print("  3. QHIN latency outlier        -> pre-fetch on priority cohorts")
    print("Each one has an owner and a next step. That is coverage intelligence.")


if __name__ == "__main__":
    main()
