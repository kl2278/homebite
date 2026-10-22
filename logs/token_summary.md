# Token summary (baseline config)

Runs analysed: 10 baseline runs (one per dish), status ok. Costs are computed from tokens with the price constants below.

## Prices used (USD per 1M tokens)

- Input $0.1 | cached input $0.01 | cache write $0.125 | output $0.5
- Source: course slides, "Cached Token Cost" slide, gpt-6-luna row.
- Cache writes: the provider reported 49170 cache-write tokens in total; they are priced at the cache-write rate.

## Per run

| Metric | Average | p90 |
|---|---|---|
| Input tokens | 11,709 | 15,291 |
| Cached input tokens | 3,265 | 6,462 |
| Output tokens | 2,829 | 4,180 |
| Cost | $0.002414 | $0.003646 |
| Latency (s) | 33.2 | 45.1 |

Cache hit ratio (cached input / input): **27.9%**

## Breakdown by stage (average per run)

| Stage | Input | Cached | Output | Cost | Share of cost | Requests | Tool calls |
|---|---|---|---|---|---|---|---|
| guard | 337 | 0 | 38 | $0.000052 | 2.2% | 1.0 | 0.0 |
| intake | 316 | 0 | 88 | $0.000076 | 3.1% | 1.0 | 0.0 |
| analyst | 8,432 | 3,265 | 1,535 | $0.001425 | 59.0% | 3.0 | 15.8 |
| substitution | 1,899 | 0 | 625 | $0.000517 | 21.4% | 2.1 | 3.6 |
| writer | 726 | 0 | 544 | $0.000344 | 14.3% | 1.1 | 0.0 |

The guard stage is the cheap input classifier; it is included in every total above.

## Projected monthly cost

**Assumption: 12 runs per user per month (the report author's assumption, not measured).** Average cost per run, including the guard stage: $0.002414.

| Users | Runs per month | Estimated monthly cost |
|---|---|---|
| 1 | 12 | $0.03 |
| 100 | 1,200 | $2.90 |
| 10,000 | 120,000 | $289.72 |

## What the daily token cap implies

The cap counts input + output tokens: 3,000,000 per UTC day, across all sessions.
- At the measured token mix, that is about **$0.50 per day** at most ($0.1661 per 1M capped tokens).
- Worst case, if every capped token were an output token: $1.50 per day.

## Suspected gateway cache hits

No baseline run was flagged.

## Assumptions and limits

- Hosting, storage and bandwidth costs are not included.
- Provider rate limits at scale (100 or 10,000 users) are not modeled.
- Only 10 dishes with one run each; the p90 of 10 samples is rough, and run-to-run variation of the model is not measured.
- The 12 runs per user per month is an assumption.
- Costs are estimates from token counts and the course price slide, not an invoice.
- Blocked or failed runs are not part of these averages.
