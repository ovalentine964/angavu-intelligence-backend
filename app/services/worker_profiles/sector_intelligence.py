"""
Sector Intelligence — Msaidizi / Angavu Intelligence

Provides sector-specific intelligence for each of the worker sectors:
- Price benchmarks by sector
- Seasonal patterns and cycles
- Common challenges and how to address them
- Best practices from successful workers
- Market dynamics and trends

This module powers the intelligence layer that makes Msaidizi's
recommendations feel like they come from someone who truly understands
the worker's world.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .profiles import (
    WorkerSector,
    get_all_profiles,
    get_profiles_by_sector,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class PriceBenchmark:
    """A price benchmark for a common item or service in a sector."""
    item_name: str
    item_name_sw: str           # Swahili name
    unit: str                   # "per kg", "per litre", "per piece", "per trip"
    wholesale_price: float      # KSh — what workers pay
    retail_price: float         # KSh — what customers pay
    margin_pct: float           # Typical margin %
    price_range_low: float      # Low end of normal range
    price_range_high: float     # High end of normal range
    notes: str


@dataclass
class SeasonalPattern:
    """Seasonal pattern for a sector."""
    month: int                  # 1-12
    month_name: str
    demand_level: str           # "very_low", "low", "moderate", "high", "very_high"
    demand_pct_of_average: float  # 0.5 = 50% of average, 1.5 = 150% of average
    key_drivers: list[str]      # What drives demand this month
    worker_actions: list[str]   # What workers should do this month


@dataclass
class SectorChallenge:
    """A common challenge faced by workers in a sector."""
    challenge: str
    impact: str                 # "high", "medium", "low"
    prevalence: str             # "very_common", "common", "occasional"
    solutions: list[str]
    success_story: str          # Brief real-world example


@dataclass
class BestPractice:
    """A best practice from successful workers in a sector."""
    practice: str
    description: str
    impact: str                 # What difference it makes
    difficulty: str             # "easy", "moderate", "hard"
    applicable_types: list[str] # Which worker types in this sector
    example: str                # Real-world example


@dataclass
class MarketTrend:
    """A market trend affecting a sector."""
    trend: str
    direction: str              # "growing", "stable", "declining"
    timeframe: str              # "short_term", "medium_term", "long_term"
    impact_on_workers: str
    adaptation_suggestions: list[str]


@dataclass
class SectorIntelligence:
    """Complete intelligence package for a sector."""
    sector: WorkerSector
    sector_name: str
    description: str
    total_workers_estimate: str     # Estimated number of workers in Kenya
    avg_daily_income: float         # Average daily income across sector
    avg_monthly_income: float
    price_benchmarks: list[PriceBenchmark]
    seasonal_patterns: list[SeasonalPattern]
    challenges: list[SectorChallenge]
    best_practices: list[BestPractice]
    market_trends: list[MarketTrend]
    cross_sector_insights: list[str]  # Insights from comparing with other sectors


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Sector Intelligence Builder
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _build_food_sector() -> SectorIntelligence:
    return SectorIntelligence(
        sector=WorkerSector.FOOD,
        sector_name="Food & Beverage",
        description="Vendors selling fresh produce, cooked food, snacks, and beverages in Kenya's informal economy",
        total_workers_estimate="~3.5 million",
        avg_daily_income=600,
        avg_monthly_income=15_600,
        price_benchmarks=[
            PriceBenchmark("Tomatoes", "Nyanya", "per kg", 60, 100, 40, 50, 120, "Prices spike March-April (planting season gap)"),
            PriceBenchmark("Sukuma Wiki (Kale)", "Sukuma Wiki", "per bunch", 10, 20, 50, 10, 30, "Cheapest vegetable, high volume seller"),
            PriceBenchmark("Onions", "Vitunguu", "per kg", 70, 120, 42, 60, 150, "Stable demand year-round"),
            PriceBenchmark("Cooking Oil", "Mafuta ya Kupikia", "per litre", 200, 260, 23, 180, 280, "Price varies with global palm oil markets"),
            PriceBenchmark("Maize Flour (Unga)", "Unga wa Sima", "per 2kg", 120, 160, 25, 100, 180, "Government subsidies can lower price"),
            PriceBenchmark("Rice", "Mchele", "per kg", 130, 180, 28, 120, 200, "Pishori variety commands premium"),
            PriceBenchmark("Eggs", "Mayai", "per tray (30)", 350, 420, 17, 300, 500, "Prices rise during baking season (Dec)"),
            PriceBenchmark("Milk", "Maziwa", "per litre", 50, 70, 29, 45, 80, "Fresh milk vs processed price gap"),
            PriceBenchmark("Sugar", "Sukari", "per kg", 150, 200, 25, 130, 220, "Prices volatile due to import policies"),
            PriceBenchmark("Chapati", "Chapati", "per piece", 10, 20, 50, 10, 30, "High margin, labor intensive"),
        ],
        seasonal_patterns=[
            SeasonalPattern(1, "January", "high", 1.3, ["School opening", "Back to work", "Post-holiday restocking"], ["Stock up on school snack items", "Position near schools and offices"]),
            SeasonalPattern(2, "February", "moderate", 1.0, ["Steady demand", "Valentine's Day boost for some"], ["Maintain normal stock levels"]),
            SeasonalPattern(3, "March", "moderate", 0.9, ["Long rains begin", "Some outdoor customers reduce"], ["Shift to sheltered locations", "Focus on indoor-friendly items"]),
            SeasonalPattern(4, "April", "low", 0.7, ["Heavy rains", "Easter holiday", "Reduced foot traffic"], ["Reduce perishable stock", "Offer delivery services"]),
            SeasonalPattern(5, "May", "low", 0.7, ["Peak rainy season", "Flooding in some areas"], ["Focus on non-perishables", "Consider indoor markets"]),
            SeasonalPattern(6, "June", "moderate", 0.8, ["Rains easing", "Cold weather boosts warm food"], ["Warm food and drinks sell well", "Soup ingredients in demand"]),
            SeasonalPattern(7, "July", "moderate", 0.9, ["Cold season", "School term"], ["Warm beverages and comfort food", "Position near schools"]),
            SeasonalPattern(8, "August", "moderate", 0.9, ["School holiday begins", "Cold continues"], ["Holiday snacks for children", "Reduce school-focused stock"]),
            SeasonalPattern(9, "September", "high", 1.2, ["School opening", "Short rains begin"], ["Back to school demand spike", "Stock school-friendly items"]),
            SeasonalPattern(10, "October", "moderate", 1.0, ["Short rains", "Mixed demand"], ["Adapt to weather patterns"]),
            SeasonalPattern(11, "November", "high", 1.2, ["Festive preparations begin", "Weddings and events"], ["Stock up for December", "Event catering opportunities"]),
            SeasonalPattern(12, "December", "very_high", 1.5, ["Christmas", "New Year", "Festive cooking peak"], ["Maximum stock levels", "Premium pricing accepted", "Extended hours"]),
        ],
        challenges=[
            SectorChallenge(
                "Perishable stock spoilage",
                "high", "very_common",
                [
                    "Buy smaller quantities more frequently",
                    "Focus on fast-turnover items",
                    "Sell near-expiry at cost rather than discarding",
                    "Invest in simple cold storage (cool box with ice)",
                    "Track spoilage rates by item — cut slow movers",
                ],
                "A mama mboga in Gikomba reduced waste from 25% to 8% by buying daily instead of twice a week and tracking which items spoil first.",
            ),
            SectorChallenge(
                "Price fluctuations at wholesale markets",
                "high", "common",
                [
                    "Visit multiple wholesale vendors to compare prices",
                    "Buy in groups with other vendors for bulk discounts",
                    "Track wholesale prices weekly to spot trends",
                    "Build relationships with specific vendors for consistent pricing",
                ],
                "A group of 5 mama mbogas in Kawangware started buying tomatoes together, reducing their per-kg cost by 20%.",
            ),
            SectorChallenge(
                "County inspector (kanjo) harassment",
                "medium", "common",
                [
                    "Get the correct permits and display them visibly",
                    "Know your rights — ask for identification",
                    "Join a vendor association for collective bargaining",
                    "Keep a record of interactions and fines paid",
                ],
                "The Mama Mboga Association in Nairobi successfully negotiated reduced daily levies from KSh 100 to KSh 50 per vendor.",
            ),
        ],
        best_practices=[
            BestPractice(
                "Track daily waste by item",
                "Record every item thrown away with its cost. After 2 weeks, you'll see exactly which items to reduce.",
                "Reduces waste by 30-50%, directly improving profit",
                "easy", ["mama_mboga", "mama_lishe", "smokie_vendor", "eggs_ndizi_vendor"],
                "Mama Njeri in Nairobi tracked waste for a month and discovered she was over-buying sukuma wiki by 40%. Reducing her order saved KSh 2,000/week.",
            ),
            BestPractice(
                "Build a WhatsApp customer list",
                "Collect phone numbers from regulars. Send 1-2 messages per week about new stock, specials, or your location.",
                "Increases repeat customers by 20-30%",
                "easy", ["mama_mboga", "dukawallah", "mama_lishe", "mitumba_seller"],
                "A dukawallah in Eastlands sends a weekly 'new stock' message to 50 customers — it drives 15% of his weekly sales.",
            ),
            BestPractice(
                "Use M-Pesa till for all transactions",
                "Accept M-Pesa payments to automatically track sales, reduce cash handling, and build a financial record.",
                "Saves 30 minutes daily on manual records, builds credit history",
                "easy", ["mama_mboga", "dukawallah", "mama_lishe", "machinga", "smokie_vendor"],
                "Vendors using M-Pesa tills report 15% better financial awareness and qualify for mobile loans within 6 months.",
            ),
        ],
        market_trends=[
            MarketTrend(
                "Online grocery delivery growth",
                "growing", "medium_term",
                "Platforms like Glovo, Jumia Food, and local apps are capturing some walk-in customer base",
                ["Differentiate on freshness and personal service", "Consider registering on delivery platforms", "Offer your own WhatsApp ordering"],
            ),
            MarketTrend(
                "Supermarket expansion into fresh produce",
                "growing", "long_term",
                "Supermarkets like Naivas and Quickmart are expanding into neighborhoods, competing with mama mbogas",
                ["Focus on convenience (closer to customers)", "Offer home delivery", "Emphasize freshness (daily vs weekly stock)"],
            ),
            MarketTrend(
                "Digital payment adoption",
                "growing", "short_term",
                "More customers want to pay via M-Pesa — cash-only vendors lose customers",
                ["Get an M-Pesa till number", "Display payment options prominently", "Track M-Pesa vs cash split"],
            ),
        ],
        cross_sector_insights=[
            "Food vendors who also sell non-food items (soap, airtime) report 15% higher daily revenue",
            "Mama mbogas who track waste and adjust purchasing have 30% higher margins than those who don't",
            "Food vendors near matatu stages earn 40% more than those in residential-only areas",
            "Vendors who accept M-Pesa have 25% more transactions than cash-only peers",
        ],
    )


def _build_transport_sector() -> SectorIntelligence:
    return SectorIntelligence(
        sector=WorkerSector.TRANSPORT,
        sector_name="Transport & Logistics",
        description="Motorcycle taxis (boda boda), matatus, tuk-tuks, and ride-hailing drivers",
        total_workers_estimate="~2.5 million",
        avg_daily_income=800,
        avg_monthly_income=20_800,
        price_benchmarks=[
            PriceBenchmark("Petrol", "Petroli", "per litre", 210, 220, 3, 195, 230, "Price set by EPRA, changes monthly"),
            PriceBenchmark("Boda boda fare (short)", "Nauli ya boda", "per trip", 50, 100, 50, 30, 150, "Varies by distance and area"),
            PriceBenchmark("Boda boda fare (long)", "Nauli ya boda ndefu", "per trip", 100, 300, 67, 80, 500, "Cross-town trips"),
            PriceBenchmark("Matatu fare (within town)", "Nauli ya matatu", "per trip", 30, 60, 50, 20, 100, "Peak hours can double"),
            PriceBenchmark("Engine oil", "Mafuta ya injini", "per litre", 400, 600, 33, 350, 800, "Change every 2,000-3,000 km"),
            PriceBenchmark("Tyre (boda front)", "Tai la mbele", "per piece", 2000, 3000, 33, 1500, 4000, "Replace every 6-12 months"),
            PriceBenchmark("Helmet", "Kofia ya kichwa", "per piece", 1000, 2000, 50, 500, 5000, "Mandatory, fines for non-compliance"),
        ],
        seasonal_patterns=[
            SeasonalPattern(1, "January", "high", 1.3, ["School opening", "Back to work", "New commuters"], ["Maximize morning and evening rush hours"]),
            SeasonalPattern(2, "February", "moderate", 1.0, ["Steady commuter demand"], ["Normal operations"]),
            SeasonalPattern(3, "March", "moderate", 0.9, ["Long rains begin", "Some routes affected by flooding"], ["Know alternative routes", "Rain gear essential"]),
            SeasonalPattern(4, "April", "low", 0.7, ["Heavy rains", "Road flooding", "Fewer passengers"], ["Focus on delivery services", "Maintain bike for wet conditions"]),
            SeasonalPattern(5, "May", "low", 0.6, ["Peak rainy season", "Worst road conditions"], ["Income drops 40-50%", "Save aggressively in good months"]),
            SeasonalPattern(6, "June", "moderate", 0.8, ["Rains easing", "Passengers returning"], ["Gradual return to normal routes"]),
            SeasonalPattern(7, "July", "moderate", 0.9, ["Cold season", "School term"], ["Consistent demand"]),
            SeasonalPattern(8, "August", "moderate", 0.9, ["School holiday", "Some routes quieter"], ["Shift to holiday-related transport"]),
            SeasonalPattern(9, "September", "high", 1.2, ["School opening", "High demand for transport"], ["Peak earning opportunity"]),
            SeasonalPattern(10, "October", "moderate", 1.0, ["Short rains begin", "Mixed conditions"], ["Be prepared for wet roads"]),
            SeasonalPattern(11, "November", "moderate", 1.0, ["Short rains", "Pre-festive deliveries begin"], ["Delivery demand increases"]),
            SeasonalPattern(12, "December", "high", 1.3, ["Festive season", "Holiday travel", "Deliveries peak"], ["Extended hours", "Higher fares accepted"]),
        ],
        challenges=[
            SectorChallenge(
                "High accident risk",
                "high", "very_common",
                [
                    "Always wear a helmet — non-negotiable",
                    "Avoid night riding when visibility is poor",
                    "Don't carry passengers who are intoxicated",
                    "Maintain bike regularly — brakes, lights, tyres",
                    "Take breaks to avoid fatigue",
                ],
                "A boda boda SACCO in Nakuru reduced member accidents by 60% through mandatory safety training and helmet checks.",
            ),
            SectorChallenge(
                "Fuel price volatility",
                "high", "common",
                [
                    "Track fuel consumption (km per litre) religiously",
                    "Maintain tyre pressure — under-inflated tyres waste fuel",
                    "Plan routes to minimize distance",
                    "Consider fuel-efficient bikes when replacing",
                ],
                "Riders who track fuel consumption save an average of KSh 50/day by identifying and eliminating waste.",
            ),
            SectorChallenge(
                "Police harassment and fines",
                "medium", "very_common",
                [
                    "Keep all documents current (license, insurance, logbook)",
                    "Carry originals, not copies",
                    "Know the legal fine amounts — don't overpay",
                    "Join a SACCO for collective advocacy",
                ],
                "The Boda Boda Association of Kenya lobbied for standardized fines, reducing arbitrary payments by 40%.",
            ),
        ],
        best_practices=[
            BestPractice(
                "Track fuel consumption per trip",
                "Record litres purchased and km covered. Calculate cost per trip to know your true profit.",
                "Identifies fuel waste, saves KSh 50-100/day",
                "easy", ["boda_boda", "matatu_crew", "taxi_driver"],
                "A boda rider in Kisumu discovered his fuel cost per trip was KSh 15 higher than expected due to a clogged air filter. Cleaning it saved KSh 300/day.",
            ),
            BestPractice(
                "SACCO membership for group benefits",
                "Join a transport SACCO for group insurance, bulk fuel purchase, and collective bargaining power.",
                "Reduces insurance costs by 30%, provides emergency fund access",
                "easy", ["boda_boda", "matatu_crew", "taxi_driver"],
                "Boda boda SACCO members in Nakuru pay KSh 3,000/year for group insurance vs KSh 8,000 individually.",
            ),
        ],
        market_trends=[
            MarketTrend(
                "Ride-hailing app competition",
                "growing", "medium_term",
                "Uber, Bolt, and Little are expanding boda boda services, competing with independent riders",
                ["Register on multiple platforms", "Build a regular customer base independent of apps", "Offer delivery services"],
            ),
            MarketTrend(
                "Electric boda bodas",
                "growing", "long_term",
                "Companies like Ampersand and Roam are introducing electric motorcycles",
                ["Watch for financing options", "Electric bikes have 80% lower fuel costs", "Battery swap infrastructure is expanding"],
            ),
        ],
        cross_sector_insights=[
            "Boda riders who also do deliveries earn 30% more than passenger-only riders",
            "Riders with M-Pesa tills have better financial records and qualify for loans faster",
            "SACCO members have 50% fewer financial emergencies than non-members",
            "Riders who avoid night shifts have 70% fewer accidents",
        ],
    )


def _build_retail_sector() -> SectorIntelligence:
    return SectorIntelligence(
        sector=WorkerSector.RETAIL,
        sector_name="Retail & Trade",
        description="Small shops (dukas), street hawkers, mitumba sellers, and general merchandise vendors",
        total_workers_estimate="~4 million",
        avg_daily_income=600,
        avg_monthly_income=15_600,
        price_benchmarks=[
            PriceBenchmark("Sugar", "Sukari", "per kg", 150, 200, 25, 130, 220, "Government price controls sometimes apply"),
            PriceBenchmark("Cooking Oil", "Mafuta", "per litre", 200, 260, 23, 180, 280, "Palm oil global prices affect local cost"),
            PriceBenchmark("Maize Flour", "Unga", "per 2kg", 120, 160, 25, 100, 180, "Staple food, price-sensitive"),
            PriceBenchmark("Soap Bar", "Sabuni", "per bar", 35, 55, 36, 30, 70, "High turnover item"),
            PriceBenchmark("Matchbox", "Kiberiti", "per box", 5, 10, 50, 5, 15, "Small but high margin"),
            PriceBenchmark("Airtime", "Airtime", "per voucher", 95, 100, 5, 95, 100, "Very thin margin, volume play"),
            PriceBenchmark("Mitumba shirt", "Shati la mtumba", "per piece", 80, 200, 60, 50, 400, "Quality varies hugely"),
            PriceBenchmark("Mitumba dress", "Gauni la mtumba", "per piece", 120, 350, 65, 80, 600, "Designer items command premium"),
        ],
        seasonal_patterns=[
            SeasonalPattern(1, "January", "high", 1.3, ["School opening", "Back to work", "New year purchases"], ["Stock school supplies", "Position near schools"]),
            SeasonalPattern(2, "February", "moderate", 1.0, ["Steady demand", "Valentine's gifts"], ["Stock gift items"]),
            SeasonalPattern(3, "March", "moderate", 0.9, ["End of first quarter", "Budget pressure"], ["Offer small pack sizes"]),
            SeasonalPattern(4, "April", "moderate", 1.1, ["Easter holiday", "Eid celebrations"], ["Stock festive items"]),
            SeasonalPattern(5, "May", "moderate", 0.9, ["School term", "Rainy season"], ["Reduce outdoor stock"]),
            SeasonalPattern(6, "June", "low", 0.7, ["Mid-year budget crunch", "Cold weather"], ["Focus on essentials"]),
            SeasonalPattern(7, "July", "moderate", 0.9, ["School holiday begins", "Cold season"], ["Children's items sell"]),
            SeasonalPattern(8, "August", "moderate", 0.9, ["School holiday continues"], ["Holiday activities stock"]),
            SeasonalPattern(9, "September", "high", 1.2, ["School opening", "Third term"], ["School supplies peak"]),
            SeasonalPattern(10, "October", "moderate", 1.0, ["Steady demand"], ["Normal operations"]),
            SeasonalPattern(11, "November", "high", 1.2, ["Festive preparations", "Weddings"], ["Stock festive items"]),
            SeasonalPattern(12, "December", "very_high", 1.5, ["Christmas", "New Year", "Gift-giving"], ["Maximum stock", "Extended hours", "Premium pricing"]),
        ],
        challenges=[
            SectorChallenge(
                "Dead stock tying up capital",
                "high", "common",
                [
                    "Track stock age — anything unsold for 30 days is dead stock",
                    "Mark down dead stock by 20-30% to clear it",
                    "Bundle dead stock with fast-moving items",
                    "Return to supplier if possible",
                    "Never buy more of items that don't sell",
                ],
                "A dukawallah in Kayole identified KSh 15,000 in dead stock. After marking down and bundling, he recovered KSh 10,000 and freed up capital for fast-moving goods.",
            ),
            SectorChallenge(
                "Customer credit (owe list) growing",
                "high", "very_common",
                [
                    "Limit credit to maximum 10% of customers",
                    "Set clear repayment dates and follow up",
                ],
                "A duka owner limited credit to 5 trusted customers and recovered KSh 8,000 in outstanding debts within a month.",
            ),
        ],
        best_practices=[
            BestPractice(
                "Daily stock audit",
                "At end of each day, count remaining stock and compare to morning levels. Know exactly what sold.",
                "Prevents theft, identifies fast/slow movers, improves ordering",
                "easy", ["dukawallah", "mitumba_seller", "machinga"],
                "Dukawallahs who do daily stock counts report 20% less theft and 15% better ordering accuracy.",
            ),
            BestPractice(
                "Price anchoring technique",
                "Display a premium item next to your target item. The comparison makes the target item seem like a better deal.",
                "Increases average sale value by 10-20%",
                "easy", ["dukawallah", "mitumba_seller", "machinga"],
                "Mitumba sellers who display a 'premium' item at KSh 500 next to regular items at KSh 200 sell more of the regular items.",
            ),
        ],
        market_trends=[
            MarketTrend(
                "E-commerce and social media selling",
                "growing", "medium_term",
                "WhatsApp, Instagram, and TikTok are becoming sales channels for informal retailers",
                ["Create a WhatsApp Business catalog", "Post product photos on social media", "Offer delivery for online orders"],
            ),
        ],
        cross_sector_insights=[
            "Retailers who track daily sales in a notebook have 25% better margins than those who don't",
            "Dukawallahs who accept M-Pesa have 20% more transactions",
            "Mitumba sellers who wash and iron items before display charge 30% more",
            "Hawkers who rotate locations earn 25% more than those stuck in one spot",
        ],
    )


def _build_services_sector() -> SectorIntelligence:
    return SectorIntelligence(
        sector=WorkerSector.SERVICES,
        sector_name="Services",
        description="Repair technicians, salons, barbers, laundry workers, watchmen, shoe shiners, and other service providers",
        total_workers_estimate="~3 million",
        avg_daily_income=550,
        avg_monthly_income=14_300,
        price_benchmarks=[
            PriceBenchmark("Phone screen repair", "Kuremba screen", "per job", 500, 2000, 75, 300, 5000, "Price varies hugely by phone model"),
            PriceBenchmark("Haircut (men)", "Kunyoa", "per cut", 80, 150, 47, 50, 300, "Urban vs rural price gap"),
            PriceBenchmark("Braids (full)", "Kusuka", "per head", 400, 1000, 60, 300, 3000, "Style complexity affects price"),
            PriceBenchmark("Shoe polish", "Kupulisha viatu", "per pair", 20, 50, 60, 10, 100, "Location matters — CBD vs estate"),
            PriceBenchmark("Laundry (per load)", "Kufulia", "per load", 80, 200, 60, 50, 500, "Ironing adds KSh 30-50/item"),
            PriceBenchmark("Watchman salary", "Mshahara wa mlinzi", "per month", 6000, 12000, 50, 5000, 15000, "Night shifts pay more"),
        ],
        seasonal_patterns=[
            SeasonalPattern(1, "January", "high", 1.2, ["Back to work", "School opening", "New year resolutions"], ["Barbers and salons busy with fresh starts"]),
            SeasonalPattern(2, "February", "moderate", 1.0, ["Valentine's Day prep"], ["Salons busy for dates"]),
            SeasonalPattern(3, "March", "moderate", 0.9, ["Steady demand"], ["Normal operations"]),
            SeasonalPattern(4, "April", "high", 1.2, ["Easter holiday", "Wedding season"], ["Salons peak — braiding and styling"]),
            SeasonalPattern(5, "May", "moderate", 0.9, ["Rainy season", "Some slowdown"], ["Phone repairs increase (water damage)"]),
            SeasonalPattern(6, "June", "low", 0.7, ["Cold season", "Reduced events"], ["Fundis see slower order flow"]),
            SeasonalPattern(7, "July", "moderate", 0.9, ["School holiday"], ["Children's haircuts increase"]),
            SeasonalPattern(8, "August", "moderate", 0.9, ["Graduation season prep"], ["Salons busy with graduation prep"]),
            SeasonalPattern(9, "September", "moderate", 1.0, ["Back to school"], ["School-related services"]),
            SeasonalPattern(10, "October", "moderate", 1.0, ["Steady demand"], ["Normal operations"]),
            SeasonalPattern(11, "November", "high", 1.2, ["Wedding season", "Festive prep"], ["Peak salon/barber demand"]),
            SeasonalPattern(12, "December", "very_high", 1.5, ["Christmas", "Weddings", "Year-end events"], ["Salons and barbers at peak — extended hours"]),
        ],
        challenges=[
            SectorChallenge(
                "Inconsistent income — feast or famine",
                "high", "very_common",
                [
                    "Build a regular customer base — appointments and follow-ups",
                    "Offer packages (e.g., monthly barber plan)",
                    "Save aggressively during good months",
                    "Diversify income sources",
                ],
                "A barber in Nairobi started offering a 'weekly shave' package at KSh 500/month. 20 regulars gave him KSh 10,000 guaranteed monthly income.",
            ),
            SectorChallenge(
                "Skills obsolescence",
                "medium", "common",
                [
                    "Learn new techniques via YouTube tutorials",
                    "Attend workshops and training when available",
                    "Practice new styles/models before offering to customers",
                    "Network with peers to share knowledge",
                ],
                "A phone fundi who learned iPhone repair tripled his income — most fundis only knew Android.",
            ),
        ],
        best_practices=[
            BestPractice(
                "Build a portfolio of your work",
                "Take before/after photos of every job. Show them to potential customers as proof of quality.",
                "Increases customer trust and conversion rate by 40%",
                "easy", ["fundi", "salon_barber", "tailor", "jua_kali", "photographer"],
                "A fundi in Mombasa shows phone repair photos on his WhatsApp status — it brings 3-4 new customers per week.",
            ),
            BestPractice(
                "Offer a satisfaction guarantee",
                "A simple 'if you're not happy, I'll fix it for free' guarantee builds massive trust.",
                "Reduces customer hesitation, increases referrals by 50%",
                "easy", ["fundi", "salon_barber", "tailor", "jua_kali"],
                "A tailor who offers free alterations on all custom orders has a 90% repeat customer rate.",
            ),
        ],
        market_trends=[
            MarketTrend(
                "Growing demand for phone and electronics repair",
                "growing", "medium_term",
                "Smartphone penetration is increasing, creating more repair demand",
                ["Specialize in specific brands/models", "Learn micro-soldering for board-level repairs", "Stock common parts"],
            ),
        ],
        cross_sector_insights=[
            "Service providers who use M-Pesa till for payments have 30% better financial records",
            "Fundis who photograph completed work get 40% more referrals",
            "Salon owners who offer loyalty cards retain 50% more customers",
            "Service providers who join SACCOs qualify for equipment loans within 6 months",
        ],
    )


def _build_agriculture_sector() -> SectorIntelligence:
    return SectorIntelligence(
        sector=WorkerSector.AGRICULTURE,
        sector_name="Agriculture",
        description="Small-scale farmers growing crops, keeping livestock, and selling farm produce",
        total_workers_estimate="~5 million",
        avg_daily_income=400,
        avg_monthly_income=10_400,
        price_benchmarks=[
            PriceBenchmark("Maize (per 90kg bag)", "Mahindi", "per bag", 2500, 3500, 29, 2000, 5000, "Harvest vs planting season price gap"),
            PriceBenchmark("Beans (per 90kg bag)", "Maharagwe", "per bag", 5000, 7000, 29, 4000, 9000, "Many varieties, price varies"),
            PriceBenchmark("Potatoes (per 50kg bag)", "Viazi", "per bag", 1500, 2500, 40, 1000, 4000, "Nyandarua is major source"),
            PriceBenchmark("Tomatoes (per crate)", "Nyanya", "per crate", 1000, 2000, 50, 500, 4000, "Highly seasonal and volatile"),
            PriceBenchmark("Fertilizer (per 50kg)", "Mbolea", "per bag", 3000, 4000, 25, 2500, 5000, "Subsidized sometimes available"),
            PriceBenchmark("Seeds (maize, 10kg)", "Mbegu", "per 10kg", 800, 1500, 47, 600, 2000, "Hybrid vs local variety"),
        ],
        seasonal_patterns=[
            SeasonalPattern(1, "January", "high", 1.2, ["Short rains harvest", "Sell stored grain"], ["Sell maize/beans at good prices"]),
            SeasonalPattern(2, "February", "moderate", 1.0, ["Land preparation begins"], ["Plan planting, buy inputs"]),
            SeasonalPattern(3, "March", "low", 0.6, ["Long rains planting", "High expenses, no income"], ["Minimize spending, focus on planting"]),
            SeasonalPattern(4, "April", "low", 0.5, ["Peak planting season", "Maximum input costs"], ["This is the hardest month financially"]),
            SeasonalPattern(5, "May", "low", 0.6, ["Growing season", "Weeding and spraying"], ["No income, continued expenses"]),
            SeasonalPattern(6, "June", "low", 0.7, ["Growing continues", "Some early harvests"], ["Wait for harvest"]),
            SeasonalPattern(7, "July", "high", 1.3, ["Long rains harvest begins"], ["Sell at farm gate or store for better prices"]),
            SeasonalPattern(8, "August", "high", 1.4, ["Peak harvest", "Market flooded with produce"], ["Consider storage — prices are lowest now"]),
            SeasonalPattern(9, "September", "moderate", 0.9, ["Short rains planting begins"], ["Prepare for second season"]),
            SeasonalPattern(10, "October", "low", 0.7, ["Planting expenses", "Growing season"], ["Expenses again, no income"]),
            SeasonalPattern(11, "November", "moderate", 0.9, ["Growing season", "Some green maize sales"], ["Early green maize can fetch good prices"]),
            SeasonalPattern(12, "December", "high", 1.2, ["Short rains harvest begins", "Festive demand"], ["Sell for festive market"]),
        ],
        challenges=[
            SectorChallenge(
                "Post-harvest losses",
                "high", "very_common",
                [
                    "Invest in proper storage — granaries, hermetic bags",
                    "Sell gradually, not all at harvest when prices are lowest",
                    "Join a warehouse receipt system if available",
                    "Dry produce properly before storage",
                    "Protect against pests (weevils, rats)",
                ],
                "Farmers using hermetic storage bags (PICS bags) reduce post-harvest losses from 30% to under 5%. A KSh 200 bag protects a KSh 3,000 harvest.",
            ),
            SectorChallenge(
                "Middleman exploitation",
                "high", "very_common",
                [
                    "Know market prices before selling — check via phone or radio",
                    "Join a farmers' cooperative for collective bargaining",
                    "Sell directly to markets when possible",
                    "Consider value addition (drying, milling, packaging)",
                ],
                "A farmers' cooperative in Meru doubled their tomato income by selling directly to Nairobi supermarkets instead of to middlemen.",
            ),
        ],
        best_practices=[
            BestPractice(
                "Crop diversification",
                "Plant at least 3 different crops to spread risk. If one fails, others may succeed.",
                "Reduces total crop failure risk by 60%",
                "moderate", ["mkulima"],
                "Farmers who plant maize, beans, and vegetables together report 40% more stable income than maize-only farmers.",
            ),
            BestPractice(
                "Record keeping per season",
                "Record all costs (seeds, fertilizer, labor), yields, and selling prices for each season. Compare across seasons.",
                "Identifies most profitable crops and practices",
                "easy", ["mkulima"],
                "A farmer in Machakos discovered beans were 3x more profitable per acre than maize by tracking costs and yields over 3 seasons.",
            ),
        ],
        market_trends=[
            MarketTrend(
                "Climate change increasing weather variability",
                "growing", "long_term",
                "Droughts and floods are becoming more frequent and severe",
                ["Invest in irrigation (drip systems)", "Plant drought-resistant varieties", "Consider crop insurance"],
            ),
            MarketTrend(
                "Digital agricultural platforms",
                "growing", "medium_term",
                "Apps connecting farmers directly to buyers are growing",
                ["Register on platforms like Twiga Foods, iProcure", "Use weather apps for planning", "Access market price information via USSD"],
            ),
        ],
        cross_sector_insights=[
            "Farmers who also keep poultry have 25% more stable income (eggs provide daily income between harvests)",
            "Farmers in SACCOs get 30% better prices for inputs through group buying",
            "Those who add value (drying, milling) earn 50-100% more than raw produce sellers",
            "Record-keeping farmers make 30% better crop selection decisions",
        ],
    )


def _build_manufacturing_sector() -> SectorIntelligence:
    return SectorIntelligence(
        sector=WorkerSector.MANUFACTURING,
        sector_name="Manufacturing & Craft",
        description="Jua kali artisans, tailors, furniture makers, metalworkers, and informal manufacturers",
        total_workers_estimate="~2 million",
        avg_daily_income=700,
        avg_monthly_income=18_200,
        price_benchmarks=[
            PriceBenchmark("Steel per kg", "Chuma", "per kg", 100, 150, 33, 80, 180, "Price fluctuates with scrap metal markets"),
            PriceBenchmark("Timber per foot", "Mbao", "per foot", 50, 80, 38, 30, 120, "Hardwood vs softwood price gap"),
            PriceBenchmark("Welding rod", "Fimbo ya kuchoma", "per packet", 200, 350, 43, 150, 500, "Different sizes for different jobs"),
            PriceBenchmark("Paint per litre", "Rangi", "per litre", 300, 500, 40, 200, 800, "Quality varies hugely"),
            PriceBenchmark("Fabric per metre", "Kitenge", "per metre", 200, 400, 50, 100, 1000, "Ankara vs kitenge vs cotton"),
            PriceBenchmark("Sewing thread", "Uzi", "per spool", 30, 60, 50, 20, 100, "Quality thread saves time"),
        ],
        seasonal_patterns=[
            SeasonalPattern(1, "January", "high", 1.3, ["New year orders", "Businesses refreshing furniture"], ["Furniture and metalwork orders peak"]),
            SeasonalPattern(2, "February", "moderate", 1.0, ["Steady orders"], ["Normal operations"]),
            SeasonalPattern(3, "March", "moderate", 1.0, ["Construction season starts"], ["Gates, windows, grills in demand"]),
            SeasonalPattern(4, "April", "high", 1.2, ["Easter orders", "Wedding season prep"], ["Tailoring peaks — wedding outfits"]),
            SeasonalPattern(5, "May", "moderate", 0.9, ["Rain slows outdoor work"], ["Focus on indoor orders"]),
            SeasonalPattern(6, "June", "low", 0.7, ["Slow season", "Rain continues"], ["Use slow time for skill development"]),
            SeasonalPattern(7, "July", "moderate", 0.9, ["Orders picking up"], ["Prepare for August peak"]),
            SeasonalPattern(8, "August", "high", 1.2, ["Graduation season", "School furniture"], ["Tailors busy with graduation outfits"]),
            SeasonalPattern(9, "September", "moderate", 1.0, ["Construction resumes"], ["Metalwork and furniture orders"]),
            SeasonalPattern(10, "October", "moderate", 1.0, ["Wedding season begins"], ["Tailoring orders increase"]),
            SeasonalPattern(11, "November", "high", 1.3, ["Wedding season peak", "Festive orders"], ["Peak tailoring and furniture demand"]),
            SeasonalPattern(12, "December", "high", 1.2, ["Festive orders", "Year-end rush"], ["Complete all orders before Christmas"]),
        ],
        challenges=[
            SectorChallenge(
                "Raw material cost fluctuations",
                "high", "common",
                [
                    "Buy materials in bulk when prices are low",
                    "Build relationships with multiple suppliers",
                    "Track material costs per job to maintain margins",
                    "Consider alternative materials when prices spike",
                ],
                "A jua kali workshop in Kamukunji started buying steel in bulk during price dips, saving 15% on material costs.",
            ),
            SectorChallenge(
                "Customer payment delays",
                "high", "very_common",
                [
                    "Always take 50% deposit before starting",
                    "Set clear payment terms before the job begins",
                    "Don't release finished goods until fully paid",
                    "Keep formal records of all transactions",
                ],
                "A furniture maker reduced payment delays by 80% after implementing a strict 50% deposit policy.",
            ),
        ],
        best_practices=[
            BestPractice(
                "Photograph every completed job",
                "Take clear photos of finished work from multiple angles. Build a portfolio on WhatsApp and social media.",
                "Converts 30% more inquiries into paying customers",
                "easy", ["jua_kali", "tailor", "fundi"],
                "A jua kali artisan in Nairobi's Industrial Area gets 40% of new customers from WhatsApp portfolio photos.",
            ),
        ],
        market_trends=[
            MarketTrend(
                "Growing demand for locally made furniture",
                "growing", "medium_term",
                "Kenya's growing middle class wants affordable, locally-made furniture",
                ["Invest in quality finishing", "Offer modern designs", "Build an online presence"],
            ),
        ],
        cross_sector_insights=[
            "Manufacturers who take deposits have 70% fewer payment disputes",
            "Tailors with WhatsApp catalogs get 3x more orders than those without",
            "Jua kali artisans who learn digital skills (CAD, social media) earn 50% more",
            "Those who track material costs per job maintain 20% better margins",
        ],
    )


def _build_digital_sector() -> SectorIntelligence:
    return SectorIntelligence(
        sector=WorkerSector.DIGITAL,
        sector_name="Digital & Mobile Services",
        description="M-Pesa agents, cyber cafes, phone accessories vendors, and digital service providers",
        total_workers_estimate="~1.5 million",
        avg_daily_income=650,
        avg_monthly_income=16_900,
        price_benchmarks=[
            PriceBenchmark("M-Pesa withdrawal commission", "Kamisheni", "per transaction", 0, 0, 0, 0, 0, "Based on Safaricom's tiered structure"),
            PriceBenchmark("B&W print per page", "Kuprinti", "per page", 3, 10, 70, 3, 15, "Volume discounts for large jobs"),
            PriceBenchmark("Color print per page", "Rangi", "per page", 10, 30, 67, 15, 50, "Higher margin than B&W"),
            PriceBenchmark("Internet per hour", "Intaneti", "per hour", 20, 50, 60, 30, 100, "Competition from mobile data"),
            PriceBenchmark("Phone case", "Kesi ya simu", "per piece", 80, 200, 60, 50, 500, "Trendy designs sell faster"),
            PriceBenchmark("Phone charger", "Chaja", "per piece", 150, 350, 57, 100, 800, "Genuine vs generic price gap"),
        ],
        seasonal_patterns=[
            SeasonalPattern(1, "January", "very_high", 1.5, ["School fees payments", "M-Pesa volumes peak"], ["M-Pesa agents at maximum capacity"]),
            SeasonalPattern(2, "February", "moderate", 1.0, ["Steady transactions"], ["Normal operations"]),
            SeasonalPattern(3, "March", "moderate", 0.9, ["End of quarter"], ["Steady demand"]),
            SeasonalPattern(4, "April", "moderate", 1.1, ["Easter", "Some remittances"], ["Moderate increase"]),
            SeasonalPattern(5, "May", "high", 1.2, ["School fees season", "High M-Pesa volumes"], ["Peak agent earnings"]),
            SeasonalPattern(6, "June", "moderate", 0.9, ["Mid-year", "Budget pressure"], ["Steady"]),
            SeasonalPattern(7, "July", "low", 0.7, ["School holiday", "Lower volumes"], ["Reduced transactions"]),
            SeasonalPattern(8, "August", "moderate", 0.9, ["Back to school prep"], ["Registration services in demand"]),
            SeasonalPattern(9, "September", "high", 1.3, ["School fees", "High M-Pesa volumes"], ["Peak agent earnings again"]),
            SeasonalPattern(10, "October", "moderate", 1.0, ["Steady demand"], ["Normal operations"]),
            SeasonalPattern(11, "November", "moderate", 1.1, ["Pre-festive remittances begin"], ["Increasing volumes"]),
            SeasonalPattern(12, "December", "very_high", 1.5, ["Christmas remittances", "Highest M-Pesa volumes"], ["Maximum earnings, extended hours"]),
        ],
        challenges=[
            SectorChallenge(
                "Declining M-Pesa commission rates",
                "high", "common",
                [
                    "Add complementary services (airtime, bill payments, registration)",
                    "Increase transaction volume through better location and service",
                    "Negotiate with Safaricom for higher commission tier",
                    "Diversify income beyond M-Pesa",
                ],
                "An M-Pesa agent in Thika added KRA PIN registration, NHIF enrollment, and photocopy services, increasing daily revenue by 60%.",
            ),
        ],
        best_practices=[
            BestPractice(
                "Add complementary digital services",
                "M-Pesa agents who also offer photocopying, printing, and government registration services earn 50% more.",
                "Increases revenue per customer and foot traffic",
                "moderate", ["mpesa_agent", "cyber_print"],
                "An agent in Nairobi's CBD earns KSh 3,000/day from M-Pesa alone but KSh 5,000/day when including printing and registration services.",
            ),
        ],
        market_trends=[
            MarketTrend(
                "Mobile money evolution",
                "growing", "medium_term",
                "M-Pesa is evolving with new products (Fuliza, Mali) — agents need to understand and offer these",
                ["Learn all M-Pesa products", "Register customers for new services", "Stay updated on Safaricom changes"],
            ),
        ],
        cross_sector_insights=[
            "M-Pesa agents with complementary services earn 50% more than single-service agents",
            "Cyber cafes near schools and colleges have 3x higher utilization",
            "Agents who track daily transactions by type optimize their float management better",
            "Digital service providers who learn to troubleshoot devices earn premium rates",
        ],
    )


def _build_construction_sector() -> SectorIntelligence:
    return SectorIntelligence(
        sector=WorkerSector.CONSTRUCTION,
        sector_name="Construction",
        description="Construction laborers, masons, plumbers, electricians, and painters",
        total_workers_estimate="~1.5 million",
        avg_daily_income=700,
        avg_monthly_income=18_200,
        price_benchmarks=[
            PriceBenchmark("Cement per bag", "Saruji", "per 50kg bag", 650, 750, 13, 600, 850, "Prices set by manufacturers"),
            PriceBenchmark("Sand per tonne", "Mchanga", "per tonne", 1500, 2500, 40, 1000, 4000, "River vs building sand"),
            PriceBenchmark("Bricks per piece", "Matofali", "per piece", 10, 15, 33, 7, 20, "Machine vs handmade"),
            PriceBenchmark("Mason daily wage", "Mshahara wa fundi", "per day", 600, 1000, 40, 500, 1500, "Skilled vs unskilled gap"),
            PriceBenchmark("Laborer daily wage", "Mshahara wa mkazi", "per day", 400, 600, 33, 300, 800, "Entry level"),
        ],
        seasonal_patterns=[
            SeasonalPattern(1, "January", "high", 1.3, ["Construction season begins", "New projects start"], ["High demand for all trades"]),
            SeasonalPattern(2, "February", "high", 1.2, ["Peak construction"], ["Full employment typically"]),
            SeasonalPattern(3, "March", "high", 1.2, ["Construction continues"], ["Active building season"]),
            SeasonalPattern(4, "April", "moderate", 0.8, ["Long rains begin", "Outdoor work slows"], ["Some indoor work continues"]),
            SeasonalPattern(5, "May", "low", 0.5, ["Heavy rains", "Many sites shut down"], ["Toughest month — save from Jan-Mar"]),
            SeasonalPattern(6, "June", "low", 0.6, ["Rains continue", "Limited work"], ["Consider indoor renovations"]),
            SeasonalPattern(7, "July", "moderate", 0.9, ["Rains easing", "Some sites reopen"], ["Gradual return to work"]),
            SeasonalPattern(8, "August", "high", 1.2, ["Dry season", "Construction boom"], ["Peak demand for tradespeople"]),
            SeasonalPattern(9, "September", "high", 1.2, ["Construction continues"], ["Full employment"]),
            SeasonalPattern(10, "October", "high", 1.1, ["Pre-festive rush", "Completing projects"], ["Rush to finish before December"]),
            SeasonalPattern(11, "November", "moderate", 1.0, ["Some projects finishing"], ["Mixed demand"]),
            SeasonalPattern(12, "December", "low", 0.6, ["Holiday season", "Projects pause"], ["Limited work, festive break"]),
        ],
        challenges=[
            SectorChallenge(
                "Seasonal unemployment during rains",
                "high", "very_common",
                [
                    "Save 40% of earnings during dry season for rainy months",
                    "Learn indoor skills (plumbing, electrical) for rainy season work",
                    "Take on renovation projects that can be done under cover",
                    "Consider complementary income (boda boda, small business)",
                ],
                "A mason in Nakuru who learned plumbing now works year-round — plumbing jobs continue during rains.",
            ),
        ],
        best_practices=[
            BestPractice(
                "Learn multiple trades",
                "A mason who also does plumbing or electrical work gets 2x more job offers.",
                "Doubles employment opportunities and earning potential",
                "hard", ["construction_fundi"],
                "A fundi in Kiambu who does masonry, plumbing, and basic electrical earns KSh 1,500/day vs KSh 800 for masonry alone.",
            ),
        ],
        market_trends=[
            MarketTrend(
                "Affordable housing program",
                "growing", "medium_term",
                "Government's affordable housing agenda is creating construction jobs",
                ["Register with NCA for formal construction work", "Learn modern building techniques", "Get safety certifications"],
            ),
        ],
        cross_sector_insights=[
            "Construction workers who save through SACCOs have 60% fewer financial emergencies",
            "Those who learn multiple trades have 50% less seasonal unemployment",
            "Workers with NHIF are 3x more likely to seek medical care early (cheaper than late treatment)",
            "Fundis who keep job records get 40% more repeat and referral work",
        ],
    )


def _build_energy_sector() -> SectorIntelligence:
    return SectorIntelligence(
        sector=WorkerSector.ENERGY,
        sector_name="Energy & Waste",
        description="Charcoal sellers, water vendors, recyclers, and energy product distributors",
        total_workers_estimate="~500,000",
        avg_daily_income=450,
        avg_monthly_income=11_700,
        price_benchmarks=[
            PriceBenchmark("Charcoal per 50kg bag", "Mkaa", "per bag", 800, 1400, 43, 600, 1800, "Seasonal price variation"),
            PriceBenchmark("Firewood per bundle", "Kuni", "per bundle", 100, 200, 50, 50, 300, "Urban vs rural price gap"),
            PriceBenchmark("Water per 20L jerrycan", "Maji", "per jerrycan", 20, 50, 60, 10, 100, "Treated vs untreated"),
            PriceBenchmark("Recyclable plastic per kg", "Plastiki", "per kg", 10, 25, 60, 5, 40, "Sorted vs mixed"),
            PriceBenchmark("Scrap metal per kg", "Chuma", "per kg", 20, 50, 60, 10, 100, "Type matters — copper vs iron"),
        ],
        seasonal_patterns=[
            SeasonalPattern(1, "January", "moderate", 1.0, ["Post-holiday", "Back to normal cooking"], ["Moderate charcoal demand"]),
            SeasonalPattern(2, "February", "moderate", 0.9, ["Steady demand"], ["Normal operations"]),
            SeasonalPattern(3, "March", "moderate", 1.0, ["Rains beginning", "Less outdoor cooking"], ["Demand starts increasing"]),
            SeasonalPattern(4, "April", "high", 1.3, ["Heavy rains", "More indoor cooking"], ["Charcoal demand peaks"]),
            SeasonalPattern(5, "May", "high", 1.4, ["Peak rainy season", "Cold weather"], ["Highest charcoal demand"]),
            SeasonalPattern(6, "June", "high", 1.3, ["Cold season continues"], ["Sustained high demand"]),
            SeasonalPattern(7, "July", "high", 1.2, ["Cold season", "High demand"], ["Good earning period"]),
            SeasonalPattern(8, "August", "moderate", 1.1, ["Rains easing"], ["Demand moderating"]),
            SeasonalPattern(9, "September", "moderate", 1.0, ["Short rains begin"], ["Mixed demand"]),
            SeasonalPattern(10, "October", "moderate", 1.0, ["Short rains"], ["Normal operations"]),
            SeasonalPattern(11, "November", "moderate", 1.0, ["Pre-festive"], ["Some demand increase"]),
            SeasonalPattern(12, "December", "high", 1.2, ["Festive cooking"], ["Demand spike for festive season"]),
        ],
        challenges=[
            SectorChallenge(
                "Environmental regulations tightening",
                "high", "common",
                [
                    "Diversify into legal alternative fuels (briquettes, LPG)",
                    "Get proper permits and licenses",
                    "Consider recycling as a complementary business",
                    "Stay informed about policy changes",
                ],
                "A charcoal seller in Nairobi started selling briquettes alongside charcoal — briquettes are legal, cheaper, and growing in demand.",
            ),
        ],
        best_practices=[
            BestPractice(
                "Sell in multiple quantities",
                "Offer charcoal in 1kg, 5kg, 10kg, and 50kg sizes. Different customers need different amounts.",
                "Increases customer base by 40% — from apartment dwellers to restaurants",
                "easy", ["charcoal_seller"],
                "A seller who added 1kg packs (KSh 40) attracted apartment residents who couldn't buy full bags.",
            ),
        ],
        market_trends=[
            MarketTrend(
                "Shift to cleaner cooking fuels",
                "growing", "long_term",
                "Government and NGOs promoting LPG, briquettes, and electric cooking",
                ["Diversify into cleaner fuel options", "Learn about briquette production", "Consider LPG distribution"],
            ),
        ],
        cross_sector_insights=[
            "Energy sellers who offer delivery earn 30% more than walk-in only",
            "Recyclers who sort materials before selling get 50% higher prices",
            "Water vendors with regular routes have 60% more predictable income",
            "Those who combine energy products (charcoal + firewood + paraffin) serve more customers",
        ],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Sector Intelligence Registry
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _build_sector_registry() -> dict[WorkerSector, SectorIntelligence]:
    """Build the complete sector intelligence registry."""
    builders = [
        _build_food_sector,
        _build_transport_sector,
        _build_retail_sector,
        _build_services_sector,
        _build_agriculture_sector,
        _build_manufacturing_sector,
        _build_digital_sector,
        _build_construction_sector,
        _build_energy_sector,
    ]
    registry: dict[WorkerSector, SectorIntelligence] = {}
    for builder in builders:
        intel = builder()
        registry[intel.sector] = intel
    return registry


_SECTOR_REGISTRY: dict[WorkerSector, SectorIntelligence] | None = None


def get_all_sector_intelligence() -> dict[WorkerSector, SectorIntelligence]:
    """Get all sector intelligence. Builds once, returns cached."""
    global _SECTOR_REGISTRY
    if _SECTOR_REGISTRY is None:
        _SECTOR_REGISTRY = _build_sector_registry()
    return _SECTOR_REGISTRY


def get_sector_intelligence(sector: WorkerSector) -> SectorIntelligence | None:
    """Get intelligence for a specific sector."""
    return get_all_sector_intelligence().get(sector)


def get_sector_for_type(type_id: str) -> SectorIntelligence | None:
    """Get sector intelligence for a worker type."""
    from .profiles import get_profile
    profile = get_profile(type_id)
    if profile:
        return get_sector_intelligence(profile.sector)
    return None


def get_price_benchmarks_for_type(type_id: str) -> list[PriceBenchmark]:
    """Get relevant price benchmarks for a worker type."""
    intel = get_sector_for_type(type_id)
    if intel:
        return intel.price_benchmarks
    return []


def get_seasonal_forecast(
    sector: WorkerSector, month: int
) -> SeasonalPattern | None:
    """Get seasonal forecast for a sector in a given month."""
    intel = get_sector_intelligence(sector)
    if intel:
        for pattern in intel.seasonal_patterns:
            if pattern.month == month:
                return pattern
    return None


def get_best_practices_for_type(type_id: str) -> list[BestPractice]:
    """Get best practices applicable to a specific worker type."""
    intel = get_sector_for_type(type_id)
    if not intel:
        return []
    return [
        bp for bp in intel.best_practices
        if type_id in bp.applicable_types
    ]
