# Biashara Intelligence — Architecture Mapping
## Valentine's BSc Economics & Statistics → Product Architecture

> Every line of code in this platform traces back to a specific economic or
> statistical concept from Valentine's 42-unit degree at Masinde Muliro University.

---

## Product → Academic Unit Mapping

### Soko Pulse (FMCG Demand Forecasting)
| Unit | Method | Application |
|------|--------|-------------|
| **STA 244** | ARIMA/SARIMA, Holt-Winters, STL decomposition | Price forecasting, seasonal patterns |
| **ECO 424** | Log-log regression, IV, robust SE | Price elasticity estimation, causal analysis |
| **ECO 201** | Supply-demand, PED, consumer surplus | Market efficiency measurement |
| **ECO 203** | Laspeyres, Paasche, Fisher indices | Market price indices |
| **STA 241** | Log-normal, gamma, extreme value | Price distribution modeling |
| **ECO 210** | LP, break-even, optimization | Inventory management |
| **ECO 305** | Gravity model, exchange rate | Cross-border intelligence |

### Biashara Pulse (Government MSME Activity Index)
| Unit | Method | Application |
|------|--------|-------------|
| **ECO 203** | Index construction, seasonal adjustment | Activity indices (Laspeyres, Fisher) |
| **ECO 205** | GDP methodology, IS-LM, AD-AS | Informal GDP estimation, business cycles |
| **STA 245** | HDI, MPI, SDG monitoring | Development indicators |
| **ECO 322** | Nowcasting, HANK models | Real-time economic monitoring |
| **STA 442** | PCA, factor analysis | Composite index construction |
| **STA 341** | Bootstrap CI, MLE | Uncertainty quantification |

### Alama Score (Transaction-Based Credit Scoring)
| Unit | Method | Application |
|------|--------|-------------|
| **STA 341** | MLE (logit), Bayesian (Beta-Binomial), shrinkage | Credit model estimation, cold-start |
| **STA 444** | KDE, bootstrap CI, LOESS | Default distribution, score calibration |
| **STA 442** | Factor analysis, LDA, PCA, clustering | Latent creditworthiness, classification |
| **ECO 206** | Adverse selection, moral hazard, screening | Credit market design |
| **ECO 321** | Information economics, mechanism design | Scoring as screening mechanism |
| **ECO 424** | Logit/Probit, Heckman correction | Binary outcome modeling, selection bias |
| **STA 342** | LRT, A/B testing, fairness tests | Model validation |

### Jamii Insights (NGO Financial Inclusion)
| Unit | Method | Application |
|------|--------|-------------|
| **STA 246** | Life tables, cohort-component, migration | Demographic analysis, workforce planning |
| **ECO 401** | Lewis model, Sen's capability, poverty traps | Development framework |
| **ECO 206** | Financial inclusion, group lending, M-Pesa | Financial services design |
| **ECO 204** | FGT poverty, Gini, Theil, gender analysis | Poverty and inequality measurement |
| **STA 245** | SDG monitoring, composite indices | Development tracking |
| **ECO 106** | Health-productivity nexus | Health-economic intelligence |

### Tax Base Estimation
| Unit | Method | Application |
|------|--------|-------------|
| **ECO 421** | Tax incidence, DWL, Ramsey rule, Laffer | Revenue optimization |
| **ECO 203** | Index numbers, regression | Revenue tracking, elasticity |
| **ECO 422** | Industry-specific compliance | Sector tax profiles |
| **STA 341** | Bayesian compliance estimation | Limited data handling |

### Distribution Gap Analysis
| Unit | Method | Application |
|------|--------|-------------|
| **ECO 422** | HHI, barriers to entry, Hotelling | Market structure analysis |
| **ECO 210** | LP, optimization, break-even | Expansion planning |
| **ECO 201** | Spatial price analysis | Market integration |
| **STA 444** | KDE, non-parametric regression | Coverage estimation |
| **ECO 305** | Gravity model | Cross-border gaps |

---

## Shared Infrastructure

### Statistical Foundation (`app/services/statistical_foundation.py`)
- **STA 241**: Probability distributions, sufficient statistics
- **STA 443**: Measure theory, conditional expectation
- **STA 341**: Bayesian estimation, MLE, bootstrap
- **STA 444**: KDE, non-parametric methods
- **STA 342**: Hypothesis testing

### Econometric Engine (`app/services/econometric_engine.py`)
- **ECO 414**: OLS, robust SE, R², F-test
- **ECO 424**: Logit/Probit, IV/2SLS, Heckman, panel data, time series
- **ECO 203**: Index number construction
- **STA 244**: Exponential smoothing (SES, Holt, Holt-Winters)

---

## Android Agent → Theory Mapping

| Agent | Theory | Key Concept |
|-------|--------|-------------|
| BusinessAgent | Producer Theory (ECO 201) | Q=f(K,L), cost minimization |
| AnalysisAgent | Econometrics (ECO 414/424) | Regression, causal inference |
| AdvisorAgent | Behavioral Economics (ECO 321) | Nudges, prospect theory |
| LearningAgent | Endogenous Growth (ECO 401) | Human capital accumulation |
| IntentRouter | Consumer Theory (ECO 201) | Utility maximization |
| BusinessPatternTracker | Time Series (STA 244) | Pattern detection, stationarity |
| Orchestrator | Mechanism Design (ECO 321) | Agent coordination |
| AdaptiveLearningEngine | Bayesian Estimation (STA 341) | Prior → Data → Posterior |

---

## Data Flow

```
Transaction → Statistical Foundation (STA 241/443/341)
           → Econometric Engine (ECO 414/424)
           → Analysis Methods (STA 444, STA 442, STA 244)
           → Intelligence Products (6 services)
           → API Response
```

---

*Generated: 2026-07-01 | Biashara Intelligence Architecture v2.0*
