// =============================================================================
// Angavu Intelligence — Property Rights Scoring
// Assess informal property documentation status for workers.
//
// Many informal workers operate on property they don't formally own.
// This module scores property documentation status and recommends
// formalization paths.
// =============================================================================

use serde::{Deserialize, Serialize};

/// Property types common in informal economy
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum PropertyType {
    Stall,           // Market stall
    Workshop,        // Jua Kali workshop
    FarmPlot,        // Agricultural land
    ResidentialPlot, // Residential land
    Shop,            // Permanent shop/duka
    Vehicle,         // Boda boda, matatu, tuk-tuk
    Equipment,       // Tools, machinery
    FishingBoat,     // Fishing vessel
}

/// Documentation level
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub enum DocumentationLevel {
    NoDocumentation, // Verbal agreement only
    InformalReceipt, // Handwritten receipt
    OfficialReceipt, // Printed receipt from authority
    Permit,          // Government permit
    TitleDeed,       // Full legal ownership
}

/// Property rights assessment for a worker
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PropertyRightsAssessment {
    pub worker_id: String,
    pub properties: Vec<PropertyAssessment>,
    pub overall_score: f64, // 0-100
    pub risk_level: String, // "Low", "Medium", "High", "Critical"
    pub recommendations: Vec<String>,
    pub estimated_value_at_risk: f64,
}

/// Assessment of a single property
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PropertyAssessment {
    pub property_type: PropertyType,
    pub description: String,
    pub documentation_level: DocumentationLevel,
    pub score: f64, // 0-100
    pub estimated_value: f64,
    pub eviction_risk: String, // "Low", "Medium", "High"
    pub formalization_path: String,
    pub formalization_cost: f64,
}

/// Property rights scoring module
pub struct PropertyRightsScorer;

impl PropertyRightsScorer {
    pub fn new() -> Self {
        Self
    }

    /// Score documentation level (0-100)
    pub fn score_documentation(level: &DocumentationLevel) -> f64 {
        match level {
            DocumentationLevel::NoDocumentation => 10.0,
            DocumentationLevel::InformalReceipt => 30.0,
            DocumentationLevel::OfficialReceipt => 55.0,
            DocumentationLevel::Permit => 75.0,
            DocumentationLevel::TitleDeed => 100.0,
        }
    }

    /// Assess eviction risk
    pub fn eviction_risk(level: &DocumentationLevel, property_type: &PropertyType) -> String {
        match (level, property_type) {
            (DocumentationLevel::NoDocumentation, _) => "High".to_string(),
            (DocumentationLevel::InformalReceipt, PropertyType::Stall) => "High".to_string(),
            (DocumentationLevel::InformalReceipt, _) => "Medium".to_string(),
            (DocumentationLevel::OfficialReceipt, _) => "Low".to_string(),
            (DocumentationLevel::Permit, _) => "Low".to_string(),
            (DocumentationLevel::TitleDeed, _) => "Very Low".to_string(),
        }
    }

    /// Recommend formalization path
    pub fn formalization_path(
        property_type: &PropertyType,
        current_level: &DocumentationLevel,
    ) -> (String, f64) {
        match (property_type, current_level) {
            (PropertyType::Stall, DocumentationLevel::NoDocumentation) => (
                "Apply for market allocation from county government. Visit county offices with ID and 2 passport photos. Fee: KES 500-2000.".into(),
                1500.0
            ),
            (PropertyType::Stall, DocumentationLevel::InformalReceipt) => (
                "Convert to official permit. Visit market superintendent with your receipt and ID. Fee: KES 1000-5000.".into(),
                3000.0
            ),
            (PropertyType::FarmPlot, DocumentationLevel::NoDocumentation) => (
                "Apply for land adjudication through the Land Control Board. You'll need witnesses who can attest to your occupation. Process takes 3-6 months.".into(),
                5000.0
            ),
            (PropertyType::FarmPlot, DocumentationLevel::InformalReceipt) => (
                "Register with the Land Registry. Bring your family land agreement, ID, and a surveyor's map. Fee: KES 3000-10000.".into(),
                8000.0
            ),
            (PropertyType::Vehicle, DocumentationLevel::NoDocumentation) => (
                "Register vehicle with NTSA. You need a logbook from the seller, insurance certificate, and inspection report. Fee: KES 2000-5000.".into(),
                3500.0
            ),
            (PropertyType::Workshop, DocumentationLevel::NoDocumentation) => (
                "Apply for a Single Business Permit from county government. Fee: KES 3000-10000 depending on location.".into(),
                6500.0
            ),
            (PropertyType::Shop, DocumentationLevel::NoDocumentation) => (
                "Get a Single Business Permit and consider registering a business name. Fee: KES 5000-15000.".into(),
                10000.0
            ),
            _ => (
                "Consult with a legal aid provider (e.g., Kituo Cha Sheria) for your specific situation. Many services are free for low-income workers.".into(),
                2000.0
            ),
        }
    }

    /// Full assessment for a worker
    pub fn assess(
        &self,
        worker_id: &str,
        properties: Vec<(PropertyType, String, DocumentationLevel, f64)>,
    ) -> PropertyRightsAssessment {
        let mut assessments = Vec::new();
        let mut total_score = 0.0;
        let mut total_value_at_risk = 0.0;

        for (ptype, desc, doc_level, value) in properties {
            let doc_score = Self::score_documentation(&doc_level);
            let eviction = Self::eviction_risk(&doc_level, &ptype);
            let (path, cost) = Self::formalization_path(&ptype, &doc_level);

            let value_at_risk = if doc_score < 50.0 {
                value * 0.8
            } else if doc_score < 75.0 {
                value * 0.3
            } else {
                0.0
            };

            assessments.push(PropertyAssessment {
                property_type: ptype,
                description: desc,
                documentation_level: doc_level,
                score: doc_score,
                estimated_value: value,
                eviction_risk: eviction,
                formalization_path: path,
                formalization_cost: cost,
            });

            total_score += doc_score;
            total_value_at_risk += value_at_risk;
        }

        let overall_score = if assessments.is_empty() {
            0.0
        } else {
            total_score / assessments.len() as f64
        };

        let risk_level = match overall_score as u32 {
            0..=25 => "Critical",
            26..=50 => "High",
            51..=75 => "Medium",
            _ => "Low",
        }
        .to_string();

        let mut recommendations = Vec::new();
        if overall_score < 50.0 {
            recommendations
                .push("Prioritize formalizing your most valuable property first.".into());
            recommendations
                .push("Visit your county's land registry or market superintendent office.".into());
        }
        if total_value_at_risk > 50000.0 {
            recommendations.push(format!(
                "You have KES {:,.0f} in property at risk. Legal aid may help.",
                total_value_at_risk
            ));
        }
        recommendations.push("Keep all receipts and agreements in a safe place — photos on your phone count as evidence.".into());

        PropertyRightsAssessment {
            worker_id: worker_id.to_string(),
            properties: assessments,
            overall_score,
            risk_level,
            recommendations,
            estimated_value_at_risk: total_value_at_risk,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_documentation_scoring() {
        assert_eq!(
            PropertyRightsScorer::score_documentation(&DocumentationLevel::NoDocumentation),
            10.0
        );
        assert_eq!(
            PropertyRightsScorer::score_documentation(&DocumentationLevel::TitleDeed),
            100.0
        );
    }

    #[test]
    fn test_high_risk_no_docs() {
        let scorer = PropertyRightsScorer::new();
        let assessment = scorer.assess(
            "worker1",
            vec![(
                PropertyType::Stall,
                "Market stall".into(),
                DocumentationLevel::NoDocumentation,
                20000.0,
            )],
        );
        assert_eq!(assessment.risk_level, "Critical");
        assert!(assessment.estimated_value_at_risk > 10000.0);
    }

    #[test]
    fn test_low_risk_title_deed() {
        let scorer = PropertyRightsScorer::new();
        let assessment = scorer.assess(
            "worker2",
            vec![(
                PropertyType::FarmPlot,
                "Family shamba".into(),
                DocumentationLevel::TitleDeed,
                500000.0,
            )],
        );
        assert_eq!(assessment.risk_level, "Low");
        assert_eq!(assessment.estimated_value_at_risk, 0.0);
    }
}
