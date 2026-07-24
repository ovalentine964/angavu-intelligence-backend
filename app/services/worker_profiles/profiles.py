"""
Worker Type Profiles — Msaidizi / Angavu Intelligence

Defines 25 worker types common in Kenya's informal economy (jua kali sector).
Each profile captures the real-world characteristics, income patterns,
financial needs, and operational realities of that worker type.

These profiles drive:
- Personalized recommendations and insights
- Sector-specific financial product matching
- Health score calibration per worker type
- Dashboard metrics and KPIs
- Conversational AI context

Worker types are grounded in Kenya's informal economy data:
- ~83% of Kenya's workforce is in the informal sector
- ~14.5 million workers across diverse occupations
- Average daily income ranges from KSh 200 to KSh 3,000+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Enums & Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class WorkerSector(str, Enum):
    """High-level sectors grouping worker types."""
    FOOD = "food"
    TRANSPORT = "transport"
    RETAIL = "retail"
    SERVICES = "services"
    AGRICULTURE = "agriculture"
    MANUFACTURING = "manufacturing"
    DIGITAL = "digital"
    CONSTRUCTION = "construction"
    ENERGY = "energy"


class RiskLevel(str, Enum):
    """Business risk level for worker types."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SeasonalityPattern(str, Enum):
    """Revenue seasonality patterns."""
    STEADY = "steady"                   # Relatively stable year-round
    SCHOOL_DRIVEN = "school_driven"     # Peaks during school terms
    HARVEST_DRIVEN = "harvest_driven"   # Peaks around harvest seasons
    FESTIVAL_DRIVEN = "festival_driven" # Peaks during holidays/festivals
    WEATHER_DRIVEN = "weather_driven"   # Affected by rain/dry seasons
    DAILY_FLUCTUATING = "daily_fluctuating"  # Day-to-day variation


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data Classes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class IncomeRange:
    """Typical income range in KSh per day."""
    low: float          # Bad day / slow season
    average: float      # Typical day
    high: float         # Good day / peak season
    peak: float         # Exceptional day (market day, holiday, etc.)

    @property
    def monthly_average(self) -> float:
        """Estimated monthly income assuming 26 working days."""
        return self.average * 26

    @property
    def annual_average(self) -> float:
        """Estimated annual income."""
        return self.average * 300  # ~300 working days


@dataclass
class OperatingCosts:
    """Typical daily operating costs in KSh."""
    rent: float = 0.0               # Daily rent / stall fee
    stock: float = 0.0              # Daily stock/supply cost
    transport: float = 0.0          # Transport costs
    utilities: float = 0.0          # Water, electricity, phone
    labor: float = 0.0              # Hiring helpers
    licenses: float = 0.0           # Daily equivalent of permits/licenses
    other: float = 0.0             # Miscellaneous

    @property
    def total(self) -> float:
        return (self.rent + self.stock + self.transport +
                self.utilities + self.labor + self.licenses + self.other)


@dataclass
class KeyMetric:
    """A key performance metric for this worker type."""
    name: str
    description: str
    unit: str                       # "KSh", "%", "count", "days", etc.
    target_good: float | None       # Good benchmark value
    target_average: float | None    # Average benchmark value
    target_poor: float | None       # Poor benchmark value
    track_frequency: str = "daily"  # "daily", "weekly", "monthly"


@dataclass
class FinancialProduct:
    """A financial product relevant to this worker type."""
    name: str
    provider_type: str              # "sacco", "bank", "mobile", "chama", "government"
    description: str
    why_relevant: str
    typical_amount: str             # e.g. "KSh 5,000 - 50,000"
    interest_rate: str              # e.g. "1.5% per month" or "N/A"
    best_for: str                   # Use case


@dataclass
class WorkerProfile:
    """Complete profile for a worker type."""
    # Identity
    type_id: str                    # Unique identifier (snake_case)
    name: str                       # Display name
    name_sw: str                    # Swahili name
    description: str                # Short description
    sector: WorkerSector
    icon: str                       # Emoji icon

    # Financials
    income: IncomeRange
    operating_costs: OperatingCosts
    startup_cost: float             # Typical startup cost in KSh
    break_even_days: int            # Days to break even from startup

    # Risk & Seasonality
    risk_level: RiskLevel
    seasonality: SeasonalityPattern
    peak_months: list[int]          # Month numbers (1-12) when revenue peaks
    slow_months: list[int]          # Month numbers when revenue dips

    # Operations
    typical_hours: str              # e.g. "6 AM - 7 PM"
    working_days_per_week: int
    location_type: str              # "fixed", "mobile", "home", "client_site"
    requires_stock: bool
    requires_equipment: bool
    requires_license: bool

    # Tracking & Metrics
    key_metrics: list[KeyMetric]
    what_to_track: list[str]        # Business data points to track
    financial_products: list[FinancialProduct]

    # Intelligence
    common_challenges: list[str]
    success_tips: list[str]
    seasonal_insights: list[str]
    price_benchmarks: dict[str, float]  # Common items → typical price in KSh

    # Context for AI
    swahili_terms: dict[str, str]   # Domain-specific terms
    conversation_starters: list[str]  # Relevant questions to ask


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Profile Builder Helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _metric(name: str, desc: str, unit: str,
            good: float | None = None, avg: float | None = None,
            poor: float | None = None, freq: str = "daily") -> KeyMetric:
    return KeyMetric(name, desc, unit, good, avg, poor, freq)


def _product(name: str, ptype: str, desc: str, why: str,
             amount: str, rate: str, best_for: str) -> FinancialProduct:
    return FinancialProduct(name, ptype, desc, why, amount, rate, best_for)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 25 WORKER TYPE PROFILES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _profile_mama_mboga() -> WorkerProfile:
    return WorkerProfile(
        type_id="mama_mboga",
        name="Mama Mboga",
        name_sw="Mama Mboga",
        description="Vegetable and fresh produce vendor operating from a market stall or roadside stand",
        sector=WorkerSector.FOOD,
        icon="🥬",
        income=IncomeRange(low=200, average=500, high=1200, peak=2500),
        operating_costs=OperatingCosts(
            rent=100, stock=800, transport=150, utilities=20,
            labor=0, licenses=30, other=20,
        ),
        startup_cost=5_000,
        break_even_days=14,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.WEATHER_DRIVEN,
        peak_months=[1, 2, 5, 9, 12],       # Festive & planting seasons
        slow_months=[4, 6, 7],               # Heavy rains reduce customers
        typical_hours="5 AM - 6 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=False,
        requires_license=True,
        key_metrics=[
            _metric("daily_sales", "Total daily revenue", "KSh", 800, 500, 200),
            _metric("daily_profit", "Net profit after stock cost", "KSh", 300, 150, 50),
            _metric("waste_rate", "Percentage of stock lost to spoilage", "%", 5, 15, 30),
            _metric("stock_turnover", "How many times stock sells out per week", "count", 4, 2, 1, "weekly"),
            _metric("customer_count", "Number of customers per day", "count", 40, 20, 8),
            _metric("profit_margin", "Profit as percentage of sales", "%", 35, 25, 15, "weekly"),
        ],
        what_to_track=[
            "Daily sales by product (tomatoes, sukuma wiki, onions, etc.)",
            "Stock purchases and wholesale prices",
            "Spoilage and waste — what was thrown away",
            "Customer count per day",
            "Best-selling items vs slow movers",
            "Market days vs regular days",
            "Rainy days impact on foot traffic",
            "Price fluctuations at wholesale market",
        ],
        financial_products=[
            _product(
                "M-Pesa Savings (Mali)", "mobile",
                "Automatic savings from M-Pesa transactions",
                "Irregular income makes regular savings hard — auto-save helps",
                "KSh 100 - 70,000", "5-8% p.a.",
                "Building emergency fund",
            ),
            _product(
                "Chama / Table Banking", "chama",
                "Group savings and lending circle",
                "Mama mbogas thrive in groups — pool capital for bulk buying",
                "KSh 1,000 - 50,000 per cycle", "0-10% per cycle",
                "Bulk stock purchases, emergency funds",
            ),
            _product(
                "KCB M-Pesa / M-Shwari", "mobile",
                "Instant mobile loans based on M-Pesa history",
                "Quick capital for restocking when cash is tight",
                "KSh 1,000 - 1,000,000", "7.5% per month",
                "Emergency restocking",
            ),
            _product(
                "SACCO Savings", "sacco",
                "Formal savings with withdrawal benefits",
                "Long-term savings for school fees or expansion",
                "KSh 500 - 50,000/month", "8-12% p.a.",
                "School fees, land purchase",
            ),
        ],
        common_challenges=[
            "Perishable stock — vegetables spoil within 1-3 days",
            "Price fluctuations at Wakulima/Kawangware wholesale markets",
            "County kanjo (inspector) harassment and daily levies",
            "Rainy seasons reduce customer foot traffic by 30-50%",
            "Competition from supermarkets and online grocery delivery",
            "Lack of cold storage — no way to preserve perishables",
            "Irregular income makes budgeting extremely difficult",
            "Theft of stock at night or during transport",
        ],
        success_tips=[
            "Buy at wholesale markets (Wakulima, Kangemi) before 6 AM for best prices",
            "Track which vegetables sell fastest — focus on high-turnover items",
            "Group with other mama mbogas to buy in bulk and split transport costs",
            "Sell fruits in the afternoon when vegetable demand drops",
            "Build a customer base — regulars who come daily are your bread and butter",
            "Keep waste under 10% by buying smaller quantities more frequently",
            "Save at least KSh 50 daily — even small amounts compound",
            "Use M-Pesa for all transactions to build a financial history",
            "Negotiate stall rent — many landlords accept weekly vs daily payment",
        ],
        seasonal_insights=[
            "January-February: Post-holiday demand recovers, school opening drives sales",
            "March-April: Long rains begin — stock less, expect 20-30% fewer customers",
            "May-June: Heavy rains peak — focus on root vegetables (carrots, potatoes) that last longer",
            "July-August: Cold season — sukuma wiki and soups sell well",
            "September-October: Short rains begin, mixed demand",
            "November-December: Festive season — high demand for tomatoes, onions, cooking oil",
        ],
        price_benchmarks={
            "sukuma_bunch": 20,
            "tomato_1kg": 80,
            "onion_1kg": 100,
            "potato_1kg": 60,
            "cabbage_head": 40,
            "carrot_1kg": 120,
            "avocado_each": 30,
            "cooking_oil_1l": 250,
        },
        swahili_terms={
            "sukuma wiki": "Collard greens (kale) — Kenya's staple vegetable",
            "mboga": "Vegetables / greens",
            "mbogaini": "At the vegetable stall",
            "kanjo": "County inspector / enforcement officer",
            "soko": "Market",
            "wakulima": "Wakulima Market — Nairobi's main wholesale produce market",
            "stock": "Mali / bidhaa — inventory",
            "fundi wa mboga": "Expert vegetable selector (good at picking quality)",
        },
        conversation_starters=[
            "Umeuza ngapi leo? (How much did you sell today?)",
            "Ni mboga gani inauka haraka? (Which vegetables sell fastest?)",
            "Umeenda sokoni lini? (When did you go to the market?)",
            "Kuna mboga imeharibika? (Did any vegetables spoil?)",
            "Wateja wangapi leo? (How many customers today?)",
        ],
    )


def _profile_boda_boda() -> WorkerProfile:
    return WorkerProfile(
        type_id="boda_boda",
        name="Boda Boda Rider",
        name_sw="Boda Boda",
        description="Motorcycle taxi operator providing passenger and delivery transport",
        sector=WorkerSector.TRANSPORT,
        icon="🏍️",
        income=IncomeRange(low=300, average=800, high=1500, peak=3000),
        operating_costs=OperatingCosts(
            rent=0, stock=0, transport=0, utilities=50,
            labor=0, licenses=50, other=100,
        ),
        startup_cost=80_000,        # Second-hand bike
        break_even_days=120,
        risk_level=RiskLevel.HIGH,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[1, 5, 9, 12],  # School openings, festive
        slow_months=[4, 6, 7],       # Heavy rains
        typical_hours="5 AM - 10 PM",
        working_days_per_week=7,
        location_type="mobile",
        requires_stock=False,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_fares", "Total fare revenue", "KSh", 1200, 800, 300),
            _metric("fuel_cost", "Daily fuel/petrol spend", "KSh", 200, 300, 400),
            _metric("net_income", "Revenue minus fuel and costs", "KSh", 700, 450, 100),
            _metric("trip_count", "Number of trips per day", "count", 25, 15, 6),
            _metric("average_fare", "Average fare per trip", "KSh", 80, 50, 30),
            _metric("maintenance_cost", "Monthly maintenance and repairs", "KSh", 2000, 4000, 8000, "monthly"),
        ],
        what_to_track=[
            "Daily fare collection (cash + M-Pesa)",
            "Fuel purchases and consumption (km per litre)",
            "Number of trips and average fare",
            "Maintenance costs (oil change, tyres, brakes, chain)",
            "Accident and repair costs",
            "Police bribes / fines",
            "Loan repayment if bike is financed",
            "Best routes and peak hours",
        ],
        financial_products=[
            _product(
                "Boda Boda SACCO", "sacco",
                "Savings cooperative specifically for riders",
                "Group buying power for fuel, insurance, and bike parts",
                "KSh 200 - 5,000/month", "8-15% p.a.",
                "Bike replacement fund, insurance pool",
            ),
            _product(
                "Lipa Mdogo Mdogo (Bike Loan)", "bank",
                "Pay-as-you-go motorcycle financing",
                "Own your bike instead of renting — builds equity",
                "KSh 5,000 - 100,000", "2-4% per month",
                "Bike ownership",
            ),
            _product(
                "NHIF / Insurance", "government",
                "Health and accident insurance",
                "Boda riders have high accident risk — insurance is critical",
                "KSh 500 - 1,500/month", "N/A",
                "Medical emergencies, accident cover",
            ),
            _product(
                "M-Shwari / Fuliza", "mobile",
                "Instant mobile overdraft for fuel and emergencies",
                "Quick cash when fares are slow but bike needs fuel",
                "KSh 100 - 50,000", "7.5% per month",
                "Emergency fuel, repairs",
            ),
        ],
        common_challenges=[
            "High accident risk — boda boda accidents are #1 cause of injury for young men",
            "Fuel price fluctuations eat directly into profits",
            "Police harassment and arbitrary fines (KSh 500-2,000 per stop)",
            "Bike theft — especially at night and in unfamiliar areas",
            "Wear and tear — tyres, chain, brakes need constant replacement",
            "Loan repayment pressure if bike is financed",
            "Rain reduces passengers by 60-70%",
            "Competition from ride-hailing apps (Bolt, Uber Boda)",
            "NTSA crackdowns on licenses and helmets",
        ],
        success_tips=[
            "Track fuel consumption religiously — know your km/litre",
            "Identify peak hours: 6-8 AM, 12-1 PM, 5-8 PM are gold",
            "Keep KSh 200 emergency fund hidden on the bike for fuel",
            "Do basic maintenance yourself — oil change, chain tightening",
            "Avoid night riding if possible — accident and theft risk doubles",
            "Build relationships with regular passengers (estate commuters)",
            "Use M-Pesa for fares — creates a financial record for loans",
            "Join a boda SACCO for group insurance and savings",
            "Save for a rainy day fund — literally, rain kills income",
        ],
        seasonal_insights=[
            "January: School opening — high demand for stationery delivery and passenger trips",
            "March-April: Long rains start — fewer passengers, more mud, higher maintenance costs",
            "May-June: Rainy peak — income drops 40-50%, focus on delivery services",
            "July-August: Cold but dry — good riding season, passengers return",
            "September: Back-to-school rush — high demand",
            "November-December: Festive deliveries peak, then January slowdown",
        ],
        price_benchmarks={
            "petrol_1l": 217,
            "engine_oil_1l": 500,
            "tyre_front": 2500,
            "tyre_rear": 3000,
            "chain_set": 1500,
            "brake_pads": 400,
            "helmet": 1500,
            "reflective_jacket": 500,
        },
        swahili_terms={
            "boda boda": "Motorcycle taxi",
            "fare": "Nauli — passenger fare",
            "route": "Route — common path",
            "pikipiki": "Motorcycle",
            "mate": "Conductor/helper (rare on boda)",
            "kanjo": "County inspector",
            "checkpoint": "Kizuizi — police/NTSA check",
            "sokoni": "To the market",
            "haraka": "Urgent/rush delivery",
        },
        conversation_starters=[
            "Umepata wangapi leo? (How much did you make today?)",
            "Umeenda route gani? (Which route did you take?)",
            "Petroli imetumika ngapi? (How much fuel did you use?)",
            "Kuna trip yoyote kubwa? (Any big delivery trips?)",
            "Boda iko sawa? (Is the bike okay?)",
        ],
    )


def _profile_dukawallah() -> WorkerProfile:
    return WorkerProfile(
        type_id="dukawallah",
        name="Dukawallah",
        name_sw="Mmiliki wa Duka",
        description="Small retail shop owner selling household goods, groceries, and essentials",
        sector=WorkerSector.RETAIL,
        icon="🏪",
        income=IncomeRange(low=300, average=700, high=1500, peak=3000),
        operating_costs=OperatingCosts(
            rent=300, stock=2000, transport=100, utilities=100,
            labor=200, licenses=50, other=50,
        ),
        startup_cost=50_000,
        break_even_days=90,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[1, 5, 9, 12],
        slow_months=[6, 7],
        typical_hours="6 AM - 9 PM",
        working_days_per_week=7,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_sales", "Total daily revenue", "KSh", 1500, 700, 300),
            _metric("daily_profit", "Net profit after cost of goods", "KSh", 400, 200, 80),
            _metric("stock_value", "Total inventory value", "KSh", 30000, 20000, 5000, "weekly"),
            _metric("profit_margin", "Average margin on goods", "%", 30, 20, 10, "weekly"),
            _metric("customer_count", "Daily customer visits", "count", 50, 25, 10),
            _metric("dead_stock", "Items unsold for >30 days", "KSh", 500, 2000, 5000, "monthly"),
        ],
        what_to_track=[
            "Daily sales by product category",
            "Stock purchases and supplier costs",
            "Profit margins per product",
            "Dead stock (items sitting unsold >30 days)",
            "Customer buying patterns (time of day, common combos)",
            "Credit given to customers (tab/owe list)",
            "Rent and utility payments",
            "Competitor pricing nearby",
        ],
        financial_products=[
            _product(
                "Duka Float Loan", "mobile",
                "Short-term stock financing via M-Pesa",
                "Never run out of stock — bridge cash flow gaps",
                "KSh 5,000 - 100,000", "5-10% per month",
                "Restocking between payment cycles",
            ),
            _product(
                "Wholesale Credit (Stall)", "supplier",
                "Buy-now-pay-later from wholesale suppliers",
                "Access stock without immediate cash — pay when you sell",
                "KSh 10,000 - 200,000", "0-5% per month",
                "Bulk stock purchases",
            ),
            _product(
                "SACCO Business Account", "sacco",
                "Formal savings with access to larger loans",
                "Build credit history for shop expansion or second location",
                "KSh 1,000 - 100,000/month", "10-14% p.a.",
                "Shop expansion, school fees, land",
            ),
            _product(
                "Insurance (Stock & Fire)", "insurance",
                "Protect inventory against fire, theft, floods",
                "One fire can wipe out years of savings",
                "KSh 2,000 - 15,000/year", "N/A",
                "Stock protection",
            ),
        ],
        common_challenges=[
            "Cash flow gaps between buying stock and selling it",
            "Dead stock — items that don't sell tie up capital",
            "Customer credit (owe list) — people don't pay back",
            "Competition from supermarkets and wholesale shops",
            "High rent relative to sales — landlords increase arbitrarily",
            "Stock theft by customers or staff",
            "Power outages affecting cold drinks and perishables",
            "Counterfeit products from suppliers",
            "Regulatory compliance — county permits, fire certificates",
        ],
        success_tips=[
            "Track every shilling — use a notebook or phone app",
            "Focus on fast-moving goods: sugar, cooking oil, flour, soap",
            "Don't give credit to more than 10% of customers",
            "Restock early morning before customers arrive",
            "Negotiate with suppliers for better wholesale prices",
            "Display high-margin items at eye level",
            "Know your best sellers and never run out of them",
            "Join a duka owners association for bulk buying",
            "Use M-Pesa tills to track sales automatically",
        ],
        seasonal_insights=[
            "January: Post-holiday recovery, school opening drives stationery and food demand",
            "February-March: Steady demand, good time to clear dead stock",
            "April: Easter holiday boosts sales temporarily",
            "May-June: School term — steady but rain reduces evening customers",
            "July-August: Cold season — warm drinks, soup ingredients sell well",
            "September: School opening — high demand",
            "October: Mixed — election years can disrupt",
            "November-December: Festive season peak — stock up on cooking supplies",
        ],
        price_benchmarks={
            "sugar_1kg": 180,
            "cooking_oil_1l": 250,
            "maize_flour_2kg": 150,
            "rice_1kg": 180,
            "soap_bar": 50,
            "matchbox": 10,
            "candle": 20,
            "milk_500ml": 60,
        },
        swahili_terms={
            "duka": "Shop / store",
            "mali": "Stock / inventory / goods",
            "deni": "Debt / credit owed",
            "karatasi": "Receipt / paper record",
            "bei": "Price",
            "faida": "Profit",
            "hasara": "Loss",
            "mteja": "Customer",
            "msambazaji": "Supplier / distributor",
        },
        conversation_starters=[
            "Mauzo ya leo ni ngapi? (What are today's sales?)",
            "Kuna mali imebaki? (Is there stock left over?)",
            "Wateja wangapi wamenunua? (How many customers bought?)",
            "Kuna deni yoyote? (Any outstanding debts?)",
            "Ni bidhaa gani zinauzika sana? (Which products sell best?)",
        ],
    )


def _profile_machinga() -> WorkerProfile:
    return WorkerProfile(
        type_id="machinga",
        name="Machinga (Street Hawker)",
        name_sw="Machinga",
        description="Mobile street vendor selling goods from a cart, mat, or carrying goods",
        sector=WorkerSector.RETAIL,
        icon="🧺",
        income=IncomeRange(low=150, average=400, high=1000, peak=2000),
        operating_costs=OperatingCosts(
            rent=0, stock=500, transport=100, utilities=0,
            labor=0, licenses=0, other=50,
        ),
        startup_cost=3_000,
        break_even_days=10,
        risk_level=RiskLevel.HIGH,
        seasonality=SeasonalityPattern.DAILY_FLUCTUATING,
        peak_months=[1, 5, 12],
        slow_months=[4, 6, 7],
        typical_hours="7 AM - 7 PM",
        working_days_per_week=6,
        location_type="mobile",
        requires_stock=True,
        requires_equipment=False,
        requires_license=False,
        key_metrics=[
            _metric("daily_sales", "Total daily revenue", "KSh", 800, 400, 150),
            _metric("daily_profit", "Net profit after stock", "KSh", 250, 120, 40),
            _metric("locations_hit", "Number of selling spots visited", "count", 4, 2, 1),
            _metric("best_location", "Highest revenue location", "text", None, None, None, "weekly"),
            _metric("seized_stock", "Stock confiscated by kanjo", "KSh", 0, 0, 500),
            _metric("items_sold", "Total items sold", "count", 30, 15, 5),
        ],
        what_to_track=[
            "Daily revenue and items sold",
            "Location performance — which spots generate most sales",
            "Stock costs and best wholesale sources",
            "Kanjo encounters and confiscations",
            "Time spent at each location",
            "Weather impact on sales",
            "Best-selling items by location",
            "Competitor locations and pricing",
        ],
        financial_products=[
            _product(
                "M-Pesa Savings", "mobile",
                "Daily micro-savings via M-Pesa",
                "Irregular income needs automatic savings to work",
                "KSh 50 - 10,000", "5-8% p.a.",
                "Building an emergency fund",
            ),
            _product(
                "Chama / Merry-go-round", "chama",
                "Group savings where each member gets a lump sum",
                "Pool small daily savings into meaningful capital",
                "KSh 500 - 10,000/month", "N/A",
                "Stock capital, equipment",
            ),
            _product(
                "Micro-finance Loan", "mfi",
                "Small group-based loans for traders",
                "Access capital without collateral — group guarantee",
                "KSh 2,000 - 50,000", "15-25% p.a.",
                "Stock expansion, cart upgrade",
            ),
        ],
        common_challenges=[
            "Kanjo (county inspector) harassment — confiscation of goods",
            "No fixed location means no consistent customer base",
            "Physical exhaustion — carrying/wheeling goods all day",
            "Risk of theft, especially in crowded areas",
            "Rain completely stops business",
            "No social protections — no sick leave, no insurance",
            "Competition from other hawkers in the same area",
            "Difficulty getting wholesale credit without a fixed shop",
        ],
        success_tips=[
            "Map out 3-4 high-traffic locations and rotate between them",
            "Learn kanjo patrol schedules — avoid confiscation times",
            "Specialize in 2-3 products you know well rather than carrying everything",
            "Build rapport with shop owners — they may let you sell nearby",
            "Keep stock lightweight and portable — agility is survival",
            "Use M-Pesa for all transactions to build a financial record",
            "Save KSh 30-50 daily, no matter what",
            "Network with other machingas for market intelligence",
        ],
        seasonal_insights=[
            "January: New year, people have money from December bonuses — good sales",
            "March-April: Long rains — limited selling hours, focus on indoor locations",
            "May-June: Rainy peak — very tough, consider indoor markets",
            "July-August: Cold season — warm items (mandazi, tea) do well",
            "September: Back to school — stationery and snacks sell",
            "November-December: Festive peak — highest earning period",
        ],
        price_benchmarks={
            "mandazi_each": 10,
            "chapati_each": 20,
            "samosa_each": 30,
            "sunglasses_pair": 200,
            "phone_case": 150,
            "earphones": 200,
            "handkerchief": 50,
            "belt": 200,
        },
        swahili_terms={
            "machinga": "Street hawker / mobile vendor",
            "soko": "Market",
            "kanjo": "County inspector (enemy #1)",
            "mkokoteni": "Hand cart",
            "gunia": "Sack / bag for carrying goods",
            "bei ya jioni": "Evening discount price",
            "sokoni": "At the market",
            "kuhama": "Moving to a new location",
        },
        conversation_starters=[
            "Leo umepata wapi? (Where did you sell today?)",
            "Kanjo walikuja? (Did the inspectors come?)",
            "Umeuza ngapi leo? (How much did you sell today?)",
            "Ni bidhaa gani inauka? (Which items are selling?)",
        ],
    )


def _profile_fundi() -> WorkerProfile:
    return WorkerProfile(
        type_id="fundi",
        name="Fundi (Repair Technician)",
        name_sw="Fundi",
        description="Skilled repair technician — electronics, phones, appliances, shoes, watches",
        sector=WorkerSector.SERVICES,
        icon="🔧",
        income=IncomeRange(low=200, average=600, high=1500, peak=3000),
        operating_costs=OperatingCosts(
            rent=200, stock=300, transport=50, utilities=50,
            labor=0, licenses=20, other=30,
        ),
        startup_cost=15_000,
        break_even_days=30,
        risk_level=RiskLevel.LOW,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[1, 5, 9],
        slow_months=[7, 8],
        typical_hours="8 AM - 6 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=True,
        requires_license=False,
        key_metrics=[
            _metric("daily_revenue", "Daily repair fees collected", "KSh", 1000, 600, 200),
            _metric("jobs_completed", "Number of repairs done", "count", 8, 4, 1),
            _metric("average_job_value", "Average repair fee", "KSh", 200, 150, 80),
            _metric("parts_cost", "Daily parts/spares spending", "KSh", 200, 300, 500),
            _metric("repeat_customers", "Returning customers per week", "count", 10, 5, 2, "weekly"),
            _metric("skill_utilization", "% of time doing paid work vs waiting", "%", 80, 50, 20),
        ],
        what_to_track=[
            "Number and type of repairs done daily",
            "Repair fees charged per job",
            "Parts/spares costs per job",
            "Customer complaints and warranty returns",
            "Repeat customers and referrals",
            "New skills learned and tools acquired",
            "Time per job (efficiency)",
            "Dead time (waiting for customers)",
        ],
        financial_products=[
            _product(
                "Tool Loan", "mfi",
                "Micro-loan for purchasing tools and equipment",
                "Better tools = faster repairs = more income",
                "KSh 5,000 - 50,000", "10-20% p.a.",
                "Tool upgrade, new equipment",
            ),
            _product(
                "SACCO Savings", "sacco",
                "Regular savings with loan access",
                "Build capital for a proper workshop or training",
                "KSh 500 - 20,000/month", "8-12% p.a.",
                "Workshop rental, training courses",
            ),
            _product(
                "M-Pesa Business Account", "mobile",
                "Till number for receiving payments professionally",
                "Track income automatically, appear professional",
                "N/A", "Free to register",
                "Payment tracking, business records",
            ),
        ],
        common_challenges=[
            "Customers haggle down repair prices",
            "Lack of genuine spare parts — counterfeits cause warranty returns",
            "Rapid technology changes require constant learning",
            "Rent eats into profits — location must justify cost",
            "Customers delay payment or claim repairs broke something else",
            "Power outages affect work (especially electronics repair)",
            "Competition from manufacturer service centers",
            "Difficulty pricing jobs — too high loses customers, too low kills margins",
        ],
        success_tips=[
            "Specialize in 2-3 device types — become the go-to expert",
            "Build a reputation for honesty — don't overcharge or fabricate problems",
            "Stock common spare parts for your specialty — faster turnaround",
            "Offer a 7-day warranty to build trust",
            "Learn from YouTube and manufacturer guides — stay current",
            "Network with other fundis for referrals and parts sourcing",
            "Use social media to showcase before/after repairs",
            "Track which repairs are most profitable and focus on those",
        ],
        seasonal_insights=[
            "January: Post-holiday — people repair gifts and old items",
            "March-April: Steady — phones always break",
            "May-June: Rainy season — water damage repairs spike (phones, electronics)",
            "July-August: Moderate — school holidays mean more free time for repairs",
            "September: Back to school — electronics repairs increase",
            "November-December: Festive season — phone repairs spike, people want devices working",
        ],
        price_benchmarks={
            "phone_screen_repair": 1500,
            "phone_charging_port": 800,
            "shoe_resole": 300,
            "watch_battery": 100,
            "radio_repair": 500,
            "iron_repair": 300,
            "fan_repair": 400,
            "blender_repair": 500,
        },
        swahili_terms={
            "fundi": "Skilled technician / repair person",
            "kazi": "Work / job",
            "sehemu": "Parts / spare parts",
            "bei": "Price / charge",
            "garansi": "Warranty / guarantee",
            "kufanya": "To do / repair",
            "kuvunjika": "Broken / damaged",
            "kutengeneza": "To fix / repair",
        },
        conversation_starters=[
            "Kazi ngapi leo? (How many jobs today?)",
            "Ulipata wangapi kwa kazi? (How much did you earn per job?)",
            "Kuna sehemu unahitaji? (Do you need any parts?)",
            "Ni kazi gani inalipa zaidi? (Which repair pays best?)",
        ],
    )


def _profile_mama_lishe() -> WorkerProfile:
    return WorkerProfile(
        type_id="mama_lishe",
        name="Mama Lishe (Food Vendor)",
        name_sw="Mama Lishe",
        description="Cooked food vendor serving meals from a kiosk, roadside stall, or home kitchen",
        sector=WorkerSector.FOOD,
        icon="🍲",
        income=IncomeRange(low=300, average=800, high=2000, peak=4000),
        operating_costs=OperatingCosts(
            rent=200, stock=1200, transport=100, utilities=200,
            labor=200, licenses=50, other=50,
        ),
        startup_cost=20_000,
        break_even_days=30,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.SCHOOL_DRIVEN,
        peak_months=[1, 2, 5, 9],
        slow_months=[4, 8, 12],
        typical_hours="5 AM - 8 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_revenue", "Total daily meal sales", "KSh", 2000, 800, 300),
            _metric("daily_profit", "Net profit after ingredients", "KSh", 600, 300, 80),
            _metric("plates_sold", "Number of meals served", "count", 60, 30, 10),
            _metric("food_cost_ratio", "Ingredient cost as % of revenue", "%", 50, 60, 75, "weekly"),
            _metric("waste_rate", "Food thrown away as % of prepared", "%", 5, 15, 30),
            _metric("customer_count", "Regular daily customers", "count", 40, 20, 8),
        ],
        what_to_track=[
            "Number of plates/meals sold daily",
            "Ingredient purchases and costs",
            "Food waste (prepared but unsold)",
            "Customer preferences and peak hours",
            "Revenue by meal type (lunch vs breakfast)",
            "Water and charcoal/gas costs",
            "Hygiene compliance costs",
            "Competitor pricing and menu",
        ],
        financial_products=[
            _product(
                "M-Pesa Till", "mobile",
                "Digital payment collection",
                "Track sales automatically, accept cashless payments",
                "N/A", "Free",
                "Sales tracking, customer convenience",
            ),
            _product(
                "Chama / Women's Group", "chama",
                "Group savings and lending",
                "Women food vendors thrive in groups — shared knowledge and capital",
                "KSh 500 - 20,000/month", "N/A",
                "Bulk ingredient purchase, equipment",
            ),
            _product(
                "SACCO Loan", "sacco",
                "Medium-term loan for kitchen equipment",
                "A bigger pot, better stove, or fridge increases capacity",
                "KSh 10,000 - 200,000", "12-18% p.a.",
                "Kitchen equipment, expansion",
            ),
        ],
        common_challenges=[
            "Rising ingredient costs — cooking oil, maize flour prices fluctuate",
            "Food safety and hygiene compliance — county health inspections",
            "Customer haggling and credit requests",
            "Charcoal/gas costs are significant and rising",
            "Water availability and cost",
            "Competition from other food vendors and fast food",
            "Food waste from over-preparation",
            "Physical exhaustion — cooking and serving all day",
        ],
        success_tips=[
            "Know your daily customer count — prepare exactly that amount",
            "Buy ingredients in bulk at wholesale markets early morning",
            "Offer a limited menu done excellently vs a large mediocre menu",
            "Build a loyal customer base — regulars are predictable income",
            "Keep your space spotlessly clean — hygiene attracts customers",
            "Price meals to include all costs (charcoal, water, transport)",
            "Save at least KSh 100 per day for emergencies",
            "Learn customer preferences — some want more meat, some want cheaper options",
        ],
        seasonal_insights=[
            "January: School opening — high demand from students and workers",
            "March-April: Steady, but Easter holiday may reduce office workers",
            "May-June: Rainy season — fewer walk-in customers, consider delivery",
            "July-August: Cold season — soups, tea, and warm food sell more",
            "September: Back to school — strong demand",
            "November-December: Festive season — catering orders peak, but regular customers go home",
        ],
        price_benchmarks={
            "ugali_plate": 50,
            "rice_plate": 80,
            "githeri_plate": 50,
            "nyama_choma_plate": 250,
            "chapo_2": 40,
            "chai_cup": 30,
            "sukuma_wiki_plate": 30,
            "ndengu_plate": 50,
        },
        swahili_terms={
            "lishe": "Food / nutrition",
            "mama lishe": "Food vendor (literally 'nutrition mama')",
            "chakula": "Food",
            "sufuria": "Cooking pot",
            "jiko": "Stove / kitchen",
            "mkaa": "Charcoal",
            "maji": "Water",
            "sahani": "Plate",
            "wateja": "Customers",
        },
        conversation_starters=[
            "Leo umepika nini? (What did you cook today?)",
            "Sahani ngapi zimeuzika? (How many plates sold?)",
            "Bei ya mafuta imepanda? (Did oil prices go up?)",
            "Kuna chakula kimebaki? (Is there food left over?)",
        ],
    )


def _profile_mpesa_agent() -> WorkerProfile:
    return WorkerProfile(
        type_id="mpesa_agent",
        name="M-Pesa Agent",
        name_sw="Wakala wa M-Pesa",
        description="Mobile money agent handling M-Pesa deposits, withdrawals, and transfers",
        sector=WorkerSector.DIGITAL,
        icon="📱",
        income=IncomeRange(low=200, average=500, high=1000, peak=2000),
        operating_costs=OperatingCosts(
            rent=300, stock=0, transport=50, utilities=100,
            labor=200, licenses=100, other=50,
        ),
        startup_cost=100_000,       # Float capital + shop setup
        break_even_days=180,
        risk_level=RiskLevel.LOW,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[1, 5, 9, 12],  # School fees, festive
        slow_months=[3, 7],
        typical_hours="6 AM - 9 PM",
        working_days_per_week=7,
        location_type="fixed",
        requires_stock=False,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_commission", "Total daily commission earned", "KSh", 800, 500, 200),
            _metric("transaction_count", "Number of M-Pesa transactions", "count", 80, 40, 15),
            _metric("float_utilization", "% of float used daily", "%", 80, 50, 20),
            _metric("float_amount", "Total float (working capital)", "KSh", 50000, 30000, 10000),
            _metric("dead_float", "Unused float sitting idle", "KSh", 5000, 15000, 30000),
            _metric("customer_count", "Unique daily customers", "count", 60, 30, 10),
        ],
        what_to_track=[
            "Daily transaction count by type (deposit, withdraw, transfer)",
            "Commission earned per transaction type",
            "Float levels — how much is used vs idle",
            "Peak hours and transaction volumes",
            "Customer complaints and reversals",
            "Cash handling costs (bank trips for float)",
            "Rental and utility costs",
            "Lipa na M-Pesa (pay bill) transaction volumes",
        ],
        financial_products=[
            _product(
                "Float Financing Loan", "bank",
                "Short-term loan to increase M-Pesa float",
                "More float = more transactions = more commission",
                "KSh 20,000 - 500,000", "1.5-3% per month",
                "Increasing transaction capacity",
            ),
            _product(
                "SACCO Savings", "sacco",
                "Regular savings from commission income",
                "Steady income makes regular saving easy",
                "KSh 1,000 - 30,000/month", "8-12% p.a.",
                "Long-term wealth building",
            ),
            _product(
                "Business Insurance", "insurance",
                "Theft and liability cover for cash on premises",
                "Agents hold significant cash — risk of robbery",
                "KSh 5,000 - 20,000/year", "N/A",
                "Theft and loss protection",
            ),
        ],
        common_challenges=[
            "Float management — too little loses customers, too much sits idle",
            "Cash handling risks — robbery, counterfeit notes",
            "Network downtime from Safaricom — no transactions, no income",
            "Customer disputes and reversals eat time",
            "Commission rates keep declining as Safaricom adjusts",
            "Competition from nearby agents — saturation",
            "Regulatory compliance — KYC requirements",
            "Cash logistics — frequent trips to bank for float replenishment",
        ],
        success_tips=[
            "Track float levels hourly — know your peak times",
            "Keep KSh 5,000-10,000 reserve for unexpected high-demand periods",
            "Offer exceptional customer service — friendliness brings regulars",
            "Add complementary services: airtime, bill payments, NHIF registration",
            "Location is everything — near markets, matatu stages, or residential areas",
            "Negotiate with Safaricom for better commission tiers",
            "Use the M-Pesa app to track transactions in real-time",
            "Build relationship with your nearest bank for quick float top-ups",
        ],
        seasonal_insights=[
            "January: School fees season — massive withdrawal volumes",
            "March-April: Steady — regular transactions",
            "May: Worker remittances peak (end of first quarter)",
            "June-July: Moderate — but end-month peaks",
            "August-September: School fees again — high volumes",
            "October: Steady",
            "November: Pre-festive remittances begin",
            "December: Christmas remittances peak — highest volumes of the year",
        ],
        price_benchmarks={
            "deposit_commission_rate": 0.04,    # ~4% of deposit value
            "withdraw_commission_rate": 0.03,   # ~3% of withdrawal
            "float_top_up_fee": 0,
            "minimum_float": 10000,
            "average_transaction": 2000,
            "daily_target_transactions": 50,
        },
        swahili_terms={
            "wakala": "Agent",
            "float": "Pesa ya kufanyia kazi — working capital",
            "kutoa": "Withdraw",
            "kuweka": "Deposit",
            "kutuma": "Send/transfer",
            "reversal": "Kurejesha — undo a transaction",
            "commission": "Msahara wa wakala — agent earnings",
            "lipa na M-Pesa": "Pay with M-Pesa (paybill)",
        },
        conversation_starters=[
            "Transaction ngapi leo? (How many transactions today?)",
            "Commission umepata ngapi? (How much commission today?)",
            "Float inatosha? (Is the float enough?)",
            "Kuna time yenye wateja wengi? (Is there a peak time?)",
        ],
    )


def _profile_mitumba_seller() -> WorkerProfile:
    return WorkerProfile(
        type_id="mitumba_seller",
        name="Mitumba Seller",
        name_sw="Muuzaji wa Mitumba",
        description="Second-hand clothing dealer selling imported used clothes",
        sector=WorkerSector.RETAIL,
        icon="👗",
        income=IncomeRange(low=200, average=600, high=1500, peak=4000),
        operating_costs=OperatingCosts(
            rent=200, stock=1500, transport=200, utilities=30,
            labor=0, licenses=30, other=50,
        ),
        startup_cost=15_000,
        break_even_days=30,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.FESTIVAL_DRIVEN,
        peak_months=[1, 4, 9, 12],
        slow_months=[6, 7],
        typical_hours="8 AM - 6 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=False,
        requires_license=True,
        key_metrics=[
            _metric("daily_sales", "Daily revenue", "KSh", 1200, 600, 200),
            _metric("items_sold", "Clothes sold per day", "count", 8, 4, 1),
            _metric("average_price", "Average selling price per item", "KSh", 200, 150, 80),
            _metric("bale_cost", "Cost per bale of mitumba", "KSh", 5000, 8000, 12000, "monthly"),
            _metric("profit_per_bale", "Profit from one bale", "KSh", 3000, 5000, 10000, "monthly"),
            _metric("dead_stock", "Unsold items accumulating", "count", 10, 30, 100, "weekly"),
        ],
        what_to_track=[
            "Daily sales by item type (dresses, shirts, trousers, etc.)",
            "Bale purchase cost and contents",
            "Price per item and margin",
            "Best-selling brands and styles",
            "Customer preferences by season",
            "Dead stock items (mark down or donate)",
            "Market day performance vs regular days",
        ],
        financial_products=[
            _product(
                "Bale Financing Loan", "mfi",
                "Short-term loan for purchasing bales",
                "Buy larger bales for better wholesale pricing",
                "KSh 5,000 - 100,000", "5-10% per month",
                "Stock capital for bale purchases",
            ),
            _product(
                "SACCO Savings", "sacco",
                "Regular savings from profits",
                "Predictable income supports regular savings",
                "KSh 500 - 10,000/month", "8-12% p.a.",
                "Shop upgrade, land, school fees",
            ),
        ],
        common_challenges=[
            "Quality inconsistency — bales can contain damaged/worn items",
            "Trends change fast — yesterday's fashion doesn't sell",
            "Competition from online sellers and other mitumba traders",
            "Import duty and clearing costs fluctuate",
            "Dead stock from wrong bale selection",
            "Customer haggling — margins are thin",
            "Storage space for bales",
            "Rain reduces market attendance significantly",
        ],
        success_tips=[
            "Learn to assess bale quality before buying — inspect samples",
            "Specialize in a niche (designer, children's, plus-size)",
            "Wash and iron items before displaying — presentation adds value",
            "Price fairly but firmly — know your minimum acceptable price",
            "Keep up with fashion trends — TikTok and Instagram drive demand",
            "Sell slow items at cost rather than letting them accumulate",
            "Build a WhatsApp group for regular customers to see new arrivals",
        ],
        seasonal_insights=[
            "January: Post-holiday sales, new year new clothes",
            "February-March: Steady — people buying for Easter",
            "April: Easter holiday boost",
            "May-June: Rainy season — warm clothes sell, market attendance drops",
            "July-August: Cold season — jackets, sweaters in demand",
            "September: Back to school — children's clothes sell well",
            "October: Moderate",
            "November-December: Festive season peak — party wear, new outfits",
        ],
        price_benchmarks={
            "bale_gmt_45kg": 8000,
            "bale_shoes_45kg": 12000,
            "shirt_price": 150,
            "dress_price": 250,
            "trousers_price": 200,
            "jacket_price": 400,
            "shoes_pair": 350,
            "children_outfit": 100,
        },
        swahili_terms={
            "mitumba": "Second-hand clothes (literally 'bundles')",
            "bale": "Bundle of clothes (45kg bale)",
            "GMT": "General merchandise — mixed clothing bale",
            "bei ya mwisho": "Final price",
            "piga bei": "To bargain / negotiate price",
            "mtumba": "Single second-hand item",
        },
        conversation_starters=[
            "Leo umepata mauzo ngapi? (How were today's sales?)",
            "Bale mpya imefika? (Did a new bale arrive?)",
            "Ni nguo gani zinauzika? (Which clothes sell best?)",
        ],
    )


def _profile_jua_kali() -> WorkerProfile:
    return WorkerProfile(
        type_id="jua_kali",
        name="Jua Kali Artisan",
        name_sw="Fundi wa Jua Kali",
        description="Informal manufacturer — metalwork, woodwork, furniture, fabrication",
        sector=WorkerSector.MANUFACTURING,
        icon="⚒️",
        income=IncomeRange(low=200, average=800, high=2500, peak=5000),
        operating_costs=OperatingCosts(
            rent=300, stock=800, transport=200, utilities=100,
            labor=300, licenses=30, other=100,
        ),
        startup_cost=30_000,
        break_even_days=60,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[1, 5, 9],
        slow_months=[7, 8, 12],
        typical_hours="7 AM - 5 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=True,
        requires_license=False,
        key_metrics=[
            _metric("daily_revenue", "Daily revenue from orders and sales", "KSh", 2000, 800, 200),
            _metric("order_backlog", "Pending orders in queue", "count", 5, 10, 20, "weekly"),
            _metric("material_cost_ratio", "Material cost as % of selling price", "%", 40, 55, 70, "weekly"),
            _metric("jobs_completed", "Completed jobs per week", "count", 3, 5, 8, "weekly"),
            _metric("average_job_value", "Average order value", "KSh", 3000, 5000, 15000),
            _metric("rework_rate", "Jobs requiring rework/fixes", "%", 2, 5, 15, "monthly"),
        ],
        what_to_track=[
            "Orders received and completed",
            "Material costs per job (metal, wood, paint, etc.)",
            "Labor costs (hired helpers)",
            "Job completion time vs estimate",
            "Customer deposits and outstanding payments",
            "Tool maintenance and replacement",
            "Referrals and repeat customers",
            "New designs and skills learned",
        ],
        financial_products=[
            _product(
                "Asset Financing", "bank",
                "Loan for purchasing equipment (welder, grinder, lathe)",
                "Better equipment = higher quality = higher prices",
                "KSh 20,000 - 500,000", "12-24% p.a.",
                "Workshop equipment upgrade",
            ),
            _product(
                "SACCO Business Loan", "sacco",
                "Medium-term business expansion loan",
                "Scale from solo artisan to small workshop with employees",
                "KSh 50,000 - 1,000,000", "12-18% p.a.",
                "Workshop expansion, hiring",
            ),
            _product(
                "Raw Material Credit", "supplier",
                "Buy-now-pay-later from material suppliers",
                "Take orders without full material cost upfront",
                "KSh 5,000 - 100,000", "0-5% per month",
                "Material purchasing",
            ),
        ],
        common_challenges=[
            "Customer deposits don't cover full material cost",
            "Skilled labor is expensive and hard to find",
            "Material prices fluctuate (steel, timber, paint)",
            "Customer delays in paying final balance",
            "Power outages halt production",
            "Competition from mass-produced imported goods",
            "Lack of formal business records makes loans hard to get",
            "Safety hazards — welding burns, cuts, eye damage",
        ],
        success_tips=[
            "Always take a 50% deposit before starting any job",
            "Photograph completed work for your portfolio",
            "Price jobs at material cost × 2.5 minimum",
            "Learn to say no to rush jobs that compromise quality",
            "Invest in safety equipment — one accident can end your career",
            "Build a WhatsApp catalog of your work",
            "Network with contractors and interior designers for referrals",
            "Keep formal records of every job — deposits, costs, payments",
        ],
        seasonal_insights=[
            "January: New year — businesses order new furniture and equipment",
            "March-April: Construction season begins — gates, windows, grills",
            "May-June: Rainy season — outdoor work slows, indoor orders continue",
            "July-August: Cold season — moderate demand",
            "September: Construction picks up again",
            "November: Festive orders begin — furniture, decorations",
            "December: Some orders, but many customers wait for January",
        ],
        price_benchmarks={
            "metallic_door": 12000,
            "window_grill_set": 8000,
            "steel_table": 5000,
            "bookshelf": 6000,
            "metallic_gate": 25000,
            "welding_per_hour": 500,
            "painting_per_sqm": 300,
            "steel_per_kg": 120,
        },
        swahili_terms={
            "jua kali": "Informal sector / literally 'hot sun' (working under the sun)",
            "kazi ya mkono": "Handmade work",
            "deposit": "Kabla — advance payment",
            "mpango": "Plan / design",
            "kuchoma": "To weld",
            "kukata": "To cut",
            "kupaka rangi": "To paint",
            "sekta isiyo rasmi": "Informal sector",
        },
        conversation_starters=[
            "Kazi ngapi kwa queue? (How many jobs in the queue?)",
            "Umeamua bei gani? (What price did you decide?)",
            "Material imetosha? (Is the material enough?)",
            "Client amelipa deposit? (Did the client pay a deposit?)",
        ],
    )


def _profile_salon_barber() -> WorkerProfile:
    return WorkerProfile(
        type_id="salon_barber",
        name="Salon / Barber Shop",
        name_sw="Saluni / Kinyozi",
        description="Hair salon or barber shop offering haircuts, braiding, styling, and grooming",
        sector=WorkerSector.SERVICES,
        icon="💇",
        income=IncomeRange(low=200, average=700, high=2000, peak=4000),
        operating_costs=OperatingCosts(
            rent=300, stock=400, transport=50, utilities=150,
            labor=400, licenses=50, other=50,
        ),
        startup_cost=25_000,
        break_even_days=45,
        risk_level=RiskLevel.LOW,
        seasonality=SeasonalityPattern.FESTIVAL_DRIVEN,
        peak_months=[4, 8, 12],
        slow_months=[6, 7],
        typical_hours="8 AM - 7 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_revenue", "Total daily service revenue", "KSh", 1500, 700, 200),
            _metric("clients_served", "Number of clients per day", "count", 12, 6, 2),
            _metric("average_ticket", "Average spend per client", "KSh", 300, 200, 100),
            _metric("product_sales", "Revenue from selling hair products", "KSh", 200, 100, 0),
            _metric("repeat_rate", "% of returning clients", "%", 70, 50, 20, "monthly"),
            _metric("utilization", "% of available time spent on clients", "%", 80, 50, 20),
        ],
        what_to_track=[
            "Number of clients per day by service type",
            "Revenue per service (cut, braid, wash, treatment)",
            "Product sales (hair products, oils, relaxers)",
            "Client retention rate",
            "Staff utilization and productivity",
            "Stock usage and restocking needs",
            "Walk-in vs appointment clients",
            "Client preferences and feedback",
        ],
        financial_products=[
            _product(
                "Beauty Industry SACCO", "sacco",
                "Savings cooperative for salon/barber owners",
                "Group buying of products, shared training costs",
                "KSh 500 - 20,000/month", "8-12% p.a.",
                "Equipment upgrade, training",
            ),
            _product(
                "M-Pesa Till + Business Records", "mobile",
                "Digital payment tracking for all services",
                "Know exactly what each service type earns",
                "N/A", "Free",
                "Income tracking, business growth",
            ),
            _product(
                "Working Capital Loan", "mfi",
                "Short-term loan for product stock",
                "Never run out of popular products",
                "KSh 5,000 - 50,000", "5-10% per month",
                "Product restocking",
            ),
        ],
        common_challenges=[
            "Client no-shows and last-minute cancellations",
            "Product cost — genuine products are expensive",
            "Staff poaching by competitors",
            "Rent increases without matching revenue growth",
            "Client complaints about inconsistent quality",
            "Electricity outages (dryers, flat irons need power)",
            "Water supply interruptions",
            "Competition from mobile/home-based stylists",
        ],
        success_tips=[
            "Build a loyal client base — regulars are your foundation",
            "Use WhatsApp to confirm appointments and reduce no-shows",
            "Upsell treatments and products naturally during service",
            "Keep your space clean and welcoming — first impressions matter",
            "Learn new styles regularly — YouTube tutorials are free",
            "Offer loyalty cards (every 10th haircut free)",
            "Cross-sell products: 'I used this on your hair, want to take one home?'",
            "Track which services are most profitable and promote them",
        ],
        seasonal_insights=[
            "January: Post-holiday — people back at work, moderate demand",
            "February-Mavelentine's Day — couples grooming",
            "March-April: Easter prep — braiding and styling peak",
            "May-June: Rainy season — fewer walk-ins, braids last longer",
            "July-August: Moderate — back-to-school prep for children",
            "September: Moderate",
            "October: Pre-festive prep begins",
            "November-December: Festive peak — highest demand of the year",
        ],
        price_benchmarks={
            "haircut_men": 150,
            "haircut_women": 200,
            "braids_full": 800,
            "weave_installation": 1500,
            "relaxer_treatment": 500,
            "wash_and_blow": 300,
            "beard_trim": 100,
            "kids_haircut": 100,
        },
        swahili_terms={
            "kinyozi": "Barber shop",
            "saluni": "Salon",
            "kunyoa": "To shave / cut hair",
            "kunyolea": "To braid / plait",
            "nywele": "Hair",
            "rangi ya nywele": "Hair dye / color",
            "msuko": "Braids / weave",
            "mteja": "Customer / client",
        },
        conversation_starters=[
            "Leo umeona wateja wangapi? (How many clients today?)",
            "Kuna appointment za kesho? (Any appointments for tomorrow?)",
            "Ni service gani inalipa zaidi? (Which service pays best?)",
            "Products zimetosha? (Are products sufficient?)",
        ],
    )


def _profile_matatu_crew() -> WorkerProfile:
    return WorkerProfile(
        type_id="matatu_crew",
        name="Matatu Driver / Conductor",
        name_sw="Dereva / Makanga wa Matatu",
        description="Public minibus transport operator — driver or conductor (tout)",
        sector=WorkerSector.TRANSPORT,
        icon="🚐",
        income=IncomeRange(low=400, average=1000, high=2000, peak=4000),
        operating_costs=OperatingCosts(
            rent=0, stock=0, transport=0, utilities=80,
            labor=0, licenses=100, other=150,
        ),
        startup_cost=0,             # Employed by owner
        break_even_days=0,
        risk_level=RiskLevel.HIGH,
        seasonality=SeasonalityPattern.SCHOOL_DRIVEN,
        peak_months=[1, 5, 9],
        slow_months=[4, 7, 8],
        typical_hours="5 AM - 10 PM",
        working_days_per_week=6,
        location_type="mobile",
        requires_stock=False,
        requires_equipment=False,
        requires_license=True,
        key_metrics=[
            _metric("daily_collection", "Total fare collected", "KSh", 5000, 3000, 1000),
            _metric("daily_payout", "Amount paid to crew (after owner's share)", "KSh", 1500, 1000, 400),
            _metric("trips_completed", "Number of round trips", "count", 6, 4, 2),
            _metric("passenger_count", "Total passengers carried", "count", 80, 50, 20),
            _metric("fuel_cost", "Daily fuel expense", "KSh", 2000, 1500, 1000),
            _metric("target_vs_actual", "Daily target vs actual collection", "%", 100, 80, 50),
        ],
        what_to_track=[
            "Daily fare collection (total and per trip)",
            "Number of passengers per trip",
            "Fuel costs and consumption",
            "Route and timing performance",
            "Police fines and bribes",
            "Vehicle maintenance costs",
            "Target achievement (daily target set by owner)",
            "Peak hours and route optimization",
        ],
        financial_products=[
            _product(
                "SACCO Savings", "sacco",
                "Regular savings with loan access for vehicle purchase",
                "Goal: eventually own your own matatu",
                "KSh 500 - 20,000/month", "8-12% p.a.",
                "Vehicle purchase fund",
            ),
            _product(
                "NHIF", "government",
                "Health insurance",
                "High-risk occupation — health cover is essential",
                "KSh 500 - 1,700/month", "N/A",
                "Medical emergencies",
            ),
        ],
        common_challenges=[
            "Owner demands — daily targets that are hard to meet",
            "Police harassment and fines on the route",
            "Traffic jams kill earnings — fewer trips per day",
            "Sacco/owner rules and penalties",
            "Passenger disputes and fare evasion",
            "High accident risk on Kenyan roads",
            "Fuel price increases without fare adjustments",
            "Exhausting long hours with no job security",
        ],
        success_tips=[
            "Know your route's peak hours — maximize trips during rush times",
            "Build relationships with regular passengers",
            "Keep detailed records of collections vs target",
            "Negotiate with owner for fair targets based on route realities",
            "Save consistently — don't spend all daily payout",
            "Learn basic vehicle maintenance — reduce breakdown delays",
            "Network with other crew for route intelligence",
        ],
        seasonal_insights=[
            "January: School opening — very high demand on school routes",
            "March-April: Steady but Easter holiday reduces commuters",
            "May-June: Rainy season — traffic worse, more passengers seeking rides",
            "July-August: School holiday — lower volumes",
            "September: School opening — high demand again",
            "November-December: Festive travel — long-distance routes peak",
        ],
        price_benchmarks={
            "average_fare": 50,
            "rush_hour_fare": 70,
            "off_peak_fare": 40,
            "fuel_per_litre": 217,
            "daily_target": 4000,
            "crew_share": 0.30,
        },
        swahili_terms={
            "matatu": "Public minibus",
            "makanga": "Conductor / tout",
            "dereva": "Driver",
            "nauli": "Fare",
            "route": "Route / njia",
            "stage": "Bus stop / stage",
            "sacco": "Savings cooperative (also the vehicle owner group)",
            "target": "Daily collection target",
        },
        conversation_starters=[
            "Leo target imefika? (Did you hit today's target?)",
            "Umebeba abiria wangapi? (How many passengers did you carry?)",
            "Route ilikuwaje? (How was the route today?)",
        ],
    )


def _profile_mkulima() -> WorkerProfile:
    return WorkerProfile(
        type_id="mkulima",
        name="Mkulima (Small-Scale Farmer)",
        name_sw="Mkulima",
        description="Small-scale farmer growing crops or keeping livestock for sale",
        sector=WorkerSector.AGRICULTURE,
        icon="🌾",
        income=IncomeRange(low=0, average=400, high=2000, peak=10000),
        operating_costs=OperatingCosts(
            rent=0, stock=1500, transport=300, utilities=50,
            labor=500, licenses=20, other=100,
        ),
        startup_cost=20_000,
        break_even_days=90,         # One planting cycle
        risk_level=RiskLevel.HIGH,
        seasonality=SeasonalityPattern.HARVEST_DRIVEN,
        peak_months=[3, 7, 11],     # Harvest times
        slow_months=[1, 5, 9],      # Planting (expenses, no income)
        typical_hours="6 AM - 4 PM",
        working_days_per_week=6,
        location_type="home",
        requires_stock=True,
        requires_equipment=True,
        requires_license=False,
        key_metrics=[
            _metric("harvest_value", "Total value of harvest", "KSh", 30000, 15000, 3000, "monthly"),
            _metric("yield_per_acre", "Crop yield per acre", "bags", 20, 12, 5, "seasonal"),
            _metric("input_cost", "Seeds, fertilizer, pesticide cost", "KSh", 5000, 10000, 20000, "seasonal"),
            _metric("market_price", "Price received per unit", "KSh", None, None, None),
            _metric("post_harvest_loss", "% of harvest lost to spoilage/pests", "%", 5, 15, 30, "seasonal"),
            _metric("profit_margin", "Net profit as % of revenue", "%", 40, 25, 5, "seasonal"),
        ],
        what_to_track=[
            "Crop planted, area (acres), and expected yield",
            "Input costs: seeds, fertilizer, pesticide, labor",
            "Harvest date and actual yield",
            "Selling price at farm gate vs market",
            "Post-harvest losses (spoilage, pests, transport damage)",
            "Rainfall and weather patterns",
            "Livestock health and production (if applicable)",
            "Market prices for your crops",
        ],
        financial_products=[
            _product(
                "Agricultural SACCO", "sacco",
                "Farmers' cooperative for savings and input loans",
                "Access subsidized inputs and guaranteed markets",
                "KSh 1,000 - 100,000/season", "10-15% p.a.",
                "Input financing, market access",
            ),
            _product(
                "Crop Insurance (AII)", "insurance",
                "Index-based crop insurance against drought/flood",
                "One failed season can bankrupt a farmer — insurance mitigates",
                "KSh 500 - 5,000/season", "N/A",
                "Drought and flood protection",
            ),
            _product(
                "Warehouse Receipt System", "government",
                "Store harvest and get a loan against it",
                "Sell when prices are high, not when desperate after harvest",
                "KSh 10,000 - 500,000", "8-12% p.a.",
                "Post-harvest price optimization",
            ),
        ],
        common_challenges=[
            "Weather dependency — drought or excess rain destroys crops",
            "Post-harvest losses — 20-30% of produce lost to poor storage",
            "Price exploitation by middlemen at farm gate",
            "High input costs — seeds, fertilizer, pesticides",
            "Land insecurity — many farm on rented or ancestral land",
            "Pest and disease outbreaks (fall armyworm, locusts)",
            "Lack of storage and cold chain infrastructure",
            "Market access — getting produce to buyers",
        ],
        success_tips=[
            "Diversify crops — don't plant only one thing",
            "Join a farmers' cooperative for bulk input buying and market access",
            "Invest in proper storage — a simple granary reduces post-harvest loss by 50%",
            "Time your sales — don't sell immediately after harvest when prices are lowest",
            "Learn about weather patterns and plant accordingly",
            "Keep records of every season — costs, yields, prices — to learn what works",
            "Consider drip irrigation for water efficiency",
            "Add value where possible — dry, mill, or package your produce",
        ],
        seasonal_insights=[
            "January-February: Short rains harvest — sell or store maize/beans",
            "March-April: Long rains planting season — buy inputs, prepare land",
            "May-June: Growing season — weeding, spraying, no income",
            "July-August: Long rains harvest — maize, beans ready",
            "September-October: Short rains planting — another cycle begins",
            "November-December: Growing season or early harvest depending on crop",
        ],
        price_benchmarks={
            "maize_90kg_bag": 3000,
            "beans_90kg_bag": 6000,
            "rice_90kg_bag": 8000,
            "potato_50kg_bag": 2000,
            "tomato_crate": 1500,
            "fertilizer_50kg": 3500,
            "seed_maize_10kg": 1200,
            "pesticide_1l": 800,
        },
        swahili_terms={
            "mkulima": "Farmer",
            "shamba": "Farm / field",
            "mazao": "Crops / produce",
            "mbegu": "Seeds",
            "mbolea": "Fertilizer",
            "dawa": "Pesticide / medicine",
            "mavuno": "Harvest",
            "soko": "Market",
            "wakulima": "Farmers (plural)",
        },
        conversation_starters=[
            "Mavuno yako yamekuwaje? (How was your harvest?)",
            "Umeuza wapi mazao yako? (Where did you sell your produce?)",
            "Bei ya soko ni ngapi? (What's the market price?)",
            "Umezungumza na SACCO? (Have you talked to the SACCO?)",
        ],
    )


def _profile_changaa_brewer() -> WorkerProfile:
    return WorkerProfile(
        type_id="changaa_brewer",
        name="Busaa / Chang'aa Brewer",
        name_sw="Mtu wa Busaa",
        description="Traditional brewer of busaa, chang'aa, or other local beverages",
        sector=WorkerSector.FOOD,
        icon="🍺",
        income=IncomeRange(low=300, average=1000, high=3000, peak=5000),
        operating_costs=OperatingCosts(
            rent=100, stock=800, transport=100, utilities=50,
            labor=200, licenses=0, other=100,
        ),
        startup_cost=10_000,
        break_even_days=14,
        risk_level=RiskLevel.HIGH,
        seasonality=SeasonalityPattern.FESTIVAL_DRIVEN,
        peak_months=[1, 4, 8, 12],
        slow_months=[5, 6, 7],
        typical_hours="10 AM - 10 PM",
        working_days_per_week=7,
        location_type="home",
        requires_stock=True,
        requires_equipment=True,
        requires_license=False,
        key_metrics=[
            _metric("daily_sales", "Daily revenue", "KSh", 2000, 1000, 300),
            _metric("litres_sold", "Litres sold per day", "litres", 30, 15, 5),
            _metric("production_cost", "Cost per litre to produce", "KSh", 30, 50, 80),
            _metric("profit_per_litre", "Profit margin per litre", "KSh", 70, 50, 20),
            _metric("customer_count", "Daily customers", "count", 30, 15, 5),
            _metric("spoilage", "Litres lost to spoilage", "litres", 0, 2, 10),
        ],
        what_to_track=[
            "Raw material costs (millet, maize, yeast, sugar)",
            "Production volume and timeline",
            "Daily sales revenue",
            "Customer count and preferences",
            "Spoilage and production losses",
            "Regulatory risk (county enforcement)",
            "Credit given to customers",
            "Seasonal demand patterns",
        ],
        financial_products=[
            _product(
                "M-Pesa Savings", "mobile",
                "Daily savings from cash sales",
                "High cash business — save before you spend",
                "KSh 100 - 10,000", "5-8% p.a.",
                "Emergency fund, school fees",
            ),
            _product(
                "Chama", "chama",
                "Group savings circle",
                "Pool resources for bulk raw material purchase",
                "KSh 500 - 10,000/month", "N/A",
                "Bulk buying, community support",
            ),
        ],
        common_challenges=[
            "Legal ambiguity — traditional brewing occupies a grey area",
            "Quality control — inconsistent batches lose customers",
            "County enforcement and potential confiscation",
            "Health and safety standards",
            "Customer intoxication issues and liability",
            "Raw material price fluctuations",
            "Competition from commercial brands",
            "Community stigma in some areas",
        ],
        success_tips=[
            "Consistency is king — same taste every time keeps customers",
            "Maintain cleanliness — word spreads fast about hygiene",
            "Build a loyal customer base through quality and fair pricing",
            "Diversify into other beverages (mursik, mnazi) if possible",
            "Save aggressively — this income is unpredictable",
            "Keep production quantities manageable — don't overproduce",
        ],
        seasonal_insights=[
            "January: Post-holiday celebrations — high demand",
            "March-April: Easter period — moderate demand",
            "May-June: Rainy season — fewer customers visiting",
            "July-August: Cold season — warm busaa in demand",
            "September-October: Moderate",
            "November-December: Festive peak — celebrations drive demand",
        ],
        price_benchmarks={
            "busaa_1l": 80,
            "changaa_250ml": 50,
            "millet_1kg": 120,
            "maize_flour_1kg": 80,
            "sugar_1kg": 180,
            "yeast_packet": 50,
        },
        swahili_terms={
            "busaa": "Traditional millet beer",
            "chang'aa": "Traditional spirit (historically dangerous, now regulated)",
            "mnazi": "Palm wine",
            "mursik": "Kalenjin fermented milk",
            "jiko": "Brewing setup",
            "sufuria": "Pot for brewing",
        },
        conversation_starters=[
            "Leo umeuza ngapi? (How much did you sell today?)",
            "Bei ya mahindi imepanda? (Did maize prices go up?)",
        ],
    )


def _profile_boda_mechanic() -> WorkerProfile:
    return WorkerProfile(
        type_id="boda_mechanic",
        name="Boda Boda Mechanic",
        name_sw="Mekaniki wa Boda Boda",
        description="Motorcycle mechanic specializing in boda boda repair and maintenance",
        sector=WorkerSector.SERVICES,
        icon="🔩",
        income=IncomeRange(low=300, average=700, high=1500, peak=3000),
        operating_costs=OperatingCosts(
            rent=200, stock=500, transport=50, utilities=30,
            labor=0, licenses=20, other=50,
        ),
        startup_cost=20_000,
        break_even_days=45,
        risk_level=RiskLevel.LOW,
        seasonality=SeasonalityPattern.WEATHER_DRIVEN,
        peak_months=[3, 7, 11],     # After rains (damage repairs)
        slow_months=[1, 5, 9],
        typical_hours="7 AM - 6 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=True,
        requires_license=False,
        key_metrics=[
            _metric("daily_revenue", "Daily repair revenue", "KSh", 1200, 700, 200),
            _metric("jobs_completed", "Repairs done per day", "count", 6, 3, 1),
            _metric("average_job_value", "Average repair charge", "KSh", 300, 200, 100),
            _metric("parts_margin", "Profit from parts sold", "KSh", 300, 150, 0),
            _metric("customer_count", "Unique riders served per day", "count", 6, 3, 1),
            _metric("comeback_rate", "Returns due to bad repair", "%", 2, 5, 15, "monthly"),
        ],
        what_to_track=[
            "Types of repairs done (engine, electrical, body, tyres)",
            "Parts used and their cost vs charge",
            "Customer count and repeat rate",
            "Time per repair job",
            "Parts inventory levels",
            "Revenue from parts vs labor",
            "Best customers (frequent riders)",
        ],
        financial_products=[
            _product(
                "Tool Loan", "mfi",
                "Micro-loan for specialized tools",
                "Better tools = more repair types = more income",
                "KSh 5,000 - 50,000", "10-15% p.a.",
                "Tool and equipment upgrade",
            ),
            _product(
                "Spare Parts Credit", "supplier",
                "Buy-now-pay-later from parts distributors",
                "Stock common parts without full cash outlay",
                "KSh 5,000 - 50,000", "0-5% per month",
                "Parts inventory",
            ),
        ],
        common_challenges=[
            "Fake/counterfeit spare parts flood the market",
            "Customers want cheap fixes that won't last",
            "Rainy season creates backlog of repair jobs",
            "Keeping up with new motorcycle models",
            "Parts sourcing delays for uncommon models",
            "Customers disputing repair quality",
            "Physical strain — bending, lifting heavy parts",
        ],
        success_tips=[
            "Stock common parts: brake pads, clutch plates, chains, spark plugs",
            "Learn to diagnose quickly — riders want fast turnaround",
            "Offer fair pricing — reputation spreads by word of mouth",
            "Keep a clean, organized workspace — it builds trust",
            "Learn electrical repair — many mechanics can't do it",
            "Build relationships with parts suppliers for better prices",
            "Offer mobile repair for breakdowns — premium pricing opportunity",
        ],
        seasonal_insights=[
            "January-February: Moderate demand, post-holiday repairs",
            "March-April: Rain damage repairs begin — high demand",
            "May-June: Peak repair season — water damage, mud clogging",
            "July-August: Moderate — routine maintenance",
            "September: Pre-rain maintenance rush",
            "October-November: Moderate demand",
            "December: Some holiday prep repairs",
        ],
        price_benchmarks={
            "oil_change": 500,
            "brake_repair": 800,
            "chain_replacement": 1500,
            "engine_service": 2000,
            "tyre_change": 1500,
            "electrical_diagnosis": 500,
            "carburetor_clean": 400,
            "suspension_repair": 1500,
        },
        swahili_terms={
            "mekaniki": "Mechanic",
            "sehemu": "Parts / spare parts",
            "injini": "Engine",
            "breki": "Brakes",
            "tai": "Tyre",
            "mnyororo": "Chain",
            "mafuta": "Oil / fuel",
            "kuchunguza": "To diagnose / inspect",
        },
        conversation_starters=[
            "Leo kazi gani umefanya? (What jobs did you do today?)",
            "Sehemu zipi unahitaji? (Which parts do you need?)",
            "Bei ya sehemu imepanda? (Have part prices gone up?)",
        ],
    )


def _profile_charcoal_seller() -> WorkerProfile:
    return WorkerProfile(
        type_id="charcoal_seller",
        name="Charcoal Seller",
        name_sw="Muuzaji wa Mkaa",
        description="Charcoal dealer selling cooking fuel to households and food vendors",
        sector=WorkerSector.ENERGY,
        icon="⬛",
        income=IncomeRange(low=200, average=500, high=1200, peak=2500),
        operating_costs=OperatingCosts(
            rent=150, stock=1000, transport=300, utilities=20,
            labor=0, licenses=30, other=50,
        ),
        startup_cost=10_000,
        break_even_days=30,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.WEATHER_DRIVEN,
        peak_months=[4, 5, 6, 7, 8],   # Rainy/cold — more cooking at home
        slow_months=[1, 2, 9, 10],
        typical_hours="6 AM - 6 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=False,
        requires_license=True,
        key_metrics=[
            _metric("daily_sales", "Daily revenue", "KSh", 800, 500, 200),
            _metric("bags_sold", "Bags of charcoal sold", "count", 5, 3, 1),
            _metric("profit_per_bag", "Profit margin per bag", "KSh", 100, 150, 200),
            _metric("transport_cost", "Transport cost per delivery", "KSh", 300, 200, 100),
            _metric("stock_level", "Bags in stock", "count", 30, 15, 3),
            _metric("customer_count", "Daily customers", "count", 8, 4, 1),
        ],
        what_to_track=[
            "Bags purchased and sold daily",
            "Wholesale price per bag from producers",
            "Transport costs (from production site to selling point)",
            "Customer count and buying frequency",
            "Stock levels and reorder timing",
            "Credit given to customers",
            "Seasonal demand patterns",
        ],
        financial_products=[
            _product(
                "Stock Loan", "mfi",
                "Short-term loan for bulk charcoal purchase",
                "Buy in bulk at lower wholesale prices",
                "KSh 5,000 - 50,000", "5-10% per month",
                "Bulk stock purchases",
            ),
            _product(
                "M-Pesa Savings", "mobile",
                "Daily savings from cash sales",
                "Steady daily sales support regular saving",
                "KSh 50 - 5,000", "5-8% p.a.",
                "Emergency fund",
            ),
        ],
        common_challenges=[
            "Transport costs are high — charcoal is heavy and bulky",
            "Environmental regulations tightening on charcoal trade",
            "Quality varies — wet or poorly burned charcoal loses customers",
            "Storage losses from rain and moisture",
            "Competition from gas and electricity alternatives",
            "Price fluctuations based on supply from rural areas",
            "Physical labor — loading and unloading heavy bags",
        ],
        success_tips=[
            "Build relationships with charcoal producers for consistent supply",
            "Sell in different bag sizes — 1kg, 5kg, 10kg, 50kg",
            "Keep stock dry — moisture ruins charcoal quality",
            "Deliver to loyal customers for a small fee — builds loyalty",
            "Buy in bulk during dry season when supply is high and prices low",
            "Complementary products: matchboxes, jikos, cooking oil",
        ],
        seasonal_insights=[
            "January-February: Moderate demand",
            "March-April: Rain begins — demand increases as people cook more at home",
            "May-June: Peak demand — rainy season, cold weather",
            "July-August: High demand continues — cold season",
            "September: Demand starts to moderate",
            "October-November: Moderate",
            "December: Festive cooking increases demand temporarily",
        ],
        price_benchmarks={
            "charcoal_50kg_bag": 1200,
            "charcoal_5kg": 150,
            "charcoal_1kg": 40,
            "transport_per_bag": 100,
            "jiko_simple": 500,
            "matchbox": 10,
        },
        swahili_terms={
            "mkaa": "Charcoal",
            "jiko": "Stove / charcoal stove",
            "gunia": "Sack / bag",
            "kuni": "Firewood",
            "mkaa mzuri": "Good quality charcoal",
        },
        conversation_starters=[
            "Leo umepata wangapi? (How much did you make today?)",
            "Bei ya mkaa imepanda? (Have charcoal prices gone up?)",
            "Stock imetosha? (Is stock sufficient?)",
        ],
    )


def _profile_water_vendor() -> WorkerProfile:
    return WorkerProfile(
        type_id="water_vendor",
        name="Water Vendor",
        name_sw="Muuzaji wa Maji",
        description="Water delivery service — selling treated or borehole water to households",
        sector=WorkerSector.ENERGY,
        icon="💧",
        income=IncomeRange(low=200, average=600, high=1500, peak=3000),
        operating_costs=OperatingCosts(
            rent=100, stock=0, transport=300, utilities=50,
            labor=200, licenses=50, other=50,
        ),
        startup_cost=15_000,
        break_even_days=30,
        risk_level=RiskLevel.LOW,
        seasonality=SeasonalityPattern.WEATHER_DRIVEN,
        peak_months=[1, 2, 8, 9],    # Dry seasons
        slow_months=[4, 5, 6],        # Rainy — people collect rainwater
        typical_hours="6 AM - 6 PM",
        working_days_per_week=7,
        location_type="mobile",
        requires_stock=False,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_revenue", "Daily sales", "KSh", 1000, 600, 200),
            _metric("litres_delivered", "Total litres delivered", "litres", 2000, 1000, 300),
            _metric("trips_completed", "Delivery trips", "count", 6, 3, 1),
            _metric("customers_served", "Households served", "count", 20, 10, 3),
            _metric("cost_per_litre", "Cost to source and deliver per litre", "KSh", 1, 2, 4),
            _metric("profit_per_trip", "Net profit per delivery trip", "KSh", 200, 150, 50),
        ],
        what_to_track=[
            "Litres delivered per trip and per day",
            "Number of customers and delivery frequency",
            "Water source cost (borehole, treated, purchased)",
            "Transport costs (cart, bicycle, motorbike)",
            "Container/jerry can inventory",
            "Customer payment patterns (daily, weekly, monthly)",
            "Dry season vs rainy season volumes",
        ],
        financial_products=[
            _product(
                "Equipment Loan", "mfi",
                "Loan for water tank, cart, or bicycle",
                "Better transport = more deliveries = more income",
                "KSh 5,000 - 30,000", "10-15% p.a.",
                "Transport equipment",
            ),
            _product(
                "SACCO Savings", "sacco",
                "Regular savings from daily income",
                "Consistent income supports regular saving",
                "KSh 200 - 5,000/month", "8-12% p.a.",
                "Long-term savings",
            ),
        ],
        common_challenges=[
            "Water source contamination and quality control",
            "Dry seasons increase demand but also source scarcity",
            "Rainy seasons reduce demand significantly",
            "Physical strain of carrying/delivering water",
            "Competition from piped water connections",
            "Customer payment delays",
            "Container theft and damage",
        ],
        success_tips=[
            "Build a delivery route — same customers, same times, reliable service",
            "Invest in a water tank for storage during dry spells",
            "Offer weekly/monthly payment plans for regular customers",
            "Ensure water quality — one contamination incident ruins reputation",
            "Sell clean water at a premium — treated water commands higher prices",
            "Add value: deliver to door, not just to the road",
        ],
        seasonal_insights=[
            "January-February: Dry season peak — highest demand",
            "March-April: Long rains begin — demand starts dropping",
            "May-June: Rainy peak — people collect rainwater, low demand",
            "July-August: Demand recovers as rains ease",
            "September-October: Dry season returns — demand increases",
            "November-December: Short rains reduce demand somewhat",
        ],
        price_benchmarks={
            "water_20l_jerrycan": 50,
            "water_1l_bottle": 20,
            "delivery_fee": 30,
            "tank_1000l": 8000,
            "jerrycan": 300,
        },
        swahili_terms={
            "maji": "Water",
            "maji safi": "Clean water",
            "maji ya kunywa": "Drinking water",
            "jerry can": "Container for water",
            "tank": "Water storage tank",
            "delivery": "Kuleta — to deliver",
        },
        conversation_starters=[
            "Leo umetoa maji ngapi? (How much water did you deliver today?)",
            "Wateja wako wangapi? (How many customers do you have?)",
            "Maji yako ni safi? (Is your water clean?)",
        ],
    )


def _profile_shoe_shiner() -> WorkerProfile:
    return WorkerProfile(
        type_id="shoe_shiner",
        name="Shoe Shiner",
        name_sw="Mtu wa Kupulishia Viatu",
        description="Street shoe cleaning and polishing service provider",
        sector=WorkerSector.SERVICES,
        icon="👞",
        income=IncomeRange(low=100, average=300, high=600, peak=1000),
        operating_costs=OperatingCosts(
            rent=0, stock=100, transport=30, utilities=0,
            labor=0, licenses=0, other=20,
        ),
        startup_cost=1_000,
        break_even_days=5,
        risk_level=RiskLevel.LOW,
        seasonality=SeasonalityPattern.WEATHER_DRIVEN,
        peak_months=[1, 7, 8, 12],
        slow_months=[4, 5, 6],
        typical_hours="7 AM - 6 PM",
        working_days_per_week=6,
        location_type="mobile",
        requires_stock=True,
        requires_equipment=True,
        requires_license=False,
        key_metrics=[
            _metric("daily_earnings", "Daily tips and charges", "KSh", 500, 300, 100),
            _metric("shoes_polished", "Number of shoes cleaned", "count", 15, 8, 3),
            _metric("average_charge", "Average charge per pair", "KSh", 50, 40, 20),
            _metric("best_location", "Highest earning spot", "text", None, None, None, "weekly"),
            _metric("product_cost", "Daily polish and supplies cost", "KSh", 50, 30, 10),
            _metric("repeat_customers", "Returning clients per week", "count", 5, 2, 0, "weekly"),
        ],
        what_to_track=[
            "Daily earnings (charges + tips)",
            "Number of shoes polished",
            "Location performance",
            "Supplies cost (polish, brushes, rags)",
            "Weather impact on business",
            "Best times of day for customers",
            "Regular customer schedules",
        ],
        financial_products=[
            _product(
                "M-Pesa Savings", "mobile",
                "Micro-savings from daily tips",
                "Even small daily savings add up over time",
                "KSh 20 - 1,000", "5-8% p.a.",
                "Emergency fund, tools upgrade",
            ),
        ],
        common_challenges=[
            "Rainy season destroys business — wet shoes can't be polished",
            "Low barriers to entry — many competitors",
            "Physical discomfort — kneeling, bending all day",
            "Location security — some areas have hostile security guards",
            "Supplies cost erodes thin margins",
            "No social protections or benefits",
            "Customer volume is unpredictable",
        ],
        success_tips=[
            "Position near office buildings, banks, courts — men in formal shoes",
            "Morning hours (7-9 AM) are gold — people want shoes polished before work",
            "Offer quick-dry techniques for rainy days",
            "Build relationships with regulars — they come every week",
            "Carry business cards (yes, even shoe shiners benefit)",
            "Invest in quality polish — better results, faster work",
            "Save at least KSh 20 daily — build an emergency fund",
        ],
        seasonal_insights=[
            "January: Back to work — good demand",
            "February-March: Steady",
            "April-May: Long rains — very difficult, shoes get muddy but can't polish wet shoes",
            "June-July: Cold and dry — moderate demand",
            "August: Moderate",
            "September: Good — dry season",
            "October-November: Mixed with short rains",
            "December: Festive — people dress up, good demand",
        ],
        price_benchmarks={
            "shoe_polish_tin": 100,
            "brush": 150,
            "rag": 50,
            "shoe_polish_per_pair": 40,
            "leather_conditioner": 200,
        },
        swahili_terms={
            "viatu": "Shoes",
            "kupulisha": "To polish / shine",
            "brashi": "Brush",
            "dawa ya viatu": "Shoe polish",
            "mswaki": "Toothbrush (also used for shoe cleaning details)",
        },
        conversation_starters=[
            "Leo umepata wangapi? (How much did you earn today?)",
            "Wapi pa kazi ni bora? (Where is the best working spot?)",
        ],
    )


def _profile_watchman() -> WorkerProfile:
    return WorkerProfile(
        type_id="watchman",
        name="Watchman / Security Guard",
        name_sw="Mlinzi",
        description="Private security guard providing night watch and property protection",
        sector=WorkerSector.SERVICES,
        icon="🛡️",
        income=IncomeRange(low=200, average=400, high=600, peak=800),
        operating_costs=OperatingCosts(
            rent=0, stock=0, transport=100, utilities=0,
            labor=0, licenses=0, other=30,
        ),
        startup_cost=0,
        break_even_days=0,
        risk_level=RiskLevel.HIGH,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[12],            # December — theft increases
        slow_months=[],
        typical_hours="6 PM - 6 AM",
        working_days_per_week=6,
        location_type="client_site",
        requires_stock=False,
        requires_equipment=False,
        requires_license=False,
        key_metrics=[
            _metric("monthly_salary", "Monthly take-home pay", "KSh", 12000, 8000, 6000, "monthly"),
            _metric("overtime_hours", "Extra hours worked", "hours", 20, 10, 0, "monthly"),
            _metric("incidents_reported", "Security incidents logged", "count", 3, 1, 0, "monthly"),
            _metric("side_income", "Extra income from tips, errands", "KSh", 2000, 500, 0, "monthly"),
        ],
        what_to_track=[
            "Salary payments and any delays",
            "Overtime hours and pay",
            "Side income from the job (tips, errands for residents)",
            "Safety incidents at the work site",
            "Personal safety expenses (flashlight, warm clothing)",
            "Savings from salary",
            "Other income-generating activities during off-hours",
        ],
        financial_products=[
            _product(
                "SACCO Savings", "sacco",
                "Regular salary-based savings",
                "Fixed salary makes regular saving possible",
                "KSh 500 - 3,000/month", "8-12% p.a.",
                "Land purchase, school fees, business startup",
            ),
            _product(
                "NHIF", "government",
                "Health insurance",
                "Night work and physical risk — health cover is critical",
                "KSh 500/month", "N/A",
                "Medical emergencies",
            ),
            _product(
                "Emergency Loan", "mfi",
                "Quick access to small loans for emergencies",
                "Low salary means no buffer for unexpected expenses",
                "KSh 1,000 - 10,000", "10-15% per month",
                "Medical, family emergencies",
            ),
        ],
        common_challenges=[
            "Very low pay relative to risk and hours worked",
            "Night shifts destroy health and social life",
            "Physical danger — confronting thieves, dog attacks",
            "No overtime pay in many cases",
            "Isolation and loneliness during night shifts",
            "Exposure to cold and weather",
            "Limited career progression",
            "Delayed salary payments from security companies",
        ],
        success_tips=[
            "Use day hours for skill building or side business",
            "Save at least KSh 1,000/month — even on low salary",
            "Learn a trade during off-hours (fundi skills, driving, etc.)",
            "Network with residents — they may offer better-paying opportunities",
            "Keep records of all salary payments and any unpaid overtime",
            "Join NHIF — medical emergencies can bankrupt you",
        ],
        seasonal_insights=[
            "Year-round: Demand is relatively stable",
            "December: Peak demand — holiday season, more property to protect",
            "Election periods: Increased demand for security",
        ],
        price_benchmarks={
            "average_monthly_salary": 8000,
            "flashlight": 300,
            "warm_jacket": 1000,
            "whistle": 50,
        },
        swahili_terms={
            "mlinzi": "Guard / watchman",
            "usalama": "Security / safety",
            "wizi": "Theft",
            "kichakani": "On patrol",
            "usalama wa usiku": "Night security",
        },
        conversation_starters=[
            "Mshahara umelipwa? (Have you been paid?)",
            "Kuna kitu kilifanyika usiku? (Anything happen last night?)",
            "Unafanya kazi ya ziada wapi? (Where do you do extra work?)",
        ],
    )


def _profile_laundry_mama() -> WorkerProfile:
    return WorkerProfile(
        type_id="laundry_mama",
        name="Laundry Mama",
        name_sw="Mama wa Kufulia",
        description="Professional washerwoman providing laundry and ironing services",
        sector=WorkerSector.SERVICES,
        icon="🫧",
        income=IncomeRange(low=200, average=500, high=1000, peak=1500),
        operating_costs=OperatingCosts(
            rent=0, stock=200, transport=100, utilities=100,
            labor=0, licenses=0, other=30,
        ),
        startup_cost=2_000,
        break_even_days=7,
        risk_level=RiskLevel.LOW,
        seasonality=SeasonalityPattern.WEATHER_DRIVEN,
        peak_months=[1, 7, 8, 12],
        slow_months=[4, 5, 6],
        typical_hours="7 AM - 5 PM",
        working_days_per_week=6,
        location_type="client_site",
        requires_stock=True,
        requires_equipment=False,
        requires_license=False,
        key_metrics=[
            _metric("daily_earnings", "Daily income", "KSh", 700, 500, 200),
            _metric("loads_washed", "Number of laundry loads", "count", 5, 3, 1),
            _metric("charge_per_load", "Average charge per load", "KSh", 200, 150, 100),
            _metric("clients_served", "Regular clients", "count", 8, 4, 1, "weekly"),
            _metric("soap_cost", "Daily soap and supplies", "KSh", 100, 60, 30),
            _metric("repeat_rate", "Client retention rate", "%", 80, 60, 30, "monthly"),
        ],
        what_to_track=[
            "Number of loads washed daily",
            "Charge per load and total daily earnings",
            "Soap, water, and transport costs",
            "Client list and payment schedules",
            "Weather impact (rain delays drying)",
            "Seasonal demand changes",
            "Additional services (ironing, folding)",
        ],
        financial_products=[
            _product(
                "M-Pesa Savings", "mobile",
                "Daily micro-savings",
                "Steady client income supports regular saving",
                "KSh 50 - 2,000", "5-8% p.a.",
                "Emergency fund, equipment",
            ),
            _product(
                "Chama", "chama",
                "Women's savings group",
                "Network for referrals and financial support",
                "KSh 500 - 5,000/month", "N/A",
                "Bulk soap buying, emergency fund",
            ),
        ],
        common_challenges=[
            "Rain disrupts drying — delays service delivery",
            "Soap and water costs add up",
            "Physical strain — hand washing is exhausting",
            "Client disputes over damaged or lost items",
            "Inconsistent income — clients may skip weeks",
            "Seasonal fluctuations — fewer clients during rainy season",
            "Competition from laundromats and washing machines",
        ],
        success_tips=[
            "Build a loyal client base — regulars provide predictable income",
            "Invest in a simple iron — ironing triples your charge per item",
            "Offer weekly packages — guaranteed income",
            "Return clothes neatly folded — presentation matters",
            "Use WhatsApp to coordinate pickups and deliveries",
            "Save for a hand cart to transport more laundry per trip",
        ],
        seasonal_insights=[
            "January-February: Good — back to work, school uniforms needed",
            "March-April: Steady, but rain starts to affect drying",
            "May-June: Rainy peak — very challenging for drying",
            "July-August: Cold season — clothes take longer to dry",
            "September: Improving as dry season approaches",
            "October-November: Good season",
            "December: Festive — extra laundry from celebrations",
        ],
        price_benchmarks={
            "wash_load": 150,
            "iron_per_item": 30,
            "soap_bar": 50,
            "bleach_500ml": 100,
            "weekly_package": 500,
        },
        swahili_terms={
            "kufua": "To wash clothes",
            "kufulia": "To wash for someone (professional)",
            "kupiga pasi": "To iron",
            "sabuni": "Soap",
            "maji": "Water",
            "nguo": "Clothes",
            "kukausha": "To dry",
        },
        conversation_starters=[
            "Leo umeosha nguo za nani? (Whose clothes did you wash today?)",
            "Mvua ilikuathiri? (Did the rain affect you?)",
            "Una wateja wangapi? (How many clients do you have?)",
        ],
    )


def _profile_smokie_vendor() -> WorkerProfile:
    return WorkerProfile(
        type_id="smokie_vendor",
        name="Smokie / Smocha Vendor",
        name_sw="Muuzaji wa Smocha",
        description="Processed food vendor selling smokies, smochas, boiled eggs, and sausages",
        sector=WorkerSector.FOOD,
        icon="🌭",
        income=IncomeRange(low=200, average=500, high=1000, peak=2000),
        operating_costs=OperatingCosts(
            rent=100, stock=500, transport=80, utilities=50,
            labor=0, licenses=30, other=30,
        ),
        startup_cost=5_000,
        break_even_days=14,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[1, 5, 9, 12],
        slow_months=[6, 7],
        typical_hours="10 AM - 9 PM",
        working_days_per_week=6,
        location_type="mobile",
        requires_stock=True,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_sales", "Daily revenue", "KSh", 800, 500, 200),
            _metric("items_sold", "Total items sold", "count", 40, 20, 8),
            _metric("profit_margin", "Profit as % of sales", "%", 40, 30, 20, "weekly"),
            _metric("waste_rate", "Items unsold/expired", "%", 5, 10, 25),
            _metric("best_seller", "Top selling item", "text", None, None, None),
            _metric("location_score", "Performance by location", "KSh", 800, 500, 200, "weekly"),
        ],
        what_to_track=[
            "Items sold per day by type (smokie, smocha, egg, sausage)",
            "Revenue and profit per item type",
            "Stock purchases and supplier prices",
            "Waste (unsold items at end of day)",
            "Location performance comparison",
            "Sauce and accompaniment costs",
            "Customer preferences",
        ],
        financial_products=[
            _product(
                "M-Pesa Savings", "mobile",
                "Daily savings from sales",
                "Consistent daily sales support regular saving",
                "KSh 50 - 3,000", "5-8% p.a.",
                "Emergency fund",
            ),
            _product(
                "Micro-loan for Stock", "mfi",
                "Quick loan for restocking",
                "Never run out of stock — daily sales depend on daily stock",
                "KSh 2,000 - 20,000", "5-10% per month",
                "Stock capital",
            ),
        ],
        common_challenges=[
            "Perishable stock — smokies and smochas expire",
            "Kanjo harassment at selling locations",
            "Competition from other vendors at the same spot",
            "Rain reduces customer traffic significantly",
            "Supplier price increases (Meatco, local manufacturers)",
            "Food safety compliance — county health inspections",
            "Limited locations with good foot traffic",
        ],
        success_tips=[
            "Buy only what you can sell in one day — minimize waste",
            "Position near schools, bus stops, or offices at lunch time",
            "Offer kachumbari (salsa) and sauce as value-add",
            "Keep a clean and appetizing display",
            "Know your daily customer count and buy accordingly",
            "Rotate locations — morning near offices, evening near residential",
            "Use M-Pesa for sales tracking",
        ],
        seasonal_insights=[
            "January: School opening — students are major customers",
            "February-March: Steady demand",
            "April-May: Moderate — Easter holiday",
            "June-July: Cold season — warm smokies sell better",
            "August-September: Back to school — strong demand",
            "October-November: Moderate",
            "December: Festive — parties and gatherings boost sales",
        ],
        price_benchmarks={
            "smokie_each": 30,
            "smocha_each": 40,
            "boiled_egg": 30,
            "sausage_each": 50,
            "kachumbari_portion": 10,
            "sauce_portion": 10,
        },
        swahili_terms={
            "smokie": "Processed sausage (small)",
            "smocha": "Smoked sausage (larger)",
            "kachumbari": "Fresh tomato-onion salsa",
            "mayai ya kuchemsha": "Boiled eggs",
            "sosi": "Sauce / ketchup",
        },
        conversation_starters=[
            "Leo umepata wangapi? (How much did you make today?)",
            "Ni kitu gani kinauzika? (What's selling best?)",
            "Umepata wapi smokies? (Where did you get the smokies?)",
        ],
    )


def _profile_eggs_ndizi_vendor() -> WorkerProfile:
    return WorkerProfile(
        type_id="eggs_ndizi_vendor",
        name="Eggs & Ndizi Vendor",
        name_sw="Muuzaji wa Mayai na Ndizi",
        description="Vendor specializing in eggs, bananas (ndizi), and related produce",
        sector=WorkerSector.FOOD,
        icon="🥚",
        income=IncomeRange(low=150, average=400, high=800, peak=1500),
        operating_costs=OperatingCosts(
            rent=80, stock=600, transport=100, utilities=10,
            labor=0, licenses=20, other=20,
        ),
        startup_cost=5_000,
        break_even_days=14,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[1, 5, 9, 12],
        slow_months=[6, 7],
        typical_hours="6 AM - 6 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=False,
        requires_license=True,
        key_metrics=[
            _metric("daily_sales", "Daily revenue", "KSh", 600, 400, 150),
            _metric("trays_sold", "Egg trays sold per day", "count", 4, 2, 0),
            _metric("bunches_sold", "Banana bunches sold", "count", 3, 2, 0),
            _metric("breakage_rate", "Eggs broken in handling", "%", 2, 5, 10),
            _metric("spoilage", "Bananas spoiling before sale", "%", 3, 8, 15),
            _metric("profit_margin", "Net margin", "%", 30, 22, 12, "weekly"),
        ],
        what_to_track=[
            "Egg trays purchased and sold",
            "Banana bunches purchased and sold",
            "Breakage and spoilage rates",
            "Wholesale prices from suppliers",
            "Customer buying patterns",
            "Price fluctuations in the market",
        ],
        financial_products=[
            _product(
                "M-Pesa Savings", "mobile",
                "Daily micro-savings",
                "Regular daily sales support small consistent savings",
                "KSh 50 - 2,000", "5-8% p.a.",
                "Emergency fund",
            ),
            _product(
                "Chama", "chama",
                "Group savings for bulk buying",
                "Pool capital for wholesale egg and banana purchases",
                "KSh 500 - 5,000/month", "N/A",
                "Stock capital",
            ),
        ],
        common_challenges=[
            "Egg breakage during transport — each broken egg is lost money",
            "Banana spoilage — ripe bananas must sell same day",
            "Price fluctuations at wholesale markets",
            "Competition from supermarkets selling eggs cheaper",
            "Storage — eggs need careful handling, bananas need ventilation",
            "Seasonal supply variations",
        ],
        success_tips=[
            "Buy eggs in trays (30 eggs) for better wholesale pricing",
            "Store bananas in shade with good ventilation — they last longer",
            "Sell ripe bananas at a discount before they spoil",
            "Position near residential areas — daily shopping patterns",
            "Complementary products: bread, tomatoes, cooking oil",
            "Keep eggs in a sturdy container — breakage kills margins",
        ],
        seasonal_insights=[
            "Year-round: Eggs and bananas have relatively stable demand",
            "School terms: Higher demand for breakfast items",
            "Festive seasons: Baking demand increases egg sales",
            "Rainy seasons: Transport challenges, higher breakage risk",
        ],
        price_benchmarks={
            "egg_tray_30": 380,
            "egg_single": 15,
            "banana_bunch": 200,
            "banana_single": 10,
            "ndizi_kg": 80,
        },
        swahili_terms={
            "mayai": "Eggs",
            "ndizi": "Bananas (cooking bananas)",
            "tray": "Egg tray (30 eggs)",
            "bunch": "Mkono — banana bunch",
            "kombe": "Ripe banana",
        },
        conversation_starters=[
            "Leo mayai yameuzika? (Did the eggs sell today?)",
            "Ndizi zimeiva sana? (Are the bananas very ripe?)",
            "Bei ya mayai imepanda? (Have egg prices gone up?)",
        ],
    )


def _profile_cyber_print() -> WorkerProfile:
    return WorkerProfile(
        type_id="cyber_print",
        name="Cyber Cafe / Print Shop",
        name_sw="Cyber",
        description="Internet cafe and printing/photocopying business",
        sector=WorkerSector.DIGITAL,
        icon="🖨️",
        income=IncomeRange(low=300, average=800, high=2000, peak=4000),
        operating_costs=OperatingCosts(
            rent=500, stock=300, transport=50, utilities=500,
            labor=300, licenses=100, other=100,
        ),
        startup_cost=200_000,
        break_even_days=180,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.SCHOOL_DRIVEN,
        peak_months=[1, 4, 5, 9],
        slow_months=[7, 8, 12],
        typical_hours="8 AM - 8 PM",
        working_days_per_week=7,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_revenue", "Daily total revenue", "KSh", 1500, 800, 300),
            _metric("print_pages", "Pages printed/copied per day", "count", 200, 100, 30),
            _metric("internet_sessions", "Internet browsing sessions", "count", 30, 15, 5),
            _metric("paper_usage", "Reams of paper used per day", "count", 2, 1, 0),
            _metric("ink_cost", "Daily ink/toner cost", "KSh", 200, 150, 50),
            _metric("utilization", "% of computers in use at peak", "%", 80, 50, 20),
        ],
        what_to_track=[
            "Print/copy jobs by type (B&W, color, binding, scanning)",
            "Internet session hours and revenue",
            "Paper and ink consumption vs revenue",
            "Peak hours and customer flow",
            "Equipment maintenance costs",
            "Additional services (CV writing, KRA filing, registration)",
            "Customer types (students, job seekers, businesses)",
        ],
        financial_products=[
            _product(
                "Asset Finance", "bank",
                "Loan for computers, printers, and equipment",
                "Better equipment = more services = more revenue",
                "KSh 50,000 - 500,000", "12-24% p.a.",
                "Equipment upgrade",
            ),
            _product(
                "SACCO Savings", "sacco",
                "Regular savings from steady income",
                "Predictable daily income supports regular saving",
                "KSh 1,000 - 20,000/month", "8-12% p.a.",
                "Business expansion, second location",
            ),
        ],
        common_challenges=[
            "High electricity costs — computers and printers consume power",
            "Internet service interruptions",
            "Paper and ink costs keep rising",
            "Equipment breakdowns — printers are maintenance-heavy",
            "Competition from smartphones (people browse on their phones)",
            "Rent is a major fixed cost",
            "Power outages halt all business",
            "Customer complaints about slow internet",
        ],
        success_tips=[
            "Location near schools, colleges, or government offices is critical",
            "Offer value-added services: CV writing, KRA PIN, NHIF registration",
            "Keep printers well-maintained — breakdowns lose customers",
            "Buy paper and ink in bulk for better prices",
            "Have backup internet (Safaricom + Telkom) for redundancy",
            "Charge per page, not per minute for printing — simpler for customers",
            "Offer binding and laminating — high-margin services",
        ],
        seasonal_insights=[
            "January: School opening — printing assignments, registrations",
            "March-April: Exam season — students printing notes and past papers",
            "May-June: Moderate — university semester",
            "July-August: School holiday — lower student traffic",
            "September: Back to school — registrations and printing",
            "October-November: Moderate — some government filing deadlines",
            "December: Holiday — lower traffic, but CV updates for January job seekers",
        ],
        price_benchmarks={
            "b_w_print_per_page": 10,
            "color_print_per_page": 30,
            "photocopy_per_page": 5,
            "scanning_per_page": 20,
            "internet_per_hour": 50,
            "binding_per_copy": 100,
            "lamination_a4": 50,
            "ream_of_paper": 500,
        },
        swahili_terms={
            "cyber": "Internet cafe / print shop",
            "printi": "Print out",
            "photocopy": "Photocopy",
            "scan": "Scan",
            "internet": "Internet access",
            "karatasi": "Paper",
            "inki": "Ink cartridge",
        },
        conversation_starters=[
            "Leo umeprinti ngapi? (How many prints today?)",
            "Internet iko pole pole? (Is the internet slow?)",
            "Inki imetosha? (Is there enough ink?)",
        ],
    )


def _profile_construction_fundi() -> WorkerProfile:
    return WorkerProfile(
        type_id="construction_fundi",
        name="Construction Worker (Fundi Ujenzi)",
        name_sw="Fundi wa Ujenzi",
        description="Construction laborer or skilled tradesperson — masonry, plumbing, electrical, painting",
        sector=WorkerSector.CONSTRUCTION,
        icon="🧱",
        income=IncomeRange(low=300, average=700, high=1500, peak=3000),
        operating_costs=OperatingCosts(
            rent=0, stock=0, transport=150, utilities=0,
            labor=0, licenses=0, other=50,
        ),
        startup_cost=5_000,         # Basic tools
        break_even_days=10,
        risk_level=RiskLevel.HIGH,
        seasonality=SeasonalityPattern.WEATHER_DRIVEN,
        peak_months=[1, 2, 7, 8, 9, 10],
        slow_months=[4, 5, 6],
        typical_hours="7 AM - 5 PM",
        working_days_per_week=6,
        location_type="client_site",
        requires_stock=False,
        requires_equipment=True,
        requires_license=False,
        key_metrics=[
            _metric("daily_wage", "Daily earnings", "KSh", 1000, 700, 300),
            _metric("days_worked", "Days with work this month", "count", 24, 18, 8, "monthly"),
            _metric("monthly_income", "Total monthly earnings", "KSh", 18000, 12000, 4000, "monthly"),
            _metric("skill_type", "Type of work (mason, plumber, etc.)", "text", None, None, None),
            _metric("projects_completed", "Jobs finished per month", "count", 3, 2, 1, "monthly"),
            _metric("payment_delays", "Days waiting for payment", "days", 0, 7, 30),
        ],
        what_to_track=[
            "Days worked and daily wage",
            "Type of work done each day",
            "Payment received vs promised",
            "Tools purchased or replaced",
            "Transport costs to work sites",
            "Safety incidents or near-misses",
            "Contacts and referrals from each job",
            "New skills learned",
        ],
        financial_products=[
            _product(
                "SACCO Savings", "sacco",
                "Regular savings when working",
                "Construction is irregular — save during good months",
                "KSh 500 - 5,000/month", "8-12% p.a.",
                "Land, school fees, business startup",
            ),
            _product(
                "NHIF", "government",
                "Health insurance",
                "Construction has high injury risk — medical cover is critical",
                "KSh 500/month", "N/A",
                "Injury and medical emergencies",
            ),
            _product(
                "Emergency Loan", "mfi",
                "Quick loan for gaps between jobs",
                "Construction work is seasonal — bridge income gaps",
                "KSh 2,000 - 20,000", "10-15% per month",
                "Rainy season survival",
            ),
        ],
        common_challenges=[
            "Seasonal unemployment — rains halt outdoor construction",
            "Payment delays — contractors and homeowners delay paying",
            "Unsafe working conditions — falls, injuries common",
            "No benefits — no sick leave, no insurance, no pension",
            "Physical toll — back pain, joint problems, dust exposure",
            "Exploitation by contractors — underpayment, no contracts",
            "Skill stagnation — doing same basic tasks without advancement",
        ],
        success_tips=[
            "Learn multiple trades — mason who also does plumbing gets more work",
            "Always get payment agreement in writing (even informal)",
            "Save 30% of earnings during good months for rainy season",
            "Invest in safety — hard hat, gloves, boots prevent injuries",
            "Build a contact network — most jobs come through referrals",
            "Take on small side projects during rainy season",
            "Learn to read building plans — commands higher wages",
        ],
        seasonal_insights=[
            "January-February: Building season begins — high demand",
            "March-April: Construction continues but rain interruptions start",
            "May-June: Rainy peak — many sites shut down, tough months",
            "July-August: Dry season returns — construction resumes strongly",
            "September-October: Peak construction — everyone building before December",
            "November-December: Construction slows as holidays approach",
        ],
        price_benchmarks={
            "mason_daily_wage": 800,
            "plumber_daily_wage": 1000,
            "painter_daily_wage": 700,
            "electrician_daily_wage": 1200,
            "general_laborer": 500,
            "hard_hat": 500,
            "safety_boots": 1500,
            "work_gloves": 200,
        },
        swahili_terms={
            "ujenzi": "Construction",
            "fundi wa ujenzi": "Construction worker",
            "msingi": "Foundation",
            "ukuta": "Wall",
         	"paa": "Roof",
            "kupaka rangi": "To paint",
            "kuchimba": "To dig",
            "matofali": "Bricks",
            "saruji": "Cement",
        },
        conversation_starters=[
            "Leo kuna kazi? (Is there work today?)",
            "Umepata kazi wapi? (Where did you get work?)",
            "Mshahara umelipwa? (Have you been paid?)",
            "Mvua itakusumbua? (Will the rain affect you?)",
        ],
    )


def _profile_taxi_driver() -> WorkerProfile:
    return WorkerProfile(
        type_id="taxi_driver",
        name="Taxi / Ride-hailing Driver",
        name_sw="Dereva wa Taxi",
        description="Taxi or ride-hailing (Uber, Bolt, Little) driver",
        sector=WorkerSector.TRANSPORT,
        icon="🚕",
        income=IncomeRange(low=500, average=1200, high=2500, peak=5000),
        operating_costs=OperatingCosts(
            rent=0, stock=0, transport=0, utilities=100,
            labor=0, licenses=200, other=200,
        ),
        startup_cost=0,             # Usually driving owner's car
        break_even_days=0,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[1, 5, 9, 12],
        slow_months=[3, 7],
        typical_hours="5 AM - 11 PM",
        working_days_per_week=6,
        location_type="mobile",
        requires_stock=False,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_revenue", "Total daily fare revenue", "KSh", 3000, 1200, 500),
            _metric("daily_payout", "Driver's share after owner/platform cut", "KSh", 1500, 600, 200),
            _metric("fuel_cost", "Daily fuel expense", "KSh", 1000, 600, 300),
            _metric("net_income", "Revenue minus all costs", "KSh", 800, 400, 100),
            _metric("trips_completed", "Number of rides", "count", 12, 6, 2),
            _metric("platform_rating", "Driver rating on app", "score", 4.8, 4.5, 4.0, "weekly"),
        ],
        what_to_track=[
            "Daily fare collection (app + cash trips)",
            "Fuel consumption and cost",
            "Platform commission deducted",
            "Owner's daily cut (if driving someone's car)",
            "Number of trips and average fare",
            "Maintenance costs",
            "Peak hours and surge pricing areas",
            "Rating and customer feedback",
        ],
        financial_products=[
            _product(
                "Vehicle Financing", "bank",
                "Loan to own a car instead of renting",
                "Ownership = no daily cut to owner = much higher income",
                "KSh 200,000 - 2,000,000", "12-18% p.a.",
                "Vehicle ownership",
            ),
            _product(
                "SACCO Savings", "sacco",
                "Regular savings from daily earnings",
                "Good daily income supports consistent saving",
                "KSh 1,000 - 20,000/month", "8-12% p.a.",
                "Vehicle fund, land, school fees",
            ),
            _product(
                "Comprehensive Insurance", "insurance",
                "Vehicle insurance cover",
                "One accident without insurance = financial ruin",
                "KSh 20,000 - 80,000/year", "N/A",
                "Accident and theft cover",
            ),
        ],
        common_challenges=[
            "Platform commission (25-30%) eats into earnings significantly",
            "Fuel costs are the biggest expense",
            "Traffic jams — time stuck in traffic is money lost",
            "Owner demands daily remittance regardless of earnings",
            "Car maintenance — constant wear and tear",
            "Safety risks — passengers can be dangerous",
            "Surge pricing creates unrealistic income expectations",
            "Competition from other drivers and matatus",
        ],
        success_tips=[
            "Learn the city's surge patterns — be in the right area at the right time",
            "Track fuel consumption religiously — know your cost per km",
            "Maintain high ratings — better ratings get more ride requests",
            "Drive during peak hours (6-9 AM, 4-8 PM, Friday/Saturday nights)",
            "Negotiate with owner for fair daily targets based on realistic earnings",
            "Keep the car clean — first impressions affect ratings and tips",
            "Use multiple platforms (Uber + Bolt + Little) to maximize requests",
        ],
        seasonal_insights=[
            "January: Back to work — steady demand",
            "February-March: Corporate events, meetings — good demand",
            "April: Easter travel — airport runs peak",
            "May-June: Moderate — rain increases ride-hailing demand",
            "July-August: Moderate",
            "September: Corporate quarter-end — business travel increases",
            "October-November: Moderate",
            "December: Festive season — party goers, airport runs, highest demand",
        ],
        price_benchmarks={
            "fuel_per_litre": 217,
            "average_trip_fare": 350,
            "platform_commission": 0.25,
            "owner_daily_target": 2500,
            "car_service_cost": 5000,
            "tyre_per_set": 30000,
        },
        swahili_terms={
            "taxi": "Taxi / ride-hailing car",
            "dereva": "Driver",
            "fare": "Nauli / fare",
            "app": "Ride-hailing application",
            "surge": "Higher pricing during peak demand",
            "rating": "Customer rating",
            "trip": "Safari / ride",
        },
        conversation_starters=[
            "Leo umefanya trips ngapi? (How many trips today?)",
            "App imetumika sana? (Was the app busy?)",
            "Petroli imetumika ngapi? (How much fuel did you use?)",
        ],
    )


def _profile_recycler() -> WorkerProfile:
    return WorkerProfile(
        type_id="recycler",
        name="Recycler / Waste Collector",
        name_sw="Mtu wa Recycle",
        description="Waste collector and recycler — collecting plastics, metals, and scrap for sale",
        sector=WorkerSector.ENERGY,
        icon="♻️",
        income=IncomeRange(low=150, average=400, high=800, peak=1500),
        operating_costs=OperatingCosts(
            rent=0, stock=0, transport=100, utilities=0,
            labor=0, licenses=0, other=30,
        ),
        startup_cost=1_000,
        break_even_days=5,
        risk_level=RiskLevel.LOW,
        seasonality=SeasonalityPattern.STEADY,
        peak_months=[1, 5, 9],
        slow_months=[4, 6],
        typical_hours="6 AM - 4 PM",
        working_days_per_week=6,
        location_type="mobile",
        requires_stock=False,
        requires_equipment=False,
        requires_license=False,
        key_metrics=[
            _metric("daily_earnings", "Daily sales to recyclers", "KSh", 600, 400, 150),
            _metric("kg_collected", "Kilograms collected per day", "kg", 30, 15, 5),
            _metric("price_per_kg", "Average selling price per kg", "KSh", 30, 25, 15),
            _metric("collection_spots", "Number of areas covered", "count", 5, 3, 1),
            _metric("material_mix", "Types of materials collected", "text", None, None, None),
        ],
        what_to_track=[
            "Daily weight collected by material type",
            "Selling prices at buy-back centers",
            "Collection route efficiency",
            "Best collection spots and timing",
            "Transport costs to recycling centers",
            "Seasonal material availability",
        ],
        financial_products=[
            _product(
                "M-Pesa Savings", "mobile",
                "Daily micro-savings from scrap sales",
                "Small daily earnings add up with consistent saving",
                "KSh 20 - 1,000", "5-8% p.a.",
                "Emergency fund",
            ),
        ],
        common_challenges=[
            "Very low pay per kilogram — need volume to earn",
            "Health hazards — cuts, infections from waste",
            "Social stigma — waste picking is looked down upon",
            "Physical exhaustion — carrying heavy loads all day",
            "Price fluctuations at buy-back centers",
            "Competition from other collectors",
            "No protective equipment (gloves, boots)",
        ],
        success_tips=[
            "Learn which materials pay best — copper, aluminum, plastics have different rates",
            "Map out efficient collection routes — cover more ground",
            "Build relationships with buy-back centers for better prices",
            "Sort materials before selling — mixed loads get lower prices",
            "Collect from consistent spots — businesses, markets, estates",
            "Invest in protective gear — gloves and boots prevent injuries",
        ],
        seasonal_insights=[
            "Year-round: Relatively consistent waste generation",
            "Post-holiday: More packaging waste from festive consumption",
            "Rainy seasons: Harder to collect, materials get wet and heavy",
        ],
        price_benchmarks={
            "plastic_per_kg": 20,
            "metal_per_kg": 40,
            "aluminum_per_kg": 80,
            "copper_per_kg": 500,
            "paper_per_kg": 10,
            "glass_per_kg": 5,
        },
        swahili_terms={
            "takataka": "Waste / garbage",
            "recycle": "Recycle / reuse",
            "chuma": "Metal",
            "plastiki": "Plastic",
            "karatasi": "Paper",
            "gunia": "Sack for collecting",
        },
        conversation_starters=[
            "Leo umepata wangapi? (How much did you earn today?)",
            "Ni material gani inalipa? (Which material pays best?)",
        ],
    )


def _profile_photographer() -> WorkerProfile:
    return WorkerProfile(
        type_id="photographer",
        name="Photographer / Videographer",
        name_sw="Mtapicha",
        description="Event and portrait photographer serving local communities",
        sector=WorkerSector.DIGITAL,
        icon="📸",
        income=IncomeRange(low=0, average=800, high=3000, peak=10000),
        operating_costs=OperatingCosts(
            rent=200, stock=100, transport=300, utilities=50,
            labor=200, licenses=30, other=100,
        ),
        startup_cost=80_000,
        break_even_days=120,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.FESTIVAL_DRIVEN,
        peak_months=[4, 8, 12],
        slow_months=[6, 7, 9],
        typical_hours="8 AM - 8 PM (varies by event)",
        working_days_per_week=5,
        location_type="client_site",
        requires_stock=False,
        requires_equipment=True,
        requires_license=False,
        key_metrics=[
            _metric("monthly_income", "Total monthly earnings", "KSh", 20000, 15000, 3000, "monthly"),
            _metric("events_covered", "Events photographed per month", "count", 8, 4, 1, "monthly"),
            _metric("average_event_fee", "Average charge per event", "KSh", 5000, 3000, 1500),
            _metric("editing_hours", "Hours spent editing per event", "hours", 4, 6, 10),
            _metric("client_referrals", "New clients from referrals", "count", 3, 1, 0, "monthly"),
            _metric("equipment_cost", "Monthly equipment maintenance/replacement", "KSh", 2000, 3000, 5000, "monthly"),
        ],
        what_to_track=[
            "Events booked and completed",
            "Revenue per event type (wedding, birthday, graduation, corporate)",
            "Editing time per event",
            "Equipment costs and depreciation",
            "Client referrals and repeat bookings",
            "Social media engagement and inquiries",
            "Travel and transport costs to events",
        ],
        financial_products=[
            _product(
                "Asset Finance", "bank",
                "Loan for camera equipment",
                "Better equipment = higher quality = premium pricing",
                "KSh 50,000 - 300,000", "12-24% p.a.",
                "Camera, lenses, lighting upgrade",
            ),
            _product(
                "SACCO Savings", "sacco",
                "Irregular income savings plan",
                "Lumpy income needs structured saving approach",
                "KSh 2,000 - 20,000/month", "8-12% p.a.",
                "Studio setup, equipment fund",
            ),
        ],
        common_challenges=[
            "Irregular income — feast or famine cycle",
            "High equipment costs — cameras, lenses, computers for editing",
            "Client payment delays — event photography often paid after delivery",
            "Editing takes hours — time not spent earning",
            "Competition from smartphone cameras and cheap photographers",
            "Equipment theft and damage",
            "Seasonal demand — wedding and graduation seasons only",
        ],
        success_tips=[
            "Build a portfolio on Instagram and TikTok",
            "Offer packages (photo + video) for higher per-event revenue",
            "Specialize in 2-3 event types — weddings, corporate, or portraits",
            "Deliver edited photos within 1 week — speed beats perfection",
            "Network with event planners, churches, and schools",
            "Save 50% of each event payment for slow months",
            "Learn drone photography — commands premium pricing",
        ],
        seasonal_insights=[
            "January: Post-holiday — few events",
            "February-March: Valentine's, some weddings begin",
            "April: Easter weddings peak",
            "May-June: Moderate — school events, graduations",
            "July-August: Graduation season peak",
            "September: Moderate",
            "October: Pre-December wedding rush begins",
            "November-December: Wedding and festive season peak",
        ],
        price_benchmarks={
            "wedding_full_day": 30000,
            "graduation_event": 5000,
            "birthday_party": 8000,
            "corporate_event": 15000,
            "passport_photo": 200,
            "studio_portrait": 1000,
            "photo_print_a4": 100,
        },
        swahili_terms={
            "mtapicha": "Photographer",
            "picha": "Photo / picture",
            "kamera": "Camera",
            "harusi": "Wedding",
            "sherehe": "Celebration / party",
            "kupiga picha": "To take a photo",
            "kurediti": "To edit",
        },
        conversation_starters=[
            "Una event ngapi mwezi huu? (How many events this month?)",
            "Bei ya harusi ni ngapi? (What's the wedding rate?)",
            "Camera iko sawa? (Is the camera okay?)",
        ],
    )


def _profile_tailor() -> WorkerProfile:
    return WorkerProfile(
        type_id="tailor",
        name="Tailor / Dressmaker",
        name_sw="Mshonaji",
        description="Seamstress or tailor making and altering clothes",
        sector=WorkerSector.MANUFACTURING,
        icon="🧵",
        income=IncomeRange(low=200, average=600, high=1500, peak=3000),
        operating_costs=OperatingCosts(
            rent=200, stock=400, transport=50, utilities=80,
            labor=0, licenses=20, other=50,
        ),
        startup_cost=20_000,
        break_even_days=45,
        risk_level=RiskLevel.LOW,
        seasonality=SeasonalityPattern.FESTIVAL_DRIVEN,
        peak_months=[4, 8, 12],
        slow_months=[6, 7],
        typical_hours="8 AM - 6 PM",
        working_days_per_week=6,
        location_type="fixed",
        requires_stock=True,
        requires_equipment=True,
        requires_license=False,
        key_metrics=[
            _metric("daily_revenue", "Daily income from orders", "KSh", 1000, 600, 200),
            _metric("orders_in_progress", "Current active orders", "count", 5, 8, 15, "weekly"),
            _metric("average_order_value", "Average charge per garment", "KSh", 800, 500, 200),
            _metric("fabric_cost", "Fabric cost as % of order price", "%", 30, 40, 60, "weekly"),
            _metric("on_time_delivery", "% of orders delivered on time", "%", 90, 70, 50, "monthly"),
            _metric("repeat_customers", "Returning clients per month", "count", 10, 5, 2, "monthly"),
        ],
        what_to_track=[
            "Orders received, in progress, and completed",
            "Revenue per order and fabric costs",
            "Customer measurements and preferences",
            "Order completion time vs promised date",
            "Fabric purchases and supplier costs",
            "Alteration vs new garment revenue",
            "Customer satisfaction and referrals",
        ],
        financial_products=[
            _product(
                "SACCO Savings", "sacco",
                "Regular savings from steady order income",
                "Predictable income supports regular saving",
                "KSh 500 - 10,000/month", "8-12% p.a.",
                "Equipment upgrade, shop expansion",
            ),
            _product(
                "Working Capital Loan", "mfi",
                "Loan for fabric stock",
                "Buy fabric in bulk for better prices",
                "KSh 5,000 - 50,000", "5-10% per month",
                "Fabric inventory",
            ),
            _product(
                "Equipment Loan", "mfi",
                "Loan for sewing machine upgrade",
                "Better machine = faster work = more orders",
                "KSh 10,000 - 80,000", "10-15% p.a.",
                "Sewing machine, overlocker",
            ),
        ],
        common_challenges=[
            "Customer measurements sometimes wrong — rework required",
            "Fabric quality from suppliers is inconsistent",
            "Customers delay picking up completed orders",
            "Rush orders during festive season create backlog",
            "Power outages halt sewing machine operation",
            "Competition from ready-made clothes (mitumba, new imports)",
            "Keeping up with fashion trends",
            "Thread, needles, and accessories add up",
        ],
        success_tips=[
            "Take accurate measurements — measure twice, cut once",
            "Show fabric samples and previous work to customers",
            "Set realistic delivery dates — under-promise, over-deliver",
            "Learn trending styles from social media",
            "Offer alterations as a steady income base between big orders",
            "Build a WhatsApp catalog of your designs",
            "Invest in a good overlocker for professional finishing",
        ],
        seasonal_insights=[
            "January: Post-holiday — school uniform orders peak",
            "February-Mavelentine's — couples outfits",
            "March-April: Easter — dress orders peak",
            "May-June: Moderate — school uniforms continue",
            "July-August: Graduation outfits, school uniforms",
            "September: Moderate",
            "October-November: Wedding season prep — bridal orders",
            "December: Festive peak — new clothes for Christmas",
        ],
        price_benchmarks={
            "school_uniform_set": 800,
            "dress_custom": 1500,
            "shirt_custom": 800,
            "suit_custom": 5000,
            "alteration_hem": 200,
            "alteration_zip": 300,
            "curtains_per_metre": 500,
            "fabric_per_metre": 300,
        },
        swahili_terms={
            "mshonaji": "Tailor / dressmaker",
            "ushonaji": "Sewing / tailoring",
            "nguo": "Clothes / fabric",
            "kipimo": "Measurement",
            "sindano": "Needle",
            "uzi": "Thread",
            "machine": "Sewing machine",
            "kata": "Cut (fabric)",
        },
        conversation_starters=[
            "Order ngapi kwa queue? (How many orders in the queue?)",
            "Umemaliza nguo za client? (Did you finish the client's clothes?)",
            "Bei ya kitenge imepanda? (Has fabric price gone up?)",
        ],
    )


def _profile_food_cart() -> WorkerProfile:
    return WorkerProfile(
        type_id="food_cart",
        name="Food Cart Vendor",
        name_sw="Muuzaji wa Cart ya Chakula",
        description="Mobile food cart selling snacks, roasted maize, sausages, or street food",
        sector=WorkerSector.FOOD,
        icon="🍿",
        income=IncomeRange(low=200, average=500, high=1200, peak=2500),
        operating_costs=OperatingCosts(
            rent=50, stock=400, transport=50, utilities=50,
            labor=0, licenses=30, other=30,
        ),
        startup_cost=8_000,
        break_even_days=20,
        risk_level=RiskLevel.MEDIUM,
        seasonality=SeasonalityPattern.WEATHER_DRIVEN,
        peak_months=[6, 7, 8, 12],
        slow_months=[4, 5],
        typical_hours="10 AM - 9 PM",
        working_days_per_week=6,
        location_type="mobile",
        requires_stock=True,
        requires_equipment=True,
        requires_license=True,
        key_metrics=[
            _metric("daily_sales", "Daily revenue", "KSh", 800, 500, 200),
            _metric("items_sold", "Total items sold", "count", 50, 25, 10),
            _metric("average_item_price", "Average selling price", "KSh", 30, 20, 10),
            _metric("waste_rate", "Items unsold/spoiled", "%", 5, 10, 25),
            _metric("best_location", "Highest revenue location", "text", None, None, None, "weekly"),
            _metric("best_time", "Peak selling hours", "text", None, None, None),
        ],
        what_to_track=[
            "Items sold by type",
            "Revenue per location and time of day",
            "Stock costs and waste",
            "Fuel/charcoal costs for cooking",
            "Location performance comparison",
            "Customer preferences",
            "Weather impact on sales",
        ],
        financial_products=[
            _product(
                "M-Pesa Savings", "mobile",
                "Daily micro-savings",
                "Consistent daily sales support regular saving",
                "KSh 50 - 2,000", "5-8% p.a.",
                "Emergency fund",
            ),
            _product(
                "Cart Upgrade Loan", "mfi",
                "Loan for better cart or equipment",
                "Better cart = more capacity = more sales",
                "KSh 5,000 - 30,000", "10-15% p.a.",
                "Cart upgrade, equipment",
            ),
        ],
        common_challenges=[
            "Kanjo harassment and location instability",
            "Perishable ingredients — waste from unsold stock",
            "Weather dependence — rain stops business",
            "Fire/charcoal safety hazards",
            "Competition from other food vendors",
            "Customer haggling",
            "Health inspection requirements",
        ],
        success_tips=[
            "Specialize in 2-3 items you do really well",
            "Position near schools, offices, or matatu stages during lunch",
            "Keep food display clean and appetizing",
            "Buy ingredients daily — freshness is your selling point",
            "Learn your peak hours and be in position before they start",
            "Use M-Pesa for all sales — track revenue automatically",
        ],
        seasonal_insights=[
            "January: Back to school/work — good demand",
            "February-March: Steady",
            "April-May: Rainy season — limited outdoor selling",
            "June-July: Cold season — warm snacks (maize, smokies) sell well",
            "August-September: Moderate",
            "October-November: Mixed weather",
            "December: Festive season — high demand for snacks",
        ],
        price_benchmarks={
            "roasted_maize": 50,
            "boiled_maize": 50,
            "smokie": 30,
            "chapati": 20,
            "mandazi": 10,
            "samosa": 30,
            "chips_portion": 100,
        },
        swahili_terms={
            "mtumbwi": "Food cart",
            "mahindi ya kuchoma": "Roasted maize",
            "mahindi ya kuchemsha": "Boiled maize",
            "viazi": "Potatoes / chips",
            "chapati": "Flatbread",
            "mandazi": "Sweet fried dough",
        },
        conversation_starters=[
            "Leo umepata wangapi? (How much did you make today?)",
            "Wapi pa kazi ni bora? (Where is the best spot?)",
            "Mvua ilikuathiri? (Did the rain affect you?)",
        ],
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PROFILE REGISTRY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _build_registry() -> dict[str, WorkerProfile]:
    """Build the complete worker profile registry."""
    builders = [
        _profile_mama_mboga,
        _profile_boda_boda,
        _profile_dukawallah,
        _profile_machinga,
        _profile_fundi,
        _profile_mama_lishe,
        _profile_mpesa_agent,
        _profile_mitumba_seller,
        _profile_jua_kali,
        _profile_salon_barber,
        _profile_matatu_crew,
        _profile_mkulima,
        _profile_changaa_brewer,
        _profile_boda_mechanic,
        _profile_charcoal_seller,
        _profile_water_vendor,
        _profile_shoe_shiner,
        _profile_watchman,
        _profile_laundry_mama,
        _profile_smokie_vendor,
        _profile_eggs_ndizi_vendor,
        _profile_cyber_print,
        _profile_construction_fundi,
        _profile_taxi_driver,
        _profile_recycler,
        _profile_photographer,
        _profile_tailor,
        _profile_food_cart,
    ]
    registry: dict[str, WorkerProfile] = {}
    for builder in builders:
        profile = builder()
        registry[profile.type_id] = profile
    return registry


_REGISTRY: dict[str, WorkerProfile] | None = None


def get_all_profiles() -> dict[str, WorkerProfile]:
    """Get all worker profiles. Builds once, returns cached."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def get_profile(type_id: str) -> WorkerProfile | None:
    """Get a specific worker profile by type_id."""
    return get_all_profiles().get(type_id)


def get_profiles_by_sector(sector: WorkerSector) -> list[WorkerProfile]:
    """Get all profiles in a given sector."""
    return [p for p in get_all_profiles().values() if p.sector == sector]


def get_type_ids() -> list[str]:
    """Get all registered worker type IDs."""
    return list(get_all_profiles().keys())


def search_profiles(query: str) -> list[WorkerProfile]:
    """Search profiles by name, description, or Swahili terms."""
    q = query.lower()
    results = []
    for profile in get_all_profiles().values():
        searchable = (
            profile.name.lower()
            + profile.name_sw.lower()
            + profile.description.lower()
            + " ".join(profile.swahili_terms.keys())
        )
        if q in searchable:
            results.append(profile)
    return results
