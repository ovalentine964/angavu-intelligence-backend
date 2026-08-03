//! Occupation-specific hazard risk profiles

use super::insurance::InsuranceProductType;
use super::types::*;

fn boda_boda_risk_profile() -> OccupationRiskProfile {
    OccupationRiskProfile {
        occupation: OccupationType::BodaBodaRider,
        display_name: "Boda Boda Rider".into(),
        display_name_sw: "Msafiri wa Boda Boda".into(),
        overall_risk_multiplier: 3.5,
        typical_work_hours_per_day: 11.0,
        exposure_duration_years_avg: 6.0,
        hazards: vec![
            Hazard {
                id: "boda_accident_road".into(),
                category: HazardCategory::Accident,
                name: "Road Traffic Accident".into(),
                description: "Collision, skidding, or being hit by other vehicles. \
                              Leading cause of death and serious injury for boda boda riders in Kenya.".into(),
                severity: HazardSeverity::Critical,
                base_risk_multiplier: 4.5,
                prevalence: 0.35,  // ~35% involved in serious accident per year
                data_signals: vec![
                    DataSignal {
                        name: "daily_trip_count".into(),
                        description: "More trips per day → higher exposure".into(),
                        source: DataSource::TransactionPatterns,
                        impact_on_risk: RiskDirection::Increases,
                    },
                    DataSignal {
                        name: "night_activity".into(),
                        description: "Transactions after 8PM indicate night riding".into(),
                        source: DataSource::TransactionPatterns,
                        impact_on_risk: RiskDirection::Increases,
                    },
                    DataSignal {
                        name: "rainy_season_activity".into(),
                        description: "Riding during rainy season (March-May, Oct-Dec) increases risk".into(),
                        source: DataSource::SeasonalPatterns,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Helmet use".into(),
                    "Daytime-only riding".into(),
                    "Speed limit adherence".into(),
                    "Motorcycle maintenance".into(),
                ],
                who_reference: Some("ICD-10: V20-V29".into()),
                recommended_insurance: vec![
                    InsuranceProductType::PersonalAccident,
                    InsuranceProductType::MotorVehicle,
                ],
            },
            Hazard {
                id: "boda_musculoskeletal".into(),
                category: HazardCategory::Musculoskeletal,
                name: "Joint and Back Problems".into(),
                description: "Prolonged sitting on motorcycle, vibration exposure, \
                              heavy lifting of passengers/goods.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.8,
                prevalence: 0.45,
                data_signals: vec![
                    DataSignal {
                        name: "daily_hours".into(),
                        description: "Longer daily hours → more wear on joints".into(),
                        source: DataSource::WorkHours,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Regular stretching".into(),
                    "Ergonomic seat cushion".into(),
                    "Limiting daily hours".into(),
                ],
                who_reference: Some("ICD-10: M54 (Dorsalgia)".into()),
                recommended_insurance: vec![
                    InsuranceProductType::OutpatientCover,
                ],
            },
            Hazard {
                id: "boda_hearing_loss".into(),
                category: HazardCategory::HearingDamage,
                name: "Noise-Induced Hearing Loss".into(),
                description: "Chronic exposure to engine noise and wind at speed. \
                              Progressive and irreversible.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 1.8,
                prevalence: 0.30,
                data_signals: vec![
                    DataSignal {
                        name: "years_in_occupation".into(),
                        description: "Cumulative exposure over time".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec!["Earplugs".into(), "Helmet with visor".into()],
                who_reference: Some("ICD-10: H83.3".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "boda_weather_exposure".into(),
                category: HazardCategory::EnvironmentalExposure,
                name: "Weather and UV Exposure".into(),
                description: "All-day outdoor exposure to sun, rain, dust, and cold. \
                              Skin damage, respiratory issues from dust.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.0,
                prevalence: 0.80,
                data_signals: vec![
                    DataSignal {
                        name: "work_hours_outdoor".into(),
                        description: "All work is outdoors by nature".into(),
                        source: DataSource::WorkHours,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Sunscreen".into(),
                    "Protective clothing".into(),
                    "Hydration".into(),
                ],
                who_reference: None,
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "boda_mental_health".into(),
                category: HazardCategory::MentalHealth,
                name: "Stress and Anxiety".into(),
                description: "Financial pressure, traffic danger, police harassment, \
                              irregular income. High rates of depression and anxiety.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.5,
                prevalence: 0.40,
                data_signals: vec![
                    DataSignal {
                        name: "income_volatility".into(),
                        description: "High income swings correlate with stress".into(),
                        source: DataSource::TransactionPatterns,
                        impact_on_risk: RiskDirection::Increases,
                    },
                    DataSignal {
                        name: "work_hours_extreme".into(),
                        description: "14+ hour days indicate overwork stress".into(),
                        source: DataSource::WorkHours,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Peer support groups".into(),
                    "Financial planning tools".into(),
                    "Rest days".into(),
                ],
                who_reference: Some("ICD-10: F41 (Anxiety)".into()),
                recommended_insurance: vec![InsuranceProductType::MentalHealthCover],
            },
            Hazard {
                id: "boda_violence".into(),
                category: HazardCategory::Violence,
                name: "Robbery and Assault".into(),
                description: "Cash-carrying riders are targets for robbery, \
                              especially at night and in isolated areas.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 3.0,
                prevalence: 0.20,
                data_signals: vec![
                    DataSignal {
                        name: "night_activity".into(),
                        description: "Night riding increases robbery risk".into(),
                        source: DataSource::TransactionPatterns,
                        impact_on_risk: RiskDirection::Increases,
                    },
                    DataSignal {
                        name: "cash_dominant_transactions".into(),
                        description: "Cash payments indicate cash-carrying".into(),
                        source: DataSource::TransactionPatterns,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "M-Pesa adoption (less cash)".into(),
                    "Avoiding high-risk areas at night".into(),
                    "Riding in groups".into(),
                ],
                who_reference: None,
                recommended_insurance: vec![InsuranceProductType::PersonalAccident],
            },
        ],
        notes: "Boda boda riders are the highest-risk informal worker group in Kenya. \
                WHO estimates motorcycle accidents are the #1 cause of death for males 18-35 in East Africa. \
                Income stability tells us NOTHING about this risk.".into(),
    }
}

fn miner_risk_profile() -> OccupationRiskProfile {
    OccupationRiskProfile {
        occupation: OccupationType::Miner,
        display_name: "Artisanal Miner".into(),
        display_name_sw: "Mchimbaji Madini".into(),
        overall_risk_multiplier: 4.0,
        typical_work_hours_per_day: 10.0,
        exposure_duration_years_avg: 8.0,
        hazards: vec![
            Hazard {
                id: "miner_respiratory".into(),
                category: HazardCategory::Respiratory,
                name: "Silicosis and Tuberculosis".into(),
                description: "Inhalation of crystalline silica dust causes silicosis \
                              (irreversible lung scarring). Silicosis massively increases \
                              TB risk. Combined, they are the #1 killer of miners.".into(),
                severity: HazardSeverity::Critical,
                base_risk_multiplier: 4.5,
                prevalence: 0.25,  // 25% develop respiratory disease within 10 years
                data_signals: vec![
                    DataSignal {
                        name: "mine_type".into(),
                        description: "Underground mining has highest dust exposure".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                    DataSignal {
                        name: "years_in_occupation".into(),
                        description: "Silicosis is cumulative — years of exposure matter".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Wet drilling (reduces dust)".into(),
                    "Respiratory masks (N95)".into(),
                    "Ventilation".into(),
                    "Regular health screening".into(),
                ],
                who_reference: Some("ICD-10: J62 (Silicosis), A15-A19 (TB)".into()),
                recommended_insurance: vec![
                    InsuranceProductType::CriticalIllness,
                    InsuranceProductType::InpatientCover,
                ],
            },
            Hazard {
                id: "miner_cave_in".into(),
                category: HazardCategory::Accident,
                name: "Cave-In and Structural Collapse".into(),
                description: "Artisanal mines lack structural engineering. \
                              Collapse risk is ever-present in shaft and tunnel mining.".into(),
                severity: HazardSeverity::Critical,
                base_risk_multiplier: 4.0,
                prevalence: 0.08,
                data_signals: vec![
                    DataSignal {
                        name: "mine_depth".into(),
                        description: "Deeper mines have higher collapse risk".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Proper shoring".into(),
                    "Safety training".into(),
                    "Emergency communication".into(),
                ],
                who_reference: Some("ICD-10: W20-W49".into()),
                recommended_insurance: vec![
                    InsuranceProductType::PersonalAccident,
                    InsuranceProductType::LifeInsurance,
                ],
            },
            Hazard {
                id: "miner_heavy_metal".into(),
                category: HazardCategory::ChemicalExposure,
                name: "Heavy Metal Exposure".into(),
                description: "Mercury (gold processing), lead, arsenic, cadmium. \
                              Mercury causes neurological damage. Lead causes kidney damage. \
                              No safe level of mercury exposure.".into(),
                severity: HazardSeverity::Critical,
                base_risk_multiplier: 4.2,
                prevalence: 0.60,  // Most artisanal gold miners use mercury
                data_signals: vec![
                    DataSignal {
                        name: "mineral_type".into(),
                        description: "Gold mining involves mercury; other minerals have different toxins".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Mercury-free gold processing".into(),
                    "Protective equipment".into(),
                    "Proper mercury storage and disposal".into(),
                ],
                who_reference: Some("ICD-10: T56 (Metals)".into()),
                recommended_insurance: vec![
                    InsuranceProductType::CriticalIllness,
                    InsuranceProductType::InpatientCover,
                ],
            },
            Hazard {
                id: "miner_hearing_damage".into(),
                category: HazardCategory::HearingDamage,
                name: "Noise-Induced Hearing Loss".into(),
                description: "Pneumatic drills, crushing equipment, and blasting \
                              generate extreme noise levels (>85 dB).".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.5,
                prevalence: 0.50,
                data_signals: vec![
                    DataSignal {
                        name: "equipment_type".into(),
                        description: "Use of mechanized equipment increases noise exposure".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec!["Hearing protection".into(), "Equipment maintenance".into()],
                who_reference: Some("ICD-10: H83.3".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "miner_musculoskeletal".into(),
                category: HazardCategory::Musculoskeletal,
                name: "Back and Joint Injuries".into(),
                description: "Heavy lifting, awkward postures in tunnels, \
                              repetitive manual labor.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.8,
                prevalence: 0.55,
                data_signals: vec![
                    DataSignal {
                        name: "manual_vs_mechanized".into(),
                        description: "Manual mining has higher musculoskeletal risk".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec!["Ergonomic tools".into(), "Weight limits".into(), "Rest breaks".into()],
                who_reference: Some("ICD-10: M54".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
        ],
        notes: "Artisanal miners face the highest occupational disease burden of any informal worker group. \
                WHO estimates 12% of global lung disease deaths are occupation-related, with mining as top contributor. \
                Mercury exposure in gold mining affects ~15 million miners globally (UNEP).".into(),
    }
}

fn construction_worker_risk_profile() -> OccupationRiskProfile {
    OccupationRiskProfile {
        occupation: OccupationType::ConstructionWorker,
        display_name: "Construction Worker".into(),
        display_name_sw: "Mjenzi".into(),
        overall_risk_multiplier: 3.0,
        typical_work_hours_per_day: 10.0,
        exposure_duration_years_avg: 10.0,
        hazards: vec![
            Hazard {
                id: "construction_fall".into(),
                category: HazardCategory::Accident,
                name: "Fall from Height".into(),
                description: "Scaffolding, unfinished floors, roof work. \
                              Falls are the #1 cause of construction fatalities globally (ILO).".into(),
                severity: HazardSeverity::Critical,
                base_risk_multiplier: 4.0,
                prevalence: 0.15,
                data_signals: vec![
                    DataSignal {
                        name: "project_type".into(),
                        description: "Multi-story projects have higher fall risk than single-story".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Safety harnesses".into(),
                    "Guardrails".into(),
                    "Safety training".into(),
                    "Proper scaffolding".into(),
                ],
                who_reference: Some("ICD-10: W00-W19 (Falls)".into()),
                recommended_insurance: vec![
                    InsuranceProductType::PersonalAccident,
                    InsuranceProductType::Disability,
                ],
            },
            Hazard {
                id: "construction_musculoskeletal".into(),
                category: HazardCategory::Musculoskeletal,
                name: "Musculoskeletal Injuries".into(),
                description: "Heavy lifting, repetitive motions, awkward postures. \
                              Back injuries, joint damage, herniated discs.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 3.0,
                prevalence: 0.60,
                data_signals: vec![
                    DataSignal {
                        name: "daily_hours".into(),
                        description: "Longer hours → more cumulative strain".into(),
                        source: DataSource::WorkHours,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Proper lifting technique".into(),
                    "Mechanical aids".into(),
                    "Rest breaks".into(),
                ],
                who_reference: Some("ICD-10: M54, S13-S39".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "construction_dust".into(),
                category: HazardCategory::Respiratory,
                name: "Dust Exposure (Cement, Silica, Asbestos)".into(),
                description: "Cement dust causes skin and lung irritation. \
                              Silica dust causes silicosis. Asbestos (in demolition) causes mesothelioma.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 3.0,
                prevalence: 0.70,
                data_signals: vec![
                    DataSignal {
                        name: "work_type".into(),
                        description: "Demolition and cutting work has highest dust exposure".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Dust masks (N95)".into(),
                    "Wet cutting".into(),
                    "Ventilation".into(),
                ],
                who_reference: Some("ICD-10: J60-J67".into()),
                recommended_insurance: vec![
                    InsuranceProductType::CriticalIllness,
                    InsuranceProductType::InpatientCover,
                ],
            },
            Hazard {
                id: "construction_hearing".into(),
                category: HazardCategory::HearingDamage,
                name: "Noise-Induced Hearing Loss".into(),
                description: "Power tools, concrete cutting, demolition equipment \
                              generate sustained high noise levels.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.0,
                prevalence: 0.40,
                data_signals: vec![],
                mitigation_factors: vec!["Ear protection".into(), "Tool maintenance".into()],
                who_reference: Some("ICD-10: H83.3".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "construction_electrical".into(),
                category: HazardCategory::Accident,
                name: "Electrical Shock".into(),
                description: "Contact with live wires, improper wiring, \
                              wet conditions near electrical installations.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 3.5,
                prevalence: 0.05,
                data_signals: vec![],
                mitigation_factors: vec![
                    "Electrical safety training".into(),
                    "Proper PPE".into(),
                    "Lockout/tagout procedures".into(),
                ],
                who_reference: Some("ICD-10: T75.4".into()),
                recommended_insurance: vec![
                    InsuranceProductType::PersonalAccident,
                    InsuranceProductType::InpatientCover,
                ],
            },
        ],
        notes: "ILO estimates 60,000 construction workers die annually from workplace accidents. \
                Construction is the most dangerous sector globally by fatality count. \
                In Kenya, most construction workers lack any safety equipment or training.".into(),
    }
}

fn farmer_risk_profile() -> OccupationRiskProfile {
    OccupationRiskProfile {
        occupation: OccupationType::Farmer,
        display_name: "Farmer".into(),
        display_name_sw: "Mkulima".into(),
        overall_risk_multiplier: 2.5,
        typical_work_hours_per_day: 9.0,
        exposure_duration_years_avg: 20.0,
        hazards: vec![
            Hazard {
                id: "farmer_pesticide".into(),
                category: HazardCategory::ChemicalExposure,
                name: "Pesticide Exposure".into(),
                description: "Organophosphates, herbicides, fungicides. \
                              Acute poisoning (nausea, dizziness, death) and chronic effects \
                              (cancer, neurological damage, reproductive harm). \
                              385 million cases of unintentional pesticide poisoning annually (WHO).".into(),
                severity: HazardSeverity::Critical,
                base_risk_multiplier: 3.5,
                prevalence: 0.50,
                data_signals: vec![
                    DataSignal {
                        name: "crop_type".into(),
                        description: "Cash crops (flowers, tea, coffee) use more pesticides than food crops".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                    DataSignal {
                        name: "farm_size".into(),
                        description: "Larger farms are more likely to use mechanized spraying".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Protective equipment (gloves, masks, goggles)".into(),
                    "Proper pesticide storage".into(),
                    "Integrated pest management".into(),
                    "Training on safe application".into(),
                ],
                who_reference: Some("ICD-10: T60 (Pesticides)".into()),
                recommended_insurance: vec![
                    InsuranceProductType::CriticalIllness,
                    InsuranceProductType::InpatientCover,
                ],
            },
            Hazard {
                id: "farmer_heat_stress".into(),
                category: HazardCategory::EnvironmentalExposure,
                name: "Sun and Heat Stress".into(),
                description: "All-day outdoor work causes heat exhaustion, heatstroke, \
                              skin damage, and dehydration. Chronic UV exposure causes skin cancer.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.5,
                prevalence: 0.80,
                data_signals: vec![
                    DataSignal {
                        name: "region_climate".into(),
                        description: "Lowland/arid regions have higher heat stress than highlands".into(),
                        source: DataSource::LocationData,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Shade breaks".into(),
                    "Hydration".into(),
                    "Wide-brimmed hats".into(),
                    "Early morning/late afternoon work".into(),
                ],
                who_reference: Some("ICD-10: T67 (Heat)".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "farmer_snake_bite".into(),
                category: HazardCategory::BiologicalExposure,
                name: "Snake Bite".into(),
                description: "Farming brings workers into contact with venomous snakes. \
                              ~5.4 million snake bites annually globally (WHO), \
                              with highest burden in sub-Saharan Africa.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 3.0,
                prevalence: 0.03,  // 3% per year
                data_signals: vec![
                    DataSignal {
                        name: "region_snake_prevalence".into(),
                        description: "Some regions have higher venomous snake populations".into(),
                        source: DataSource::LocationData,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Protective boots".into(),
                    "Walking sticks".into(),
                    "Anti-venom access".into(),
                ],
                who_reference: Some("ICD-10: T63.0".into()),
                recommended_insurance: vec![
                    InsuranceProductType::InpatientCover,
                    InsuranceProductType::PersonalAccident,
                ],
            },
            Hazard {
                id: "farmer_zoonotic".into(),
                category: HazardCategory::BiologicalExposure,
                name: "Zoonotic Diseases".into(),
                description: "Diseases transmitted from animals: brucellosis, Rift Valley fever, \
                              anthrax, rabies, avian influenza. Livestock proximity increases risk.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.8,
                prevalence: 0.15,
                data_signals: vec![
                    DataSignal {
                        name: "livestock_proximity".into(),
                        description: "Mixed crop-livestock farming increases zoonotic risk".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Livestock vaccination".into(),
                    "Hygiene after animal contact".into(),
                    "Protective equipment".into(),
                ],
                who_reference: Some("ICD-10: A20-A28 (Zoonoses)".into()),
                recommended_insurance: vec![InsuranceProductType::InpatientCover],
            },
            Hazard {
                id: "farmer_musculoskeletal".into(),
                category: HazardCategory::Musculoskeletal,
                name: "Back and Joint Problems".into(),
                description: "Bending, digging, carrying heavy loads. \
                              Chronic lower back pain is the most common farming injury.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.0,
                prevalence: 0.65,
                data_signals: vec![
                    DataSignal {
                        name: "mechanization_level".into(),
                        description: "Manual farming has higher musculoskeletal risk than mechanized".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Ergonomic tools".into(),
                    "Stretching exercises".into(),
                    "Mechanization where possible".into(),
                ],
                who_reference: Some("ICD-10: M54".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
        ],
        notes: "Farmers are the largest informal worker group in Kenya. \
                WHO estimates 860,000 deaths from agricultural work annually globally. \
                Pesticide poisoning is the most underreported occupational disease in Africa.".into(),
    }
}

fn fisherman_risk_profile() -> OccupationRiskProfile {
    OccupationRiskProfile {
        occupation: OccupationType::Fisherman,
        display_name: "Fisherman".into(),
        display_name_sw: "Mvuvi".into(),
        overall_risk_multiplier: 3.2,
        typical_work_hours_per_day: 10.0,
        exposure_duration_years_avg: 15.0,
        hazards: vec![
            Hazard {
                id: "fisherman_drowning".into(),
                category: HazardCategory::Accident,
                name: "Drowning".into(),
                description: "Capsizing, falling overboard, storms. \
                              Fishing has the highest occupational fatality rate of any sector \
                              globally (FAO). Most fishermen cannot swim well."
                    .into(),
                severity: HazardSeverity::Critical,
                base_risk_multiplier: 4.5,
                prevalence: 0.05, // 5% fatality risk per career
                data_signals: vec![
                    DataSignal {
                        name: "lake_vs_ocean".into(),
                        description: "Ocean fishing has higher drowning risk than lake fishing"
                            .into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                    DataSignal {
                        name: "boat_type".into(),
                        description: "Small boats/canoes have higher capsizing risk".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                    DataSignal {
                        name: "night_fishing".into(),
                        description: "Night fishing increases accident risk".into(),
                        source: DataSource::TransactionPatterns,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Life jackets".into(),
                    "Swimming training".into(),
                    "Weather monitoring".into(),
                    "Communication equipment".into(),
                ],
                who_reference: Some("ICD-10: W65-W74 (Drowning)".into()),
                recommended_insurance: vec![
                    InsuranceProductType::PersonalAccident,
                    InsuranceProductType::LifeInsurance,
                ],
            },
            Hazard {
                id: "fisherman_sun_exposure".into(),
                category: HazardCategory::EnvironmentalExposure,
                name: "UV and Sun Exposure".into(),
                description: "Water reflects UV radiation, doubling exposure. \
                              All-day sun causes skin damage, cataracts, and skin cancer."
                    .into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.5,
                prevalence: 0.90,
                data_signals: vec![],
                mitigation_factors: vec![
                    "Sunscreen".into(),
                    "Protective clothing".into(),
                    "Sunglasses".into(),
                ],
                who_reference: Some("ICD-10: L57 (Skin)".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "fisherman_waterborne_disease".into(),
                category: HazardCategory::BiologicalExposure,
                name: "Waterborne Diseases".into(),
                description:
                    "Schistosomiasis (bilharzia), leptospirosis, typhoid from contaminated water. \
                              Lake Victoria region has highest bilharzia burden in Kenya."
                        .into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.8,
                prevalence: 0.30,
                data_signals: vec![DataSignal {
                    name: "water_body_type".into(),
                    description: "Freshwater lakes have higher bilharzia risk than ocean".into(),
                    source: DataSource::SelfReported,
                    impact_on_risk: RiskDirection::Increases,
                }],
                mitigation_factors: vec![
                    "Protective footwear in water".into(),
                    "Clean water access".into(),
                    "Regular deworming".into(),
                ],
                who_reference: Some("ICD-10: B65 (Schistosomiasis)".into()),
                recommended_insurance: vec![InsuranceProductType::InpatientCover],
            },
            Hazard {
                id: "fisherman_fishing_injuries".into(),
                category: HazardCategory::Accident,
                name: "Fishing-Related Injuries".into(),
                description: "Hook injuries, net entanglement, fish spine punctures, \
                              cuts from fish knives. Often become infected."
                    .into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.0,
                prevalence: 0.40,
                data_signals: vec![],
                mitigation_factors: vec![
                    "Protective gloves".into(),
                    "First aid training".into(),
                    "Proper tool maintenance".into(),
                ],
                who_reference: None,
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "fisherman_mental_health".into(),
                category: HazardCategory::MentalHealth,
                name: "Isolation and Financial Stress".into(),
                description: "Long periods away from family, unpredictable catch, \
                              middleman exploitation of catch prices."
                    .into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.0,
                prevalence: 0.35,
                data_signals: vec![DataSignal {
                    name: "income_volatility".into(),
                    description: "Highly variable income from catch sales".into(),
                    source: DataSource::TransactionPatterns,
                    impact_on_risk: RiskDirection::Increases,
                }],
                mitigation_factors: vec![
                    "Community support".into(),
                    "Financial planning tools".into(),
                ],
                who_reference: Some("ICD-10: F32 (Depression)".into()),
                recommended_insurance: vec![InsuranceProductType::MentalHealthCover],
            },
        ],
        notes: "FAO estimates fishing is the most dangerous occupation globally by fatality rate. \
                In Kenya, ~500K fishermen work on Lake Victoria, Lake Turkana, and the coast. \
                Most use small boats without safety equipment."
            .into(),
    }
}

fn market_vendor_risk_profile() -> OccupationRiskProfile {
    OccupationRiskProfile {
        occupation: OccupationType::MarketVendor,
        display_name: "Market Vendor (Mama Mboga)".into(),
        display_name_sw: "Mama Mboga".into(),
        overall_risk_multiplier: 1.8,
        typical_work_hours_per_day: 12.0,
        exposure_duration_years_avg: 15.0,
        hazards: vec![
            Hazard {
                id: "vendor_respiratory".into(),
                category: HazardCategory::Respiratory,
                name: "Dust and Smoke Exposure".into(),
                description: "Charcoal smoke, vehicle exhaust, dust from roads and produce. \
                              Chronic exposure causes respiratory irritation and disease.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.0,
                prevalence: 0.60,
                data_signals: vec![
                    DataSignal {
                        name: "market_location".into(),
                        description: "Roadside vendors have higher pollution exposure than covered market vendors".into(),
                        source: DataSource::LocationData,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Covered market stalls".into(),
                    "Avoiding charcoal cooking in enclosed spaces".into(),
                ],
                who_reference: Some("ICD-10: J60-J70".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "vendor_musculoskeletal".into(),
                category: HazardCategory::Musculoskeletal,
                name: "Standing and Lifting Strain".into(),
                description: "12+ hours standing, carrying heavy produce loads, \
                              repetitive chopping and sorting motions.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.0,
                prevalence: 0.55,
                data_signals: vec![
                    DataSignal {
                        name: "daily_hours".into(),
                        description: "Longer hours → more strain".into(),
                        source: DataSource::WorkHours,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Stools for sitting breaks".into(),
                    "Proper lifting technique".into(),
                    "Supportive footwear".into(),
                ],
                who_reference: Some("ICD-10: M54".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "vendor_uv_exposure".into(),
                category: HazardCategory::EnvironmentalExposure,
                name: "UV and Heat Exposure".into(),
                description: "All-day outdoor work in sun. Skin damage, heat stress, dehydration.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 1.8,
                prevalence: 0.70,
                data_signals: vec![],
                mitigation_factors: vec!["Shade structures".into(), "Hydration".into(), "Sunscreen".into()],
                who_reference: None,
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
        ],
        notes: "Market vendors are the largest group in our system. While not as high-risk as miners or riders, \
                they face cumulative health effects from years of outdoor work with poor ergonomics. \
                Income stability is a better proxy for this group than for high-risk occupations.".into(),
    }
}

fn salon_worker_risk_profile() -> OccupationRiskProfile {
    OccupationRiskProfile {
        occupation: OccupationType::SalonWorker,
        display_name: "Salon Worker".into(),
        display_name_sw: "Mfanyakazi wa Saluni".into(),
        overall_risk_multiplier: 2.2,
        typical_work_hours_per_day: 10.0,
        exposure_duration_years_avg: 8.0,
        hazards: vec![
            Hazard {
                id: "salon_chemical".into(),
                category: HazardCategory::ChemicalExposure,
                name: "Chemical Exposure (Relaxants, Dyes, Acetone)".into(),
                description: "Hair relaxers contain formaldehyde and lye. Hair dyes contain \
                              aromatic amines (carcinogens). Nail acetone and acrylics release volatile \
                              organic compounds. Chronic exposure linked to respiratory disease and cancer.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 3.0,
                prevalence: 0.85,
                data_signals: vec![
                    DataSignal {
                        name: "service_type".into(),
                        description: "Hair relaxing and coloring has highest chemical exposure; braiding is lower risk".into(),
                        source: DataSource::SelfReported,
                        impact_on_risk: RiskDirection::Increases,
                    },
                    DataSignal {
                        name: "daily_hours_enclosed".into(),
                        description: "Longer hours in enclosed salon → more chemical inhalation".into(),
                        source: DataSource::WorkHours,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Ventilation (fans, open windows)".into(),
                    "Gloves for chemical handling".into(),
                    "Less toxic product alternatives".into(),
                    "Limiting continuous chemical service hours".into(),
                ],
                who_reference: Some("ICD-10: J60-J70 (Respiratory), T52-T65 (Chemicals)".into()),
                recommended_insurance: vec![
                    InsuranceProductType::CriticalIllness,
                    InsuranceProductType::OutpatientCover,
                ],
            },
            Hazard {
                id: "salon_respiratory".into(),
                category: HazardCategory::Respiratory,
                name: "Respiratory Irritation".into(),
                description: "Inhalation of chemical fumes, hair dust, and nail particles. \
                              Causes asthma, bronchitis, and chronic respiratory irritation.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.5,
                prevalence: 0.60,
                data_signals: vec![],
                mitigation_factors: vec!["Ventilation".into(), "Masks during chemical services".into()],
                who_reference: Some("ICD-10: J45 (Asthma)".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "salon_repetitive_strain".into(),
                category: HazardCategory::Ergonomic,
                name: "Repetitive Strain Injury".into(),
                description: "Repetitive hand/wrist motions (braiding, cutting, styling) \
                              cause carpal tunnel syndrome, tendonitis, and shoulder problems.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.0,
                prevalence: 0.45,
                data_signals: vec![
                    DataSignal {
                        name: "service_hours".into(),
                        description: "More hands-on service hours → higher repetitive strain".into(),
                        source: DataSource::WorkHours,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Stretching breaks".into(),
                    "Ergonomic tools".into(),
                    "Alternating service types".into(),
                ],
                who_reference: Some("ICD-10: G56 (Carpal Tunnel)".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
        ],
        notes: "Salon workers face significant chemical exposure risks that are completely invisible \
                to income-based health models. A high-earning salon owner using relaxers daily \
                has higher health risk than income data suggests.".into(),
    }
}

fn household_worker_risk_profile() -> OccupationRiskProfile {
    OccupationRiskProfile {
        occupation: OccupationType::HouseholdWorker,
        display_name: "Household Worker".into(),
        display_name_sw: "Mfanyakazi wa Nyumbani".into(),
        overall_risk_multiplier: 2.0,
        typical_work_hours_per_day: 10.0,
        exposure_duration_years_avg: 12.0,
        hazards: vec![
            Hazard {
                id: "household_chemical".into(),
                category: HazardCategory::ChemicalExposure,
                name: "Cleaning Chemical Exposure".into(),
                description: "Bleach, ammonia, disinfectants. Mixing chemicals creates toxic fumes. \
                              Chronic exposure causes skin irritation, respiratory damage, and chemical burns.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.2,
                prevalence: 0.75,
                data_signals: vec![
                    DataSignal {
                        name: "work_frequency".into(),
                        description: "Daily cleaning work → chronic exposure".into(),
                        source: DataSource::WorkHours,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Gloves".into(),
                    "Ventilation during cleaning".into(),
                    "Never mixing bleach and ammonia".into(),
                    "Using less toxic alternatives".into(),
                ],
                who_reference: Some("ICD-10: T52-T65".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "household_physical_strain".into(),
                category: HazardCategory::Musculoskeletal,
                name: "Physical Strain".into(),
                description: "Scrubbing floors, carrying heavy loads, lifting children, \
                              prolonged standing. Chronic back and joint pain.".into(),
                severity: HazardSeverity::Moderate,
                base_risk_multiplier: 2.0,
                prevalence: 0.60,
                data_signals: vec![],
                mitigation_factors: vec![
                    "Proper lifting technique".into(),
                    "Ergonomic tools".into(),
                    "Rest breaks".into(),
                ],
                who_reference: Some("ICD-10: M54".into()),
                recommended_insurance: vec![InsuranceProductType::OutpatientCover],
            },
            Hazard {
                id: "household_mental_health".into(),
                category: HazardCategory::MentalHealth,
                name: "Mental Health Risks".into(),
                description: "Isolation, power imbalance with employer, wage theft, \
                              verbal/physical abuse, lack of social interaction. \
                              Household workers have high rates of depression and anxiety.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 2.8,
                prevalence: 0.40,
                data_signals: vec![
                    DataSignal {
                        name: "income_regularity".into(),
                        description: "Irregular payment correlates with employer exploitation".into(),
                        source: DataSource::TransactionPatterns,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Worker support networks".into(),
                    "Know your rights".into(),
                    "Reporting mechanisms".into(),
                ],
                who_reference: Some("ICD-10: F32 (Depression), F41 (Anxiety)".into()),
                recommended_insurance: vec![InsuranceProductType::MentalHealthCover],
            },
            Hazard {
                id: "household_violence".into(),
                category: HazardCategory::Violence,
                name: "Verbal and Physical Abuse".into(),
                description: "Household workers face disproportionate rates of employer abuse. \
                              Working in private homes limits oversight and reporting.".into(),
                severity: HazardSeverity::High,
                base_risk_multiplier: 3.0,
                prevalence: 0.25,
                data_signals: vec![
                    DataSignal {
                        name: "employer_count".into(),
                        description: "Multiple employers may indicate unstable/abusive arrangements".into(),
                        source: DataSource::TransactionPatterns,
                        impact_on_risk: RiskDirection::Increases,
                    },
                ],
                mitigation_factors: vec![
                    "Formal employment contracts".into(),
                    "Worker hotlines".into(),
                    "Community oversight".into(),
                ],
                who_reference: None,
                recommended_insurance: vec![InsuranceProductType::PersonalAccident],
            },
        ],
        notes: "Household workers are among the most vulnerable informal workers. \
                ILO Convention 189 recognizes domestic workers' rights, but compliance is minimal in Kenya. \
                Mental health risks are particularly acute due to isolation and power imbalance.".into(),
    }
}

// Hawker — similar to Market Vendor but with:
//   - Higher accident risk (traffic exposure while selling roadside)
//   - Police harassment/violence risk (High severity)
//   - Higher weather exposure
//   overall_risk_multiplier: 2.2

// Jua Kali Artisan — similar to Construction Worker but with:
//   - Metal fume exposure (welding, cutting)
//   - Noise exposure (grinding, hammering)
//   - Eye injury risk (sparks, metal fragments)
//   - Burns from hot metal
//   overall_risk_multiplier: 2.8

// Matatu Operator — similar to Boda Boda but with:
//   - Lower accident severity (enclosed vehicle) but higher accident frequency
//   - Sedentary health effects (sitting 12+ hours)
//   - Stress from traffic and passenger management
//   overall_risk_multiplier: 2.5

// Waste Picker — similar to Miner but with:
//   - Biological exposure (needles, medical waste, rotting material)
//   - Chemical exposure (batteries, electronics, paint)
//   - Infection risk (tetanus, hepatitis, HIV from needle sticks)
//   - Respiratory exposure (burning waste, dust)
//   overall_risk_multiplier: 3.5

// Cross-Border Trader:
//   - Travel fatigue and road accident risk
//   - Exposure to unfamiliar diseases in different regions
//   - Stress from border crossing uncertainty
//   - Robbery risk (carrying goods/cash)
//   overall_risk_multiplier: 2.0

// M-Pesa Agent:
//   - Robbery risk (cash handling) — HIGH
//   - Sedentary health effects — Moderate
//   - Stress from balancing float — Moderate
//   overall_risk_multiplier: 1.5

// Duka Owner:
//   - Sedentary health effects — Moderate
//   - Robbery risk — Moderate
//   - Dust exposure (some duka types) — Low-Moderate
//   overall_risk_multiplier: 1.5

// Food Seller:
//   - Burns from cooking — Moderate
//   - Smoke inhalation (charcoal cooking) — High
//   - Musculoskeletal from standing/cooking — Moderate
//   - Foodborne illness risk — Moderate
//   overall_risk_multiplier: 2.0

fn translate_hazard_name(hazard_id: &str) -> String {
    match hazard_id {
        "boda_accident_road" => "Ajali ya Barabarani",
        "boda_musculoskeletal" => "Maumivu ya Viungo",
        "boda_hearing_loss" => "Kupungua kwa Kusikia",
        "boda_weather_exposure" => "Athari za Hali ya Hewa",
        "boda_mental_health" => "Afya ya Akili",
        "boda_violence" => "Uvamizi/Unyanyasaji",
        "miner_respiratory" => "Magonjwa ya Kupumua",
        "miner_cave_in" => "Kuanguka kwa Mgodi",
        "miner_heavy_metal" => "Sumu ya Metali",
        "construction_fall" => "Kuanguka kutoka Juu",
        "construction_musculoskeletal" => "Maumivu ya Mifupa",
        "construction_dust" => "Vumbi/Dust",
        "farmer_pesticide" => "Sumu ya Dawa za Kilimo",
        "farmer_heat_stress" => "Joto/Jua",
        "farmer_snake_bite" => "Kuumwa na Nyoka",
        "fisherman_drowning" => "Kuzama",
        "salon_chemical" => "Sumu za Kemikali",
        "household_mental_health" => "Afya ya Akili",
        _ => hazard_id.to_string(),
    }
}
