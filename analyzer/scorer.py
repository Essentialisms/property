"""Deal rating engine for Berlin property listings."""

from scraper.models import Property, PropertyRating, RatedProperty
from analyzer.districts import get_district_data
from analyzer.risk import evaluate as evaluate_risk, labels_for

# Land prices per m2 are inherently lower than apartment/house prices.
# These factors adjust the district average for fair comparison.
PROPERTY_TYPE_FACTORS = {
    "land": 0.30,
    "house": 0.85,
    "apartment": 1.0,
}


def rate_property(prop: Property) -> RatedProperty:
    """Rate a single property listing."""
    district_data = get_district_data(prop.district) if prop.district else None
    district_avg_for_risk = (
        district_data["avg_price_m2"] * PROPERTY_TYPE_FACTORS.get(prop.property_type, 1.0)
        if district_data else None
    )
    risk_flags, risk_score = evaluate_risk(prop, district_avg_for_risk)

    if not prop.price or not prop.area_m2 or prop.area_m2 <= 0:
        return RatedProperty(
            property=prop,
            rating=None,
            rating_note="Insufficient data for rating (missing price or area)",
            risk_score=risk_score,
            risk_flags=risk_flags,
            risk_labels=labels_for(risk_flags),
        )

    if not prop.district:
        return RatedProperty(
            property=prop,
            rating=None,
            rating_note="Unknown district — cannot rate",
            risk_score=risk_score,
            risk_flags=risk_flags,
            risk_labels=labels_for(risk_flags),
        )

    if not district_data:
        return RatedProperty(
            property=prop,
            rating=None,
            rating_note=f"No reference data for district '{prop.district}'",
            risk_score=risk_score,
            risk_flags=risk_flags,
            risk_labels=labels_for(risk_flags),
        )

    price_per_m2 = prop.price_per_m2 or (prop.price / prop.area_m2)

    # Adjust district average by property type
    type_factor = PROPERTY_TYPE_FACTORS.get(prop.property_type, 1.0)
    adjusted_avg = district_data["avg_price_m2"] * type_factor

    deal_score = _calculate_deal_score(price_per_m2, adjusted_avg)
    growth_score = _calculate_growth_score(district_data)
    combined = deal_score * 0.7 + growth_score * 0.3

    grade = _score_to_grade(combined)
    stars = max(1, min(5, round(combined / 20)))
    # The text label describes the *price* (cheap vs. overpriced), so it's
    # derived from deal_score alone. The letter grade and stars combine
    # deal + growth and are the right place to express overall pickiness.
    label = _grade_label(_score_to_grade(deal_score))

    price_vs_avg = round((price_per_m2 / adjusted_avg) * 100, 1) if adjusted_avg > 0 else None

    growth_trend = district_data.get("growth_trend", 1.0)
    tier = district_data.get("tier")

    rating = PropertyRating(
        deal_score=round(deal_score, 1),
        growth_score=round(growth_score, 1),
        combined_score=round(combined, 1),
        grade=grade,
        stars=stars,
        label=label,
        district_avg_price=round(adjusted_avg, 2),
        price_vs_avg_pct=price_vs_avg,
        district_growth_pct=round((growth_trend - 1.0) * 100, 1),
        district_tier=tier,
    )

    return RatedProperty(
        property=prop,
        rating=rating,
        risk_score=risk_score,
        risk_flags=risk_flags,
        risk_labels=labels_for(risk_flags),
    )


def rate_properties(properties: list[Property]) -> list[RatedProperty]:
    """Rate all properties and sort by best deal first."""
    rated = [rate_property(p) for p in properties]
    # Sort: rated properties first (by combined_score desc), unrated last
    rated.sort(
        key=lambda rp: rp.rating.combined_score if rp.rating else -1,
        reverse=True,
    )
    return rated


def filter_by_budget(properties: list[RatedProperty], budget: float | None) -> list[RatedProperty]:
    """Filter properties by maximum budget."""
    if budget is None or budget <= 0:
        return properties
    return [rp for rp in properties if rp.property.price is None or rp.property.price <= budget]


def filter_by_size(properties: list[RatedProperty], min_size: float | None) -> list[RatedProperty]:
    """Filter properties by minimum area."""
    if min_size is None or min_size <= 0:
        return properties
    return [rp for rp in properties if rp.property.area_m2 is None or rp.property.area_m2 >= min_size]


def sort_properties(properties: list[RatedProperty], sort_by: str) -> list[RatedProperty]:
    """Sort rated properties by the specified criterion."""
    if sort_by == "price":
        return sorted(properties, key=lambda rp: rp.property.price or float("inf"))
    elif sort_by == "size":
        return sorted(properties, key=lambda rp: rp.property.area_m2 or 0, reverse=True)
    elif sort_by == "growth_score":
        return sorted(
            properties,
            key=lambda rp: rp.rating.growth_score if rp.rating else -1,
            reverse=True,
        )
    else:  # deal_score (default)
        return sorted(
            properties,
            key=lambda rp: rp.rating.combined_score if rp.rating else -1,
            reverse=True,
        )


def _calculate_deal_score(price_per_m2: float, district_avg: float) -> float:
    """How cheap is this listing vs. the district average?

    100 = listed at 50% or less of district average (incredible deal)
    50  = listed at exactly district average (fair price)
    0   = listed at 150%+ of district average (overpriced)
    """
    if district_avg <= 0:
        return 50.0
    ratio = price_per_m2 / district_avg
    score = max(0, min(100, (1.5 - ratio) * 100))
    return score


def _calculate_growth_score(district_data: dict) -> float:
    """Score based on district growth trend and tier."""
    growth = district_data.get("growth_trend", 1.0)
    tier = district_data.get("tier", "mid")

    tier_bonus = {
        "emerging": 20,
        "budget": 15,
        "mid": 5,
        "high": 0,
        "premium": -5,
    }

    # Base: growth rate mapped to 0-80 (1.00=0, 1.10=80)
    base = max(0, min(80, (growth - 1.0) * 1000))
    bonus = tier_bonus.get(tier, 0)
    return max(0, min(100, base + bonus))


def _score_to_grade(score: float) -> str:
    if score >= 80:
        return "A"
    elif score >= 65:
        return "B"
    elif score >= 50:
        return "C"
    elif score >= 35:
        return "D"
    return "F"


def _grade_label(grade: str) -> str:
    return {
        "A": "Excellent Deal",
        "B": "Good Deal",
        "C": "Fair Price",
        "D": "Above Market",
        "F": "Overpriced",
    }.get(grade, "Unknown")
