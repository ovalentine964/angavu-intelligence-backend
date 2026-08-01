"""
Cross-Cutting Models — Angavu Intelligence Backend

Implements:
  - Cultural Sensitivity Engine
  - Occupation Health Risk Scoring
  - Wage Gap Tracker
  - Care Economy Tracker
  - Property Rights Documentation
  - Citizen Monitoring Tools
  - Decentralization Tracker
  - Practical Validation Framework
  - Internship/Practical Tracker (ECO 404)
"""

import json
import sys
import numpy as np
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta


# ── 1. Cultural Sensitivity Engine ────────────────────────────────

class CulturalSensitivityEngine:
    """
    Adapt communication style to cultural context.
    Supports Kenyan ethnic groups with communication norms,
    greeting protocols, and taboo avoidance.
    """

    CULTURAL_PROFILES = {
        "kikuyu": {
            "greeting_style": "formal_handshake",
            "business_directness": 0.7,
            "time_orientation": "monochronic",
            "hierarchy_respect": 0.6,
            "taboo_topics": ["witchcraft"],
            "preferred_language": "sw",
            "proverb_tradition": "moderate",
            "collectivism_score": 0.6,
        },
        "luo": {
            "greeting_style": "warm_prolonged",
            "business_directness": 0.8,
            "time_orientation": "polychronic",
            "hierarchy_respect": 0.5,
            "taboo_topics": [],
            "preferred_language": "luo",
            "proverb_tradition": "strong",
            "collectivism_score": 0.7,
        },
        "kalenjin": {
            "greeting_style": "respectful_formal",
            "business_directness": 0.5,
            "time_orientation": "polychronic",
            "hierarchy_respect": 0.8,
            "taboo_topics": ["age_disrespect"],
            "preferred_language": "kln",
            "proverb_tradition": "strong",
            "collectivism_score": 0.8,
        },
        "kamba": {
            "greeting_style": "warm_modest",
            "business_directness": 0.6,
            "time_orientation": "polychronic",
            "hierarchy_respect": 0.7,
            "taboo_topics": [],
            "preferred_language": "kam",
            "proverb_tradition": "moderate",
            "collectivism_score": 0.7,
        },
        "meru": {
            "greeting_style": "formal_respectful",
            "business_directness": 0.7,
            "time_orientation": "monochronic",
            "hierarchy_respect": 0.7,
            "taboo_topics": [],
            "preferred_language": "mer",
            "proverb_tradition": "moderate",
            "collectivism_score": 0.6,
        },
        "coastal": {
            "greeting_style": "salaam_greeting",
            "business_directness": 0.4,
            "time_orientation": "polychronic",
            "hierarchy_respect": 0.8,
            "taboo_topics": ["religious_insensitivity"],
            "preferred_language": "sw",
            "proverb_tradition": "strong",
            "collectivism_score": 0.8,
        },
        "maasai": {
            "greeting_style": "ceremonial",
            "business_directness": 0.3,
            "time_orientation": "polychronic",
            "hierarchy_respect": 0.9,
            "taboo_topics": ["cattle_disrespect", "age_disrespect"],
            "preferred_language": "mas",
            "proverb_tradition": "very_strong",
            "collectivism_score": 0.9,
        },
    }

    def adapt_communication(self, cultural_group: str, message: str,
                            context: str = "business") -> Dict[str, Any]:
        """Adapt a message to cultural context."""
        group = cultural_group.lower()
        if group not in self.CULTURAL_PROFILES:
            return {"error": f"Unknown cultural group: {cultural_group}",
                    "available": list(self.CULTURAL_PROFILES.keys())}

        profile = self.CULTURAL_PROFILES[group]
        adaptations = []

        # Greeting adaptation
        if profile["greeting_style"] == "salaam_greeting":
            adaptations.append("Use 'Assalamu alaikum' greeting before business")
        elif profile["greeting_style"] == "warm_prolonged":
            adaptations.append("Allow extended greeting and personal inquiries")
        elif profile["greeting_style"] == "ceremonial":
            adaptations.append("Use formal ceremonial greeting protocol")
        else:
            adaptations.append(f"Use {profile['greeting_style'].replace('_', ' ')} greeting")

        # Directness adaptation
        if profile["business_directness"] < 0.5:
            adaptations.append("Use indirect communication style; build rapport first")
        elif profile["business_directness"] > 0.7:
            adaptations.append("Direct communication is acceptable")

        # Hierarchy
        if profile["hierarchy_respect"] > 0.7:
            adaptations.append("Address elders and authority figures with extra respect")

        # Collectivism
        if profile["collectivism_score"] > 0.7:
            adaptations.append("Frame proposals in terms of community benefit, not just individual")

        # Proverbs
        if profile["proverb_tradition"] in ("strong", "very_strong"):
            adaptations.append(f"Incorporate {group} proverbs for persuasion and rapport")

        return {
            "cultural_group": cultural_group,
            "profile": profile,
            "adaptations": adaptations,
            "context": context,
            "adjusted_directness": profile["business_directness"],
            "adjusted_hierarchy": profile["hierarchy_respect"],
        }


# ── 2. Occupation Health Risk Scoring ─────────────────────────────

class OccupationHealthRiskScorer:
    """
    Formal health risk scoring per worker type for Kenyan informal sector.
    Based on occupation-specific hazards, working conditions, and exposure.
    """

    OCCUPATION_RISKS = {
        "boda_boda": {
            "accident_risk": 0.85,
            "respiratory_risk": 0.4,
            "musculoskeletal_risk": 0.7,
            "noise_exposure": 0.7,
            "pollution_exposure": 0.8,
            "mental_stress": 0.6,
            "uv_exposure": 0.6,
            "typical_hours_week": 70,
        },
        "jua_kali": {
            "accident_risk": 0.6,
            "respiratory_risk": 0.7,
            "musculoskeletal_risk": 0.8,
            "noise_exposure": 0.8,
            "pollution_exposure": 0.6,
            "mental_stress": 0.5,
            "uv_exposure": 0.5,
            "typical_hours_week": 60,
        },
        "construction": {
            "accident_risk": 0.8,
            "respiratory_risk": 0.6,
            "musculoskeletal_risk": 0.9,
            "noise_exposure": 0.7,
            "pollution_exposure": 0.5,
            "mental_stress": 0.5,
            "uv_exposure": 0.7,
            "typical_hours_week": 55,
        },
        "vendor": {
            "accident_risk": 0.2,
            "respiratory_risk": 0.3,
            "musculoskeletal_risk": 0.5,
            "noise_exposure": 0.4,
            "pollution_exposure": 0.4,
            "mental_stress": 0.5,
            "uv_exposure": 0.6,
            "typical_hours_week": 65,
        },
        "farmer": {
            "accident_risk": 0.4,
            "respiratory_risk": 0.5,
            "musculoskeletal_risk": 0.7,
            "noise_exposure": 0.3,
            "pollution_exposure": 0.3,
            "mental_stress": 0.4,
            "uv_exposure": 0.8,
            "typical_hours_week": 60,
        },
        "fisherman": {
            "accident_risk": 0.7,
            "respiratory_risk": 0.3,
            "musculoskeletal_risk": 0.6,
            "noise_exposure": 0.2,
            "pollution_exposure": 0.3,
            "mental_stress": 0.5,
            "uv_exposure": 0.7,
            "typical_hours_week": 50,
        },
        "domestic_worker": {
            "accident_risk": 0.2,
            "respiratory_risk": 0.3,
            "musculoskeletal_risk": 0.5,
            "noise_exposure": 0.2,
            "pollution_exposure": 0.2,
            "mental_stress": 0.6,
            "uv_exposure": 0.1,
            "typical_hours_week": 60,
        },
        "mining": {
            "accident_risk": 0.8,
            "respiratory_risk": 0.9,
            "musculoskeletal_risk": 0.8,
            "noise_exposure": 0.9,
            "pollution_exposure": 0.8,
            "mental_stress": 0.6,
            "uv_exposure": 0.2,
            "typical_hours_week": 55,
        },
    }

    def score(self, occupation: str, years_experience: int = 5,
              has_ppe: bool = False, region: str = "urban") -> Dict[str, Any]:
        """Compute comprehensive health risk score for a worker."""
        occ = occupation.lower()
        if occ not in self.OCCUPATION_RISKS:
            return {"error": f"Unknown occupation: {occupation}",
                    "available": list(self.OCCUPATION_RISKS.keys())}

        risks = self.OCCUPATION_RISKS[occ]

        # PPE mitigation
        ppe_factor = 0.7 if has_ppe else 1.0

        # Experience effect (experienced workers have lower accident risk)
        exp_factor = max(0.5, 1.0 - years_experience * 0.02)

        # Regional adjustment (rural areas may have less safety infrastructure)
        region_factor = 1.1 if region == "rural" else 1.0

        # Weighted composite score
        weights = {
            "accident_risk": 0.25,
            "respiratory_risk": 0.15,
            "musculoskeletal_risk": 0.15,
            "noise_exposure": 0.10,
            "pollution_exposure": 0.10,
            "mental_stress": 0.15,
            "uv_exposure": 0.10,
        }

        adjusted_risks = {}
        for key, weight in weights.items():
            base = risks.get(key, 0)
            if key == "accident_risk":
                base *= exp_factor * ppe_factor
            adjusted_risks[key] = min(base * region_factor, 1.0)

        composite = sum(adjusted_risks[k] * weights[k] for k in weights)

        # Overwork risk
        overwork = max(0, (risks["typical_hours_week"] - 48) / 48)

        return {
            "occupation": occupation,
            "composite_risk_score": round(composite, 3),
            "risk_category": (
                "critical" if composite > 0.7 else
                "high" if composite > 0.5 else
                "moderate" if composite > 0.3 else "low"
            ),
            "individual_risks": adjusted_risks,
            "overwork_score": round(overwork, 3),
            "typical_hours_week": risks["typical_hours_week"],
            "has_ppe": has_ppe,
            "years_experience": years_experience,
            "region": region,
            "recommendations": self._recommendations(adjusted_risks, occ, has_ppe),
        }

    def _recommendations(self, risks: Dict, occupation: str, has_ppe: bool) -> List[str]:
        recs = []
        if risks.get("accident_risk", 0) > 0.5:
            recs.append("Enroll in NHIF occupational accident cover")
        if risks.get("respiratory_risk", 0) > 0.5:
            recs.append("Use respiratory protection (N95 or dust mask)")
        if risks.get("musculoskeletal_risk", 0) > 0.5:
            recs.append("Ergonomic assessment and regular stretching breaks")
        if not has_ppe:
            recs.append("Obtain basic PPE (gloves, helmet, reflective vest)")
        if risks.get("mental_stress", 0) > 0.5:
            recs.append("Access mental health support services")
        return recs


# ── 3. Wage Gap Tracker ───────────────────────────────────────────

class WageGapTracker:
    """
    Track and analyze wage gaps across demographics.
    Supports gender, education, region, and occupation comparisons.
    """

    def analyze(self, wages_a: List[float], wages_b: List[float],
                group_a_name: str = "Group A", group_b_name: str = "Group B") -> Dict[str, Any]:
        """Compute wage gap statistics between two groups."""
        a = np.array(wages_a)
        b = np.array(wages_b)

        mean_a = float(np.mean(a))
        mean_b = float(np.mean(b))
        median_a = float(np.median(a))
        median_b = float(np.median(b))

        # Raw gap
        raw_gap = (mean_a - mean_b) / mean_a if mean_a > 0 else 0

        # Oaxaca-Blinder decomposition (simplified)
        # Gap = explained (by characteristics) + unexplained (discrimination proxy)

        # Percentile gaps
        p10_a, p90_a = float(np.percentile(a, 10)), float(np.percentile(a, 90))
        p10_b, p90_b = float(np.percentile(b, 10)), float(np.percentile(b, 90))

        return {
            "group_a": group_a_name,
            "group_b": group_b_name,
            "mean_a": mean_a,
            "mean_b": mean_b,
            "median_a": median_a,
            "median_b": median_b,
            "raw_wage_gap": round(raw_gap, 4),
            "raw_gap_percentage": f"{raw_gap * 100:.1f}%",
            "median_gap": round((median_a - median_b) / median_a, 4) if median_a > 0 else 0,
            "p10_gap": round((p10_a - p10_b) / p10_a, 4) if p10_a > 0 else 0,
            "p90_gap": round((p90_a - p90_b) / p90_a, 4) if p90_a > 0 else 0,
            "n_group_a": len(a),
            "n_group_b": len(b),
            "std_a": float(np.std(a)),
            "std_b": float(np.std(b)),
        }


# ── 4. Care Economy Tracker ───────────────────────────────────────

class CareEconomyTracker:
    """
    Track unpaid care work hours and their economic value.
    Critical for gender economics and GDP measurement gaps.
    """

    # Average daily hours for care activities in Kenya (from time-use surveys)
    DEFAULT_CARE_ACTIVITIES = {
        "childcare": {"avg_hours": 3.5, "market_wage_equivalent": 200},
        "elder_care": {"avg_hours": 1.5, "market_wage_equivalent": 250},
        "cooking": {"avg_hours": 2.5, "market_wage_equivalent": 150},
        "cleaning": {"avg_hours": 2.0, "market_wage_equivalent": 150},
        "water_collection": {"avg_hours": 1.0, "market_wage_equivalent": 100},
        "firewood_collection": {"avg_hours": 0.5, "market_wage_equivalent": 80},
    }

    def estimate(self, care_hours: Optional[Dict[str, float]] = None,
                 gender: str = "female", days_per_month: int = 30) -> Dict[str, Any]:
        """Estimate care economy contribution."""
        activities = care_hours or {
            k: v["avg_hours"] for k, v in self.DEFAULT_CARE_ACTIVITIES.items()
        }

        total_daily_hours = sum(activities.values())
        total_monthly_hours = total_daily_hours * days_per_month

        # Economic value
        total_daily_value = 0
        activity_values = {}
        for activity, hours in activities.items():
            if activity in self.DEFAULT_CARE_ACTIVITIES:
                wage = self.DEFAULT_CARE_ACTIVITIES[activity]["market_wage_equivalent"]
            else:
                wage = 150  # default
            daily_val = hours * wage
            total_daily_value += daily_val
            activity_values[activity] = {
                "daily_hours": hours,
                "monthly_hours": hours * days_per_month,
                "daily_value_kes": daily_val,
                "monthly_value_kes": daily_val * days_per_month,
            }

        monthly_value = total_daily_value * days_per_month
        annual_value = monthly_value * 12

        return {
            "gender": gender,
            "total_daily_hours": round(total_daily_hours, 1),
            "total_monthly_hours": round(total_monthly_hours, 1),
            "total_annual_hours": round(total_monthly_hours * 12, 1),
            "daily_value_kes": round(total_daily_value, 0),
            "monthly_value_kes": round(monthly_value, 0),
            "annual_value_kes": round(annual_value, 0),
            "annual_value_usd": round(annual_value / 150, 0),  # approx KES/USD
            "activity_breakdown": activity_values,
            "gender_burden_note": "Women in Kenya承担 3-4x more unpaid care work than men" if gender == "female" else "",
        }


# ── 5. Property Rights Documentation ──────────────────────────────

class PropertyRightsDocumenter:
    """
    Track informal property rights status.
    Many Kenyans hold land informally — this tracks documentation gaps.
    """

    TENURE_TYPES = [
        "freehold", "leasehold", "customary", "informal_settlement",
        "family_land", "community_land", "government_allocation"
    ]

    def assess(self, tenure_type: str, has_title_deed: bool = False,
               has_survey: bool = False, has_beacons: bool = False,
               has_consent: bool = False, area_sqm: float = 0,
               value_estimate_kes: float = 0, county: str = "") -> Dict[str, Any]:
        """Assess property rights documentation completeness."""
        # Documentation score (0-1)
        doc_score = 0.0
        if has_title_deed:
            doc_score += 0.4
        if has_survey:
            doc_score += 0.2
        if has_beacons:
            doc_score += 0.15
        if has_consent:
            doc_score += 0.15

        # Additional score for formal tenure
        tenure_formality = {
            "freehold": 1.0, "leasehold": 0.8, "government_allocation": 0.7,
            "customary": 0.4, "family_land": 0.3, "community_land": 0.3,
            "informal_settlement": 0.1
        }
        tenure_score = tenure_formality.get(tenure_type, 0.2)

        composite = 0.6 * doc_score + 0.4 * tenure_score

        # Risk factors
        risks = []
        if not has_title_deed:
            risks.append("No title deed — vulnerable to land grabbing")
        if tenure_type == "informal_settlement":
            risks.append("Informal settlement — high eviction risk")
        if not has_survey:
            risks.append("No survey — boundary disputes likely")

        return {
            "tenure_type": tenure_type,
            "documentation_score": round(doc_score, 2),
            "tenure_formality_score": round(tenure_score, 2),
            "composite_security_score": round(composite, 2),
            "security_level": (
                "secure" if composite > 0.7 else
                "moderate" if composite > 0.4 else
                "vulnerable" if composite > 0.2 else "insecure"
            ),
            "has_title_deed": has_title_deed,
            "has_survey": has_survey,
            "has_beacons": has_beacons,
            "risks": risks,
            "recommendations": self._recommendations(composite, has_title_deed, tenure_type),
            "area_sqm": area_sqm,
            "value_estimate_kes": value_estimate_kes,
            "county": county,
        }

    def _recommendations(self, score: float, has_title: bool, tenure: str) -> List[str]:
        recs = []
        if not has_title:
            recs.append("Apply for title deed through National Land Commission")
        if tenure in ("informal_settlement", "customary"):
            recs.append("Register with community land registrar")
        if score < 0.5:
            recs.append("Seek legal aid for land rights protection")
        return recs


# ── 6. Citizen Monitoring Tools ───────────────────────────────────

class CitizenMonitor:
    """
    Governance transparency tools for citizens.
    Track government spending, service delivery, and accountability.
    """

    def track_service_delivery(self, county: str, services: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Track service delivery metrics for a county.

        Args:
            services: {"health": {"target": 10, "actual": 7}, "water": {...}}
        """
        results = {}
        for service, data in services.items():
            target = data.get("target", 1)
            actual = data.get("actual", 0)
            delivery_rate = actual / target if target > 0 else 0
            results[service] = {
                "target": target,
                "actual": actual,
                "delivery_rate": round(delivery_rate, 3),
                "status": (
                    "on_track" if delivery_rate >= 0.9 else
                    "behind" if delivery_rate >= 0.5 else
                    "critical"
                )
            }

        overall = np.mean([r["delivery_rate"] for r in results.values()])
        return {
            "county": county,
            "services": results,
            "overall_delivery_rate": round(float(overall), 3),
            "accountability_score": round(float(overall * 100), 1),
        }

    def budget_transparency_check(self, county: str,
                                   published_items: int,
                                   total_items: int) -> Dict[str, Any]:
        """Check budget transparency compliance."""
        score = published_items / total_items if total_items > 0 else 0
        return {
            "county": county,
            "published_items": published_items,
            "total_items": total_items,
            "transparency_score": round(score, 3),
            "compliant": score >= 0.8,
            "recommendation": "Publish all budget line items for transparency" if score < 0.8 else "Good transparency"
        }


# ── 7. Decentralization Tracker ───────────────────────────────────

class DecentralizationTracker:
    """
    Track Kenya's devolution progress across 47 counties.
    Measures fiscal decentralization, function transfer, and capacity.
    """

    DEVOLUTION_PILLARS = [
        "fiscal_autonomy", "function_transfer", "hr_capacity",
        "planning_mcbf", "public_participation", "oversight"
    ]

    def assess_county(self, county: str, scores: Dict[str, float]) -> Dict[str, Any]:
        """Assess devolution progress for a county."""
        pillar_scores = {}
        for pillar in self.DEVOLUTION_PILLARS:
            raw = scores.get(pillar, 0)
            pillar_scores[pillar] = {
                "score": min(max(raw, 0), 1.0),
                "level": (
                    "advanced" if raw >= 0.8 else
                    "progressing" if raw >= 0.5 else
                    "emerging" if raw >= 0.3 else "nascent"
                )
            }

        overall = np.mean([p["score"] for p in pillar_scores.values()])

        return {
            "county": county,
            "pillar_scores": pillar_scores,
            "overall_devolution_score": round(float(overall), 3),
            "devolution_level": (
                "advanced" if overall >= 0.8 else
                "progressing" if overall >= 0.5 else
                "emerging" if overall >= 0.3 else "nascent"
            ),
            "weakest_pillar": min(pillar_scores, key=lambda k: pillar_scores[k]["score"]),
            "strongest_pillar": max(pillar_scores, key=lambda k: pillar_scores[k]["score"]),
        }


# ── 8. Practical Validation Framework ─────────────────────────────

class PracticalValidationFramework:
    """
    Framework for testing tools and interventions in real-world settings.
    Supports RCTs, A/B tests, and quasi-experimental designs.
    """

    def design_experiment(self, intervention: str, outcome: str,
                          n_treatment: int = 100, n_control: int = 100,
                          baseline_mean: float = 0, baseline_std: float = 1,
                          min_detectable_effect: float = 0.2) -> Dict[str, Any]:
        """Design a validation experiment with power analysis."""
        # Power analysis for two-sample t-test
        from scipy import stats as sp_stats
        alpha = 0.05
        effect_size = min_detectable_effect / baseline_std if baseline_std > 0 else 0.2

        # Required sample size (simplified)
        z_alpha = 1.96  # two-tailed
        z_beta = 0.84   # 80% power
        n_required = ((z_alpha + z_beta) ** 2 * 2) / (effect_size ** 2) if effect_size > 0 else 100

        return {
            "intervention": intervention,
            "outcome": outcome,
            "design": "RCT",
            "n_treatment": n_treatment,
            "n_control": n_control,
            "n_required_per_arm": int(np.ceil(n_required)),
            "adequately_powered": n_treatment >= n_required,
            "min_detectable_effect": min_detectable_effect,
            "effect_size_cohens_d": round(effect_size, 3),
            "alpha": alpha,
            "power": 0.80,
            "baseline_mean": baseline_mean,
            "baseline_std": baseline_std,
        }

    def analyze_results(self, treatment: List[float], control: List[float]) -> Dict[str, Any]:
        """Analyze experimental results."""
        t = np.array(treatment)
        c = np.array(control)

        mean_diff = float(np.mean(t) - np.mean(c))
        pooled_std = np.sqrt((np.var(t) + np.var(c)) / 2)
        cohens_d = mean_diff / pooled_std if pooled_std > 0 else 0

        # Welch's t-test
        from scipy import stats as sp_stats
        t_stat, p_value = sp_stats.ttest_ind(t, c, equal_var=False)

        return {
            "treatment_mean": float(np.mean(t)),
            "control_mean": float(np.mean(c)),
            "mean_difference": mean_diff,
            "cohens_d": round(float(cohens_d), 3),
            "t_statistic": round(float(t_stat), 3),
            "p_value": round(float(p_value), 4),
            "significant_at_05": p_value < 0.05,
            "effect_size_label": (
                "large" if abs(cohens_d) > 0.8 else
                "medium" if abs(cohens_d) > 0.5 else
                "small" if abs(cohens_d) > 0.2 else "negligible"
            ),
            "n_treatment": len(t),
            "n_control": len(c),
        }


# ── 9. Internship/Practical Tracker (ECO 404) ────────────────────

class InternshipPracticalTracker:
    """
    Track ECO 404 practical application — internship hours,
    skills applied, and learning outcomes.
    """

    REQUIRED_HOURS = 480  # ECO 404 requirement
    SKILL_CATEGORIES = [
        "data_collection", "data_analysis", "report_writing",
        "fieldwork", "presentation", "policy_analysis",
        "econometric_application", "community_engagement"
    ]

    def track_progress(self, student_id: str, entries: List[Dict]) -> Dict[str, Any]:
        """Track internship/practical progress."""
        total_hours = 0
        skill_hours = {s: 0 for s in self.SKILL_CATEGORIES}
        weekly_hours = {}

        for entry in entries:
            hours = entry.get("hours", 0)
            skill = entry.get("skill", "data_collection")
            week = entry.get("week", 0)

            total_hours += hours
            if skill in skill_hours:
                skill_hours[skill] += hours
            weekly_hours.setdefault(week, 0)
            weekly_hours[week] += hours

        progress = total_hours / self.REQUIRED_HOURS if self.REQUIRED_HOURS > 0 else 0
        skills_covered = sum(1 for v in skill_hours.values() if v > 0)

        return {
            "student_id": student_id,
            "total_hours": total_hours,
            "required_hours": self.REQUIRED_HOURS,
            "progress_percentage": round(progress * 100, 1),
            "hours_remaining": max(0, self.REQUIRED_HOURS - total_hours),
            "on_track": progress >= 0.5,
            "skill_breakdown": skill_hours,
            "skills_covered": skills_covered,
            "total_skill_categories": len(self.SKILL_CATEGORIES),
            "weekly_summary": weekly_hours,
            "recommendation": (
                "On track" if progress >= 0.8 else
                "Increase fieldwork hours" if progress < 0.5 else
                "Focus on underrepresented skills"
            ),
        }


# ── Runner ────────────────────────────────────────────────────────

def run_method(method: str, args: Dict[str, Any]) -> Dict[str, Any]:
    dispatch = {
        "cultural_adapt": lambda a: CulturalSensitivityEngine().adapt_communication(
            a["cultural_group"], a.get("message", ""), a.get("context", "business")
        ),
        "health_risk_score": lambda a: OccupationHealthRiskScorer().score(
            a["occupation"], a.get("years_experience", 5),
            a.get("has_ppe", False), a.get("region", "urban")
        ),
        "wage_gap": lambda a: WageGapTracker().analyze(
            a["wages_a"], a["wages_b"],
            a.get("group_a_name", "Group A"), a.get("group_b_name", "Group B")
        ),
        "care_economy": lambda a: CareEconomyTracker().estimate(
            a.get("care_hours"), a.get("gender", "female"), a.get("days_per_month", 30)
        ),
        "property_rights": lambda a: PropertyRightsDocumenter().assess(
            a["tenure_type"], a.get("has_title_deed", False),
            a.get("has_survey", False), a.get("has_beacons", False),
            a.get("has_consent", False), a.get("area_sqm", 0),
            a.get("value_estimate_kes", 0), a.get("county", "")
        ),
        "citizen_service_delivery": lambda a: CitizenMonitor().track_service_delivery(
            a["county"], a["services"]
        ),
        "citizen_budget_transparency": lambda a: CitizenMonitor().budget_transparency_check(
            a["county"], a["published_items"], a["total_items"]
        ),
        "devolution_assess": lambda a: DecentralizationTracker().assess_county(
            a["county"], a["scores"]
        ),
        "practical_design": lambda a: PracticalValidationFramework().design_experiment(
            a["intervention"], a["outcome"],
            a.get("n_treatment", 100), a.get("n_control", 100),
            a.get("baseline_mean", 0), a.get("baseline_std", 1),
            a.get("min_detectable_effect", 0.2)
        ),
        "practical_analyze": lambda a: PracticalValidationFramework().analyze_results(
            a["treatment"], a["control"]
        ),
        "internship_track": lambda a: InternshipPracticalTracker().track_progress(
            a["student_id"], a["entries"]
        ),
    }
    if method not in dispatch:
        return {"error": f"Unknown method: {method}"}
    try:
        return dispatch[method](args)
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    input_data = json.loads(sys.argv[1])
    result = run_method(input_data["method"], input_data["args"])
    print(json.dumps(result, default=str))
