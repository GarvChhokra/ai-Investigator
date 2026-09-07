# Junior AI Investigator — Write-up

## 1. The problem I designed for

Fraud investigators spend most of their day on cases that turn out to be benign. The fraud
engine hands them a queue; they open a reactive tool, paste a claim number, and read through
~10 signals per case to decide *real / false-positive / dig deeper*. It's slow, it's
inconsistent between investigators, and the time is spent in the wrong place.

The product goal is to **flip the first pass from human to AI**: when the investigator opens
the tool, the queue is already triaged, with reasoning and a recommended next step, so their
attention goes straight to the cases that need judgement. The AI does the reading; the human
does the deciding.

So the design priorities, in order:

1. **The queue view is the product.** The single most valuable thing is walking in to
   "12 need review, 30 likely benign" with a one-line reason on each — not a chatbot, not a
   score column.
2. **Every claim must be traceable to case data.** An investigator will not trust — and
   compliance will not allow — a risk call the AI can't show its work for.
3. **Being wrong safely.** Missing context, low confidence, and model failure have to degrade
   into something an investigator can still act on, not a confident hallucination.

## 2. How the system reasons about a case

**A deterministic-first pipeline with a single constrained LLM step**, orchestrated as a
small LangGraph state machine: `build_packet → llm_assess → validate → finalize`.

### The split

- **`RiskScorer` (no LLM)** does all the quantitative work: for each numeric signal it
  computes the case's percentile within its peer group (same `care_type`), keeps only the
  portion above the peer median, and multiplies by a hand-set weight; binary rule flags
  contribute their full weight. The weighted sum is a transparent 0–100 score → band.
- **`EvidencePacketBuilder` (no LLM)** turns that into a list of `Evidence` objects — each
  with a human label, the raw value, plain-language peer context, a direction, a severity,
  and how much it moved the score. It also adds non-scoring context and data-quality flags.
- **One LLM call** (`AssessmentLlmClient`, schema-constrained) does *only* what models are
  good at: write the summary, pick which indicators mattered and why, assign `risk_level` and
  `confidence`, recommend a next action, and name what it couldn't verify. **It never emits a
  number** — it references evidence by `id`.

### Single call / multi-agent / tools / retrieval

- **One call, not multi-agent.** For a bounded, well-structured decision, a
  planner/critic/researcher swarm adds latency, cost, and failure surface without improving
  the answer. The `validate` node provides the "critic" value deterministically and for free.
- **Tools: minimal.** The assessment path needs none — the evidence packet front-loads every
  fact. Chat has no tools either; the packet is already in its context.
- **Retrieval: none in the prototype.** No policy/SOP corpus was provided, and for 50 rows of
  ~10 well-defined signals, RAG adds latency with nothing to retrieve. The graph keeps a seam
  for a `retrieve` node (SOPs, regulation, prior dispositions of similar cases) — it earns its
  place the moment unstructured context (adjuster notes, medical records, policy language)
  enters.

Why this shape: the risky part (arithmetic, peer comparison) goes to rules, which are exact,
free, and unit-testable; the part rules are bad at (nuanced explanation, "what should a human
do next") goes to the model. It generalises cleanly — a new signal is a new `Evidence`
producer; new context is a new node.

## 3. Grounding — how the AI stays tied to the actual case

- The model's entire input is **the case row + the evidence packet**. No dataset access, no
  other cases, no memory.
- It **cannot produce figures**; it cites `Evidence.id`. The `validate` node **drops any
  indicator that cites an id not in the packet**, and requires at least one to survive.
- The UI renders every cited indicator **next to the raw value and peer context** that
  produced it, so the investigator sees the grounding, not just trusts it.
- The rule-based score is always kept alongside the LLM's `risk_level`. If they disagree, the
  UI shows a banner with both — the system never silently reconciles them.
- **Chat** uses the same packet and a system prompt that forbids going beyond it: if the
  answer isn't in the data, it says so ("that isn't in the case data — you'd need to pull it
  from `<system>`") rather than guessing.

## 4. Uncertainty, missing info, and bad outputs

| Situation | What happens |
|---|---|
| **Low confidence** | `confidence` is a required output and is surfaced prominently. A suspicious-looking case with low confidence reads as "needs a closer look", not "cleared". |
| **Missing context** | `missing_info[]` is required — the model must name what it couldn't verify (provider licensing, claim-line detail, medical history). Shown as an amber "the AI could not verify" callout. The scorer independently flags null / out-of-range values as their own evidence. |
| **Malformed output** | Schema-constrained decoding rejects the wrong shape outright. |
| **Hallucinated citation** | `validate` drops it; if nothing valid remains, that's a retry trigger. |
| **LLM disagrees wildly with the rule score** (>1 band) | one retry with the disagreement fed back as feedback; if it persists, the LLM output is discarded. |
| **Model unavailable / errors / still invalid after retry** | **rules-only `Assessment`**: `llm_used=false`, `confidence=Low`, summary from the deterministic score, indicators = top scored evidence, recommended action = "escalate for manual review". Clearly labelled in the UI. A broken card is never shown. |
| **The human disagrees with any of it** | accept/reject per indicator, override the risk level, add a rationale, Accept / Reject / Escalate — all recorded. |

## 5. How the human stays in the loop

- **Scannable first, drillable second.** The queue is grouped by risk with a one-liner each;
  the case view leads with the summary + recommended action, and every indicator expands to
  its evidence.
- **Traceability builds trust.** No figure appears that isn't a computed value from the case
  row; the "grounding" disclosure shows the peer group, the score, the model id, and the
  validation notes.
- **Override is first-class, not buried.** Per-indicator ✓/✗, a risk-level override dropdown,
  free-text rationale, and a status workflow (`NEW → AI_TRIAGED → UNDER_REVIEW → RESOLVED`).
- **The disagreement banner** is deliberate: when the model and the rules diverge, the
  investigator is told, and shown both, rather than handed a smoothed-over answer.
- Every decision is captured with actor + timestamp — in a real system this audit trail is
  also the training/calibration signal (see §7).

## 6. Scaling past 50 cases

The deterministic layer is O(n) and already fine for tens of thousands. LLM calls are the
only real cost/latency. The [target architecture](ARCHITECTURE.md#target-architecture-how-this-scales-past-50-cases)
shows:

- **Batch pre-compute** on a schedule before the shift — the investigator opens to an
  already-triaged queue. The prototype demonstrates this with the committed `snapshot.json`
  and the `Assess queue` button.
- **Cache by `hash(signal values)`** — unchanged cases are never re-assessed. Already
  implemented.
- **Tiered models** — a fast model for the bulk triage pass, escalate only
  borderline / low-confidence / high-dollar cases to a stronger model.
- **Horizontal workers** — each case is independent and the graph is stateless per case, so a
  work queue (Azure Service Bus) fans out to autoscaled workers (Container Apps) and
  throughput scales with worker count. The same path handles the pre-shift batch, on-change
  re-assessment, and a **full backlog re-run after a prompt / weight / model change** — a
  burst far larger than the daily feed, which is why the queue is the design from day one, not
  a later add-on.
- **The ceiling is the LLM provider, not compute** — workers are cheap; provider rate limits
  and per-token cost are not. Run the overnight batch through Azure OpenAI Batch (roughly half
  the price), keep quota headroom for chat, and apply backpressure at the queue when
  throttled.
- **PHI boundary** — long-term *care* data is PHI, so the model call runs against Azure OpenAI
  in Manulife's own tenant (covered by Microsoft's HIPAA BAA, prompts not used for training)
  or carries only the evidence packet, never the raw member / provider record.
- **Persistence** moves to Azure Database for PostgreSQL (assessments keyed by `signals_hash`,
  partitioned by date past a few million rows) + Blob Storage; a vector store (Azure AI Search
  or pgvector) appears only when unstructured context is added.
- **Cost controls** — prompts are already small (one case + ~14 evidence rows); add
  prompt caching of the system instructions and a per-run token budget.

## 7. Trade-offs, cuts, and risks

**Deliberate cuts** (per the brief — no auth, infra, or deployment):

- No database. In-memory state + a JSON snapshot. Fine for a prototype; the `CaseRepository`
  and store boundaries make the swap to Postgres mechanical.
- The backend imports the AI package **in-process** rather than running a 4th network
  service. Fewer moving parts; the package boundary keeps it splittable.
- **Hand-tuned weights**, not learned. Transparent and good enough for 50 rows; a real system
  calibrates against investigator outcomes.
- Only chat streams. Assessments are short and cached, so no streaming there.
- **One model for everything** (`gemini-3.1-flash-lite`, env-overridable). Fine at this volume;
  the target design tiers it (fast model for bulk, strong model for borderline cases). The
  reasoning is model-agnostic — `AssessmentLlmClient` / `QuestionLlmClient` are the only
  SDK-aware code.
- `QuestionGraphRunner` is a single grounded call, not a real graph — kept the name for
  package symmetry and the future seam (history summarisation, tool use).
- **The UI is plain HTML/CSS/JS** served by FastAPI, not a framework build. The brief doesn't
  grade framework, and "one `pip install`, one command, one URL, no Node" removes a whole
  class of "won't start on my machine" risk for a reviewer. It's ~600 lines and still does
  the things that matter: risk-grouped queue, indicator → evidence traceability, streamed
  chat, the full accept/reject/override/notes loop.

**With more time:**

- An **eval harness**: a small labelled set + a script scoring band accuracy, grounding
  (every citation resolves), schema validity, and disagreement rate — so prompt/model changes
  are measured, not vibes.
- **Feedback loop**: investigator decisions → calibration of the scorer weights and few-shot
  examples for the model.
- **Observability** — per-node tracing of latency, token cost, the prompt, and the validation
  outcome for every assessment (OpenTelemetry into Azure Monitor / App Insights, or Langfuse),
  so regressions are caught and cost is visible.
- Richer peer grouping (`care_type × state`, or provider cohort) once there's more data.

**Risks I see:**

| Risk | Mitigation in the prototype | Residual |
|---|---|---|
| **Hallucination** | LLM can't emit numbers; citations validated; UI shows raw values | Narrative tone could still over/understate — confidence + human review catch this |
| **Trust / over-reliance** | disagreement banner, missing-info callout, "rules-only" labelling, per-indicator override | Automation bias is real; needs monitoring of override rates |
| **Cost / latency at scale** | caching + small prompts | needs tiering + batching (designed, not built) |
| **Calibration drift** (weights, model behaviour) | deterministic layer is inspectable and tested | needs the eval harness + feedback loop |
| **Abuse** (someone gaming known signals) | signals are engineered upstream; scorer is one input not the verdict | out of scope here; belongs with the fraud engine |

## 8. Assumptions

- Each CSV row is one fraud-engine referral; the engineered columns *are* the "signals".
- **`case_id` is the unique key; `claim_number` is not treated as one.** `LTC-2034786` appears
  on both **C1001** and **C1031** — every other field differs (dates, amounts, states, care
  types), so the prototype treats them as two independent records and does nothing special
  with the collision. `claim_number` duplication is a data-quality concern for the ingestion
  layer to resolve against source systems (keying error? resubmission? linked pair?), not
  something this tool models. It is **not** treated as a fraud-ring link.
- Peer group = same `care_type`. With more data, `care_type × state` or a provider cohort.
- Risk taxonomy: Low / Medium / High. "Likely false positive" = Low band + high confidence.
- No external policy/SOP corpus is available, so no retrieval in the prototype.
- Single investigator; no auth, multi-tenancy, or deployment (per the brief).
- USD amounts and ISO dates as given; no currency/timezone handling.

## 9. What to look at

- **Reasoning:** `investigator-ai/investigator_ai/scoring/risk_scorer.py`,
  `evidence/evidence_packet.py`, `graphs/assessment_graph.py` (the `validate` node is the
  interesting bit).
- **Wiring:** `investigator-ai/investigator_ai/container.py`,
  `investigator-be/app/container.py`.
- **Grounding in the UI:** `investigator-web/app.js` — `renderDetail()` puts each cited
  indicator next to its raw value + peer context; every figure is traceable.
- **Graceful failure:** `pytest investigator-ai -k "fallback or unknown_evidence or disagreement"`.
