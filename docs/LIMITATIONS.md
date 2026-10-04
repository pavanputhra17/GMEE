# GMEE Limitations & Failure Boundaries

GMEE is a research prototype. Engineering hardening, typed APIs and an evaluation
harness do not establish factual accuracy, novelty, calibrated truth odds, an
SLO or production readiness. Controlled research, load and restore experiments
remain **UNPERFORMED**; see [Research](RESEARCH.md) and [Audit](AUDIT.md).

## Similarity, stance and corpus coverage

- all-mpnet-base-v2's 768-d vectors retrieve semantic neighbors. Cosine is not
  a probability, event identity, independent corroboration or evidence of truth.
  Threshold windows are settings/heuristics, not validated universal boundaries.
- Same named entities can appear in different events; high similarity can coexist
  with contradictory numbers, negation, time scope or attribution. Low similarity
  can miss valid paraphrases. Candidate limits and approximate indexes can omit
  relevant passages; retrieval recall needs a separately labeled universe.
- Local NLI/stance checks operate on text and can fail on quotations, satire,
  hedging, context, units, dates, negation, long/truncated passages and reporting
  about assertions. They must return/disclose unavailable/neutral states rather
  than convert model failure into contradiction.
- Corpus-local checking is not live web search and never proves exhaustive
  absence. `INSUFFICIENT_EVIDENCE` is abstention, not falsehood. Unsupported legacy
  bands are not ground-truth labels; source reputation/linguistic style cannot
  serve as substitutes for cited evidence.
- Different domains do not prove independent reporting. Canonical/content
  grouping reduces duplicate inflation but cannot resolve all syndication or
  coordinated stories. A widely copied false statement may still be corroborated
  by the corpus. Duplicate/independence limitations must be visible to users.
- Current default language/model choices are English-oriented. Cross-language or
  model swaps require versioned re-embedding and validation; equal dimensionality
  does not make two embedding spaces interchangeable.

## Typed mutation and graph inference

- Typed rules expose numeric/entity/hedging/polarity/framing/wording differences
  and offsets, not a semantic proof that misinformation evolved. Legitimate
  correction, evolving evidence or a changed quote can produce the same types.
- Publication/extraction times can be missing, corrected or unreliable. Order
  must be unknown/reversed when appropriate; an older item is not automatically
  the source of a newer item. Graph adjacency, scoop timing and simulations are
  not observed copying, influence or causal diffusion.
- A one-parent constraint makes the candidate graph structurally consistent;
  it does not establish that the chosen parent is correct. `gmee01` refuses
  conflicting historical parents rather than silently erasing history. Legacy
  NULL evidence remains unverified until explicitly reanalyzed.
- Clustering changes as the corpus grows. Cluster IDs are not frozen event IDs.
  Bounded graph traversal/node/edge limits may omit relationships and must be
  reported; Neo4j mirrors can lag authoritative PostgreSQL state.
- Text comparison returns `observed_propagation: false`. Simulation outputs are
  hypothetical under supplied assumptions, not forecasts validated on diffusion
  observations. Mutation accuracy requires independent type/span gold, separate
  from binary relatedness labels.

## Scores, annotation and evaluation

- Live verdict scoring is an **uncalibrated heuristic**, not a Bayesian posterior
  or a probability of truth. Source/style factors have bias and feedback-loop
  risks. A future calibrated relatedness score would answer a different target.
- Automatic NLI/entity/lexical labels are weak diagnostics, not three independent
  humans. Bucket-dependent annotators can be circular; majority agreement does
  not repair leakage. Historical publication reports remain exploratory.
- A typed label API and server user ID improve provenance, but authentication
  does not prove independent judgments, annotator expertise or correct labels.
  Conservatively preserve human/automatic/legacy/test origins and revisions.
- Stratified similarity sampling changes class prevalence. Pair counts can be
  inflated by shared claims/articles/events; resample and split at appropriate
  event/components, not independent-row assumptions. No fixed number of labels
  automatically gives statistical significance or a publication-grade benchmark.
- Train/dev/test event identity, duplicate grouping, frozen text/model hashes,
  label independence, rights and untouched test use require review. Seeds alone
  are not reproducibility; test-optimized best-F1 is an optimistic diagnostic.
- Missing class/type support makes some metrics undefined. Report unavailability,
  uncertainty and negative findings rather than manufacturing numeric results.

## Resource and operational limits

No CPU/GPU throughput, model RSS, search p95, graph latency, fleet capacity or
restore-time benchmark is asserted here. Historical anecdotal timings/counts do
not establish reproducible measurements on this upgrade.

- One API worker avoids duplicate ML weights; lazy model loading reduces boot
  work but moves download/warm-up cost to first use. A first model load may exceed
  HTTP budgets or memory on small/free-tier hosts; cache/library/BLAS/thread
  overhead and concurrent jobs need actual RSS/latency measurements.
- Body, candidate, graph and request timeouts bound some work, not all resource
  contention. Async I/O and thread offloading do not make CPU inference free or
  guarantee event-loop responsiveness. Heavy work should be observable jobs.
- Finite Redis election TTLs do not guarantee single execution. Durable ownership
  needs renewal/fencing, crash recovery, cancellation/retry and concurrent-trigger
  validation; no exactly-once or HA claim follows from a lock or a job table.
- Redis outage affects revocation/rate limiting/coordination; behavior must be
  explicitly checked. Readiness checks stores, not all models, all providers,
  future resource availability or restore viability.
- Migration-first startup fails closed but can hold DDL locks or reject historical
  conflicts. It needs an isolated restored-snapshot rehearsal and maintenance
  plan. Multi-replica rollout requires one coordinated migration phase.
- The Compose baseline has no TLS gateway, public database access, validated
  multi-host topology or managed secret rotation. Render's free plan remains a
  demo option, not an inference capacity promise.
- A successful `pg_dump` exit/header is not full recovery. The helper produces a
  sensitive unencrypted PostgreSQL archive; actual isolated restore/integrity,
  Neo4j rebuild/backup and Redis security-state policy remain operator gates.

## Security, legal and user-facing boundaries

nginx CSP/proxy header replacement/peer allowlists reduce attack surface but are
not a penetration test. TLS scheme/client identity across an external gateway
requires known-peer configuration; wildcard raw XFF trust permits spoofing. Inline
React styles remain allowed; XSS/session storage, role provisioning, audit/log
privacy, least-privilege DB roles and dependency/model supply chain need review.

Repository MIT licensing is not permission to redistribute ingested articles,
Reddit posts, annotations or model weights. Store per-source terms/provenance,
consent/retention/takedown obligations and data-release permissions. Provider keys
also create quota/cost and text-sharing/privacy implications.

Clearly labeled simulation is useful for a UI demo but never readiness, real
citations, human labels or model performance. HTTP shape/auth smoke cannot prove
browser behavior, accessibility, scientific accuracy or production safety. Keep
[engineering/product/research acceptance](AUDIT.md) separate and open until the
corresponding evidence is attached.
