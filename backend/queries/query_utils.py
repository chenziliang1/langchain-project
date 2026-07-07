"""
Shared query utilities — parsing, sanitization, helpers.

Used by both MCP tools (core_tools_v2) and FastAPI DataService.
"""

import re
import unicodedata
from datetime import datetime, timedelta
from typing import Optional, List

# ---------------------------------------------------------------------------
# Data year defaults — all GDELT data is 2024 only
# ---------------------------------------------------------------------------
DEFAULT_DATA_YEAR = "2024"
DEFAULT_DATA_START = "2024-01-01"
DEFAULT_DATA_END = "2024-12-31"
DEFAULT_DATA_REFERENCE = "2024-01-31"


def sanitize_text(text) -> str:
    """Clean illegal characters for safe JSON/markdown output."""
    if text is None:
        return "N/A"
    text = str(text)
    text = text.encode('utf-8', 'ignore').decode('utf-8')
    text = ''.join(
        char for char in text
        if unicodedata.category(char)[0] != 'C' or char in '\n\t\r'
    )
    text = text.replace('\x00', '').replace('|', ' ').replace('\n', ' ')
    return text.strip()


def parse_time_hint(time_hint: Optional[str]) -> tuple[str, str]:
    """Parse time hint into (start_date, end_date) strings.
    All relative dates are anchored to DEFAULT_DATA_REFERENCE (2024)."""
    ref = datetime.strptime(DEFAULT_DATA_REFERENCE, '%Y-%m-%d').date()

    if not time_hint:
        start = ref - timedelta(days=7)
        end = ref
    elif time_hint == 'today':
        start = ref
        end = ref
    elif time_hint == 'yesterday':
        start = ref - timedelta(days=1)
        end = start
    elif time_hint == 'this_week':
        start = ref - timedelta(days=7)
        end = ref
    elif time_hint == 'this_month':
        start = ref - timedelta(days=30)
        end = ref
    elif len(time_hint) == 4 and time_hint.isdigit():
        start = datetime.strptime(time_hint + "-01-01", '%Y-%m-%d').date()
        end = datetime.strptime(time_hint + "-12-31", '%Y-%m-%d').date()
    elif len(time_hint) == 7:
        start = datetime.strptime(time_hint + "-01", '%Y-%m-%d').date()
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    else:
        try:
            start = datetime.strptime(time_hint, '%Y-%m-%d').date()
            end = start
        except Exception:
            start = ref - timedelta(days=7)
            end = ref

    return start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d')


def parse_region_input(region_input: str) -> list[str]:
    """Smart parse region input for index-friendly queries."""
    region = region_input.strip()
    results: set[str] = set()

    # US cities with common aliases/abbreviations
    cn_to_en = {
        # Major US cities
        'Washington': ['Washington', 'DC'],
        'New York': ['New York', 'NYC'],
        'Los Angeles': ['Los Angeles', 'LA'],
        'Chicago': ['Chicago'],
        'Houston': ['Houston'],
        'San Francisco': ['San Francisco', 'SF'],
        'SF': ['San Francisco', 'SF'],
        'NYC': ['New York', 'NYC'],
        'LA': ['Los Angeles', 'LA'],
        'DC': ['Washington', 'DC'],
        'Seattle': ['Seattle'],
        'Boston': ['Boston'],
        'Miami': ['Miami'],
        'Dallas': ['Dallas'],
        'Philadelphia': ['Philadelphia'],
        'Atlanta': ['Atlanta'],
        'Denver': ['Denver'],
        'Phoenix': ['Phoenix'],
        'Detroit': ['Detroit'],
        'Nashville': ['Nashville'],
        'Portland': ['Portland'],
        'San Diego': ['San Diego', 'SD'],
        'Austin': ['Austin'],
        'San Antonio': ['San Antonio'],
        'Oklahoma City': ['Oklahoma City'],
        'Kansas City': ['Kansas City'],
        'Minneapolis': ['Minneapolis'],
        'Cleveland': ['Cleveland'],
        'Pittsburgh': ['Pittsburgh'],
        'Baltimore': ['Baltimore'],
        'Milwaukee': ['Milwaukee'],
        'Tampa': ['Tampa'],
        'Orlando': ['Orlando'],
        'New Orleans': ['New Orleans'],
        'Memphis': ['Memphis'],
        'Louisville': ['Louisville'],
        'Buffalo': ['Buffalo'],
        'Reno': ['Reno'],
        'Albuquerque': ['Albuquerque'],
        'Omaha': ['Omaha'],
        'Tulsa': ['Tulsa'],
        'Colorado Springs': ['Colorado Springs'],
        'Virginia Beach': ['Virginia Beach'],
        'Sacramento': ['Sacramento'],
        'Long Beach': ['Long Beach'],
        'Oakland': ['Oakland'],
        'Fresno': ['Fresno'],
        'Santa Ana': ['Santa Ana'],
        'Riverside': ['Riverside'],
        'Stockton': ['Stockton'],
        'Bakersfield': ['Bakersfield'],
        'Anaheim': ['Anaheim'],
        'Irvine': ['Irvine'],
        'Santa Rosa': ['Santa Rosa'],
        'Pasadena': ['Pasadena'],
        'Thousand Oaks': ['Thousand Oaks'],
        'Visalia': ['Visalia'],
        'Concord': ['Concord'],
        'Santa Clara': ['Santa Clara'],
        'Vallejo': ['Vallejo'],
        'Berkeley': ['Berkeley'],
        'Fairfield': ['Fairfield'],
        'Richmond': ['Richmond'],
        'Carlsbad': ['Carlsbad'],
        'Santa Barbara': ['Santa Barbara'],
        'San Mateo': ['San Mateo'],
        'Santa Maria': ['Santa Maria'],
        'Santa Monica': ['Santa Monica'],
        'Chico': ['Chico'],
        'Newport Beach': ['Newport Beach'],
        'San Leandro': ['San Leandro'],
        'San Marcos': ['San Marcos'],
        'Whittier': ['Whittier'],
        'Redwood City': ['Redwood City'],
        'Mountain View': ['Mountain View'],
        'Palo Alto': ['Palo Alto'],
        'Cupertino': ['Cupertino'],
        'Sunnyvale': ['Sunnyvale'],
        'San Jose': ['San Jose'],
        'Fremont': ['Fremont'],
        'Hayward': ['Hayward'],
        'Elk Grove': ['Elk Grove'],
        'Roseville': ['Roseville'],
        'Modesto': ['Modesto'],
        'Salinas': ['Salinas'],
        'Santa Cruz': ['Santa Cruz'],
        'Merced': ['Merced'],
        'Redding': ['Redding'],
        'Yuba City': ['Yuba City'],
        'Turlock': ['Turlock'],
        'Hanford': ['Hanford'],
        'Madera': ['Madera'],
        'Lodi': ['Lodi'],
        'Tracy': ['Tracy'],
        'Livermore': ['Livermore'],
        'Dublin': ['Dublin'],
        'Pleasanton': ['Pleasanton'],
        'San Ramon': ['San Ramon'],
        'Walnut Creek': ['Walnut Creek'],
        'San Rafael': ['San Rafael'],
        'Novato': ['Novato'],
        'Petaluma': ['Petaluma'],
        'Napa': ['Napa'],
        'Sonoma': ['Sonoma'],
        'Sebastopol': ['Sebastopol'],
        'Healdsburg': ['Healdsburg'],
        'Windsor': ['Windsor'],
        'Cloverdale': ['Cloverdale'],
        'Fort Bragg': ['Fort Bragg'],
        'Ukiah': ['Ukiah'],
        'Willits': ['Willits'],
        'Laytonville': ['Laytonville'],
        'Point Arena': ['Point Arena'],
        'Mendocino': ['Mendocino'],
        'Gualala': ['Gualala'],
        'Boonville': ['Boonville'],
        'Yorkville': ['Yorkville'],
        'Philo': ['Philo'],
        'Navarro': ['Navarro'],
        'Elk': ['Elk'],
        'Manchester': ['Manchester'],
        'Anchor Bay': ['Anchor Bay'],
        'Stewarts Point': ['Stewarts Point'],
        'Sea Ranch': ['Sea Ranch'],
        'Timber Cove': ['Timber Cove'],
        'Cazadero': ['Cazadero'],
        'Duncans Mills': ['Duncans Mills'],
        'Monte Rio': ['Monte Rio'],
        'Guerneville': ['Guerneville'],
        'Forestville': ['Forestville'],
        'Occidental': ['Occidental'],
        'Graton': ['Graton'],
        'Bodega': ['Bodega'],
        'Bodega Bay': ['Bodega Bay'],
        'Valley Ford': ['Valley Ford'],
        'Tomales': ['Tomales'],
        'Dillon Beach': ['Dillon Beach'],
        'Marshall': ['Marshall'],
        'Inverness': ['Inverness'],
        'Point Reyes Station': ['Point Reyes Station'],
        'Olema': ['Olema'],
        'Stinson Beach': ['Stinson Beach'],
        'Bolinas': ['Bolinas'],
        'Muir Beach': ['Muir Beach'],
        'Sausalito': ['Sausalito'],
        'Tiburon': ['Tiburon'],
        'Belvedere': ['Belvedere'],
        'Mill Valley': ['Mill Valley'],
        'Corte Madera': ['Corte Madera'],
        'Larkspur': ['Larkspur'],
        'Greenbrae': ['Greenbrae'],
        'Kentfield': ['Kentfield'],
        'Ross': ['Ross'],
        'San Anselmo': ['San Anselmo'],
        'Fairfax': ['Fairfax'],
        'Woodacre': ['Woodacre'],
        'Forest Knolls': ['Forest Knolls'],
        'Lagunitas': ['Lagunitas'],
        'Nicasio': ['Nicasio'],
        # Countries
        'UScountry': ['United States', 'USA', 'US'],
        'incountry': ['China', 'CHN', 'CN'],
        'yingcountry': ['United Kingdom', 'UK', 'GBR', 'GB'],
        'methodcountry': ['France', 'FRA', 'FR'],
        'virtuecountry': ['Germany', 'DEU', 'DE'],
        'daythis': ['Japan', 'JPN', 'JP'],
        'Rusiasi': ['Russia', 'RUS', 'RU'],
        'addnabig': ['Canada', 'CAN', 'CA'],
        'mowestbrother': ['Mexico', 'MEX', 'MX'],
        'printdegree': ['India', 'IND', 'IN'],
        'aobiglia': ['Australia', 'AUS', 'AU'],
        'bawest': ['Brazil', 'BRA', 'BR'],
        'ineast': ['Middle East', 'Mideast'],
        'Europe': ['Europe', 'European'],
        'Asia': ['Asia', 'Asian'],
        'non-continent': ['Africa', 'African'],
        # US states aliases (for partial matching)
        'virtuestate': ['Texas', 'TX'],
        'Texasi': ['Texas', 'TX'],
        'addstate': ['California', 'CA'],
        'addlifornia': ['California', 'CA'],
        'fostate': ['Florida', 'FL'],
        'foroherereach': ['Florida', 'FL'],
        'binstate': ['Pennsylvania', 'PA'],
        'binximethodvania': ['Pennsylvania', 'PA'],
        'Illinois': ['Illinois', 'IL'],
        'Ohio': ['Ohio', 'OH'],
        'secretxieroot': ['Michigan', 'MI'],
        'Georgia': ['Georgia', 'GA'],
        'northcard': ['North Carolina', 'NC'],
        'southcard': ['South Carolina', 'SC'],
        'Virgivania': ['Virginia', 'VA'],
        'maherelan': ['Maryland', 'MD'],
        'New Jersey': ['New Jersey', 'NJ'],
        'machusetts': ['Massachusetts', 'MA'],
        'Arizothat': ['Arizona', 'AZ'],
        'Colopullmulti': ['Colorado', 'CO'],
        'Utah': ['Utah', 'UT'],
        'withinhuareach': ['Nevada', 'NV'],
        'Oregon': ['Oregon', 'OR'],
        'Washingtonstate': ['Washington State', 'WA'],
        'xiathreatyi': ['Hawaii', 'HI'],
        'apullsiadd': ['Alaska', 'AK'],
    }

    if region in cn_to_en:
        results.update(cn_to_en[region])

    results.add(region)

    region_clean = re.sub(r'\s+(City|County|State)$', '', region, flags=re.IGNORECASE)
    if region_clean != region:
        results.add(region_clean)

    parts = re.split(r'[,\s]+', region)
    for part in parts:
        if part and len(part) > 1:
            results.add(part.strip())
            if part in cn_to_en:
                results.update(cn_to_en[part])

    us_states = {
        'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
        'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
        'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
        'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
        'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
        'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
        'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
        'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
        'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
        'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
        'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
        'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
        'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia',
    }

    upper_region = region.upper()
    if upper_region in us_states:
        results.add(upper_region)
        results.add(us_states[upper_region])
        if upper_region == 'DC':
            results.add('Washington')

    return sorted(list(results))


def calculate_risk_level(intensity: float) -> str:
    if intensity > 7:
        return "extremehigh"
    elif intensity > 5:
        return "high"
    elif intensity > 3:
        return "medium"
    else:
        return "low"
