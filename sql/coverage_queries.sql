/*
Coverage Intelligence - SQL layer
Written against a Zus-style relational data mart (the SQL-friendly view of
FHIR resources). Key Zus modeling facts these queries respect:
   * UPID - primary key for patient-level analytics (a single human may 
   have many source-specific Patient resources)
   * DATA_SOURCE IS NULL  -> first-party (customer's own EHR writes)
   DATA_SOURCE IS NOT NULL -> third-party, network-sourced
   * Coverage is measured across (network x data_type x cohort)
*/


-- 1. Overall coverage rate, latency, and timeout profile 
SELECT
    COUNT(DISTINCT upid)                                  AS humans,
    ROUND(100.0 * AVG(CASE WHEN retrieved THEN 1 ELSE 0 END), 1) AS coverage_rate_pct,
    MEDIAN(CASE WHEN retrieved THEN latency_min END)      AS median_latency_min,
    ROUND(100.0 * AVG(CASE WHEN timed_out THEN 1 ELSE 0 END), 1) AS timeout_rate_pct
FROM coverage_facts;


-- 2. Coverage by network (which pipes are pulling their weight?) 
SELECT
    network,
    network_type,
    ROUND(100.0 * AVG(CASE WHEN retrieved THEN 1 ELSE 0 END), 1) AS coverage_rate_pct,
    MEDIAN(CASE WHEN retrieved THEN latency_min END)             AS median_latency_min,
    ROUND(100.0 * AVG(CASE WHEN timed_out THEN 1 ELSE 0 END), 1) AS timeout_rate_pct,
    COUNT(*)                                                      AS pulls
FROM coverage_facts
GROUP BY network, network_type
ORDER BY coverage_rate_pct ASC;


-- 3. Coverage by customer x data_type (where is a customer thin?)
SELECT
    customer,
    data_type,
    ROUND(100.0 * AVG(CASE WHEN retrieved THEN 1 ELSE 0 END), 1) AS coverage_rate_pct,
    COUNT(*)                                                      AS pulls
FROM coverage_facts
GROUP BY customer, data_type
ORDER BY customer, coverage_rate_pct ASC;


-- 4. Geographic anomaly detection 
/* Compare each state x network cell to that network's average, flag cells that sit 
well below expectation. This is the "numbers don't add up" investigation. 
*/
WITH cell AS (
    SELECT
        state,
        network,
        AVG(CASE WHEN retrieved THEN 1.0 ELSE 0 END) * 100 AS coverage_rate,
        AVG(CASE WHEN timed_out THEN 1.0 ELSE 0 END) * 100 AS timeout_rate,
        COUNT(*)                                           AS pulls
    FROM coverage_facts
    GROUP BY state, network
),
net AS (
    SELECT
        network,
        AVG(coverage_rate) AS expected_rate,
        STDDEV(coverage_rate) AS sd
    FROM cell
    GROUP BY network
)
SELECT
    c.state,
    c.network,
    ROUND(c.coverage_rate, 1)                       AS coverage_rate,
    ROUND(n.expected_rate, 1)                        AS expected_rate,
    ROUND(c.coverage_rate - n.expected_rate, 1)      AS delta_pts,
    ROUND((c.coverage_rate - n.expected_rate)
          / NULLIF(n.sd, 0), 2)                      AS z_score,
    ROUND(c.timeout_rate, 1)                         AS timeout_rate,
    c.pulls
FROM cell c
JOIN net  n USING (network)
WHERE c.pulls >= 150
  AND (c.coverage_rate - n.expected_rate) / NULLIF(n.sd, 0) <= -2.0
ORDER BY z_score ASC;


-- 5. Thin-payload data-quality scan
-- Records retrieved but near-empty: a config/format problem, not availability
SELECT
    network,
    data_type,
    ROUND(100.0 * AVG(CASE WHEN thin_payload THEN 1 ELSE 0 END), 1) AS thin_rate_pct,
    ROUND(AVG(n_resources), 1)                                       AS avg_resources,
    COUNT(*)                                                         AS retrieved_pulls
FROM coverage_facts
WHERE retrieved = TRUE
GROUP BY network, data_type
HAVING AVG(CASE WHEN thin_payload THEN 1 ELSE 0 END) * 100 >= 5.0
ORDER BY thin_rate_pct DESC;


-- 6. First-party VS network-sourced split (DATA_SOURCE semantics)
/* Demonstrates source-aware analytics: how much of each customer's record base is 
their own data VS enriched from the Zus network
*/
SELECT
    customer,
    SUM(CASE WHEN data_source IS NULL THEN 1 ELSE 0 END)     AS first_party_resources,
    SUM(CASE WHEN data_source IS NOT NULL THEN 1 ELSE 0 END) AS network_sourced_resources,
    ROUND(100.0 * SUM(CASE WHEN data_source IS NOT NULL THEN 1 ELSE 0 END)
          / COUNT(*), 1)                                     AS pct_from_network
FROM patients
GROUP BY customer
ORDER BY pct_from_network DESC;


-- 7. ADT noise-to-signal
-- Raw push alerts vs the actionable subset (dedup + has clinical context)
SELECT
    COUNT(*)                                                         AS total_alerts,
    SUM(CASE WHEN is_duplicate THEN 1 ELSE 0 END)                    AS duplicate_alerts,
    SUM(CASE WHEN missing_clinical_context THEN 1 ELSE 0 END)        AS missing_context,
    SUM(CASE WHEN NOT is_duplicate
              AND NOT missing_clinical_context
              AND event_type IN ('A01-Admit', 'A03-Discharge')
             THEN 1 ELSE 0 END)                                      AS actionable_alerts
FROM adt_events;
