from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Property:
    id: str
    title: str
    address: str
    district: Optional[str]
    postcode: Optional[str]
    price: Optional[float]
    area_m2: Optional[float]
    price_per_m2: Optional[float]
    property_type: str  # "land", "apartment", "house"
    url: str
    image_url: Optional[str] = None
    rooms: Optional[float] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class PropertyRating:
    deal_score: float  # 0-100
    growth_score: float  # 0-100
    combined_score: float  # 0-100
    grade: str  # A-F
    stars: int  # 1-5
    label: str  # "Excellent Deal", etc.
    district_avg_price: Optional[float] = None
    price_vs_avg_pct: Optional[float] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class RatedProperty:
    property: Property
    rating: Optional[PropertyRating] = None
    rating_note: Optional[str] = None  # e.g. "Insufficient data for rating"

    def to_dict(self):
        d = self.property.to_dict()
        if self.rating:
            d["rating"] = self.rating.to_dict()
        else:
            d["rating"] = None
        d["rating_note"] = self.rating_note
        return d


@dataclass
class SearchParams:
    budget: Optional[float] = None
    property_type: str = "land"  # "land", "apartment", "house", "all"
    districts: list = field(default_factory=list)  # empty = all
    min_size: Optional[float] = None
    max_size: Optional[float] = None
    sort_by: str = "deal_score"  # "deal_score", "growth_score", "price", "size"
    max_pages: int = 5

    def to_dict(self):
        return asdict(self)


@dataclass
class SearchResult:
    properties: list  # list of RatedProperty dicts
    total_count: int
    filtered_count: int
    is_demo_data: bool = False
    error: Optional[str] = None
    search_mode: str = "keyword"  # "ai" or "keyword"
    parsed_params: Optional[dict] = None

    def to_dict(self):
        return {
            "properties": self.properties,
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
            "is_demo_data": self.is_demo_data,
            "error": self.error,
            "search_mode": self.search_mode,
            "parsed_params": self.parsed_params,
        }
