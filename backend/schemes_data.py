"""Verified government scheme catalog used by the schemes endpoint.

Keep this catalog small and maintain it against the linked official source pages.
It is intentionally not a fallback API or generated sample data.
"""


SCHEMES = [
    {
        "name": "PM-KISAN",
        "category": "Direct Benefit",
        "description": "Financial support transferred directly to eligible farmer families.",
        "eligibility": "Eligible landholding farmer families, subject to the scheme exclusions.",
        "link": "https://pmkisan.gov.in/",
        "source": "PM-KISAN official portal",
    },
    {
        "name": "Rythu Bharosa",
        "category": "State Support",
        "description": "Investment support for eligible farmers in Andhra Pradesh.",
        "eligibility": "Farmers meeting Andhra Pradesh state scheme requirements.",
        "link": "https://apagrisnet.gov.in/",
        "source": "Andhra Pradesh Agriculture Department",
    },
    {
        "name": "Rythu Bandhu",
        "category": "State Support",
        "description": "Seasonal investment support for eligible farmers in Telangana.",
        "eligibility": "Farmers meeting Telangana state scheme requirements.",
        "link": "https://rythubharosa.telangana.gov.in/",
        "source": "Telangana Rythu Bharosa portal",
    },
    {
        "name": "PMFBY",
        "category": "Crop Insurance",
        "description": "Crop insurance support for notified crops and areas.",
        "eligibility": "Farmers growing notified crops in notified areas.",
        "link": "https://pmfby.gov.in/",
        "source": "PMFBY official portal",
    },
    {
        "name": "Kisan Credit Card",
        "category": "Agricultural Credit",
        "description": "Institutional credit access for agricultural and allied activities.",
        "eligibility": "Eligible owner cultivators, tenants, sharecroppers, and farmer groups.",
        "link": "https://www.jansamarth.in/",
        "source": "JanSamarth government credit portal",
    },
    {
        "name": "Soil Health Card",
        "category": "Soil Advisory",
        "description": "Soil testing results and crop-specific nutrient recommendations.",
        "eligibility": "Farmers using the government soil testing service.",
        "link": "https://soilhealth.dac.gov.in/",
        "source": "Soil Health Card official portal",
    },
    {
        "name": "e-NAM",
        "category": "Market Access",
        "description": "Online agricultural market access and price discovery through participating mandis.",
        "eligibility": "Farmers selling produce through participating APMC mandis.",
        "link": "https://www.enam.gov.in/",
        "source": "e-NAM official portal",
    },
    {
        "name": "PMKSY - Per Drop More Crop",
        "category": "Irrigation Subsidy",
        "description": "Support for efficient irrigation systems such as drip and sprinkler irrigation.",
        "eligibility": "Farmers meeting the applicable state and scheme requirements.",
        "link": "https://pmksy.gov.in/",
        "source": "Pradhan Mantri Krishi Sinchayee Yojana portal",
    },
]


def get_schemes() -> list[dict[str, str]]:
    """Return a copy so API translation cannot mutate the source catalog."""
    return [scheme.copy() for scheme in SCHEMES]
