"""Berlin district reference data for property deal scoring.

Average prices are for residential property (2025 values).
Growth trends are annual multipliers (1.08 = 8% YoY growth).
"""

BERLIN_DISTRICTS = {
    "Mitte": {
        "avg_price_m2": 7800,
        "growth_trend": 1.02,
        "tier": "premium",
    },
    "Prenzlauer Berg": {
        "avg_price_m2": 6150,
        "growth_trend": 1.01,
        "tier": "premium",
    },
    "Charlottenburg": {
        "avg_price_m2": 6100,
        "growth_trend": 1.00,
        "tier": "premium",
    },
    "Kreuzberg": {
        "avg_price_m2": 6100,
        "growth_trend": 1.03,
        "tier": "premium",
    },
    "Friedrichshain": {
        "avg_price_m2": 5900,
        "growth_trend": 1.04,
        "tier": "high",
    },
    "Charlottenburg-Wilmersdorf": {
        "avg_price_m2": 5886,
        "growth_trend": 1.00,
        "tier": "high",
    },
    "Wilmersdorf": {
        "avg_price_m2": 5886,
        "growth_trend": 1.00,
        "tier": "high",
    },
    "Schoeneberg": {
        "avg_price_m2": 5500,
        "growth_trend": 1.01,
        "tier": "high",
    },
    "Tempelhof-Schoeneberg": {
        "avg_price_m2": 4500,
        "growth_trend": 1.03,
        "tier": "mid",
    },
    "Pankow": {
        "avg_price_m2": 4867,
        "growth_trend": 1.05,
        "tier": "mid",
    },
    "Steglitz-Zehlendorf": {
        "avg_price_m2": 4800,
        "growth_trend": 1.02,
        "tier": "mid",
    },
    "Steglitz": {
        "avg_price_m2": 4800,
        "growth_trend": 1.02,
        "tier": "mid",
    },
    "Zehlendorf": {
        "avg_price_m2": 4800,
        "growth_trend": 1.02,
        "tier": "mid",
    },
    "Lichtenberg": {
        "avg_price_m2": 4574,
        "growth_trend": 1.06,
        "tier": "mid",
    },
    "Tempelhof": {
        "avg_price_m2": 4500,
        "growth_trend": 1.03,
        "tier": "mid",
    },
    "Neukoelln": {
        "avg_price_m2": 4300,
        "growth_trend": 1.07,
        "tier": "emerging",
    },
    "Treptow-Koepenick": {
        "avg_price_m2": 4200,
        "growth_trend": 1.08,
        "tier": "emerging",
    },
    "Treptow": {
        "avg_price_m2": 4200,
        "growth_trend": 1.08,
        "tier": "emerging",
    },
    "Koepenick": {
        "avg_price_m2": 4200,
        "growth_trend": 1.08,
        "tier": "emerging",
    },
    "Friedrichshain-Kreuzberg": {
        "avg_price_m2": 6000,
        "growth_trend": 1.035,
        "tier": "high",
    },
    "Spandau": {
        "avg_price_m2": 3800,
        "growth_trend": 1.04,
        "tier": "emerging",
    },
    "Reinickendorf": {
        "avg_price_m2": 3636,
        "growth_trend": 1.03,
        "tier": "budget",
    },
    "Marzahn-Hellersdorf": {
        "avg_price_m2": 3160,
        "growth_trend": 1.05,
        "tier": "budget",
    },
    "Marzahn": {
        "avg_price_m2": 3160,
        "growth_trend": 1.05,
        "tier": "budget",
    },
    "Hellersdorf": {
        "avg_price_m2": 3160,
        "growth_trend": 1.05,
        "tier": "budget",
    },
    "Wedding": {
        "avg_price_m2": 5200,
        "growth_trend": 1.04,
        "tier": "mid",
    },
    "Moabit": {
        "avg_price_m2": 5800,
        "growth_trend": 1.02,
        "tier": "high",
    },
}

# Also support common German-character variants
_UMLAUT_ALIASES = {
    "Schöneberg": "Schoeneberg",
    "Tempelhof-Schöneberg": "Tempelhof-Schoeneberg",
    "Neukölln": "Neukoelln",
    "Treptow-Köpenick": "Treptow-Koepenick",
    "Köpenick": "Koepenick",
}

for umlaut_name, ascii_name in _UMLAUT_ALIASES.items():
    if ascii_name in BERLIN_DISTRICTS:
        BERLIN_DISTRICTS[umlaut_name] = BERLIN_DISTRICTS[ascii_name]


# Berlin postcodes to district mapping
POSTCODE_TO_DISTRICT = {
    # Mitte
    "10115": "Mitte", "10117": "Mitte", "10119": "Mitte",
    "10178": "Mitte", "10179": "Mitte", "10785": "Mitte",
    "13347": "Mitte", "13349": "Mitte", "13351": "Mitte",
    "13353": "Mitte", "13355": "Mitte", "13357": "Mitte",
    "13359": "Mitte",
    # Prenzlauer Berg
    "10405": "Prenzlauer Berg", "10407": "Prenzlauer Berg",
    "10409": "Prenzlauer Berg", "10435": "Prenzlauer Berg",
    "10437": "Prenzlauer Berg", "10439": "Prenzlauer Berg",
    "10440": "Prenzlauer Berg",
    # Friedrichshain
    "10243": "Friedrichshain", "10245": "Friedrichshain",
    "10247": "Friedrichshain", "10249": "Friedrichshain",
    # Kreuzberg
    "10961": "Kreuzberg", "10963": "Kreuzberg", "10965": "Kreuzberg",
    "10967": "Kreuzberg", "10969": "Kreuzberg", "10997": "Kreuzberg",
    "10999": "Kreuzberg",
    # Charlottenburg
    "10585": "Charlottenburg", "10587": "Charlottenburg",
    "10589": "Charlottenburg", "10623": "Charlottenburg",
    "10625": "Charlottenburg", "10627": "Charlottenburg",
    "10629": "Charlottenburg", "14059": "Charlottenburg",
    # Wilmersdorf
    "10707": "Wilmersdorf", "10709": "Wilmersdorf",
    "10711": "Wilmersdorf", "10713": "Wilmersdorf",
    "10715": "Wilmersdorf", "10717": "Wilmersdorf",
    "10719": "Wilmersdorf",
    # Schoeneberg
    "10777": "Schoeneberg", "10779": "Schoeneberg",
    "10781": "Schoeneberg", "10783": "Schoeneberg",
    "10787": "Schoeneberg", "10789": "Schoeneberg",
    "10823": "Schoeneberg", "10825": "Schoeneberg",
    "10827": "Schoeneberg", "10829": "Schoeneberg",
    # Tempelhof
    "12099": "Tempelhof", "12101": "Tempelhof",
    "12103": "Tempelhof", "12105": "Tempelhof",
    "12107": "Tempelhof", "12109": "Tempelhof",
    # Neukoelln
    "12043": "Neukoelln", "12045": "Neukoelln",
    "12047": "Neukoelln", "12049": "Neukoelln",
    "12051": "Neukoelln", "12053": "Neukoelln",
    "12055": "Neukoelln", "12057": "Neukoelln",
    "12059": "Neukoelln",
    # Treptow
    "12435": "Treptow", "12437": "Treptow",
    "12439": "Treptow", "12459": "Treptow",
    # Koepenick
    "12555": "Koepenick", "12557": "Koepenick",
    "12559": "Koepenick", "12587": "Koepenick",
    "12589": "Koepenick",
    # Pankow
    "10439": "Pankow", "13086": "Pankow", "13088": "Pankow",
    "13089": "Pankow", "13125": "Pankow", "13127": "Pankow",
    "13129": "Pankow", "13156": "Pankow", "13158": "Pankow",
    "13159": "Pankow", "13187": "Pankow", "13189": "Pankow",
    # Lichtenberg
    "10315": "Lichtenberg", "10317": "Lichtenberg",
    "10318": "Lichtenberg", "10319": "Lichtenberg",
    "10365": "Lichtenberg", "10367": "Lichtenberg",
    "10369": "Lichtenberg",
    # Spandau
    "13581": "Spandau", "13583": "Spandau", "13585": "Spandau",
    "13587": "Spandau", "13589": "Spandau", "13591": "Spandau",
    "13593": "Spandau", "13595": "Spandau", "13597": "Spandau",
    "13599": "Spandau", "14052": "Spandau",
    # Steglitz
    "12157": "Steglitz", "12161": "Steglitz", "12163": "Steglitz",
    "12165": "Steglitz", "12167": "Steglitz", "12169": "Steglitz",
    # Zehlendorf
    "14109": "Zehlendorf", "14129": "Zehlendorf",
    "14163": "Zehlendorf", "14165": "Zehlendorf",
    "14167": "Zehlendorf", "14169": "Zehlendorf",
    # Reinickendorf
    "13403": "Reinickendorf", "13405": "Reinickendorf",
    "13407": "Reinickendorf", "13409": "Reinickendorf",
    "13435": "Reinickendorf", "13437": "Reinickendorf",
    "13439": "Reinickendorf", "13465": "Reinickendorf",
    "13467": "Reinickendorf", "13469": "Reinickendorf",
    "13503": "Reinickendorf", "13505": "Reinickendorf",
    "13507": "Reinickendorf", "13509": "Reinickendorf",
    # Marzahn-Hellersdorf
    "12619": "Marzahn", "12621": "Marzahn", "12623": "Marzahn",
    "12627": "Marzahn", "12629": "Marzahn",
    "12679": "Marzahn", "12681": "Marzahn", "12683": "Marzahn",
    "12685": "Marzahn", "12687": "Marzahn", "12689": "Marzahn",
    # Wedding / Moabit
    "13347": "Wedding", "13349": "Wedding", "13351": "Wedding",
    "13353": "Wedding", "13359": "Wedding",
    "10551": "Moabit", "10553": "Moabit", "10555": "Moabit",
    "10557": "Moabit", "10559": "Moabit",
}


# Each Ortsteil (small neighborhood, the value in POSTCODE_TO_DISTRICT) belongs
# to one of the 12 modern Berlin Bezirke. This is the bridge that lets the
# search filter work geographically rather than as a string match.
ORTSTEIL_TO_BEZIRK = {
    "Mitte": "Mitte",
    "Wedding": "Mitte",
    "Moabit": "Mitte",
    "Tiergarten": "Mitte",
    "Hansaviertel": "Mitte",

    "Friedrichshain": "Friedrichshain-Kreuzberg",
    "Kreuzberg": "Friedrichshain-Kreuzberg",

    "Pankow": "Pankow",
    "Prenzlauer Berg": "Pankow",
    "Weissensee": "Pankow",

    "Charlottenburg": "Charlottenburg-Wilmersdorf",
    "Wilmersdorf": "Charlottenburg-Wilmersdorf",
    "Halensee": "Charlottenburg-Wilmersdorf",
    "Schmargendorf": "Charlottenburg-Wilmersdorf",
    "Grunewald": "Charlottenburg-Wilmersdorf",
    "Westend": "Charlottenburg-Wilmersdorf",

    "Spandau": "Spandau",

    "Steglitz": "Steglitz-Zehlendorf",
    "Zehlendorf": "Steglitz-Zehlendorf",
    "Lichterfelde": "Steglitz-Zehlendorf",
    "Lankwitz": "Steglitz-Zehlendorf",
    "Dahlem": "Steglitz-Zehlendorf",
    "Nikolassee": "Steglitz-Zehlendorf",
    "Wannsee": "Steglitz-Zehlendorf",

    "Schoeneberg": "Tempelhof-Schoeneberg",
    "Tempelhof": "Tempelhof-Schoeneberg",
    "Friedenau": "Tempelhof-Schoeneberg",
    "Mariendorf": "Tempelhof-Schoeneberg",
    "Marienfelde": "Tempelhof-Schoeneberg",
    "Lichtenrade": "Tempelhof-Schoeneberg",

    "Neukoelln": "Neukoelln",
    "Britz": "Neukoelln",
    "Buckow": "Neukoelln",
    "Rudow": "Neukoelln",
    "Gropiusstadt": "Neukoelln",

    "Treptow": "Treptow-Koepenick",
    "Koepenick": "Treptow-Koepenick",
    "Adlershof": "Treptow-Koepenick",
    "Baumschulenweg": "Treptow-Koepenick",
    "Johannisthal": "Treptow-Koepenick",
    "Friedrichshagen": "Treptow-Koepenick",
    "Rahnsdorf": "Treptow-Koepenick",
    "Mueggelheim": "Treptow-Koepenick",
    "Gruenau": "Treptow-Koepenick",
    "Schmoeckwitz": "Treptow-Koepenick",
    "Altglienicke": "Treptow-Koepenick",
    "Bohnsdorf": "Treptow-Koepenick",
    "Niederschoeneweide": "Treptow-Koepenick",
    "Oberschoeneweide": "Treptow-Koepenick",

    "Marzahn": "Marzahn-Hellersdorf",
    "Hellersdorf": "Marzahn-Hellersdorf",
    "Biesdorf": "Marzahn-Hellersdorf",
    "Kaulsdorf": "Marzahn-Hellersdorf",
    "Mahlsdorf": "Marzahn-Hellersdorf",

    "Lichtenberg": "Lichtenberg",
    "Karlshorst": "Lichtenberg",
    "Friedrichsfelde": "Lichtenberg",
    "Hohenschoenhausen": "Lichtenberg",
    "Rummelsburg": "Lichtenberg",
    "Fennpfuhl": "Lichtenberg",
    "Malchow": "Lichtenberg",

    "Reinickendorf": "Reinickendorf",
    "Tegel": "Reinickendorf",
    "Frohnau": "Reinickendorf",
    "Hermsdorf": "Reinickendorf",
    "Waidmannslust": "Reinickendorf",
    "Wittenau": "Reinickendorf",
    "Heiligensee": "Reinickendorf",
}


# Authoritative postcode → Bezirk mapping for all of Berlin. Some postcodes
# straddle Bezirk borders; in those cases the dominant Bezirk is used.
POSTCODE_TO_BEZIRK = {
    # Mitte
    **{pc: "Mitte" for pc in [
        "10115", "10117", "10119", "10178", "10179",
        "10551", "10553", "10555", "10557", "10559",
        "10785",
        "13347", "13349", "13351", "13353", "13355", "13357", "13359",
    ]},
    # Friedrichshain-Kreuzberg
    **{pc: "Friedrichshain-Kreuzberg" for pc in [
        "10243", "10245", "10247", "10249",
        "10961", "10963", "10965", "10967", "10969",
        "10997", "10999",
    ]},
    # Pankow
    **{pc: "Pankow" for pc in [
        "10405", "10407", "10409", "10435", "10437", "10439",
        "13086", "13087", "13088", "13089",
        "13125", "13127", "13129",
        "13156", "13158", "13159", "13187", "13189",
    ]},
    # Charlottenburg-Wilmersdorf
    **{pc: "Charlottenburg-Wilmersdorf" for pc in [
        "10585", "10587", "10589", "10623", "10625", "10627", "10629",
        "10707", "10709", "10711", "10713", "10715", "10717", "10719",
        "10787", "10789",
        "14050", "14052", "14053", "14055", "14057", "14059",
        "14193", "14199",
    ]},
    # Spandau
    **{pc: "Spandau" for pc in [
        "13581", "13583", "13585", "13587", "13589",
        "13591", "13593", "13595", "13597", "13599",
        "14089",
    ]},
    # Steglitz-Zehlendorf
    **{pc: "Steglitz-Zehlendorf" for pc in [
        "12157", "12161", "12163", "12165", "12167", "12169",
        "12203", "12205", "12207", "12209", "12247", "12249",
        "14109", "14129", "14163", "14165", "14167", "14169",
        "14195",
    ]},
    # Tempelhof-Schöneberg
    **{pc: "Tempelhof-Schoeneberg" for pc in [
        "10777", "10779", "10781", "10783",
        "10825", "10827", "10829",
        "12099", "12101", "12103", "12105", "12107", "12109", "12159",
        "12277", "12279", "12305", "12307", "12309",
    ]},
    # Neukölln
    **{pc: "Neukoelln" for pc in [
        "12043", "12045", "12047", "12049", "12051", "12053",
        "12055", "12057", "12059",
        "12347", "12349", "12351", "12353", "12355", "12357", "12359",
    ]},
    # Treptow-Köpenick
    **{pc: "Treptow-Koepenick" for pc in [
        "12435", "12437", "12439", "12459",
        "12487", "12489", "12524", "12526", "12527",
        "12555", "12557", "12559", "12587", "12589",
    ]},
    # Marzahn-Hellersdorf
    **{pc: "Marzahn-Hellersdorf" for pc in [
        "12619", "12621", "12623", "12627", "12629",
        "12679", "12681", "12683", "12685", "12687", "12689",
    ]},
    # Lichtenberg
    **{pc: "Lichtenberg" for pc in [
        "10315", "10317", "10318", "10319",
        "10365", "10367", "10369",
        "13051", "13053", "13055", "13057", "13059",
    ]},
    # Reinickendorf
    **{pc: "Reinickendorf" for pc in [
        "13403", "13405", "13407", "13409",
        "13435", "13437", "13439", "13465", "13467", "13469",
        "13503", "13505", "13507", "13509",
        "13627", "13629",
    ]},
}


# Adjacency graph for the 12 Berlin Bezirke. Used to expand "near X" filters
# into the reference Bezirk plus its physical neighbors.
BEZIRK_NEIGHBORS = {
    "Mitte": ["Friedrichshain-Kreuzberg", "Pankow", "Charlottenburg-Wilmersdorf",
              "Tempelhof-Schoeneberg", "Reinickendorf"],
    "Friedrichshain-Kreuzberg": ["Mitte", "Pankow", "Lichtenberg",
                                 "Treptow-Koepenick", "Neukoelln",
                                 "Tempelhof-Schoeneberg"],
    "Pankow": ["Mitte", "Friedrichshain-Kreuzberg", "Lichtenberg",
               "Reinickendorf"],
    "Charlottenburg-Wilmersdorf": ["Mitte", "Reinickendorf", "Spandau",
                                   "Steglitz-Zehlendorf",
                                   "Tempelhof-Schoeneberg"],
    "Spandau": ["Charlottenburg-Wilmersdorf", "Reinickendorf",
                "Steglitz-Zehlendorf"],
    "Steglitz-Zehlendorf": ["Charlottenburg-Wilmersdorf",
                             "Tempelhof-Schoeneberg", "Spandau", "Neukoelln"],
    "Tempelhof-Schoeneberg": ["Mitte", "Friedrichshain-Kreuzberg",
                               "Charlottenburg-Wilmersdorf",
                               "Steglitz-Zehlendorf", "Neukoelln"],
    "Neukoelln": ["Friedrichshain-Kreuzberg", "Tempelhof-Schoeneberg",
                  "Steglitz-Zehlendorf", "Treptow-Koepenick"],
    "Treptow-Koepenick": ["Friedrichshain-Kreuzberg", "Lichtenberg",
                          "Marzahn-Hellersdorf", "Neukoelln"],
    "Marzahn-Hellersdorf": ["Lichtenberg", "Treptow-Koepenick"],
    "Lichtenberg": ["Friedrichshain-Kreuzberg", "Pankow",
                    "Treptow-Koepenick", "Marzahn-Hellersdorf"],
    "Reinickendorf": ["Mitte", "Pankow", "Charlottenburg-Wilmersdorf",
                      "Spandau"],
}


def near_bezirke(reference: str) -> list[str]:
    """Expand a 'near X' reference (Ortsteil, Bezirk, or postcode) to the set
    of Bezirke that count as nearby — the reference's own Bezirk plus its
    geographic neighbors. Returns [] if the reference can't be resolved.
    """
    bz = resolve_bezirk(reference if reference and reference.isdigit() else None,
                        reference)
    if not bz:
        return []
    return [bz] + BEZIRK_NEIGHBORS.get(bz, [])


def resolve_bezirk(postcode: str | None, district: str | None) -> str | None:
    """Resolve a property's Bezirk from postcode (preferred) or district string.
    Returns one of the 12 modern Berlin Bezirke names, or None.
    """
    if postcode:
        bz = POSTCODE_TO_BEZIRK.get(postcode.strip())
        if bz:
            return bz
        # Fall back to the legacy postcode-to-Ortsteil table, then upgrade.
        ortsteil = POSTCODE_TO_DISTRICT.get(postcode.strip())
        if ortsteil:
            return ORTSTEIL_TO_BEZIRK.get(ortsteil, ortsteil)
    if district:
        if district in ORTSTEIL_TO_BEZIRK.values():
            return district
        return ORTSTEIL_TO_BEZIRK.get(district)
    return None


def identify_district(address: str, postcode: str = None) -> str | None:
    """Match an address string or postcode to a Berlin district."""
    # Try substring match on district names first
    address_lower = address.lower() if address else ""

    # Check all district names (longest first to match e.g. "Treptow-Koepenick" before "Treptow")
    sorted_names = sorted(BERLIN_DISTRICTS.keys(), key=len, reverse=True)
    for name in sorted_names:
        if name.lower() in address_lower:
            return name

    # Fallback: try postcode lookup
    if postcode:
        clean_postcode = postcode.strip()
        if clean_postcode in POSTCODE_TO_DISTRICT:
            return POSTCODE_TO_DISTRICT[clean_postcode]

    # Try to extract postcode from address (5-digit number)
    import re
    match = re.search(r"\b(\d{5})\b", address or "")
    if match:
        extracted = match.group(1)
        if extracted in POSTCODE_TO_DISTRICT:
            return POSTCODE_TO_DISTRICT[extracted]

    return None


def get_district_data(district_name: str) -> dict | None:
    """Get reference data for a district."""
    return BERLIN_DISTRICTS.get(district_name)


def get_all_district_names() -> list[str]:
    """Return canonical district names (no aliases)."""
    seen = set()
    canonical = []
    for name, data in BERLIN_DISTRICTS.items():
        key = (data["avg_price_m2"], data["tier"])
        if key not in seen or "-" in name:  # prefer compound names
            seen.add(key)
            canonical.append(name)
    # Deduplicate and sort
    return sorted(set(canonical))


def get_districts_summary() -> list[dict]:
    """Return district data for the frontend reference table."""
    seen = set()
    result = []
    # Show the main 12 administrative districts + key neighborhoods
    priority_names = [
        "Mitte", "Friedrichshain-Kreuzberg", "Pankow",
        "Charlottenburg-Wilmersdorf", "Spandau", "Steglitz-Zehlendorf",
        "Tempelhof-Schoeneberg", "Neukoelln", "Treptow-Koepenick",
        "Marzahn-Hellersdorf", "Lichtenberg", "Reinickendorf",
        "Prenzlauer Berg", "Kreuzberg", "Friedrichshain",
        "Wedding", "Moabit",
    ]
    for name in priority_names:
        if name in BERLIN_DISTRICTS and name not in seen:
            seen.add(name)
            data = BERLIN_DISTRICTS[name]
            result.append({
                "name": name,
                "avg_price_m2": data["avg_price_m2"],
                "growth_pct": round((data["growth_trend"] - 1) * 100, 1),
                "tier": data["tier"],
            })
    return result
