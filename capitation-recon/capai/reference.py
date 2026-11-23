"""Reference data shared by the generator and the engine (rate-cell dimensions, codes)."""

REGIONS = {
    "R1": "Northwest",
    "R2": "Central",
    "R3": "Southeast",
    "R4": "Metro",
}

CATEGORIES = {
    "CH01": "TANF Child under 1",
    "CH20": "TANF Child 1-20",
    "ADF": "TANF Adult Female 21+",
    "ADM": "TANF Adult Male 21+",
    "SSI": "SSI / ABD Adult",
    "EXP": "Expansion Adult 19-64",
    "FC": "Foster Care",
}

# Header-level (organization) adjustment codes used in the simplified 820
HEADER_ADX = {
    "QW": "Quality withhold",
    "RT": "Retroactive rate settlement (lump sum)",
}

# Member-level adjustment reason codes used in the simplified 820
LINE_ADX = {
    "53": "Remittance for previous underpayment",
    "52": "Credit for previous overpayment (recoupment)",
}

QUALITY_WITHHOLD_PCT = 0.01  # contract term: 1.0% of gross current-month capitation


def cell_id(region: str, category: str) -> str:
    return f"{region}-{category}"


def split_cell(cell: str):
    r, c = cell.split("-", 1)
    return r, c
