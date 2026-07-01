# Biashara Intelligence — Research Methodology Documentation

## Overview

This document describes the statistical and economic methodology underlying Biashara Intelligence's data pipeline, intelligence products, and quality assurance frameworks. All methods are grounded in Valentine's BSc Economics & Statistics degree.

---

## 1. Theoretical Foundation

### 1.1 Core Units Driving Methodology

| Unit | Title | Application in Biashara Intelligence |
|------|-------|--------------------------------------|
| **ECO 315** | Research Methods | Research design, sampling methodology, data collection standards |
| **STA 342** | Test of Hypothesis | Significance testing, Type I/II error control, power analysis |
| **STA 343** | Experimental Designs | A/B testing, factorial experiments, RCT design for pilot programs |
| **STA 346** | Statistical Quality Control | SPC control charts, acceptance sampling, process capability |
| **ECO 202** | Economic Statistics | Data cleaning, validation rules, economic theory constraints |
| **ECO 203** | Economic Statistics (Advanced) | Index numbers, time series, regression analysis |
| **STA 245** | Social & Economic Statistics | National planning standards, design effects, official statistics |

### 1.2 Research Philosophy

Biashara Intelligence adopts a **critical realist** paradigm (ECO 315 §3.1):
- The informal economy has **real structures** (markets, institutions)
- These generate **observable events** (transactions, prices)
- We interpret these through **data and statistical models**

---

## 2. Data Quality Framework (STA 346 + ECO 202/203)

### 2.1 Statistical Process Control (SPC)

All incoming transaction data is monitored using SPC control charts (STA 346 §9.2):

**Charts Implemented:**
- **X̄ Chart**: Monitors transaction amount means. Detects large shifts via ±3σ control limits (ARL₀ ≈ 370)
- **EWMA Chart**: Exponentially Weighted Moving Average. Detects small sustained shifts in prices and volumes. Uses λ=0.2 for smooth detection.
- **CUSUM Chart**: Cumulative Sum. Accumulates deviations from target. Parameters: k=0.5 (allowance), h=5.0 (threshold)
- **p-Chart**: Monitors error rates (proportion of invalid transactions)
- **c-Chart**: Monitors defect counts per batch

**Control Limits:**
- UCL = CL + 3σ
- LCL = CL - 3σ
- Western Electric run rules for pattern detection (8 consecutive points on same side)

### 2.2 Outlier Detection (STA 342 §7.6)

Non-parametric outlier detection methods are preferred because:
- No distributional assumptions required
- Robust to the very outliers they detect
- Asymptotic Relative Efficiency ≈ 0.955 vs parametric methods (STA 342)

**Methods:**
1. **IQR Method**: Outlier if value < Q1 - 1.5×IQR or value > Q3 + 1.5×IQR
2. **Modified Z-Score**: Uses Median Absolute Deviation (MAD). More robust than standard z-scores.
3. **Grubbs' Test**: For normally distributed data. Tests H₀: no outliers.

### 2.3 Data Validation Rules (ECO 202/203)

Validation rules enforce economic theory constraints:

| Rule | Source | Description |
|------|--------|-------------|
| Positive prices | ECO 202 Price Theory | Prices must be > 0 (scarcity principle) |
| Non-negative quantities | ECO 202 | Quantities ≥ 0 |
| Revenue consistency | ECO 203 Accounting | amount ≈ price × quantity (1% tolerance) |
| Price range validation | ECO 203 | Prices within expected range per category |
| Valid timestamps | STA 245 | Data timeliness standards |
| Confidence score range | ECO 315 | Quality scores ∈ [0, 1] |

---

## 3. Hypothesis Testing (STA 342)

### 3.1 Tests Available

| Test | Use Case | Reference |
|------|----------|-----------|
| One-sample t-test | Compare sample mean to known value | STA 342 §7.3 |
| Two-sample t-test (Welch) | Compare two groups (unequal variance) | STA 342 §7.3 |
| Paired t-test | Before/after comparisons | STA 342 §7.3 |
| Mann-Whitney U | Non-parametric two-group comparison | STA 342 §7.6 |
| Wilcoxon signed-rank | Non-parametric paired test | STA 342 §7.6 |
| Kruskal-Wallis | Non-parametric multi-group comparison | STA 342 §7.6 |
| Chi-square test | Independence of categorical variables | STA 342 §7.5 |
| Proportion z-test | Compare two proportions | STA 342 §7.3 |

### 3.2 Multiple Testing Correction (STA 342 §7.3)

When testing m hypotheses simultaneously, family-wise error rate increases. Available corrections:

- **Bonferroni**: α/m per test. Controls FWER. Most conservative.
- **Holm**: Step-down procedure. Uniformly more powerful than Bonferroni.
- **Benjamini-Hochberg (FDR)**: Controls False Discovery Rate. Less conservative.
- **Benjamini-Yekutieli**: Controls FDR under arbitrary dependence.

### 3.3 Effect Sizes

- **Cohen's d**: Standardized mean difference (small=0.2, medium=0.5, large=0.8)
- **Rank-biserial correlation**: For Mann-Whitney U
- **Cramér's V**: For chi-square tests
- **Epsilon-squared**: For Kruskal-Wallis

### 3.4 Power Analysis (STA 342 §7.7)

Power = P(reject H₀ | H₁ is true) = 1 - β

**Factors:**
- Effect size (larger → more power)
- Sample size (larger → more power)  
- Significance level (larger α → more power)
- Variance (smaller → more power)

**Sample size formula:** n per group = 2(z_α + z_β)² / d²

---

## 4. Experimental Design (STA 343)

### 4.1 Fisher's Principles

1. **Randomization**: Randomly assign treatments to eliminate systematic bias
2. **Replication**: Repeat to estimate experimental error
3. **Blocking**: Group similar units to reduce error

### 4.2 A/B Testing Framework

All product advice variations are tested using proper experimental design:

- **Deterministic assignment**: SHA-256 hash ensures consistent user-variant mapping
- **Power analysis before start**: Required sample size computed from minimum detectable effect
- **Sequential testing**: O'Brien-Fleming boundaries for early stopping
- **Effect size reporting**: Cohen's d with confidence intervals

### 4.3 Design Types

| Design | Use Case | STA 343 Reference |
|--------|----------|-------------------|
| CRD (Completely Randomized) | Simple A/B tests | §8.2 |
| RCBD (Randomized Complete Block) | Multi-market experiments | §8.3 |
| Factorial | Multi-factor optimization | §8.5 |
| Latin Square | Controlling two variation sources | §8.4 |
| Sequential/Adaptive | Bandit algorithms | §8.8 |

---

## 5. Confidence Intervals (STA 342 + ECO 315)

### 5.1 Methods

Every intelligence product includes confidence intervals:

| Method | Use Case | Formula |
|--------|----------|---------|
| t-interval | Means (small samples) | X̄ ± t_{α/2,n-1} × S/√n |
| Wilson score | Proportions | Better than Wald for small n |
| Welch interval | Difference of means | For unequal variances |
| Bootstrap | Any statistic | Non-parametric resampling |

### 5.2 Application in Products

- **Soko Pulse**: Price intelligence includes 95% CI for average prices
- **Biashara Pulse**: Revenue estimates include CIs
- **Alama Score**: Score uncertainty based on data volume
- **All forecasts**: Include prediction intervals

---

## 6. Sampling Methodology (ECO 315 §3.3)

### 6.1 Sample Size Formula

n = (Z² × p × (1-p)) / e²

For 95% confidence, 5% margin, p=0.5: **n = 385**

### 6.2 Finite Population Correction (STA 245)

n_adjusted = n / (1 + (n-1)/N)

### 6.3 Design Effect (STA 245)

DEFF = 1 + (m̄ - 1) × ρ

Where m̄ = average cluster size, ρ = intra-class correlation

### 6.4 Sampling Methods

- **Simple Random**: Equal probability selection
- **Stratified**: Divide by product category (ECO 315)
- **Cluster**: Sample specific market sections (ECO 315)
- **Systematic**: Every kth element

---

## 7. Integration with Intelligence Products

### 7.1 Soko Pulse (FMCG Demand Forecasting)

- Demand trend significance tested with Welch's t-test (STA 342)
- Price intelligence includes 95% confidence intervals
- Forecast includes prediction intervals
- k-Anonymity enforced on all outputs

### 7.2 Biashara Pulse (Government MSME Index)

- Activity index includes confidence intervals
- Bootstrap estimation for key metrics (STA 341)
- Growth significance tested against previous period
- Design effects considered for clustered data

### 7.3 Alama Score (Credit Scoring)

- Score uncertainty quantified via confidence intervals
- Revenue volatility CIs computed
- Heckman correction for selection bias (ECO 424)
- Model performance monitored via CUSUM (STA 346)

### 7.4 Data Pipeline

- All transactions validated against economic theory rules (ECO 202/203)
- SPC charts monitor pipeline health in real-time (STA 346)
- Outliers flagged using non-parametric methods (STA 342)
- Aggregated metrics include confidence intervals

---

## 8. Privacy & Methodology Alignment

### 8.1 k-Anonymity (ECO 315 Research Ethics)

- Minimum group size: k ≥ 10
- Suppression of small groups
- Temporal minimums by geography level

### 8.2 Differential Privacy (STA 342)

- Laplace mechanism: noise ~ Lap(0, sensitivity/ε)
- Gaussian mechanism for (ε,δ)-differential privacy
- Applied to all aggregate statistics

### 8.3 Proper Statistical Methodology

- Confidence intervals communicate uncertainty honestly
- Significance tests prevent false claims
- Multiple testing correction when reporting many metrics
- Power analysis ensures adequate sample sizes

---

## 9. Validation & Quality Reports

### 9.1 Data Quality Score

Composite score (0-1) based on:
- Error violations (weight: 0.1 each)
- Warning violations (weight: 0.02 each)
- Outlier count (weight: 0.05 each)

### 9.2 Statistical Significance Reporting

All buyer-facing intelligence products include:
- p-values for key comparisons
- Effect sizes (Cohen's d or equivalent)
- Confidence intervals for estimates
- Sample sizes and data quality scores
- Plain-language interpretations

---

## References

1. Page, E.S. (1954). Continuous inspection schemes. *Biometrika*, 41(1/2), 100-115.
2. Hawkins, D.M. & Olwell, D.H. (1998). *Cumulative Sum Charts and Charting for Quality Improvement*. Springer.
3. Cohen, J. (1988). *Statistical Power Analysis for the Behavioral Sciences*. Lawrence Erlbaum.
4. Benjamini, Y. & Hochberg, Y. (1995). Controlling the false discovery rate. *JRSS-B*, 57(1), 289-300.
5. Fisher, R.A. (1935). *The Design of Experiments*. Oliver and Boyd.
6. Kenya Data Protection Act (2019).
7. KNBS Statistical Standards.
