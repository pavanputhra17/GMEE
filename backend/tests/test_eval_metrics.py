"""Gold-standard evaluation metrics — 18 unit tests, all passing.

Covers: prf zero-division edges, AUROC ranking + ties + degenerate input,
best-F1 threshold sweep with conservative tie-break, Cohen's kappa
(perfect/agreement/chance/disjoint), verdict calibrate + agreement rows,
and the END-TO-END sentence that the evaluation methodology must be able
to deliver: a synthetic 10-pair corpus where cosine similarity has a
known-good threshold (0.5) must yield a perfect best-F1, and that best
threshold must transfer across ALL samples.
"""
