# Degree Wiring Roadmap — Remaining 9 Partially Wired Units

**Date:** 2026-07-02
**Status:** Implementation roadmap for units 4-12 from the validation report
**Previous:** Top 3 high-impact units (STA 442, ECO 305/313, ECO 106) completed

---

## Completed (High Impact)

### ✅ STA 442 — Applied Multivariate Analysis
- **What was done:** Promoted PCA, Factor Analysis, LDA, and MANOVA from local helpers in `alama_score.py` to shared classes in `statistical_foundation.py`
- **Classes added:** `PCAAnalyzer`, `FactorAnalyzer`, `DiscriminantAnalyzer`, `MANOVA`
- **Products improved:** Alama Score (feature engineering), Angavu Pulse (composite indices), Jamii Insights (community profiling)
- **Commit:** `feat(degree): STA 442 — promote multivariate analysis to shared module`

### ✅ ECO 305/313 — International Trade
- **What was done:** Built `CrossBorderTradeIntelligence` class in `soko_pulse.py`
- **Features:** Gravity model (Tinbergen 1962), RCA index (Balassa 1965), ERPT estimation, PPP deviation, AfCFTA tariff impact analysis
- **Products improved:** Soko Pulse (EAC cross-border expansion)
- **Commit:** `feat(degree): ECO 305/313 — cross-border trade intelligence`

### ✅ ECO 106 — Public Health
- **What was done:** Built `HealthEconomicIntelligence` class in `jamii_insights.py`
- **Features:** Health shock tracker, Grossman health capital model, insurance gap analysis, epidemiological early warning, health-productivity correlation
- **Products improved:** Jamii Insights (health-economic module for NGOs)
- **Commit:** `feat(degree): ECO 106 — health-economic intelligence module`

---

## Medium Impact (Next Sprint)

### 4. ECO 204 — Issues in African Development
**Target:** `jamii_insights.py` — Kenya-specific development indicators
**What to build:**
- Governance indicators integration (rule of law, corruption perception)
- Structural transformation tracking (agriculture → manufacturing → services)
- Gender-disaggregated economic analysis
- Colonial legacy / institutional analysis tools
- Kenya Vision 2030 alignment scoring

**Difficulty:** Medium — requires external data integration
**Impact:** Strengthens Jamii Insights for government and NGO buyers
**Estimated effort:** 3-5 days

### 5. ECO 322 — Advanced Macroeconomics
**Target:** `biashara_pulse.py`, `gdp_estimator.py`, `inflation_tracker.py`
**What to build:**
- GDP estimator improvements (nowcasting with more indicators)
- Inflation tracker: New Keynesian Phillips Curve implementation
- Taylor rule estimation for monetary policy analysis
- Output gap estimation (HP filter vs Baxter-King)
- Business cycle dating algorithm (Bry-Boschan)

**Difficulty:** Medium — extends existing macro infrastructure
**Impact:** Improves macro intelligence quality across all products
**Estimated effort:** 4-6 days

### 6. STA 346 — Statistical Quality Control
**Target:** `drift_detector.py`, `distribution_gap.py`, pipeline monitoring
**What to build:**
- Process capability indices (Cp, Cpk) for intelligence products
- Acceptance sampling plans for data quality
- EWMA (Exponentially Weighted Moving Average) control charts
- Quality metrics dashboard for intelligence products
- Automated quality alerts when products degrade

**Difficulty:** Low-Medium — extends existing CUSUM implementation
**Impact:** Ensures intelligence product reliability
**Estimated effort:** 2-3 days

---

## Lower Impact (Backlog)

### 7. ECO 421 — Public Finance and Fiscal Policy
**Target:** `tax_base.py`, `biashara_pulse.py`
**What to build:**
- Ramsey rule implementation (optimal commodity taxation)
- Tax incidence analysis (who bears the burden)
- Deadweight loss calculation
- Fiscal decentralization modeling
- County government revenue tracking

**Difficulty:** Medium — requires economic modeling
**Impact:** Strengthens Tax Base for KRA and county government buyers
**Estimated effort:** 4-5 days

### 8. ECO 422 — Industry Economics
**Target:** `distribution_gap.py`, `fmcg_intelligence.py`
**What to build:**
- FMCG intelligence improvements (informal channel tracking)
- Market contestability analysis (Baumol)
- Two-sided market pricing models
- Industrial policy simulation
- Supply chain optimization

**Difficulty:** Medium — extends existing market structure analysis
**Impact:** Improves FMCG buyer value proposition
**Estimated effort:** 3-4 days

### 9. ECO 401 — Development Economics
**Target:** `jamii_insights.py`
**What to build:**
- Poverty dynamics tracking (entry/exit analysis)
- Development indicators dashboard (county-level)
- Demographic dividend calculator
- Structural transformation index
- Multidimensional Poverty Index (MPI) improvements

**Difficulty:** Low-Medium — extends existing poverty measures
**Impact:** Strengthens Jamii Insights for development organizations
**Estimated effort:** 2-3 days

### 10. STA 245 — Social & Economic Statistics
**Target:** `biashara_pulse.py`, `jamii_insights.py`
**What to build:**
- SDG monitoring framework (17 goals, 169 targets)
- Labor force survey methodology
- Small area estimation (Fay-Herriot model)
- Statistical quality frameworks for official statistics

**Difficulty:** Medium — requires external SDG indicator data
**Impact:** Strengthens government buyer value proposition
**Estimated effort:** 4-5 days

### 11. STA 246 — Statistical Demography
**Target:** `jamii_insights.py`
**What to build:**
- Life table construction improvements (already partially done)
- Fertility/mortality analysis (TFR, CDR, IMR)
- Cohort analysis and population pyramids
- Migration analysis (net migration estimation)
- Population projection models (cohort-component method)

**Difficulty:** Low-Medium — extends existing life table implementation
**Impact:** Strengthens demographic intelligence for NGOs
**Estimated effort:** 2-3 days

### 12. ECO 209 — Money & Banking
**Target:** `alama_score.py`, `loan_intelligence.py`
**What to build:**
- Financial inclusion tracking improvements
- M-Pesa adoption metrics
- Credit market depth analysis
- Money velocity estimation
- Banking penetration mapping

**Difficulty:** Low — extends existing financial infrastructure
**Impact:** Improves financial inclusion metrics
**Estimated effort:** 1-2 days

---

## Implementation Priority Matrix

| Priority | Unit | Product | Effort | Impact | Dependencies |
|----------|------|---------|--------|--------|-------------|
| 1 | ECO 322 | GDP/Inflation | 4-6d | High | Existing macro modules |
| 2 | ECO 204 | Jamii Insights | 3-5d | Medium | External data |
| 3 | STA 346 | Pipeline | 2-3d | Medium | Existing CUSUM |
| 4 | ECO 401 | Jamii Insights | 2-3d | Medium | Existing poverty measures |
| 5 | STA 246 | Jamii Insights | 2-3d | Medium | Existing life tables |
| 6 | ECO 422 | FMCG | 3-4d | Medium | Existing HHI/CR4 |
| 7 | ECO 421 | Tax Base | 4-5d | Medium | Existing tax estimation |
| 8 | STA 245 | Jamii/Biashara | 4-5d | Medium | SDG data |
| 9 | ECO 209 | Alama/Loan | 1-2d | Low | Existing financial infra |

**Total estimated effort:** 26-38 days (5-8 weeks)

---

## Data Requirements

Several units require external data sources:

1. **ECO 204 (African Development):** World Bank WDI, AfDB statistics, Kenya Vision 2030 indicators
2. **ECO 322 (Advanced Macro):** CBK monetary data, KNBS GDP data, Treasury fiscal data
3. **ECO 421 (Public Finance):** KRA tax data, county revenue data, Treasury budget data
4. **STA 245 (Social Statistics):** SDG indicators (UN Stats), KNBS labor force surveys
5. **STA 246 (Demography):** KNBS census data, DHS surveys, UN population estimates

---

## Success Metrics

For each completed unit:
- [ ] Code compiles without errors
- [ ] Unit tests pass
- [ ] Integration with existing service confirmed
- [ ] API response includes new intelligence fields
- [ ] Academic reference traceability maintained
- [ ] Commit message follows conventional format

---

*Last updated: 2026-07-02*
*Next review: After medium-priority units completion*
