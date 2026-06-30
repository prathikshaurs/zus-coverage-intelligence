"""
Synthetic data generator modeled on the Zus Health FHIR data-mart structure

Design notes (grounded in Zus public docs):
  - Each human is identified by a UPID (Universal Patient Index). A single human
    may have multiple source-specific Patient resources, one per organization/network
  - Every base FHIR resource row carries a DATA_SOURCE column:
        DATA_SOURCE IS NULL      -> first-party data (the customer's own EHR writes)
        DATA_SOURCE IS NOT NULL  -> third-party data sourced from the Zus network
  - National networks (Carequality, CommonWell, QHINs) give broad clinical coverage
  - Pharmacy data is best sourced from Surescripts; labs from Quest / Labcorp
  - Federated repositories have variable response latency: some respond in seconds,
    some in hours, some never
  - ADT (Admit/Discharge/Transfer) events arrive as push notifications and are noisy

This generator is deliberately injecting realistic coverage gaps and anomalies so that 
the coverage-intelligence engine has something true to surface. NOTHING here is real
patient data; it is fully synthetic (Faker + numpy).
"""

import argparse
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

fake = Faker("en_US")

# Reference dimensions modeled on the Zus network

NETWORKS = {
    "Carequality":  {"type": "national_clinical", "base_match": 0.86, "base_latency_min": 90},
    "CommonWell":   {"type": "national_clinical", "base_match": 0.83, "base_latency_min": 120},
    "QHIN-eHX":     {"type": "qhin",              "base_match": 0.74, "base_latency_min": 180},
    "Surescripts":  {"type": "pharmacy",          "base_match": 0.91, "base_latency_min": 15},
    "Quest":        {"type": "lab",               "base_match": 0.88, "base_latency_min": 30},
    "Labcorp":      {"type": "lab",               "base_match": 0.87, "base_latency_min": 35},
}

# Which FHIR data types each network type can supply (coverage - data-type specific)
DATA_TYPE_BY_NETWORK_TYPE = {
    "national_clinical": ["Condition", "Encounter", "Observation", "DocumentReference",
                          "MedicationStatement", "AllergyIntolerance", "Immunization", "Procedure"],
    "qhin":              ["Condition", "Encounter", "DocumentReference", "Observation", "Procedure"],
    "pharmacy":          ["MedicationStatement", "MedicationDispense"],
    "lab":               ["Observation", "DiagnosticReport"],
}

# EHR vendors at the facility a record came from (system compatibility matters for coverage)
EHR_VENDORS = ["Epic", "Cerner", "athenahealth", "Canvas", "Elation", "Healthie", "Veradigm", "Other"]

# Customers (Zus "Builders") with different care models -> different cohorts
CUSTOMERS = [
    {"name": "HarmonyCares",       "model": "home_based_primary", "states": ["MI", "OH", "PA", "TX", "FL"]},
    {"name": "Firefly Health",     "model": "virtual_primary",    "states": ["MA", "NH", "RI", "CT"]},
    {"name": "Author Health",      "model": "behavioral_senior",  "states": ["FL", "GA", "TX"]},
    {"name": "Evergreen Nephrology","model": "specialty_nephro",  "states": ["TN", "KY", "NC", "VA"]},
    {"name": "DispatchHealth",     "model": "in_home_acute",      "states": ["CO", "AZ", "NV", "WA", "OR"]},
]

RESOURCE_TYPES = ["Condition", "Encounter", "Observation", "DocumentReference",
                  "MedicationStatement", "MedicationDispense", "DiagnosticReport",
                  "AllergyIntolerance", "Immunization", "Procedure"]

ADT_EVENTS = ["A01-Admit", "A03-Discharge", "A02-Transfer", "A04-Register", "A08-Update"]


def _seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    Faker.seed(seed)


def generate(n_patients=4000, seed=42):
    _seed(seed)

    # PATIENT table (UPID -> source-specific patient rows)
    patient_rows = []
    upid_meta = {}  # upid (dict of attributes) reused downstream

    for _ in range(n_patients):
        upid = "upid_" + fake.unique.hexify("^^^^^^^^")
        customer = random.choice(CUSTOMERS)
        state = random.choice(customer["states"])
        # match likelihood: quality cohorts sit in the 80th+ percentile,
        # but it varies by cohort composition. Modelling age + state effects
        age = int(np.clip(np.random.normal(64, 18), 0, 99))
        # patients seen at more facilities -> more source-specific Patient resources
        n_sources = max(1, int(np.clip(np.random.poisson(3.2), 1, 9)))

        upid_meta[upid] = {
            "customer": customer["name"], "care_model": customer["model"],
            "state": state, "age": age, "n_sources": n_sources,
        }

        # one first-party Patient resource (the customer's own EHR copy)
        patient_rows.append({
            "patient_id": "pt_" + fake.hexify("^^^^^^^^"),
            "upid": upid, "customer": customer["name"], "state": state, "age": age,
            "data_source": None,  # NULL => first-party
            "source_ehr": random.choice(["Canvas", "Elation", "Healthie", "athenahealth", "Epic"]),
        })
        # plus N source-specific Patient resources from the network
        for _ in range(n_sources):
            patient_rows.append({
                "patient_id": "pt_" + fake.hexify("^^^^^^^^"),
                "upid": upid, "customer": customer["name"], "state": state, "age": age,
                "data_source": random.choice(list(NETWORKS.keys())),
                "source_ehr": random.choice(EHR_VENDORS),
            })

    patients = pd.DataFrame(patient_rows)

    # Inject a few systematic coverage problems
    # 1) A QHIN connectivity degradation in one state (regression-style outage)
    degraded_state = "TX"
    degraded_network = "QHIN-eHX"
    # 2) A specific EHR vendor returning structurally thin documents (config issue)
    thin_vendor = "Veradigm"
    # 3) One customer onboarded recently with sparse network coverage
    new_customer = "Evergreen Nephrology"

    # RESOURCE / coverage fact table
    # One row per (upid, network, data_type) describing whether Zus retrieved it,
    # how many resources, latency, and whether it looked anomalous
    fact_rows = []
    today = datetime(2026, 6, 29)

    for upid, meta in upid_meta.items():
        for net_name, net in NETWORKS.items():
            supported_types = DATA_TYPE_BY_NETWORK_TYPE[net["type"]]
            for dtype in supported_types:
                base = net["base_match"]

                # age effect: very young patients have thinner clinical histories
                if meta["age"] < 18:
                    base -= 0.18
                # new customer effect: sparse coverage
                if meta["customer"] == new_customer:
                    base -= 0.22
                # injected outage
                if meta["state"] == degraded_state and net_name == degraded_network:
                    base -= 0.45

                base = float(np.clip(base, 0.02, 0.98))
                retrieved = np.random.random() < base

                # latency draw (log-normalish), federated repos vary a lot
                lat = max(1, int(np.random.gamma(2.0, net["base_latency_min"] / 2.0)))
                # 4% of pulls effectively never return within window
                never = np.random.random() < 0.04
                if never:
                    lat = None

                n_resources = 0
                anomalous_thin = False
                if retrieved and lat is not None:
                    n_resources = int(np.clip(np.random.poisson(14), 0, 200))
                    # thin-vendor config issue: doc retrieved but near-empty
                    src_vendor = random.choice(EHR_VENDORS)
                    if src_vendor == thin_vendor and dtype == "DocumentReference":
                        n_resources = int(np.clip(np.random.poisson(1), 0, 3))
                        anomalous_thin = True

                fact_rows.append({
                    "upid": upid,
                    "customer": meta["customer"],
                    "care_model": meta["care_model"],
                    "state": meta["state"],
                    "age_band": _age_band(meta["age"]),
                    "network": net_name,
                    "network_type": net["type"],
                    "data_type": dtype,
                    "retrieved": bool(retrieved and lat is not None),
                    "n_resources": n_resources,
                    "latency_min": lat,
                    "timed_out": lat is None,
                    "thin_payload": anomalous_thin,
                    "pull_date": (today - timedelta(days=int(np.random.randint(0, 30)))).date().isoformat(),
                })

    coverage = pd.DataFrame(fact_rows)

    # ADT push events (noisy)
    adt_rows = []
    adt_patients = patients[patients["data_source"].notna()].sample(
        frac=0.35, random_state=seed)
    for _, row in adt_patients.iterrows():
        n_alerts = np.random.poisson(1.4)
        for _ in range(n_alerts):
            ts = today - timedelta(minutes=int(np.random.randint(0, 60 * 24 * 14)))
            adt_rows.append({
                "upid": row["upid"],
                "customer": row["customer"],
                "state": row["state"],
                "event_type": random.choice(ADT_EVENTS),
                "facility": fake.company() + " Medical Center",
                "source_network": random.choice(["Carequality", "CommonWell", "QHIN-eHX"]),
                "event_ts": ts.isoformat(timespec="minutes"),
                # noise flags: missing discharge dx, missing facility id, dup within 6h
                "missing_clinical_context": np.random.random() < 0.43,
                "has_followup_query": np.random.random() < 0.6,
            })
    adt = pd.DataFrame(adt_rows)
    # mark duplicates: same upid + event within 6h
    adt["event_ts_dt"] = pd.to_datetime(adt["event_ts"])
    adt = adt.sort_values(["upid", "event_ts_dt"])
    adt["mins_since_prev"] = adt.groupby("upid")["event_ts_dt"].diff().dt.total_seconds() / 60
    adt["is_duplicate"] = (adt["mins_since_prev"].fillna(9999) < 360) & \
                          (adt["mins_since_prev"].notna())
    adt = adt.drop(columns=["event_ts_dt"])

    return {
        "patients": patients,
        "coverage": coverage,
        "adt": adt,
        "meta": {
            "degraded_state": degraded_state,
            "degraded_network": degraded_network,
            "thin_vendor": thin_vendor,
            "new_customer": new_customer,
            "generated_at": datetime.now().isoformat(),
            "n_humans": len(upid_meta),
        },
    }


def _age_band(age):
    if age < 18:
        return "0-17"
    if age < 40:
        return "18-39"
    if age < 65:
        return "40-64"
    return "65+"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients", type=int, default=4000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    bundle = generate(args.patients, args.seed)
    import os
    os.makedirs(args.out, exist_ok=True)
    bundle["patients"].to_csv(f"{args.out}/patients.csv", index=False)
    bundle["coverage"].to_csv(f"{args.out}/coverage_facts.csv", index=False)
    bundle["adt"].to_csv(f"{args.out}/adt_events.csv", index=False)
    import json
    with open(f"{args.out}/meta.json", "w") as f:
        json.dump(bundle["meta"], f, indent=2)

    print(f"Humans (UPIDs): {bundle['meta']['n_humans']:,}")
    print(f"Patient resources: {len(bundle['patients']):,}")
    print(f"Coverage facts: {len(bundle['coverage']):,}")
    print(f"ADT events: {len(bundle['adt']):,}")
