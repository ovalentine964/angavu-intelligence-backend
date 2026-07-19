"""
Pwani Oil Products Ltd — Client Template.

Template for Pwani Oil, one of East Africa's largest FMCG manufacturers.
Defines product portfolio, regions, and competitive landscape for
tailored intelligence delivery.

Products:
  Cooking Oils: Fresh Fri, Salit, Popco, Pwani, Safari, Mpishi Poa, Fry Mate, Onja
  Personal Care: Detrex, Sawa, Diva, Afrisense
  Home Care: White Wash, Ushindi, Ndume

Headquarters: Mombasa, Kenya (manufacturing in Kikambala, Kilifi County)
Market: East Africa (Kenya, Uganda, Tanzania, Rwanda, Ethiopia)
Capacity: 1,000+ metric tonnes/day refining
"""

from dataclasses import dataclass, field


@dataclass
class ProductLine:
    """A product line within Pwani Oil's portfolio."""

    name: str
    category: str
    price_segment: str  # economy, mid, premium
    target_demographic: str
    informal_channel_relevance: str  # high, medium, low
    key_competitors: list[str] = field(default_factory=list)


@dataclass
class RegionProfile:
    """Regional profile for distribution analysis."""

    name: str
    counties: list[str]
    population_estimate: int
    informal_market_density: str  # high, medium, low
    key_distributor_hubs: list[str] = field(default_factory=list)
    dominant_competitors: list[str] = field(default_factory=list)
    penetration_opportunity: str = "medium"  # low, medium, high


class PwaniOilTemplate:
    """
    Template for Pwani Oil Products Ltd.

    Encodes product portfolio, regional distribution, and competitive
    landscape for generating tailored FMCG intelligence.
    """

    COMPANY_NAME = "Pwani Oil Products Ltd"
    HEADQUARTERS = "Mombasa, Kenya"
    MANUFACTURING = "Kikambala, Kilifi County"
    FOUNDED = "~1986"
    DAILY_CAPACITY_TONNES = 1000
    WEBSITE = "https://pwani.net"
    CONTACT_EMAIL = "info@pwani.net"

    # ── Product Portfolio ───────────────────────────────────────────────────

    PRODUCTS: dict[str, list[str]] = {
        "cooking_oils": [
            "Fresh Fri",       # Premium cooking oil
            "Salit",           # Refined fortified vegetable oil
            "Popco",           # Pure vegetable oil (Vitamin E)
            "Pwani",           # Brand eponymous oil
            "Safari",          # Cooking oil
            "Mpishi Poa",      # Cooking fat
            "Fry Mate",        # Cooking fat
            "Onja",            # Margarine
        ],
        "personal_care": [
            "Detrex",          # Germ protection soap
            "Sawa",            # Family bath soap
            "Diva",            # Antibacterial beauty soap
            "Afrisense",       # Personal care line
        ],
        "home_care": [
            "White Wash",      # Cleaning products
            "Ushindi",         # Washing products
            "Ndume",           # Superior washing bar soap
        ],
    }

    # Detailed product line profiles
    PRODUCT_LINES: dict[str, ProductLine] = {
        "fresh_fri": ProductLine(
            name="Fresh Fri",
            category="cooking_oils",
            price_segment="premium",
            target_demographic="middle-class households",
            informal_channel_relevance="high",
            key_competitors=["Elianto (Bidco)", "Golden Fry (Kapa)", "Rina (Menengai)"],
        ),
        "salit": ProductLine(
            name="Salit",
            category="cooking_oils",
            price_segment="mid",
            target_demographic="mass market",
            informal_channel_relevance="high",
            key_competitors=["Elianto (Bidco)", "Top Fry (Kapa)", "Kimbo (Bidco)"],
        ),
        "popco": ProductLine(
            name="Popco",
            category="cooking_oils",
            price_segment="mid",
            target_demographic="health-conscious households",
            informal_channel_relevance="high",
            key_competitors=["Elianto (Bidco)", "Golden Fry (Kapa)"],
        ),
        "mpishi_poa": ProductLine(
            name="Mpishi Poa",
            category="cooking_oils",
            price_segment="economy",
            target_demographic="price-sensitive consumers, food vendors",
            informal_channel_relevance="high",
            key_competitors=["Kimbo (Bidco)", "Cowboy (Kapa)", "Soko (Bidco)"],
        ),
        "detrex": ProductLine(
            name="Detrex",
            category="personal_care",
            price_segment="mid",
            target_demographic="families, hygiene-conscious",
            informal_channel_relevance="high",
            key_competitors=["Lifebuoy (Unilever)", "Dettol (Reckitt)", "Medisoft"],
        ),
        "sawa": ProductLine(
            name="Sawa",
            category="personal_care",
            price_segment="economy",
            target_demographic="mass market families",
            informal_channel_relevance="high",
            key_competitors=["Lux (Unilever)", "Joy (Kapa)", "Amani (Menengai)"],
        ),
        "diva": ProductLine(
            name="Diva",
            category="personal_care",
            price_segment="mid",
            target_demographic="young women, beauty-conscious",
            informal_channel_relevance="high",
            key_competitors=["Dove (Unilever)", "Nivea", "Imperial Leather"],
        ),
        "white_wash": ProductLine(
            name="White Wash",
            category="home_care",
            price_segment="mid",
            target_demographic="households",
            informal_channel_relevance="medium",
            key_competitors=["Omo (Unilever)", "Sunlight (Unilever)", "Ariel (P&G)"],
        ),
        "ushindi": ProductLine(
            name="Ushindi",
            category="home_care",
            price_segment="economy",
            target_demographic="price-sensitive households",
            informal_channel_relevance="high",
            key_competitors=["Omo (Unilever)", "Toss (Kapa)", "Jamaa (Menengai)"],
        ),
        "ndume": ProductLine(
            name="Ndume",
            category="home_care",
            price_segment="economy",
            target_demographic="rural households, heavy-duty washing",
            informal_channel_relevance="high",
            key_competitors=["Sunlight (Unilever)", "Cowboy bar (Kapa)"],
        ),
    }

    # ── Regional Profiles ───────────────────────────────────────────────────

    REGIONS: dict[str, RegionProfile] = {
        "coast": RegionProfile(
            name="Coast",
            counties=["Mombasa", "Kilifi", "Kwale", "Taita-Taveta", "Lamu", "Tana River"],
            population_estimate=4_500_000,
            informal_market_density="high",
            key_distributor_hubs=["Mombasa CBD", "Malindi", "Diani", "Mariakani"],
            dominant_competitors=["Bidco", "Kapa Oil"],
            penetration_opportunity="high",
        ),
        "nairobi": RegionProfile(
            name="Nairobi",
            counties=["Nairobi"],
            population_estimate=5_000_000,
            informal_market_density="high",
            key_distributor_hubs=["Eastleigh", "Gikomba", "City Market", "Kawangware", "Kibera"],
            dominant_competitors=["Bidco", "Unilever", "Kapa Oil"],
            penetration_opportunity="medium",
        ),
        "central": RegionProfile(
            name="Central",
            counties=["Kiambu", "Murang'a", "Nyeri", "Kirinyaga", "Nyandarua", "Laikipia"],
            population_estimate=6_000_000,
            informal_market_density="medium",
            key_distributor_hubs=["Thika", "Nyeri town", "Nanyuki", "Karatina"],
            dominant_competitors=["Bidco", "Unilever", "Menengai"],
            penetration_opportunity="medium",
        ),
        "western": RegionProfile(
            name="Western",
            counties=["Kakamega", "Bungoma", "Vihiga", "Busia", "Trans-Nzoia"],
            population_estimate=5_500_000,
            informal_market_density="high",
            key_distributor_hubs=["Kakamega town", "Bungoma", "Busia", "Kitale"],
            dominant_competitors=["Bidco", "Menengai"],
            penetration_opportunity="high",
        ),
        "nyanza": RegionProfile(
            name="Nyanza",
            counties=["Kisumu", "Homa Bay", "Migori", "Siaya", "Kisii", "Nyamira"],
            population_estimate=6_000_000,
            informal_market_density="high",
            key_distributor_hubs=["Kisumu CBD", "Kisii town", "Migori", "Homabay"],
            dominant_competitors=["Bidco", "Kapa Oil", "Menengai"],
            penetration_opportunity="high",
        ),
        "rift_valley": RegionProfile(
            name="Rift Valley",
            counties=[
                "Nakuru", "Uasin Gishu", "Nandi", "Baringo", "Kericho",
                "Bomet", "Narok", "Kajiado", "Samburu", "Turkana",
                "West Pokot", "Elgeyo-Marakwet", "Laikipia",
            ],
            population_estimate=12_000_000,
            informal_market_density="medium",
            key_distributor_hubs=["Nakuru", "Eldoret", "Kericho", "Naivasha", "Narok"],
            dominant_competitors=["Bidco", "Unilever", "Menengai"],
            penetration_opportunity="high",
        ),
        "eastern": RegionProfile(
            name="Eastern",
            counties=["Machakos", "Kitui", "Meru", "Embu", "Tharaka-Nithi", "Isiolo", "Marsabit"],
            population_estimate=6_500_000,
            informal_market_density="medium",
            key_distributor_hubs=["Machakos", "Meru town", "Embu", "Isiolo"],
            dominant_competitors=["Bidco", "Menengai"],
            penetration_opportunity="medium",
        ),
        "north_eastern": RegionProfile(
            name="North Eastern",
            counties=["Garissa", "Wajir", "Mandera"],
            population_estimate=2_500_000,
            informal_market_density="low",
            key_distributor_hubs=["Garissa"],
            dominant_competitors=["Bidco"],
            penetration_opportunity="low",
        ),
    }

    # ── Competitive Landscape ───────────────────────────────────────────────

    COMPETITORS = {
        "bidco": {
            "name": "Bidco Africa",
            "hq": "Thika, Kenya",
            "key_products": ["Elianto", "Kimbo", "Cowboy", "Soko", "Fresh", "Power Boy"],
            "categories": ["cooking_oils", "personal_care", "home_care"],
            "market_position": "market_leader",
            "informal_channel_strength": "very_high",
        },
        "kapa_oil": {
            "name": "Kapa Oil Refineries",
            "hq": "Nairobi, Kenya",
            "key_products": ["Golden Fry", "Top Fry", "Cowboy", "Toss", "Joy"],
            "categories": ["cooking_oils", "home_care", "personal_care"],
            "market_position": "strong_challenger",
            "informal_channel_strength": "high",
        },
        "menengai": {
            "name": "Menengai Oil Refineries",
            "hq": "Nakuru, Kenya",
            "key_products": ["Rina", "Amani", "Jamaa", "Menengai"],
            "categories": ["cooking_oils", "personal_care", "home_care"],
            "market_position": "challenger",
            "informal_channel_strength": "high",
        },
        "unilever": {
            "name": "Unilever Kenya",
            "hq": "Nairobi, Kenya",
            "key_products": ["Omo", "Sunlight", "Lux", "Lifebuoy", "Dove"],
            "categories": ["home_care", "personal_care"],
            "market_position": "premium_leader",
            "informal_channel_strength": "medium",
        },
    }

    # ── Intelligence Service Tiers ──────────────────────────────────────────

    RECOMMENDED_SERVICES = {
        "essential": {
            "name": "Essential Market Intelligence",
            "monthly_usd": 5_000,
            "includes": [
                "Informal channel sales tracking (all product lines)",
                "Competitive pricing intelligence (monthly)",
                "Distribution gap alerts",
                "Quarterly market penetration report",
            ],
        },
        "growth": {
            "name": "Growth Intelligence Suite",
            "monthly_usd": 12_000,
            "includes": [
                "Everything in Essential",
                "Route-to-market optimization",
                "Trade promotion ROI analysis",
                "Consumer behavior insights",
                "Weekly competitive briefings",
                "API access for Power BI integration",
            ],
        },
        "enterprise": {
            "name": "Enterprise Commercial Intelligence",
            "monthly_usd": 25_000,
            "includes": [
                "Everything in Growth",
                "Predictive demand forecasting",
                "Fleet utilization optimization",
                "Custom Python analytics models",
                "Real-time market alerts",
                "Dedicated account manager",
                "Regulatory intelligence (East Africa)",
            ],
        },
    }

    @classmethod
    def get_all_products_flat(cls) -> list[str]:
        """Return all product names as a flat list."""
        products = []
        for category_products in cls.PRODUCTS.values():
            products.extend(category_products)
        return products

    @classmethod
    def get_products_by_category(cls, category: str) -> list[str]:
        """Return products for a specific category."""
        return cls.PRODUCTS.get(category, [])

    @classmethod
    def get_high_informal_channel_products(cls) -> list[ProductLine]:
        """Return products with high informal channel relevance."""
        return [
            p for p in cls.PRODUCT_LINES.values()
            if p.informal_channel_relevance == "high"
        ]

    @classmethod
    def get_region_profile(cls, region: str) -> RegionProfile | None:
        """Return profile for a specific region."""
        return cls.REGIONS.get(region.lower())

    @classmethod
    def get_expansion_priorities(cls) -> list[dict]:
        """
        Return regions ranked by expansion opportunity.

        Combines population, informal market density, and
        penetration opportunity to prioritize distribution expansion.
        """
        density_score = {"high": 3, "medium": 2, "low": 1}
        opportunity_score = {"high": 3, "medium": 2, "low": 1}

        priorities = []
        for key, region in cls.REGIONS.items():
            score = (
                (region.population_estimate / 1_000_000)
                * density_score.get(region.informal_market_density, 1)
                * opportunity_score.get(region.penetration_opportunity, 1)
            )
            priorities.append({
                "region": key,
                "name": region.name,
                "score": round(score, 1),
                "population": region.population_estimate,
                "density": region.informal_market_density,
                "opportunity": region.penetration_opportunity,
                "key_hubs": region.key_distributor_hubs,
            })

        return sorted(priorities, key=lambda x: x["score"], reverse=True)
