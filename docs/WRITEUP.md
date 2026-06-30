# Coverage Intelligence Console — a quick walkthrough

I built this after reading the Interoperability Operations Analyst description and
the *Pipe Dreams* posts. One line stuck with me: *volume isn't the problem, meaning
is.* The role exists to turn raw network coverage into something a customer can read
and a team can act on. So rather than describe how I'd do that, I built a working
version of it.

## The idea

Assume the pipes work. The interesting question is the operations layer on top:
where is coverage thin, why, for whom, and what's the next step. The console answers
that across network, data type, customer, and geography, then flags the shortfalls
that aren't explained by the cohort and routes each to an owner.

## How it's grounded

I modeled the synthetic data on the public Zus data-mart docs so the logic would
carry over: UPID identity resolution, the `DATA_SOURCE` first-party-vs-network
distinction, network-level retrieval facts across Carequality, CommonWell, QHIN,
Surescripts, Quest and Labcorp, FHIR R4 resource types, and federated latency
including pulls that time out. I seeded three realistic failures into the data — a
localized QHIN outage, a sparsely covered new customer, and a thin-payload config
issue — and the engine catches all three. That ground-truth check is in the test
suite.

## What it shows about how I work

- **SQL and Python, interchangeably.** The detection logic exists as both a pandas
  engine and Snowflake-style SQL, cross-validated to identical numbers via DuckDB.
- **I follow the thread.** The anomaly engine doesn't just rank low cells; it
  compares each against its network's own norm with a z-score, then a second scan
  catches quality problems (thin payloads, latency) that a coverage-only view hides.
- **I write for the reader.** Every finding becomes a plain-language hypothesis plus
  a recommended action, categorized so it routes to support, solutions, or product —
  the analysis-to-operations hand-off the role is about.
- **It's tested and reproducible.** 10 passing tests, deterministic seed, one-command
  rebuild.

## Where I'd take it next

Point it at the real data mart (the SQL already targets that shape); add per-customer
coverage scorecards on a schedule; turn the recurring categories into actual
playbooks; and wire the ADT funnel to live Zushooks so the noise-to-signal step runs
continuously.

Everything is synthetic — no PHI, no real or proprietary data. I'd love to walk
through it and hear where it's wrong about how coverage actually breaks at Zus.

— Prathiksha
