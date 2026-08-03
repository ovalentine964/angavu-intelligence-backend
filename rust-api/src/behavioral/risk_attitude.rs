/// Risk Attitude Assessment Module
///
/// Classifies informal workers as risk-averse, risk-neutral, or risk-seeking
/// based on their revealed preferences from transaction data.
///
/// Uses the Holt-Laury (2002) multiple price list approach adapted for
/// field observation: instead of a lab experiment, we infer risk attitudes
/// from actual financial behavior.
///
/// Behavioral indicators of risk attitude:
///   - Savings instrument choice (mattress vs. chama vs. stock market)
///   - Business investment patterns (reinvest profits vs. spend)
///   - Insurance adoption (risk transfer behavior)
///   - Debt behavior (borrowing for investment vs. consumption)
///   - Price negotiation aggressiveness (risk tolerance in bargaining)
///
/// Reference: Holt, C. A., & Laury, S. K. (2002). Risk Aversion and
///            Incentive Effects. American Economic Review, 92(5).
use serde::{Deserialize, Serialize};

/// Risk attitude classification
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RiskAttitude {
    /// Strongly avoids risk (β > 0.8 in prospect theory)
    StronglyRiskAverse,
    /// Moderately risk-averse (β 0.5-0.8)
    RiskAverse,
    /// Approximately risk-neutral (β ≈ 0.5)
    RiskNeutral,
    /// Moderate risk-seeking (β 0.2-0.5)
    RiskSeeking,
    /// Strongly risk-seeking (β < 0.2)
    StronglyRiskSeeking,
}

impl RiskAttitude {
    /// Get the prospect theory β parameter for this attitude
    pub fn prospect_beta(&self) -> f64 {
        match self {
            Self::StronglyRiskAverse => 0.9,
            Self::RiskAverse => 0.7,
            Self::RiskNeutral => 0.5,
            Self::RiskSeeking => 0.35,
            Self::StronglyRiskSeeking => 0.2,
        }
    }

    /// Get the risk attitude score (-1 to 1)
    pub fn score(&self) -> f64 {
        match self {
            Self::StronglyRiskAverse => -1.0,
            Self::RiskAverse => -0.5,
            Self::RiskNeutral => 0.0,
            Self::RiskSeeking => 0.5,
            Self::StronglyRiskSeeking => 1.0,
        }
    }

    /// Human-readable label
    pub fn label(&self) -> &'static str {
        match self {
            Self::StronglyRiskAverse => "Hatari Sana — Hapendi Kupoteza",
            Self::RiskAverse => "Anayeepuka Hatari",
            Self::RiskNeutral => "Wastani",
            Self::RiskSeeking => "Anayependa Hatari",
            Self::StronglyRiskSeeking => "Hatari Sana — Anapenda Kupata Zaidi",
        }
    }

    /// Get recommended financial products for this attitude
    pub fn recommended_products(&self) -> Vec<&'static str> {
        match self {
            Self::StronglyRiskAverse | Self::RiskAverse => vec![
                "Savings account (benki)",
                "Chama (group savings)",
                "Government bonds (Treasury bills)",
                "Fixed deposit",
                "NHIF health insurance",
            ],
            Self::RiskNeutral => vec![
                "Savings account",
                "Chama",
                "Money market fund",
                "Business reinvestment",
                "Micro-insurance",
            ],
            Self::RiskSeeking | Self::StronglyRiskSeeking => vec![
                "Business expansion",
                "Stock market (NSE)",
                "SACCO shares",
                "Land/property investment",
                "Diversified chama investments",
            ],
        }
    }
}

/// Behavioral data used to assess risk attitude
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskBehaviorData {
    /// Worker identifier
    pub worker_id: String,
    /// Proportion of savings in "safe" instruments (mattress, savings account)
    pub safe_savings_ratio: f64,
    /// Proportion of income reinvested in business
    pub reinvestment_rate: f64,
    /// Whether the worker has insurance (any type)
    pub has_insurance: bool,
    /// Number of different income streams
    pub income_streams: usize,
    /// Proportion of income from variable/unstable sources
    pub variable_income_ratio: f64,
    /// Average negotiation aggressiveness (0-1, from PriceNegotiator)
    pub negotiation_aggressiveness: f64,
    /// Debt-to-income ratio
    pub debt_to_income: f64,
    /// Whether worker has ever defaulted on a debt
    pub has_defaulted: bool,
    /// Proportion of spending on "risky" investments vs. consumption
    pub investment_spending_ratio: f64,
    /// Frequency of trying new products/markets (0-1)
    pub novelty_seeking: f64,
}

/// Risk attitude assessment result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskAssessment {
    /// Worker identifier
    pub worker_id: String,
    /// Overall risk attitude classification
    pub risk_attitude: RiskAttitude,
    /// Continuous risk score (-1 to 1)
    pub risk_score: f64,
    /// Component scores
    pub components: RiskComponents,
    /// Recommended financial strategy
    pub recommendation: String,
    /// Recommended products
    pub recommended_products: Vec<&'static str>,
    /// Confidence in the assessment (0-1)
    pub confidence: f64,
}

/// Individual component scores
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskComponents {
    /// Score from savings instrument choice (-1 to 1)
    pub savings_instrument_score: f64,
    /// Score from reinvestment behavior (-1 to 1)
    pub reinvestment_score: f64,
    /// Score from insurance adoption (-1 to 1)
    pub insurance_score: f64,
    /// Score from income diversification (-1 to 1)
    pub diversification_score: f64,
    /// Score from negotiation behavior (-1 to 1)
    pub negotiation_score: f64,
    /// Score from debt behavior (-1 to 1)
    pub debt_score: f64,
}

/// Risk attitude assessment engine
pub struct RiskAttitudeEngine {
    /// Component weights (sum to 1.0)
    weights: RiskWeights,
}

/// Weights for different behavioral components
struct RiskWeights {
    savings_instrument: f64,
    reinvestment: f64,
    insurance: f64,
    diversification: f64,
    negotiation: f64,
    debt: f64,
}

impl RiskAttitudeEngine {
    /// Create a new engine with default weights
    pub fn new() -> Self {
        Self {
            weights: RiskWeights {
                savings_instrument: 0.20,
                reinvestment: 0.25,
                insurance: 0.15,
                diversification: 0.15,
                negotiation: 0.10,
                debt: 0.15,
            },
        }
    }

    /// Assess risk attitude from behavioral data
    pub fn assess(&self, data: &RiskBehaviorData) -> RiskAssessment {
        // Score each component (-1 to 1)
        let savings_score = self.score_savings_instrument(data.safe_savings_ratio);
        let reinvestment_score = self.score_reinvestment(data.reinvestment_rate);
        let insurance_score = self.score_insurance(data.has_insurance);
        let diversification_score =
            self.score_diversification(data.income_streams, data.variable_income_ratio);
        let negotiation_score = self.score_negotiation(data.negotiation_aggressiveness);
        let debt_score = self.score_debt(data.debt_to_income, data.has_defaulted);

        // Weighted composite score
        let composite = savings_score * self.weights.savings_instrument
            + reinvestment_score * self.weights.reinvestment
            + insurance_score * self.weights.insurance
            + diversification_score * self.weights.diversification
            + negotiation_score * self.weights.negotiation
            + debt_score * self.weights.debt;

        // Clamp to [-1, 1]
        let risk_score = composite.max(-1.0).min(1.0);

        // Classify
        let risk_attitude = match risk_score {
            s if s < -0.6 => RiskAttitude::StronglyRiskAverse,
            s if s < -0.2 => RiskAttitude::RiskAverse,
            s if s < 0.2 => RiskAttitude::RiskNeutral,
            s if s < 0.6 => RiskAttitude::RiskSeeking,
            _ => RiskAttitude::StronglyRiskSeeking,
        };

        // Confidence based on data completeness
        let mut confidence_factors = Vec::new();
        if data.safe_savings_ratio > 0.0 || data.safe_savings_ratio == 0.0 {
            confidence_factors.push(1.0);
        }
        if data.reinvestment_rate > 0.0 || data.reinvestment_rate == 0.0 {
            confidence_factors.push(1.0);
        }
        confidence_factors.push(0.8); // insurance is binary, less informative
        if data.income_streams > 0 {
            confidence_factors.push(1.0);
        }
        if data.negotiation_aggressiveness > 0.0 || data.negotiation_aggressiveness == 0.0 {
            confidence_factors.push(0.7); // negotiation data may be sparse
        }
        let confidence = confidence_factors.iter().sum::<f64>() / confidence_factors.len() as f64;

        // Generate recommendation
        let recommendation = self.generate_recommendation(risk_attitude, data);

        RiskAssessment {
            worker_id: data.worker_id.clone(),
            risk_attitude,
            risk_score,
            components: RiskComponents {
                savings_instrument_score: savings_score,
                reinvestment_score: reinvestment_score,
                insurance_score: insurance_score,
                diversification_score: diversification_score,
                negotiation_score: negotiation_score,
                debt_score: debt_score,
            },
            recommendation,
            recommended_products: risk_attitude.recommended_products(),
            confidence,
        }
    }

    /// Score savings instrument choice
    /// High safe_savings_ratio → risk-averse (negative score)
    fn score_savings_instrument(&self, safe_ratio: f64) -> f64 {
        // 1.0 = all safe → strongly risk-averse → score = -1.0
        // 0.0 = all risky → risk-seeking → score = 1.0
        -(safe_ratio * 2.0 - 1.0).max(-1.0).min(1.0)
    }

    /// Score reinvestment behavior
    /// High reinvestment → risk-seeking (positive score)
    fn score_reinvestment(&self, rate: f64) -> f64 {
        (rate * 2.0 - 1.0).max(-1.0).min(1.0)
    }

    /// Score insurance adoption
    fn score_insurance(&self, has_insurance: bool) -> f64 {
        if has_insurance {
            -0.5 // buying insurance is risk-averse behavior
        } else {
            0.3 // not buying insurance suggests risk tolerance or lack of access
        }
    }

    /// Score income diversification
    fn score_diversification(&self, streams: usize, variable_ratio: f64) -> f64 {
        let stream_score = match streams {
            0..=1 => -0.5, // single income source = risk-averse or constrained
            2..=3 => 0.0,  // moderate diversification
            _ => 0.5,      // multiple streams = risk-seeking
        };
        let variable_score = variable_ratio * 2.0 - 1.0; // high variable = risk-seeking
        (stream_score + variable_score) / 2.0
    }

    /// Score negotiation aggressiveness
    fn score_negotiation(&self, aggressiveness: f64) -> f64 {
        aggressiveness * 2.0 - 1.0
    }

    /// Score debt behavior
    fn score_debt(&self, debt_ratio: f64, has_defaulted: bool) -> f64 {
        let base = if debt_ratio > 0.5 {
            0.5 // high leverage = risk-seeking
        } else if debt_ratio > 0.2 {
            0.0
        } else {
            -0.3 // low leverage = risk-averse
        };

        if has_defaulted {
            base + 0.3 // defaulting after high leverage = very risk-seeking
        } else {
            base
        }
    }

    /// Generate personalized recommendation
    fn generate_recommendation(&self, attitude: RiskAttitude, data: &RiskBehaviorData) -> String {
        match attitude {
            RiskAttitude::StronglyRiskAverse => {
                format!(
                    "Wewe ni mtu wa kuepuka hatari sana. Hii ni nzuri kwa akiba, \
                     lakini inaweza kuzuia biashara yako kukua. Fikiria: \
                     1) Weka akiba kwenye benki (sio mfukoni). \
                     2) Anza na uwekezaji mdogo wa biashara ({}% ya faida). \
                     3) Bima ni muhimu — NHIF ni mwanzo mzuri.",
                    ((data.reinvestment_rate * 100.0) as u32 + 10).min(30)
                )
            }
            RiskAttitude::RiskAverse => {
                "Unaepuka hatari — hii ni sawa! Lakini usiache hofu ikuzuie. \
                 Tumia chama kwa akiba, na uwekeze kidogo kwenye biashara yako."
                    .to_string()
            }
            RiskAttitude::RiskNeutral => "Wewe ni wa wastani — huna hofu nyingi wala upuuzi. \
                 Endelea na mchanganyiko wa akiba na uwekezaji."
                .to_string(),
            RiskAttitude::RiskSeeking => {
                format!(
                    "Unapenda hatari — hii inaweza kukusaidia kupata zaidi, \
                     lakini pia inaweza kukupoteza. Fikiria: \
                     1) Weka angalau {}% ya mapato kwenye akiba salama. \
                     2) Epuka deni kubwa. \
                     3) Tengeneza dharura ya dharura kabla ya kuwekeza zaidi.",
                    ((1.0 - data.reinvestment_rate) * 50.0) as u32
                )
            }
            RiskAttitude::StronglyRiskSeeking => {
                "⚠️ Wewe ni mtu wa hatari sana! Hii ina faida lakini pia hatari kubwa. \
                 Hakikisha: 1) Una fedha ya dharura. 2) Huwekezi pesa unayohitaji. \
                 3) Tumia bima kulinda mali yako."
                    .to_string()
            }
        }
    }
}

impl Default for RiskAttitudeEngine {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_risk_averse_assessment() {
        let engine = RiskAttitudeEngine::new();
        let data = RiskBehaviorData {
            worker_id: "w1".to_string(),
            safe_savings_ratio: 0.95, // almost all in safe instruments
            reinvestment_rate: 0.10,  // very low reinvestment
            has_insurance: true,
            income_streams: 1,
            variable_income_ratio: 0.1,
            negotiation_aggressiveness: 0.2,
            debt_to_income: 0.1,
            has_defaulted: false,
            investment_spending_ratio: 0.05,
            novelty_seeking: 0.1,
        };

        let assessment = engine.assess(&data);
        assert_eq!(assessment.risk_attitude, RiskAttitude::StronglyRiskAverse);
        assert!(assessment.risk_score < -0.5);
    }

    #[test]
    fn test_risk_seeking_assessment() {
        let engine = RiskAttitudeEngine::new();
        let data = RiskBehaviorData {
            worker_id: "w2".to_string(),
            safe_savings_ratio: 0.1,
            reinvestment_rate: 0.8,
            has_insurance: false,
            income_streams: 4,
            variable_income_ratio: 0.7,
            negotiation_aggressiveness: 0.8,
            debt_to_income: 0.6,
            has_defaulted: false,
            investment_spending_ratio: 0.5,
            novelty_seeking: 0.7,
        };

        let assessment = engine.assess(&data);
        assert!(assessment.risk_score > 0.3);
        assert!(matches!(
            assessment.risk_attitude,
            RiskAttitude::RiskSeeking | RiskAttitude::StronglyRiskSeeking
        ));
    }

    #[test]
    fn test_risk_neutral_assessment() {
        let engine = RiskAttitudeEngine::new();
        let data = RiskBehaviorData {
            worker_id: "w3".to_string(),
            safe_savings_ratio: 0.5,
            reinvestment_rate: 0.4,
            has_insurance: true,
            income_streams: 2,
            variable_income_ratio: 0.4,
            negotiation_aggressiveness: 0.5,
            debt_to_income: 0.25,
            has_defaulted: false,
            investment_spending_ratio: 0.2,
            novelty_seeking: 0.4,
        };

        let assessment = engine.assess(&data);
        assert_eq!(assessment.risk_attitude, RiskAttitude::RiskNeutral);
        assert!(assessment.risk_score.abs() < 0.3);
    }

    #[test]
    fn test_recommended_products_differ() {
        let engine = RiskAttitudeEngine::new();

        let averse_data = RiskBehaviorData {
            worker_id: "a".to_string(),
            safe_savings_ratio: 0.9,
            reinvestment_rate: 0.1,
            has_insurance: true,
            income_streams: 1,
            variable_income_ratio: 0.1,
            negotiation_aggressiveness: 0.2,
            debt_to_income: 0.1,
            has_defaulted: false,
            investment_spending_ratio: 0.05,
            novelty_seeking: 0.1,
        };

        let seeking_data = RiskBehaviorData {
            worker_id: "s".to_string(),
            safe_savings_ratio: 0.1,
            reinvestment_rate: 0.7,
            has_insurance: false,
            income_streams: 3,
            variable_income_ratio: 0.6,
            negotiation_aggressiveness: 0.8,
            debt_to_income: 0.5,
            has_defaulted: false,
            investment_spending_ratio: 0.4,
            novelty_seeking: 0.7,
        };

        let averse = engine.assess(&averse_data);
        let seeking = engine.assess(&seeking_data);

        // Different attitudes should recommend different products
        assert_ne!(averse.risk_attitude, seeking.risk_attitude);
        assert_ne!(averse.recommended_products, seeking.recommended_products);
    }
}
