/// Behavioral Economics Module for Angavu Intelligence Backend
///
/// Implements computational behavioral economics models for informal
/// workers in Kenya. These models detect cognitive biases, measure
/// behavioral traits, and optimize nudge interventions.
///
/// Concepts implemented:
///   - Nudge effectiveness tracking (Thaler & Sunstein 2008)
///   - Behavioral segmentation (Mullainathan & Shafir 2013)
///   - Reference price modeling (Kahneman & Tversky 1979)
///   - Risk attitude assessment (Holt & Laury 2002)
///   - Inequality aversion scoring (Fehr & Schmidt 1999)

pub mod nudge_effectiveness;
pub mod behavioral_segmentation;
pub mod reference_price;
pub mod risk_attitude;
pub mod inequality_aversion;

pub use nudge_effectiveness::*;
pub use behavioral_segmentation::*;
pub use reference_price::*;
pub use risk_attitude::*;
pub use inequality_aversion::*;
