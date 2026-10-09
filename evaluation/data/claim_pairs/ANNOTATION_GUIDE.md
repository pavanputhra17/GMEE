# GMEE Claim Pair Annotation Guide

This guide provides instructions, schema definitions, and worked examples for annotating claim pairs to evaluate GMEE's semantic mutation detection and propagation graph.

---

## 1. Label Definitions

Annotators assign exactly one of the following four labels to each pair `(Claim A, Claim B)`:

| Label | Definition | Semantic Relationship | Real-World Event |
|---|---|---|---|
| **`EVOLVED_FROM`** | Claim B is a semantic mutation of Claim A — it preserves the core assertion but modifies framing, emphasis, details, figures, or attributed blame. | Direct narrative drift / mutation | Identical event |
| **`SIMILAR_TO`** | Claims share a common topic, domain, or entities, but assert distinct, non-mutated facts (e.g. two separate policy measures or statements). | Topical overlap | Same or related domain |
| **`UNRELATED`** | Claims refer to completely different events, entities, or topics with no substantive relation. | No semantic or topical connection | Independent |
| **`DUPLICATE`** | Claims are verbatim copies, near-duplicates, or direct syntactic paraphrases with identical factual content and no drift. | Syntactic paraphrase / duplicate | Identical event |

---

## 2. Target Dataset Composition

To ensure balanced evaluation across positive, negative, and borderline classes, the annotated set (`pairs_annotated.csv`) requires a minimum of **120 labeled pairs** with the following distribution:

- **`EVOLVED_FROM`:** $\ge 40$ pairs
- **`SIMILAR_TO`:** $\ge 30$ pairs
- **`UNRELATED`:** $\ge 30$ pairs
- **`DUPLICATE`:** $\ge 20$ pairs

---

## 3. Worked Annotation Examples

### Examples 1–5: `EVOLVED_FROM` (Mutations)

1. **Claim A:** *"Health officials report 12 cases of unexplained pneumonia in the province."*  
   **Claim B:** *"A mysterious viral outbreak has sickened dozens in regional hospitals amid official silence."*  
   - **Label:** `EVOLVED_FROM`  
   - **Rationale:** Same underlying event; Claim B escalates the rhetoric ("mysterious viral outbreak", "amid official silence") and inflates the case magnitude ("dozens").

2. **Claim A:** *"The central bank raised the benchmark interest rate by 25 basis points to 5.25%."*  
   **Claim B:** *"Central bankers shock markets with another aggressive rate hike choking small businesses."*  
   - **Label:** `EVOLVED_FROM`  
   - **Rationale:** Same policy decision; Claim B shifts from objective financial reporting to emotional framing ("shock markets", "choking small businesses").

3. **Claim A:** *"A cargo ship ran aground near the port entrance due to steering gear failure."*  
   **Claim B:** *"Foreign cargo vessel deliberately blocks critical shipping channel in suspected sabotage."*  
   - **Label:** `EVOLVED_FROM`  
   - **Rationale:** Classic conspiratorial mutation; an accidental mechanical grounding is reframed as deliberate sabotage.

4. **Claim A:** *"New preliminary study of 45 patients shows drug X reduced symptoms by 20%."*  
   **Claim B:** *"Miracle cure Drug X proven to eradicate disease in breakthrough clinical trial."*  
   - **Label:** `EVOLVED_FROM`  
   - **Rationale:** Over-extrapolation mutation; a modest preliminary finding is recast into an unverified "miracle cure".

5. **Claim A:** *"Local election board adjusts precinct boundaries to reflect 2024 census redistricting."*  
   **Claim B:** *"Corrupt election officials redraw voting precincts overnight to disenfranchise opposition voters."*  
   - **Label:** `EVOLVED_FROM`  
   - **Rationale:** Imputation of intent mutation; routine administrative boundary updates are reframed as partisan voter suppression.

### Examples 6–8: `SIMILAR_TO` (Topical Overlap, Non-Mutated)

6. **Claim A:** *"The city council voted to allocate $5 million for protected downtown bicycle lanes."*  
   **Claim B:** *"The municipal transit authority announced a fare increase for suburban commuter trains."*  
   - **Label:** `SIMILAR_TO`  
   - **Rationale:** Both claims concern municipal transportation infrastructure and policy, but describe two completely separate actions and decisions.

7. **Claim A:** *"Company X reported second-quarter earnings exceeding analyst projections by 8%."*  
   **Claim B:** *"Company X announced the appointment of a new Chief Technology Officer from competitor Y."*  
   - **Label:** `SIMILAR_TO`  
   - **Rationale:** Both claims are about Company X corporate developments, but assert distinct facts (financial earnings vs. executive hiring).

8. **Claim A:** *"Wildfire containment in northern county reached 40% after weekend rainfall."*  
   **Claim B:** *"State emergency agency deployed 200 additional firefighters to southern mountain blaze."*  
   - **Label:** `SIMILAR_TO`  
   - **Rationale:** Both claims involve state wildfire management, but describe different incidents in different regions.

### Examples 9–10: `UNRELATED` (Independent)

9. **Claim A:** *"The European Space Agency launched a climate-monitoring satellite from French Guiana."*  
   **Claim B:** *"The national soccer team qualified for the World Cup quarterfinals with a 2-1 victory."*  
   - **Label:** `UNRELATED`  
   - **Rationale:** Completely disparate domains (space science vs. international soccer) with no shared entities or events.

10. **Claim A:** *"Archaeologists uncovered Bronze Age pottery fragments during highway excavation."*  
    **Claim B:** *"Electric vehicle manufacturer plans to open three new battery recycling plants."*  
    - **Label:** `UNRELATED`  
    - **Rationale:** Completely unrelated topics and entities.

---

## 4. SQL Extraction Query for Candidate Pairs

To source candidate claim pairs from the live PostgreSQL corpus, execute:

```sql
SELECT
  c1.id              AS id_a,
  c1.claim_text      AS claim_a,
  c2.id              AS id_b,
  c2.claim_text      AS claim_b,
  cr.relationship_type,
  cr.score,
  a1.published_at    AS date_a,
  a2.published_at    AS date_b,
  s1.domain          AS source_a,
  s2.domain          AS source_b
FROM claim_relationships cr
JOIN claims   c1 ON cr.from_claim_id = c1.id
JOIN claims   c2 ON cr.to_claim_id   = c2.id
JOIN articles a1 ON c1.article_id    = a1.id
JOIN articles a2 ON c2.article_id    = a2.id
JOIN sources  s1 ON a1.source_id     = s1.id
JOIN sources  s2 ON a2.source_id     = s2.id
ORDER BY cr.score DESC
LIMIT 250;
```

Export results to `evaluation/data/claim_pairs/pairs_template.csv`, annotate the `label` and `annotator_confidence` (0.0 to 1.0) columns, and save as `evaluation/data/claim_pairs/pairs_annotated.csv`.
