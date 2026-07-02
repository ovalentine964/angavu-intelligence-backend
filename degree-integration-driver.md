# Degree Integration Driver — Valentine's BSc Economics & Statistics
## Every Intelligence Product Driven by Specific Degree Concepts

**Date:** 2026-07-02
**Degree:** BSc Economics & Statistics, Masinde Muliro University (42 Units)
**Repos:** biashara-intelligence-backend, msaidizi-app
**Purpose:** Ensure every product and feature is explicitly driven by specific degree units, not ad-hoc engineering.

---

## How to Read This Document

Each product lists the **degree units that drive it**, what **concept** from that unit is applied, **how** it's applied in code, and **where** the code lives. This is not a reference — it is a **driver**: every implementation decision should trace back to a degree concept.

---

## 1. Soko Pulse — Market Intelligence Engine

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 203 | Index numbers (Laspeyres) | Pᴸ = Σp₁q₀/Σp₀q₀ — base-weighted price index per product per area | econometric_engine.py:L333, biashara_pulse.py:L104 |
| ECO 203 | Index numbers (Paasche) | Pᴾ = Σp₁q₁/Σp₀q₁ — current-weighted price index | econometric_engine.py:L359, biashara_pulse.py:L126 |
| ECO 203 | Index numbers (Fisher) | Pᶠ = √(Pᴸ × Pᴾ) — ideal index satisfying time reversal | econometric_engine.py:L385, biashara_pulse.py:L149 |
| ECO 203 | Index numbers (Törnqvist) | ln(Pᵀ) = Σ(½(s₀+s₁))×ln(p₁/p₀) — superlative index with share weights | econometric_engine.py:L414, biashara_pulse.py:L167 |
| ECO 203 | Seasonal decomposition | Y = T + S + C + I — additive decomposition for demand patterns | soko_pulse.py:L87, seasonal_analyzer.py |
| STA 244 | Exponential smoothing (SES) | Sₜ₊₁ = αXₜ + (1-α)Sₜ — short-term price forecasting | econometric_engine.py:L460 |
| STA 244 | Holt-Winters | Level + trend + seasonality — medium-term price prediction | soko_pulse.py:L139 |
| STA 244 | ARIMA (simplified) | AR(1)-style forecast for price trend extrapolation | soko_pulse.py:L228 |
| STA 244 | ACF/Seasonality detection | Autocorrelation at lags 7, 30 for weekly/monthly seasonality | AnalysisAgent.kt:L364 |
| STA 244 | MAPE accuracy | Forecast accuracy metric: Σ|A-F|/A × 100/n | econometric_engine.py:L497 |
| STA 244 | Forecast confidence intervals | ±1.96σ prediction intervals on price forecasts | econometric_engine.py:L494 |
| ECO 101 | Price elasticity (PED) | Log-log OLS: ln(Q) = α + β·ln(P), β = PED — demand sensitivity | soko_pulse.py:L344 |
| ECO 101 | Consumer surplus | ∫D(Q)dQ − P*×Q* — welfare measurement for market analysis | soko_pulse.py:L419 |
| ECO 101 | Elasticity classification | Elastic (|β|>1), inelastic (|β|<1), unit elastic (|β|=1) | BusinessAgent.kt:L115 |
| STA 346 | CUSUM drift detection | Cumulative sum control for detecting structural price breaks | distribution_gap.py:L197, CusumDriftTracker.kt |
| STA 346 | Control chart limits (X̄, R) | 3σ control limits for price monitoring | distribution_gap.py:L153 |
| ECO 202 | Sampling methods | Simple random, stratified, cluster — representative price samples | sampling.py |
| ECO 202 | Confidence intervals | Wald CIs for mean prices, proportion CIs for market shares | confidence_intervals.py:L76 |
| STA 444 | Kernel Density Estimation | Gaussian KDE with Silverman bandwidth for price distributions | statistical_foundation.py:L171 |
| STA 444 | Multimodality detection | Peak detection in KDE — identifies bimodal price markets | statistical_foundation.py:L206 |
| ECO 305 | Gravity model of trade | Trade flow = f(GDP₁, GDP₂, distance) — cross-border price intelligence | **TODO: Implement in soko_pulse.py** |
| ECO 305 | Cross-border price comparison | Multi-market price comparison with FX-adjusted prices | soko_pulse.py (multi-market) |

### Implementation Notes

- **Formulas:** All four index numbers must be computed in parallel for every product-area pair. Fisher is the default report index; Törnqvist for welfare analysis.
- **Edge cases:** Zero-quantity periods (holidays), single-observation areas (use Bayesian shrinkage from STA 341), outlier prices (>5σ from median).
- **Academic references:** Diewert (1976) for superlative indices; Holt (1957), Winters (1960) for smoothing; Hyndman & Athanasopoulos for ARIMA.
- **TODO:** Implement full ARIMA(p,d,q) via Box-Jenkins methodology (STA 244 gap). Implement Granger causality for lead-lag price discovery between markets.

---

## 2. Biashara Pulse — Business Intelligence Engine

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 205 | Business cycle detection | Hodrick-Prescott filter: min Σ(yₜ−τₜ)² + λΣ(τₜ₊₁−2τₜ+τₜ₋₁)² | biashara_pulse.py:L196 |
| ECO 205 | Cycle phase classification | Expansion/peak/contraction/trough from HP cycle component | biashara_pulse.py:L233 |
| ECO 205 | GDP methodology (informal) | Activity index = f(transaction_volume, avg_margin, sector_multiplier) approximates informal GDP | biashara_pulse.py (GDP section) |
| ECO 205 | National income accounting | Expenditure approach: GDP = C + I + G + (X-M) — adapted for informal sector | biashara_pulse.py |
| STA 245 | Composite activity index | Weighted composite: Σwᵢxᵢ where weights from PCA (STA 442) | biashara_pulse.py:L318 |
| STA 245 | Development indicators | Sector health, growth rates, inequality as development proxies | biashara_pulse.py |
| STA 245 | Labor market statistics | Business formation/destruction rates as employment proxies | **TODO: Implement employment monitor** |
| ECO 322 | Nowcasting | Real-time GDP estimation from high-frequency transaction data | biashara_pulse.py (activity index) |
| STA 341 | Bootstrap confidence intervals | Percentile bootstrap for uncertainty on GDP/activity estimates | statistical_foundation.py:L225 |
| STA 341 | Bayesian shrinkage | Bayesian credible intervals when sample size is small per county | statistical_foundation.py:L80 |
| STA 244 | Time series forecasting | SES, Holt, Holt-Winters for activity trend prediction | econometric_engine.py:L443-530 |
| ECO 203 | Index numbers | Laspeyres/Paasche/Fisher/Törnqvist for sector price indices | econometric_engine.py:L333-440 |
| ECO 104 | Matrix algebra | Eigenvalue decomposition for PCA-based composite indices | numpy operations throughout |
| STA 442 | PCA | Principal Component Analysis for optimal index weights | alama_score.py:L180 |

### Implementation Notes

- **HP filter λ:** Standard values — 100 for annual, 1600 for quarterly, 129600 for monthly data. Kenyan informal data is daily; use 129600 and aggregate to monthly.
- **Activity index formula:** `activity_index = (transactions_per_day × avg_margin × sector_GDP_share) / baseline`. Baseline = 12-month rolling average.
- **Edge cases:** New counties with <6 months data (use national average as prior), sector-level aggregation when <10 workers in a county-sector cell.
- **Academic references:** Hodrick & Prescott (1997), Burns & Mitchell (1946) for cycle dating, KNBS SNA 2008 methodology.
- **TODO:** Implement full IS-LM simulation (ECO 205 gap). Add Taylor rule monetary policy indicator (ECO 205 gap).

---

## 3. Alama Score — Credit Intelligence Engine

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| STA 341 | MLE (Maximum Likelihood) | Newton-Raphson for logit: β̂ = argmax Σ[yᵢln(Λ(Xᵢβ)) + (1-yᵢ)ln(1-Λ(Xᵢβ))] | econometric_engine.py:L191 |
| STA 341 | Bayesian estimation (Beta-Binomial) | Conjugate prior for cold-start: α_post = α_prior + successes, β_post = β_prior + failures | statistical_foundation.py:L30 |
| STA 341 | Bayesian estimation (Normal-Normal) | Price estimation with shrinkage: μ_post = (τ²μ_prior + σ²x̄)/(τ² + σ²) | statistical_foundation.py:L80 |
| STA 341 | Bootstrap confidence intervals | Percentile bootstrap CI on credit scores for uncertainty quantification | statistical_foundation.py:L225 |
| STA 341 | Wald confidence intervals | CI on logit coefficients: β̂ ± z_{α/2} × SE(β̂) | confidence_intervals.py:L76 |
| STA 341 | Shrinkage factor | k = data_precision / posterior_precision — pulls extreme estimates toward prior | statistical_foundation.py:L118 |
| STA 442 | PCA (Principal Component Analysis) | SVD-based dimensionality reduction of credit features | alama_score.py:L180 |
| STA 442 | Factor Analysis | Common factor extraction for latent creditworthiness factors | alama_score.py:L226 |
| STA 442 | Varimax rotation | Orthogonal rotation for interpretable factor structure | alama_score.py:L291 |
| STA 442 | LDA (Fisher's Linear Discriminant) | Classify into credit risk tiers: max w'SBw / w'SWw | alama_score.py:L322 |
| STA 442 | KDE | Non-parametric density estimation of credit score distributions | alama_score.py:L379 |
| STA 442 | LOESS smoothing | Local polynomial regression for score calibration curves | alama_score.py:L420 |
| ECO 206 | Credit scoring (logit) | Logistic regression P(default=1|X) = 1/(1+e^(-Xβ)) | econometric_engine.py:L171, alama_score.py:L66 |
| ECO 206 | Bayesian credit updating | Beta-Binomial for cold-start workers with <90 days data | alama_score.py:L135 |
| ECO 206 | Adverse selection (screening) | Alama Score as self-selection mechanism — high-quality workers opt in | ARCHITECTURE_MAPPING.md |
| ECO 321 | Information economics (Akerlof) | Market for lemons — credit market failure without information | ARCHITECTURE_MAPPING.md |
| ECO 321 | Spence signaling | Transaction consistency as credible signal of business quality | alama_score.py (transaction regularity feature) |
| ECO 424 | Logit (MLE) | Full implementation with marginal effects: ∂P/∂Xᵢ = βᵢ·Λ(Xβ)·(1-Λ(Xβ)) | econometric_engine.py:L275 |
| ECO 424 | Probit (MLE) | Newton-Raphson for Heckman Step 1 selection equation | heckman_correction.py:L551 |
| ECO 424 | Heckman two-step | Corrects selection bias: Step 1 probit → IMR → Step 2 OLS | econometric_engine.py:L563, heckman_correction.py:L220 |
| ECO 424 | OLS with robust SE | White sandwich estimator: (X'X)⁻¹X'ΩX(X'X)⁻¹ | econometric_engine.py:L93 |
| MAT 121 | Marginal effects | ∂P/∂Xᵢ = βᵢ × Λ(Xβ) × (1−Λ(Xβ)) at sample mean | econometric_engine.py:L275 |
| STA 142 | Bayes' theorem | P(creditworthy|data) ∝ P(data|creditworthy) × P(creditworthy) | statistical_foundation.py:L30 |
| STA 241 | Beta distribution | Conjugate prior for binomial credit outcomes | statistical_foundation.py:L30 |
| STA 241 | Distribution fitting | KS goodness-of-fit for score distribution validation | statistical_foundation.py:L316 |
| ECO 210 | MLE optimization | Newton-Raphson: β_{t+1} = β_t - H⁻¹g where H = Hessian, g = gradient | econometric_engine.py:L220 |
| ECO 104 | Matrix inversion | OLS: β̂ = (X'X)⁻¹X'Y — core of all regression models | econometric_engine.py |
| STA 347 | Newton-Raphson | Iterative MLE solver with convergence check (‖Δβ‖ < 1e-6) | econometric_engine.py:L220 |
| STA 347 | Bootstrap | Non-parametric CI on credit scores | statistical_foundation.py:L225 |

### Implementation Notes

- **Score formula:** `alama_score = 100 × Σ(wᵢ × fᵢ(X))` where fᵢ are factor analysis scores, wᵢ are LDA-optimal weights.
- **Cold-start protocol:** Workers with <90 days get Beta-Binomial posterior with informative prior (industry default rate). Score = posterior mean × 100.
- **Heckman correction:** Apply when analyzing credit access (workers who applied vs. all workers). Step 1: probit(application|X). Step 2: OLS(repayment|X, IMR).
- **Edge cases:** Perfect separation in logit (use Firth's penalized MLE), multicollinearity (drop VIF > 5 features), temporal drift (retrain quarterly).
- **Academic references:** Cox (1958) for logit, Heckman (1979) for selection correction, Hotelling (1933) for PCA, Fisher (1936) for LDA.
- **TODO:** Implement IV/2SLS for causal validation (does credit CAUSE income growth?). Implement cluster analysis (K-means) for borrower segmentation.

---

## 4. Jamii Insights — Community Intelligence Engine

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| STA 246 | Abridged life tables | Construct life tables from transaction activity patterns (proxy for survival) | jamii_insights.py:L201 |
| STA 246 | Dependency ratio | DR = (pop_0_14 + pop_65+) / pop_15_64 — from worker age proxies | jamii_insights.py:L271 |
| ECO 100 | Gini coefficient | G = (2Σ(i×yi))/(n×Σyi) − (n+1)/n — income inequality | jamii_insights.py:L46 |
| ECO 100 | FGT poverty measure | Pα = (1/n)Σ((z−yi)/z)^α for yi<z — P0=headcount, P1=gap, P2=severity | jamii_insights.py:L138 |
| ECO 204 | Theil index | T = (1/n)Σ(yi/ȳ)ln(yi/ȳ) — GE(1) entropy inequality | jamii_insights.py:L74 |
| ECO 204 | Atkinson index | A = 1−(1/nΣ(yi/ȳ)^(1−ε))^(1/(1−ε)) — with inequality aversion ε | jamii_insights.py:L103 |
| ECO 204 | Lorenz curve | Cumulative income share plot: L(p) = (1/μ)∫₀ᵖ F⁻¹(t)dt | jamii_insights.py:L176 |
| ECO 204 | Gender analysis | Youth/women segmentation, gender-disaggregated financial inclusion | jamii_insights.py:L646, L659, L663 |
| ECO 401 | Development economics | Lewis dual sector model — formal/informal labor allocation | **TODO: Implement Lewis model** |
| ECO 401 | Sen's capability approach | Functionings vector: health, education, economic participation | **TODO: Implement capability index** |
| ECO 401 | Poverty traps | Threshold model: if wealth < w*, convergence to low steady state | **TODO: Implement poverty trap detection** |
| ECO 401 | Structural transformation | Sector shares over time: agriculture ↓, services ↑ as economy develops | jamii_insights.py (sector composition) |
| ECO 206 | Microfinance/financial inclusion | Savings rate, credit access, insurance penetration by community | jamii_insights.py |
| STA 245 | Development indicators | HDI-like composite from economic participation data | **TODO: Implement HDI construction** |
| STA 245 | Composite indices | Weighted composite of inequality, poverty, inclusion metrics | jamii_insights.py (index construction) |
| STA 442 | Cluster analysis | K-means for community typology (emerging, growing, mature, declining) | **TODO: Implement K-means clustering** |
| STA 442 | Multivariate analysis | Joint distribution of income, savings, credit, insurance | alama_score.py (PCA/factor analysis) |
| ECO 210 | Quantitative methods | Optimization of community classification thresholds | scipy.optimize |
| STA 341 | Confidence intervals | Bootstrap CI on inequality measures, poverty rates | statistical_foundation.py:L225 |
| BCB 108 | Multilingual reporting | Reports in Swahili, English, Sheng — multilingual templates | report_generator.py, whatsapp_bot.py |
| BCB 108 | Visual data communication | Charts via WhatsApp for community-level insights | whatsapp_charts.py |
| STA 142 | Bayes' theorem | Bayesian updating of community health estimates as new data arrives | statistical_foundation.py:L30 |
| STA 241 | Distribution fitting | KS test for income distribution validation (log-normal expected) | statistical_foundation.py:L316 |

### Implementation Notes

- **Life tables:** Abridged (5-year age groups). Use transaction activity as proxy for "alive in business." Lx = active workers in age group x.
- **Dependency ratio:** Compute from business age distribution. Workers <2 years = "young dependents," >15 years = "elderly."
- **FGT poverty line:** z = 60% of median transaction income per area. Recompute quarterly.
- **Gender analysis:** Use business_type as proxy (mama_mboga = female-coded, boda_boda = male-coded). Document assumption explicitly.
- **Academic references:** Sen (1976) for capability approach, Lewis (1954) for dual sector, Foster-Greer-Thorbecke (1984) for poverty measures, Atkinson (1970) for inequality.
- **TODO:** Implement Lewis model simulation, Alkire-Foster MPI, Lee-Carter mortality model, HDI construction.

---

## 5. Real-Time GDP Estimator (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 205 | GDP methodology | Expenditure approach: GDP = C + I + G + (X-M). Adapt: informal GDP = Σ(sectors) [transaction_volume × avg_margin × multiplier] | gdp_estimator.py |
| ECO 205 | IS-LM model | Goods market equilibrium: Y = C(Y-T) + I(r) + G — sets the theoretical frame for GDP estimation | gdp_estimator.py |
| ECO 205 | AD-AS model | Aggregate demand-supply for understanding inflation-output tradeoff | gdp_estimator.py |
| ECO 102 | GDP measurement | Three approaches (expenditure, income, output) — use output approach for informal: Σ value-added by sector | gdp_estimator.py |
| ECO 102 | Business cycles | HP filter decomposition: GDP = trend + cycle. Cycle = short-term fluctuations | biashara_pulse.py:L196 |
| STA 244 | Time series forecasting | SES/Holt-Winters for GDP trend extrapolation | econometric_engine.py:L443-530 |
| STA 244 | Forecast confidence intervals | ±1.96σ prediction intervals on GDP estimates | econometric_engine.py:L494 |
| ECO 322 | Nowcasting | Bridge equation: GDP_t = f(high_frequency_indicators_t) — monthly GDP from daily transactions | gdp_estimator.py |
| ECO 322 | Business cycle (HP filter) | Detrending GDP to extract cyclical component for nowcasting | biashara_pulse.py:L196 |
| STA 341 | Estimation theory | MLE for sector multipliers, Cramér-Rao bound for minimum variance | econometric_engine.py:L191 |
| STA 341 | Confidence intervals | Bootstrap CI on GDP estimates: percentile method | statistical_foundation.py:L225 |
| STA 342 | Hypothesis testing | Is GDP change statistically significant? t-test: H₀: ΔGDP = 0 | hypothesis_testing.py:L278 |
| STA 342 | Multiple testing correction | Bonferroni/BH when testing GDP change across 47 counties simultaneously | hypothesis_testing.py:L142-206 |
| STA 245 | Social & economic statistics | Sector classification, employment proxies, output measurement | biashara_pulse.py |
| ECO 103 | Matrix algebra | OLS for bridge equation: β̂ = (X'X)⁻¹X'Y | econometric_engine.py |
| ECO 210 | MLE | Maximum likelihood for sector-specific output functions | econometric_engine.py:L191 |
| STA 347 | Bootstrap | Non-parametric uncertainty quantification for GDP estimates | statistical_foundation.py:L225 |

### Implementation Notes

- **Core formula:** `informal_GDP_county = Σ_sectors [avg_daily_transactions × avg_margin × sector_GDP_multiplier × working_days]`
- **Sector multipliers:** Estimated from KNBS input-output tables (Leontief inverse). Update annually.
- **Nowcasting bridge equation:** Regress quarterly KNBS GDP on monthly Biashara transaction indices. Use coefficient to nowcast current quarter.
- **Edge cases:** New sectors with no historical data (use national average multiplier), extreme transaction spikes (winsorize at 99th percentile).
- **Academic references:** SNA 2008 (UN), Aruoba et al. (2011) for real-time GDP nowcasting, Banbura et al. (2013) for mixed-frequency models.
- **Confidence intervals:** Report as "KSh X.X billion (95% CI: X.X – X.X)" — this is what makes it academic-grade.

---

## 6. Real-Time Inflation Tracker (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 203 | Laspeyres index | Pᴸ = Σp₁q₀/Σp₀q₀ — base-weighted CPI analog | econometric_engine.py:L333 |
| ECO 203 | Paasche index | Pᴾ = Σp₁q₁/Σp₀q₁ — current-weighted CPI analog | econometric_engine.py:L359 |
| ECO 203 | Fisher ideal index | Pᶠ = √(Pᴸ × Pᴾ) — satisfies time and factor reversal tests | econometric_engine.py:L385 |
| ECO 203 | Törnqvist index | ln(Pᵀ) = Σ(½(s₀+s₁))×ln(p₁/p₀) — superlative cost-of-living index | econometric_engine.py:L414 |
| ECO 203 | CPI construction | Basket definition, weight estimation, price collection methodology | inflation_tracker.py |
| ECO 203 | Seasonal decomposition | Y = T + S + C + I — separate seasonal from underlying inflation | seasonal_analyzer.py |
| STA 244 | Time series forecasting | Inflation trend detection: SES for short-term, Holt for trend | econometric_engine.py:L443-530 |
| STA 244 | Stationarity | ADF test on price series before modeling (implement ADF) | **TODO: Implement ADF test** |
| ECO 202 | Economic statistics | Data collection standards, sampling design for price surveys | sampling.py |
| STA 346 | Quality control (SPC) | Control charts on data quality: flag anomalous price reports | data_quality.py:L177 |
| STA 346 | CUSUM charts | Detect structural breaks in inflation (supply shocks, policy changes) | distribution_gap.py:L197 |
| STA 444 | KDE | Non-parametric density of price changes — identify fat tails | statistical_foundation.py:L171 |
| STA 341 | Bayesian estimation | Shrinkage estimates for areas with sparse price data | statistical_foundation.py:L80 |
| STA 342 | Hypothesis testing | Is inflation rate significantly different from target? z-test | hypothesis_testing.py |
| ECO 102 | Inflation and monetary policy | CPI → monetary policy decisions (CBK target = 5% ± 2.5%) | inflation_tracker.py |

### Implementation Notes

- **Basket construction:** Use transaction frequency weights (not survey weights). If unga appears in 80% of transactions, its weight ≈ 0.08 in the basket.
- **Four indices in parallel:** Always compute all four. Fisher for headlines, Törnqvist for welfare analysis, Laspeyres for policy comparability with KNBS.
- **Core formula:** `inflation_rate_mom = (Fisher_index_t / Fisher_index_{t-1} - 1) × 100`
- **Core formula:** `inflation_rate_yoy = (Fisher_index_t / Fisher_index_{t-12} - 1) × 100`
- **Edge cases:** Product substitution (update basket quarterly), quality changes (hedonic adjustment for electronics), new products (imputation).
- **Academic references:** Diewert (1976), IMF CPI Manual (2004), Balk (2008).
- **Public dashboard:** Free — drives inbound leads. Shows daily inflation by county.

---

## 7. Worker Onboarding (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| BCB 108 | Business communication | Multilingual onboarding flow: Swahili, English, Sheng, local languages | whatsapp_bot.py |
| BCB 108 | Shannon-Weaver model | Communication channel: sender (app) → message (onboarding) → receiver (worker) → feedback (completion rate) | **TODO: Implement onboarding analytics** |
| BCB 108 | Cross-cultural communication | Adapt onboarding tone, examples, and flow to cultural context | report_templates/intelligence_report.py |
| BCB 108 | 7Cs of business writing | Clear, concise, concrete, correct, coherent, complete, courteous onboarding text | whatsapp_bot.py |
| ECO 100 | Development concepts | Understanding worker context: poverty traps, capability constraints, informal economy dynamics | ARCHITECTURE_MAPPING.md |
| STA 246 | Demography | Population-level onboarding strategy: age distribution, literacy rates, phone penetration | **TODO: Implement onboarding funnel analytics** |
| ECO 204 | African development | Cultural sensitivity: communal values, trust-building, language-first approach | report_templates/ |
| STA 245 | Social statistics | Sampling design for A/B testing onboarding flows | sampling.py |
| STA 342 | Hypothesis testing | A/B test onboarding variants: χ² test on completion rates | hypothesis_testing.py |
| STA 343 | Experimental design | CRD for onboarding flow experiments, RCBD for demographic blocks | experimental_design.py:L256, L290 |
| ECO 201 | Behavioral economics | Nudge theory: default options, framing effects in onboarding choices | ARCHITECTURE_MAPPING.md |
| STA 142 | Probability theory | Bayesian A/B testing for onboarding conversion rates | statistical_foundation.py:L30 |

### Implementation Notes

- **Onboarding funnel:** Language selection → business type → first transaction → first report. Track drop-off at each step.
- **A/B testing:** Use RCBD with blocks = (language × business_type × literacy_level). Minimum detectable effect = 5% completion rate improvement.
- **Cultural adaptation:** Mama mboga onboarding uses food examples. Boda boda uses trip examples. Don't use banking jargon.
- **Academic references:** Kahneman & Tversky (1979) for prospect theory, Thaler & Sunstein (2008) for nudge theory.

---

## 8. Critical Mass Dashboard (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| STA 245 | Social & economic statistics | Representative sampling: coverage targets per county, per sector | sampling.py |
| STA 245 | Population statistics | Worker density per area, population-weighted sampling | sampling.py |
| STA 442 | Multivariate analysis | Cluster analysis: segment workers into acquisition priority groups | **TODO: Implement K-means** |
| STA 442 | PCA | Dimensionality reduction of acquisition metrics (cost, retention, data quality) | alama_score.py:L180 |
| ECO 210 | Quantitative methods | Optimization: minimize cost per critical-mass county subject to coverage constraints | scipy.optimize |
| STA 341 | Estimation theory | Confidence intervals on worker counts per county: bootstrap CI | statistical_foundation.py:L225 |
| STA 341 | Bayesian estimation | Posterior estimate of true worker population from observed Msaidizi users | statistical_foundation.py:L30 |
| ECO 201 | Consumer theory | Utility maximization: which counties give highest data value per acquisition dollar? | **TODO: Implement acquisition optimization** |
| STA 342 | Hypothesis testing | Test: has county X reached critical mass? H₀: n < n_threshold | hypothesis_testing.py |
| STA 346 | Quality control | Control charts on acquisition rate — detect if strategy is working | distribution_gap.py:L153 |
| ECO 103 | Optimization | Lagrangian: min C = Σcᵢnᵢ s.t. coverage ≥ 80% in each county | scipy.optimize |
| STA 244 | Time series | Forecast time-to-critical-mass per county based on current growth rate | econometric_engine.py |

### Implementation Notes

- **Critical mass definition:** County has critical mass when `active_users / informal_workers ≥ 0.5%` AND `transactions_per_day ≥ 100`. Use KNBS informal employment data as denominator.
- **Cluster analysis:** Features = [acquisition_cost, retention_30d, data_quality_score, market_size]. K=4 clusters: fast-cheap, fast-expensive, slow-cheap, slow-expensive.
- **Optimization:** `min Σ(cost_i × users_i)` subject to `coverage_j ≥ threshold` for all counties j. Solve via linear programming.
- **Edge cases:** Rural counties with very small informal sectors (threshold = absolute minimum, not percentage), conflict-affected areas.

---

## 9. Outcome-Based Pricing (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 201 | Price elasticity of demand | PED for intelligence products: how much does demand change with price? | pricing.py |
| ECO 201 | Consumer surplus | Value captured by buyer = WTP - price. Set price to capture ≤50% of surplus | pricing.py |
| ECO 201 | Market structures | Monopoly pricing (Biashara is sole provider) → price discrimination | pricing.py |
| ECO 201 | Game theory | Pricing as Stackelberg game: Biashara leads, buyers follow | **TODO: Implement pricing game model** |
| ECO 421 | Ramsey pricing | P = MC / (1 - λ/ε) — inverse elasticity rule for multi-product pricing | tax_base.py:L109 |
| ECO 421 | Tax incidence | Who bears the cost? Elasticity-based incidence analysis for pricing design | tax_base.py:L160 |
| ECO 421 | Deadweight loss | DWL = ½ × t² × ε × Q — minimize DWL in pricing | tax_base.py:L137 |
| ECO 421 | Laffer curve | Revenue-maximizing price point: R(p) = p × D(p) | tax_base.py:L62 |
| ECO 422 | Market structure (HHI) | HHI = Σsᵢ² — concentration of intelligence buyers | distribution_gap.py:L46 |
| ECO 422 | Barriers to entry | Switching costs as barrier: outcome contracts create lock-in | distribution_gap.py:L87 |
| STA 342 | Hypothesis testing | A/B test pricing models: is outcome-based > subscription revenue? | hypothesis_testing.py, experimental_design.py:L367 |
| STA 343 | Experimental design | Randomized pricing experiments across buyer segments | experimental_design.py:L256 |
| STA 341 | Bayesian estimation | Dynamic pricing: update price beliefs from observed conversion rates | statistical_foundation.py:L30 |
| ECO 101 | Supply-demand equilibrium | Equilibrium price where buyer WTP = seller marginal cost | **TODO: Implement pricing equilibrium** |
| ECO 101 | Elasticity classification | Elastic (|β|>1) → lower price; inelastic (|β|<1) → raise price | BusinessAgent.kt:L115 |
| ECO 321 | Information economics | Screening: outcome pricing separates high- from low-value buyers | ARCHITECTURE_MAPPING.md |
| ECO 321 | Mechanism design | Design pricing mechanism that reveals true buyer valuation | **TODO: Implement VCG-style pricing** |

### Implementation Notes

- **Ramsey pricing formula:** For multi-product pricing: `pᵢ = mcᵢ / (1 - λ/εᵢ)` where λ is the Lagrange multiplier on the revenue constraint and εᵢ is demand elasticity for product i.
- **Outcome-based contract structure:** Base subscription (covers costs) + outcome bonus (aligns incentives). Outcome bonus ≤ 2× base.
- **A/B testing:** Randomize pricing across comparable buyers. Minimum 30 buyers per arm. Run for 6 months minimum.
- **Edge cases:** Buyer with monopsony power (government), buyer with high WTP but low elasticity (they'll pay more), price-sensitive new entrants.
- **Academic references:** Ramsey (1927), Tirole (1988) for industrial organization, Myerson (1981) for mechanism design.

---

## 10. Tax Base Estimation (EXISTING)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 421 | Tax incidence | Supply/demand elasticity-based: who bears the tax burden? | tax_base.py:L160 |
| ECO 421 | Deadweight loss | DWL = ½ × t² × ε × Q — efficiency cost of taxation | tax_base.py:L137 |
| ECO 421 | Laffer curve | Revenue = t × base(t) — revenue-maximizing tax rate | tax_base.py:L62 |
| ECO 421 | Ramsey tax rate | Inverse elasticity rule: t* = λ/ε — optimal commodity taxation | tax_base.py:L109 |
| ECO 421 | Optimal tax rate | Mirrlees-inspired optimal rate from income distribution data | tax_base.py:L89 |
| STA 341 | Bootstrap CI | Uncertainty on tax revenue estimates | tax_base.py:L199 |
| ECO 101 | Elasticity | Price elasticity of taxable supply — how much does formalization change with tax rate? | tax_base.py |
| STA 245 | Economic statistics | Sector-level taxable income estimation from transaction data | tax_base.py |
| STA 342 | Hypothesis testing | Test: did tax policy change affect formalization rate? | hypothesis_testing.py |

### Implementation Notes

- **Tax base formula:** `estimated_tax_base = Σ_sectors [avg_monthly_revenue × estimated_profit_margin × formalization_probability]`
- **Formalization probability:** From logit model: P(formal|X) = 1/(1+e^(-Xβ)) where X = [revenue, age, location, sector]
- **Academic references:** Ramsey (1927), Mirrlees (1971), Feldstein (1999) for optimal taxation.

---

## 11. Distribution Gap Analysis (EXISTING)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 422 | HHI (Herfindahl-Hirschman) | HHI = Σsᵢ² — market concentration measurement | distribution_gap.py:L46 |
| ECO 422 | Concentration ratio (CR4) | Sum of top 4 firms' market share | distribution_gap.py:L68 |
| ECO 422 | Barriers to entry | Classification: scale economies, capital requirements, regulatory | distribution_gap.py:L87 |
| STA 346 | Control chart limits | 3σ limits for distribution coverage monitoring | distribution_gap.py:L153 |
| STA 346 | CUSUM drift detection | Detect changes in market coverage over time | distribution_gap.py:L197 |
| STA 346 | Process capability (Cp, Cpk) | How capable is the distribution network? Cp = (USL-LSL)/6σ | distribution_gap.py:L245 |
| ECO 201 | Market structure | Perfect competition vs. monopoly classification by area | distribution_gap.py |
| STA 245 | Economic statistics | Area-level market sizing from transaction volumes | distribution_gap.py |

---

## 12. Insurance Risk Assessment (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| STA 341 | MLE | Logit/probit for claim probability estimation | econometric_engine.py:L191 |
| STA 341 | Bayesian estimation | Beta-Binomial for claim frequency with sparse data | statistical_foundation.py:L30 |
| STA 442 | PCA | Dimensionality reduction of risk features | alama_score.py:L180 |
| STA 442 | Factor Analysis | Latent risk factors: business stability, revenue volatility, sector risk | alama_score.py:L226 |
| STA 442 | LDA | Classify into risk tiers: low/medium/high | alama_score.py:L322 |
| STA 241 | Distribution fitting | Fit claim size distributions: log-normal, gamma, Pareto | statistical_foundation.py:L316 |
| STA 241 | KS goodness-of-fit | Validate distributional assumptions | statistical_foundation.py:L316 |
| STA 142 | Probability theory | Expected loss = P(claim) × E[claim_size] | statistical_foundation.py |
| ECO 101 | Risk and uncertainty | Risk aversion, expected utility theory for premium setting | **TODO: Implement utility-based pricing** |
| STA 341 | Bootstrap | CI on expected loss estimates | statistical_foundation.py:L225 |
| ECO 206 | Microfinance | Understanding informal worker financial behavior | alama_score.py |

### Implementation Notes

- **Risk score formula:** `risk_score = w₁·P(claim) + w₂·E[claim_size|claim] + w₃·revenue_volatility` where weights from factor analysis.
- **Claim size distribution:** Fit Gamma(α, β) via MLE. Use KS test for goodness-of-fit.
- **Academic references:** Klugman et al. (2012) for loss distributions, Bühlmann (1970) for credibility theory.

---

## 13. Employment & Labor Market Monitor (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| STA 246 | Demography | Population-level employment from business activity patterns | **TODO: Implement in jamii_insights.py** |
| STA 246 | Dependency ratios | Active workers vs. population — employment rate proxy | jamii_insights.py:L271 |
| ECO 205 | Labor economics | Employment = f(GDP, wages, expectations) — Okun's law for informal sector | **TODO: Implement Okun's law** |
| STA 245 | Labor market statistics | Unemployment rate proxy: inactive_users / total_users | **TODO: Implement labor stats** |
| STA 244 | Time series | Employment trend forecasting | econometric_engine.py |
| STA 342 | Hypothesis testing | Test: is employment change significant across counties? | hypothesis_testing.py |
| ECO 100 | Development concepts | Employment as development indicator (SDG 8) | ARCHITECTURE_MAPPING.md |
| STA 341 | Estimation | Confidence intervals on employment estimates | confidence_intervals.py |

### Implementation Notes

- **Employment proxy:** `employment_rate = active_businesses_30d / total_registered_businesses`. Active = ≥5 transactions in 30 days.
- **Okun's law adaptation:** Δemployment = α + β·Δactivity_index. Estimate β from historical data.
- **Academic references:** Okun (1962), ILO KILM methodology.

---

## 14. SDG Progress Tracker (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| STA 245 | Development indicators | HDI, MPI, poverty headcount — map to SDG targets | **TODO: Implement SDG mapping** |
| STA 245 | Composite indices | Weighted composite per SDG goal | biashara_pulse.py:L318 |
| ECO 401 | Development economics | Lewis model, Sen capabilities — SDG theoretical framework | ARCHITECTURE_MAPPING.md |
| ECO 100 | HDI construction | Health, education, income dimensions | **TODO: Implement HDI** |
| ECO 204 | Gender analysis | SDG 5: gender equality in economic participation | jamii_insights.py:L646 |
| STA 246 | Demography | SDG indicators: life expectancy proxy, dependency ratios | jamii_insights.py:L201, L271 |
| ECO 206 | Financial inclusion | SDG 8: decent work and economic growth | jamii_insights.py |
| STA 442 | PCA | Optimal weights for SDG composite index | alama_score.py:L180 |
| STA 341 | Bootstrap | Uncertainty on SDG progress estimates | statistical_foundation.py:L225 |

### Implementation Notes

- **SDG mapping:** Goal 1 (poverty) ← FGT P0, Goal 8 (decent work) ← employment rate, Goal 10 (inequality) ← Gini, Goal 17 (partnerships) ← data sharing metrics.
- **Academic references:** UN SDG indicators framework, OPHI MPI methodology.

---

## 15. Gender Economic Intelligence (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 204 | Gender analysis | Women's economic participation, income gaps, sector concentration | jamii_insights.py:L646 |
| ECO 204 | African development | Gender-specific barriers: access to credit, markets, technology | ARCHITECTURE_MAPPING.md |
| ECO 401 | Sen's capability approach | Gender capabilities: education, health, economic agency | **TODO: Implement gender capability index** |
| ECO 401 | Poverty traps | Gender-specific poverty traps: childcare, land rights, market access | **TODO: Implement gender poverty trap model** |
| STA 246 | Demography | Gender-disaggregated population statistics | jamii_insights.py |
| STA 342 | Hypothesis testing | Test: is income gap between men and women significant? | hypothesis_testing.py:L327 |
| STA 341 | Estimation | Bootstrap CI on gender gap estimates | statistical_foundation.py:L225 |
| STA 442 | Cluster analysis | Women's business typology: survival, growth, scaling | **TODO: Implement K-means** |
| ECO 201 | Labor economics | Gender wage gap decomposition (Oaxaca-Blinder) | **TODO: Implement Oaxaca-Blinder** |

### Implementation Notes

- **Gender coding:** Use business_type as proxy. Document assumption: mama_mboga, tailor, hairdresser = female-coded; boda_boda, mechanic, jua_kali = male-coded. Mixed types = unisex.
- **Oaxaca-Blinder decomposition:** Δȳ = (X̄_m - X̄_f)β̂_m + X̄_f(β̂_m - β̂_f). First term = explained (endowments), second = unexplained (discrimination).
- **Academic references:** Sen (1990) for gender and capability, Blinder (1973), Oaxaca (1973) for decomposition.

---

## 16. Market Entry Intelligence Suite (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 422 | Market structure | HHI, CR4, barriers to entry per market | distribution_gap.py:L46, L68, L87 |
| ECO 422 | Price discrimination | First/second/third degree — optimal pricing for market entry | **TODO: Implement pricing discrimination model** |
| ECO 305 | Gravity model | Trade flow = A × (GDP₁^α × GDP₂^β) / distance^γ | **TODO: Implement gravity model** |
| ECO 305 | Comparative advantage | Revealed comparative advantage: RCA = (xᵢ/Xᵢ)/(x/X) | **TODO: Implement RCA** |
| ECO 305 | Terms of trade | ToT = (P_exports / P_exports_base) / (P_imports / P_imports_base) × 100 | **TODO: Implement ToT** |
| ECO 201 | Consumer theory | Demand estimation: utility maximization → Marshallian demand | soko_pulse.py:L344 |
| ECO 201 | Market structures | Cournot/Bertrand competition analysis for market entry | **TODO: Implement competition models** |
| STA 245 | Economic statistics | Market sizing from transaction volume data | biashara_pulse.py |
| STA 442 | Cluster analysis | Consumer segmentation for targeted entry | **TODO: Implement K-means** |
| STA 341 | Estimation | Market size confidence intervals | confidence_intervals.py |

---

## 17. Supply Chain Intelligence (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 210 | Optimization | Linear programming for supply chain optimization | scipy.optimize |
| STA 346 | Quality control | SPC charts on supply chain reliability | data_quality.py:L177 |
| STA 346 | Process capability | Cp/Cpk for delivery time consistency | distribution_gap.py:L245 |
| ECO 305 | Gravity model | Trade flow estimation for cross-border supply chains | **TODO: Implement gravity model** |
| STA 244 | Time series | Supply/demand forecasting for inventory optimization | econometric_engine.py |
| ECO 203 | Index numbers | Supply chain cost indices (Laspeyres for input costs) | econometric_engine.py:L333 |
| STA 342 | Hypothesis testing | Test: did new supplier improve delivery reliability? | hypothesis_testing.py |
| ECO 104 | Input-output analysis | Leontief model for supply chain interdependencies | **TODO: Implement Leontief I-O** |

---

## 18. Research Data Platform (NEW)

### Degree Units Driving This Product

| Unit | Concept | How It's Applied | Code Location |
|------|---------|------------------|---------------|
| ECO 315 | Research design | Anonymized datasets structured for research use | **TODO: Implement data API** |
| ECO 315 | Sampling methods | Stratified, cluster, SRS sampling documentation | sampling.py |
| ECO 315 | Hypothesis testing | All tests documented with academic references | hypothesis_testing.py |
| STA 245 | Economic statistics | Development indicators as research variables | biashara_pulse.py, jamii_insights.py |
| ECO 414 | OLS regression | Full regression output with diagnostics | econometric_engine.py:L52 |
| ECO 414 | Robust SE | White sandwich estimator for all regressions | econometric_engine.py:L93 |
| STA 444 | Non-parametric methods | KDE, bootstrap, Mann-Whitney available via API | statistical_foundation.py |
| STA 341 | Estimation | MLE, Bayesian, bootstrap — all estimation methods documented | econometric_engine.py, statistical_foundation.py |
| STA 142 | Probability theory | Distribution fitting, Bayes' theorem — documented | statistical_foundation.py |
| STA 347 | Statistical computing | Newton-Raphson, bootstrap, optimization — documented | econometric_engine.py |

### Implementation Notes

- **API design:** REST endpoints for each statistical method. All return JSON with estimates, standard errors, confidence intervals, p-values, and method documentation.
- **Privacy:** k-anonymity (k≥10), differential privacy (ε=1.0), no individual-level data exposed.
- **Academic references:** All methods cite original papers in API documentation.

---

## Cross-Cutting: Methods Shared Across All Products

These degree units provide the **statistical backbone** used by every product:

| Unit | Concept | Products Using It | Code Location |
|------|---------|-------------------|---------------|
| STA 142 | Bayes' theorem | Alama Score, Biashara Pulse, Jamii Insights, all new products | statistical_foundation.py:L30 |
| STA 241 | Distribution fitting | All products with distributional assumptions | statistical_foundation.py:L316 |
| STA 341 | Bootstrap CI | All products reporting uncertainty | statistical_foundation.py:L225 |
| STA 342 | Hypothesis testing | All products with A/B tests, comparisons | hypothesis_testing.py |
| STA 343 | Experimental design | Onboarding, pricing, product experiments | experimental_design.py |
| STA 346 | Quality control | Data quality across all pipelines | data_quality.py:L177 |
| ECO 202 | Sampling | Representative data collection for all products | sampling.py |
| ECO 203 | Index numbers | Price/basket indices across Soko Pulse, Inflation, GDP | econometric_engine.py:L333-440 |
| ECO 210 | Matrix algebra/optimization | All regression, PCA, factor analysis | econometric_engine.py |
| MAT 121 | Calculus (marginal effects) | All models with derivatives | econometric_engine.py:L275 |
| MAT 124 | Integration | Consumer surplus, probability integrals | soko_pulse.py:L419 |
| MAT 101 | Foundation math | All numerical computations | Throughout |
| BIT 113 | Database/API architecture | All products served via FastAPI + PostgreSQL | db/database.py, api/, main.py |

---

## COMPLETE DEGREE UNIT COVERAGE MATRIX

| Unit | Products It Drives | Status |
|------|-------------------|--------|
| BCB 108 | Worker Onboarding, Jamii Insights | ⚠️ Partial → ✅ Full with onboarding |
| ECO 100 | Jamii Insights, SDG Tracker, Worker Onboarding | ⚠️ Partial → ✅ Full with SDG |
| ECO 101 | Soko Pulse, Pricing, Market Entry, Supply Chain | ⚠️ Partial → ✅ Full with pricing |
| ECO 102 | GDP Estimator, Inflation Tracker | ⚠️ Partial → ✅ Full with GDP/Inflation |
| ECO 103 | All products (mathematical foundations) | ✅ Full |
| ECO 104 | Biashara Pulse, Supply Chain (I-O), Alama Score | ⚠️ Partial → ✅ Full with I-O |
| ECO 106 | — | ❌ Not integrated (health economics) |
| BIT 113 | All products (infrastructure) | ✅ Full |
| MAT 101 | All products (foundations) | ✅ Full |
| MAT 121 | Alama Score, all regression models | ✅ Full |
| MAT 124 | Soko Pulse (consumer surplus), all probability | ✅ Full |
| STA 142 | Alama Score, all Bayesian products | ✅ Full |
| ECO 201 | Soko Pulse, Pricing, Market Entry, Critical Mass | ⚠️ Partial → ✅ Full with pricing |
| ECO 202 | All products (sampling, CIs) | ✅ Full |
| ECO 203 | Soko Pulse, Inflation Tracker, GDP Estimator | ✅ Full |
| ECO 204 | Jamii Insights, Gender Intel, SDG Tracker | ⚠️ Partial → ✅ Full with Gender Intel |
| ECO 205 | Biashara Pulse, GDP Estimator, Employment Monitor | ⚠️ Partial → ✅ Full with GDP |
| ECO 206 | Alama Score, Jamii Insights, Insurance Risk | ⚠️ Partial → ✅ Full with Insurance |
| ECO 209 | — | ❌ Not integrated (money & banking) |
| ECO 210 | All products (optimization, MLE) | ✅ Full |
| STA 241 | All products (distribution fitting) | ✅ Full |
| STA 244 | Soko Pulse, Inflation, GDP, Employment, Supply Chain | ⚠️ Partial → ✅ Full (still need full ARIMA) |
| STA 245 | Biashara Pulse, Jamii Insights, SDG, Employment | ⚠️ Partial → ✅ Full with SDG |
| STA 246 | Jamii Insights, Employment, Gender Intel | ⚠️ Partial → ✅ Full with Employment |
| ECO 305 | Soko Pulse, Market Entry, Supply Chain | ❌ Not integrated → ✅ Full with gravity model |
| ECO 313 | — | ❌ Not integrated (advanced trade theory) |
| ECO 315 | Research Data Platform | ⚠️ Partial → ✅ Full with Research Platform |
| ECO 321 | Alama Score (screening), Pricing (mechanism design) | ❌ Not integrated → ⚠️ Partial with pricing |
| ECO 322 | GDP Estimator (nowcasting), Biashara Pulse | ❌ Not integrated → ✅ Full with GDP |
| STA 341 | All products (estimation backbone) | ✅ Full |
| STA 342 | All products (testing backbone) | ✅ Full |
| STA 343 | All products with experiments (onboarding, pricing) | ✅ Full |
| STA 346 | Data quality, Distribution Gap, Supply Chain | ⚠️ Partial → ✅ Full with Supply Chain |
| STA 347 | All products (numerical methods) | ⚠️ Partial (no MCMC yet) |
| ECO 401 | Jamii Insights, SDG, Gender Intel | ❌ Not integrated → ⚠️ Partial |
| ECO 414 | Research Data Platform (OLS diagnostics) | ✅ Full |
| STA 442 | Alama Score, Insurance Risk, all clustering products | ⚠️ Partial → ✅ Full (still need K-means) |
| STA 443 | — | ❌ Not integrated (measure theory — abstract) |
| ECO 421 | Tax Base, Pricing (Ramsey) | ✅ Full |
| ECO 422 | Distribution Gap, Market Entry, Pricing | ⚠️ Partial → ✅ Full with Market Entry |
| ECO 424 | Alama Score (logit/Heckman), causal inference | ⚠️ Partial (need IV/DiD/RDD) |
| STA 444 | Soko Pulse, Inflation, all KDE/LOESS products | ✅ Full |

---

## UPDATED INTEGRATION SCORECARD

| Level | Before | After (with new products) |
|-------|--------|--------------------------|
| ✅ FULLY INTEGRATED | 15 (36%) | **28 (67%)** |
| ⚠️ PARTIALLY INTEGRATED | 16 (38%) | **11 (26%)** |
| ❌ NOT INTEGRATED | 11 (26%) | **3 (7%)** |

### Remaining Gaps (3 units)

| Unit | Why Not Integrated | Potential Product |
|------|-------------------|-------------------|
| ECO 106 | Emerging Public Health Issues | Health economics overlay on Jamii Insights |
| ECO 209 | Money and Banking | Monetary policy indicator for Biashara Pulse |
| ECO 313 | International Economics (advanced) | Advanced trade theory for Market Entry |
| STA 443 | Measure and Probability Theory | Abstract mathematical foundation — scipy handles implementation |

---

## NEXT STEPS FOR IMPLEMENTATION TEAM

### Priority 1: New Products with Highest Degree Impact
1. **Real-Time GDP Estimator** — drives ECO 205, ECO 102, ECO 322 (3 partially → fully integrated)
2. **Real-Time Inflation Tracker** — drives ECO 203 (already full, but adds CPI construction)
3. **Worker Onboarding** — drives BCB 108 (partial → full)
4. **Outcome-Based Pricing** — drives ECO 201, ECO 422, ECO 321 (3 partially → fully integrated)

### Priority 2: Enhance Existing Products
5. **Soko Pulse** — add full ARIMA(p,d,q) and gravity model (STA 244, ECO 305 gaps)
6. **Alama Score** — add K-means clustering and IV validation (STA 442, ECO 424 gaps)
7. **Jamii Insights** — add Lewis model and HDI construction (ECO 401 gaps)

### Priority 3: New Products for Complete Coverage
8. **Employment Monitor** — drives STA 246, ECO 205 labor economics
9. **SDG Tracker** — drives STA 245, ECO 401 development economics
10. **Gender Intel** — drives ECO 204 gender analysis, ECO 401 capability approach

---

*This document ensures every line of code traces back to a specific degree concept. When building a feature, find it here first. If a concept from the degree isn't mapped to a product, that's a gap to fill.*

*42 units. 15 products. Zero wasted education.*
