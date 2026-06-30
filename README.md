# Coverage Intelligence Console

A working prototype of the metrics, anomaly detection, and tooling an
**Interoperability Operations Analyst** builds. It measures clinical-data coverage
across a health-data network, finds where coverage is thin, explains *why*, and
turns each finding into a routable action.

**[▶ Live demo](https://prathikshaurs.github.io/zus-coverage-intelligence/)** &nbsp;·&nbsp; built around the Zus Health FHIR data-mart model

A lot of vendors can pull data from the national networks now, that part is becoming a commodity. The real differentiation is in what happens after the pull: normalizing it, catching what's missing, and explaining the gaps to the people who need the answer.
This project takes that idea literally. It assumes the pipes already work and focuses entirely on the operations layer on top: which data is missing, where, for whom, and what to do about it.

---

## What it does

| Pillar (from the role) | What's built |
|---|---|
| **Coverage intelligence** | Coverage rate computed across network, data type, customer, geography, and age band; a state × network heatmap for fast visual triage |
| **Anomaly investigation** | A z-score engine that compares every cell to its network's own norm and flags significant shortfalls; a second non-geographic scan for thin payloads and latency outliers |
| **Root-cause narratives** | Every anomaly is paired with a plain-language hypothesis and a recommended operational action (the hand-off to support / solutions / product) |
| **Operations partnership** | Findings are categorized (connectivity / configuration / participation gap) so each routes to the right owner - the start of a playbook |
| **ADT noise-to-signal** | A funnel that dedupes push alerts and filters for clinical context, down to the actionable admits/discharges |

---

## Grounded in the real data model

The synthetic data is modeled on Zus's publicly documented structure so the logic
would transfer to the real data mart with minimal change:

- **UPID identity resolution** — one human can have many source-specific Patient resources
- **`DATA_SOURCE` provenance** — `NULL` = first-party (customer's own writes), `NOT NULL` = network-sourced
- **Network-level coverage** — Carequality, CommonWell, QHIN, Surescripts (pharmacy), Quest/Labcorp (labs)
- **FHIR R4 resource types** — Condition, Encounter, Observation, DocumentReference, MedicationStatement, etc.
- **Federated latency** — variable response times, including pulls that never return

Three problems are deliberately injected into the synthetic data so the detection
logic can be validated against a known ground truth:

1. a **QHIN connectivity outage** localized to one state,
2. a **new customer** with sparse network coverage across its footprint, and
3. a **thin-payload config issue** on DocumentReferences from one EHR vendor.

The engine and tests confirm all three are found.

---

## Architecture

```
engine/generate_data.py   synthetic FHIR-style data (Faker + numpy)
engine/coverage_engine.py  metrics, anomaly detection, narratives  <- the core
sql/coverage_queries.sql   the same logic as Snowflake-style SQL
notebooks/investigation.py one investigation walked end to end
tests/test_engine.py       10 tests incl. ground-truth detection checks
dashboard/index.html       single-file interactive console (the live demo)
docs/WRITEUP.md            the one-page summary to send with it
```

The Python engine and the SQL layer are cross-validated against the same dataset
(via DuckDB) and produce identical numbers.

---

## Run it locally

```bash
# 1. To install dependencies
pip install pandas numpy faker pytest duckdb

# 2. To generate the full dataset
python engine/generate_data.py --patients 4000 --seed 42 --out data

# 3. Run the engine (produces the report JSON)
python engine/coverage_engine.py

# 4. Run the tests
python -m pytest tests/ -v

# 5. Serve the dashboard locally (open http://localhost:8000)
cd dashboard
python -m http.server 8000
```

---

## A note on data and scope

Everything here is **fully synthetic**. No real patient data, no proprietary Zus
data, and no PHI are used anywhere. The numbers exist to demonstrate the method,
the metrics, the detection, the narrative hand-off, and not to describe any real
network's performance. Not affiliated with or endorsed by Zus Health.

Built by **Prathiksha Mohan Raje Urs**, Data Engineer, HL7 certified, with
production HL7/FHIR interoperability experience.
