# Scope — structural disambiguation for gender and case

> **Snapshot.** Figures below were current when written (August 2026) and are not updated in
> place. For current accuracy see the [README](README.md).

> **Status: Phase A run. Recommendation — do NOT build Phase B.** The signal is real and does not
> convert. Findings in §10; the original proposal is kept below unedited, since the reasoning that
> led to it was sound and only measurement could have shown it does not pay.

## 1. The problem, as measured

| field | selected | oracle | gap |
|---|---|---|---|
| gender | 69.8% | 95.9% | **26.1 pt** |
| case | 72.9% | 95.4% | **22.5 pt** |

Oracle is what matters: **the correct reading is already in the candidate list ~95% of the time,
and zero tokens are unanalysable.** This is not a lexicon problem and never was. The engine has the
right answer in hand and picks the wrong one.

## 2. Why more heuristics will not close it

Five attempts, measured against DCS with kāraka checked alongside:

| attempt | result |
|---|---|
| oblique-first fallback once a subject is taken | **−13.3 pt** case |
| kartā agrees with verb in number | +0.8 pt number, −0.1 case |
| remove single-subject assumption | **0.0 pt** (already vestigial) |
| penalise lemma identical to surface form | **−0.3 pt** lemma, reverted |
| stem-gender agreement outranks lemma string | +2.0 lemma (landed) |

Only the last was a real gain, and it worked because it replaced an *arbitrary* signal (ASCII
byte order) with a *linguistic* one (the stem's declared gender). That is the pattern: heuristics
win when they inject grammar, and fail when they shuffle priors.

`select()` has now run out of grammar to inject, because of what it is: each token is assigned
independently, from its own candidate list, given two sentence-level guesses (subject = first
nominative, karma = last non-subject). **Nothing in it can express a relation between two words.**
Every remaining error needs exactly that.

## 3. The information we are not using

**a. Adjective–noun agreement (viśeṣaṇa–viśeṣya).** A Sanskrit adjective agrees with its noun in
case, number *and* gender. This is a hard Pāṇinian rule, not a tendency — and it is the single
largest untapped constraint, aimed straight at gender, our worst gap. DCS tags 866 ADJ tokens in
our 11.5k sample; each one constrains both itself and its head, and we currently disambiguate the
two in total ignorance of each other.

**b. Verb government (karmapravacanīya / dhātu valence).** Which cases a root takes: √gam a
destination in the accusative, √dā a recipient in the dative. This targets case, where agreement
alone gives little.

**c. Clause membership.** In multi-verb sentences every nominal currently competes for one
subject slot and one karma slot regardless of which verb it belongs to.

## 4. The proposed structure

Replace independent per-token selection with **joint assignment over the sentence**:

```
variables   one per token
domains     that token's candidate list        (~95% already contain the truth)
constraints agreement between related words; verb government; one karma per verb
objective   the assignment satisfying the most constraints
```

**Tractability.** If constraints are pairwise between *adjacent* tokens, this is a chain and
Viterbi solves it **exactly** in O(n·k²) — with n ≈ 10 tokens and k ≈ 20 candidates that is a few
thousand operations per sentence. No approximation, no search heuristics, no beam.

Sentence-wide constraints (subject–verb agreement) would break the chain, so they enter as *unary*
features instead: the verb is selected first, then every nominal is scored against its number. That
preserves exact inference.

**This stays within the deterministic thesis.** Agreement is a *hard grammatical rule*, so it is
encoded as a constraint, not as a weight learned from DCS. What is uncertain is only **which words
stand in a modifier relation** — and that uncertainty is resolved by search, not by training. DCS
is used to *evaluate*, never to fit parameters.

## 5. The one genuinely open question

We do not know which adjective modifies which noun. Three options:

| approach | note |
|---|---|
| adjacency | adjectives usually adjoin their head — cheap, but weak in verse |
| **agreement-as-evidence** | do not pre-link; prefer the assignment that makes the *most* agreement possible among neighbours |
| full dependency parse | out of scope |

The middle one is the interesting one: it inverts the problem. Rather than deciding links and then
enforcing agreement, it treats *achievable agreement* as the evidence for both at once.

## 6. Phase A — measure before building

Every finding this project has kept came from measuring before acting; the three predictions that
failed were made before. So Phase A builds no model. It answers:

1. **Is adjacency a real signal here?** For each DCS ADJ token, does its correct reading agree in
   case/number/gender with an adjacent token's correct reading? Gives the coverage and precision of
   the adjacency assumption on actual Sanskrit, including verse.
2. **What is the recoverable ceiling?** Restricting each token to candidates consistent with a
   correct neighbour — how much of the 26 pt and 22 pt survives? This bounds Phase B before a line
   of it exists.
3. **Do we have valence data at all?** Does the kosha expose dhātu argument structure, or would
   government have to be authored by hand?
4. **How often does agreement disambiguate uniquely?** If a token has 13 candidates and agreement
   narrows it to 4, the remaining choice still needs a prior — so measure the residual ambiguity.

**Phase A is the deliverable to decide on.** If (1) and (2) come back weak, Phase B is not worth
building and the honest answer is that these gaps stay open.

## 7. No predicted gain

Three predictions this month did not survive contact: a +7.3 pt tie-break ceiling that delivered
+1.9, a single-subject bug that did not exist, and a stem-citation "convention" that turned out to
be two-thirds ranking. Each was reasoned from a pattern rather than measured.

So: **no number is offered for Phase B until Phase A measures one.** The argument for doing this at
all is not a projected figure — it is that oracle sits 22–26 points above selection, that the gap
is entirely relational, and that `select()` structurally cannot represent a relation.

## 8. Explicit non-goals

- **No training.** DCS evaluates; it never fits parameters.
- **No LLM in the structural layer.** It stays deterministic and inspectable.
- **No full dependency parser.** Pairwise agreement, deliberately, because it keeps inference exact.
- **No kāraka regression.** 20/20 on the gold set is a hard gate, as it has been for every change.

## 9. Effort

| | |
|---|---|
| Phase A (measurement, decides Phase B) | ~1 session |
| Phase B (constraint model + Viterbi + evals) | ~2–3 sessions |

Phase B should not start until Phase A reports.


---

# 10. Phase A results — and the verdict

`python -m evals.agreement_signal`

## Q1 — is adjacency a real signal? **Yes, strongly.**

| | agrees with a neighbour |
|---|---|
| adjectives | **72.0%** (521/724) |
| any token | 55.1% (2792/5067) |
| chance baseline (non-adjacent pair, same sentence) | 34.6% |

Adjectives exceed chance by **+37.3 pt**. The linguistic premise is sound.

## Q2 — ceiling with gold neighbours: **looks excellent, and is misleading**

Restricting each token to candidates agreeing with a neighbour's *correct* reading:
mean candidates **4.5 → 2.5**; 2,391 tokens resolve uniquely, **91.9% of them correct**.

This number is what a scoping document would normally quote. It is close to worthless, because
knowing the neighbour's correct reading is already most of the answer. Truth is also *lost* 7.0% of
the time — blanket adjacency discards the right reading when the neighbour is not a modifier.

## Q2b — realistic, no oracle: **the signal does not convert**

| variant | case | gender | number |
|---|---|---|---|
| `select()` today | 72.9% | 69.8% | 87.4% |
| Viterbi replacing `select()` | 59.7% (**−13.3**) | 68.2% | 88.4% |
| …gated on adjective identity (DCS oracle) | 55.6% (**−17.3**) | 65.2% | 86.4% |
| **agreement as a refinement ON TOP of `select()`** | **73.3% (+0.4)** | **71.2% (+1.4)** | **87.9% (+0.5)** |

The first two rows are a measurement error worth recording: they compare *agreement + a weak
candidate-order prior* against *no agreement + a strong grammatical prior*, and so test the wrong
thing. Corrected — agreement layered on top of the existing priors — the honest gain is **+0.4 pt
case and +1.4 pt gender**, against gaps of 22.5 and 26.1.

And that is an **upper bound**: it uses DCS's ADJ tag as an oracle, which we do not have. Our POS
tagset collapses ADJ into "noun", so shipping any of this requires building adjective detection
first — for at most +1.4 pt.

## Q3 — valence data: **absent**

`DhatuEntry` exposes `karmatva` (transitivity) and `pada`, and both are `None` throughout this
Vidyut release. Verb government would have to be hand-authored per root.

## Q4 — residual ambiguity

Agreement narrows 4.5 candidates to 2.5. Even where it applies, more than half the choices still
fall through to a prior — the mechanism cannot carry the load on its own.

## Verdict

**Do not build Phase B.** Pairwise agreement is a genuine linguistic signal that does not convert
into accuracy: the gap it addresses is relational, but *adjacency is not the relation*. Recovering
it needs to know which word modifies which, and Q2 shows that once you know that, you already
have the answer — the two are the same problem.

The 22–26 pt gaps stay open, and that is the honest state of the engine. Closing them needs real
syntactic structure, which §8 excluded on purpose and which is a different project from this one.

**What Phase A cost: one session. What it saved: two or three building a layer worth +1.4 pt** —
sitting behind a prerequisite (adjective detection) that does not exist yet. This is the entire
argument for measuring before building, and it is the first time in this project that the measured
answer was *don't*.
