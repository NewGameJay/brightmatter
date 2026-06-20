# BrightMatter Live State — 2026-06-18

*Auto-generated. Programmatic; no LLM in the loop.*

## System health
- Accounts monitored: **223** · data through **2026-06-18**
- Episodes: **4889** · live predictions registered: **2342**
- Template health (live): SHADOW_ONLY 32 · RETIRED 3 · ACTIVE 39
- Resolved: 7d **2159** · 14d **1553** · 30d **585** (pending 7d resolution: 183)

## Accuracy (14-day window — the product metric)
- Predictions resolved: **1553**
- **Recommendation accuracy (decisive calls): 67%** (n=912)
- Abstention rate (EITHER): 41%
- Direction accuracy: 64% · magnitude MAE: 54pp

| Recommendation | n | correct |
|---|---|---|
| EITHER | 641 | 19% |
| DO_NOT_ACT | 466 | 66% |
| ACT | 234 | 61% |
| WAIT | 212 | 76% |

## Drift alerts
| Template | live | backtest |
|---|---|---|
| `budget__single__lead_gen__pool_spa__performing` | 30% | 57% |
| `campaign_setting__multi__volatile` | 35% | 60% |
| `auto_budget_optimization__multi__ecommerce__ap` | 42% | 62% |
| `budget__single__unknown__unknown__performing_w` | 46% | 71% |
| `campaign_setting__single__lead_gen__above_aver` | 50% | 67% |
| `auto_budget_optimization__multi__ecommerce__pe` | 54% | 71% |
| `campaign_setting__single__lead_gen__pool_spa__` | 67% | 83% |

## Noteworthy live calls (14d, strongest action-cost)

- [✓] **DO_NOT_ACT** auto_comprehensive_optimization__multi__lead (campaign 23370961178, predicted action cost +149pp)
- [✓] **DO_NOT_ACT** auto_comprehensive_optimization__multi__lead (campaign 23366711945, predicted action cost +149pp)
- [✓] **DO_NOT_ACT** auto_comprehensive_optimization__multi__lead (campaign 23476207576, predicted action cost +149pp)
- [✗] **DO_NOT_ACT** auto_comprehensive_optimization__multi__lead (campaign 23360844222, predicted action cost +149pp)
- [✓] **DO_NOT_ACT** auto_comprehensive_optimization__multi__lead (campaign 23374800160, predicted action cost +149pp)
- [✓] **DO_NOT_ACT** auto_comprehensive_optimization__multi__lead (campaign 23396642873, predicted action cost +149pp)
- [✓] **DO_NOT_ACT** auto_comprehensive_optimization__multi__lead (campaign 23051560964, predicted action cost +149pp)
- [✓] **DO_NOT_ACT** auto_comprehensive_optimization__multi__lead (campaign 23821898074, predicted action cost +149pp)
