"""Curated city database for the Bypass-IP geo override.

Purpose: the user's VM lives at one real IP (say us-central1), but they
want a phone that *feels like* it's elsewhere — locale, timezone, GPS —
while still egressing through the VM's own network. The ipapi.co lookup
gives us the VM's real city; this table lets the UI override it with any
major city the user picks.

~250 entries covering the most common farming targets. Keys:
  country:  ISO country name from locales.py (e.g. 'United States')
  city:     plain English, UI displays as-is
Values:
  latitude, longitude (WGS-84), timezone (IANA)

If a city the user wants isn't here, the modal also accepts raw
lat/lon + timezone as a free-form fallback.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    country: str
    name: str
    latitude: float
    longitude: float
    timezone: str


_CITIES: list[City] = [
    # United States (35)
    City("United States", "New York", 40.7128, -74.0060, "America/New_York"),
    City("United States", "Los Angeles", 34.0522, -118.2437, "America/Los_Angeles"),
    City("United States", "Chicago", 41.8781, -87.6298, "America/Chicago"),
    City("United States", "Houston", 29.7604, -95.3698, "America/Chicago"),
    City("United States", "Phoenix", 33.4484, -112.0740, "America/Phoenix"),
    City("United States", "Philadelphia", 39.9526, -75.1652, "America/New_York"),
    City("United States", "San Antonio", 29.4241, -98.4936, "America/Chicago"),
    City("United States", "San Diego", 32.7157, -117.1611, "America/Los_Angeles"),
    City("United States", "Dallas", 32.7767, -96.7970, "America/Chicago"),
    City("United States", "San Jose", 37.3382, -121.8863, "America/Los_Angeles"),
    City("United States", "Austin", 30.2672, -97.7431, "America/Chicago"),
    City("United States", "Jacksonville", 30.3322, -81.6557, "America/New_York"),
    City("United States", "Fort Worth", 32.7555, -97.3308, "America/Chicago"),
    City("United States", "Columbus", 39.9612, -82.9988, "America/New_York"),
    City("United States", "Charlotte", 35.2271, -80.8431, "America/New_York"),
    City("United States", "Indianapolis", 39.7684, -86.1581, "America/Indiana/Indianapolis"),
    City("United States", "San Francisco", 37.7749, -122.4194, "America/Los_Angeles"),
    City("United States", "Seattle", 47.6062, -122.3321, "America/Los_Angeles"),
    City("United States", "Denver", 39.7392, -104.9903, "America/Denver"),
    City("United States", "Washington", 38.9072, -77.0369, "America/New_York"),
    City("United States", "Boston", 42.3601, -71.0589, "America/New_York"),
    City("United States", "Nashville", 36.1627, -86.7816, "America/Chicago"),
    City("United States", "El Paso", 31.7619, -106.4850, "America/Denver"),
    City("United States", "Detroit", 42.3314, -83.0458, "America/Detroit"),
    City("United States", "Memphis", 35.1495, -90.0490, "America/Chicago"),
    City("United States", "Portland", 45.5152, -122.6784, "America/Los_Angeles"),
    City("United States", "Las Vegas", 36.1699, -115.1398, "America/Los_Angeles"),
    City("United States", "Louisville", 38.2527, -85.7585, "America/Kentucky/Louisville"),
    City("United States", "Baltimore", 39.2904, -76.6122, "America/New_York"),
    City("United States", "Milwaukee", 43.0389, -87.9065, "America/Chicago"),
    City("United States", "Albuquerque", 35.0844, -106.6504, "America/Denver"),
    City("United States", "Atlanta", 33.7490, -84.3880, "America/New_York"),
    City("United States", "Miami", 25.7617, -80.1918, "America/New_York"),
    City("United States", "Minneapolis", 44.9778, -93.2650, "America/Chicago"),
    City("United States", "Honolulu", 21.3069, -157.8583, "Pacific/Honolulu"),
    # Canada
    City("Canada", "Toronto", 43.6532, -79.3832, "America/Toronto"),
    City("Canada", "Montreal", 45.5017, -73.5673, "America/Toronto"),
    City("Canada", "Vancouver", 49.2827, -123.1207, "America/Vancouver"),
    City("Canada", "Calgary", 51.0447, -114.0719, "America/Edmonton"),
    City("Canada", "Ottawa", 45.4215, -75.6972, "America/Toronto"),
    City("Canada", "Edmonton", 53.5461, -113.4938, "America/Edmonton"),
    City("Canada", "Winnipeg", 49.8951, -97.1384, "America/Winnipeg"),
    City("Canada", "Halifax", 44.6488, -63.5752, "America/Halifax"),
    # United Kingdom
    City("United Kingdom", "London", 51.5074, -0.1278, "Europe/London"),
    City("United Kingdom", "Manchester", 53.4808, -2.2426, "Europe/London"),
    City("United Kingdom", "Birmingham", 52.4862, -1.8904, "Europe/London"),
    City("United Kingdom", "Liverpool", 53.4084, -2.9916, "Europe/London"),
    City("United Kingdom", "Leeds", 53.8008, -1.5491, "Europe/London"),
    City("United Kingdom", "Glasgow", 55.8642, -4.2518, "Europe/London"),
    City("United Kingdom", "Edinburgh", 55.9533, -3.1883, "Europe/London"),
    City("United Kingdom", "Bristol", 51.4545, -2.5879, "Europe/London"),
    City("United Kingdom", "Cardiff", 51.4816, -3.1791, "Europe/London"),
    City("United Kingdom", "Belfast", 54.5973, -5.9301, "Europe/London"),
    # Ireland
    City("Ireland", "Dublin", 53.3498, -6.2603, "Europe/Dublin"),
    City("Ireland", "Cork", 51.8985, -8.4756, "Europe/Dublin"),
    City("Ireland", "Galway", 53.2707, -9.0568, "Europe/Dublin"),
    # Germany
    City("Germany", "Berlin", 52.5200, 13.4050, "Europe/Berlin"),
    City("Germany", "Hamburg", 53.5511, 9.9937, "Europe/Berlin"),
    City("Germany", "Munich", 48.1351, 11.5820, "Europe/Berlin"),
    City("Germany", "Cologne", 50.9375, 6.9603, "Europe/Berlin"),
    City("Germany", "Frankfurt", 50.1109, 8.6821, "Europe/Berlin"),
    City("Germany", "Stuttgart", 48.7758, 9.1829, "Europe/Berlin"),
    City("Germany", "Düsseldorf", 51.2277, 6.7735, "Europe/Berlin"),
    City("Germany", "Leipzig", 51.3397, 12.3731, "Europe/Berlin"),
    City("Germany", "Dortmund", 51.5136, 7.4653, "Europe/Berlin"),
    # France
    City("France", "Paris", 48.8566, 2.3522, "Europe/Paris"),
    City("France", "Marseille", 43.2965, 5.3698, "Europe/Paris"),
    City("France", "Lyon", 45.7640, 4.8357, "Europe/Paris"),
    City("France", "Toulouse", 43.6047, 1.4442, "Europe/Paris"),
    City("France", "Nice", 43.7102, 7.2620, "Europe/Paris"),
    City("France", "Nantes", 47.2184, -1.5536, "Europe/Paris"),
    City("France", "Strasbourg", 48.5734, 7.7521, "Europe/Paris"),
    City("France", "Bordeaux", 44.8378, -0.5792, "Europe/Paris"),
    # Netherlands
    City("Netherlands", "Amsterdam", 52.3676, 4.9041, "Europe/Amsterdam"),
    City("Netherlands", "Rotterdam", 51.9244, 4.4777, "Europe/Amsterdam"),
    City("Netherlands", "The Hague", 52.0705, 4.3007, "Europe/Amsterdam"),
    City("Netherlands", "Utrecht", 52.0907, 5.1214, "Europe/Amsterdam"),
    City("Netherlands", "Eindhoven", 51.4416, 5.4697, "Europe/Amsterdam"),
    # Spain
    City("Spain", "Madrid", 40.4168, -3.7038, "Europe/Madrid"),
    City("Spain", "Barcelona", 41.3851, 2.1734, "Europe/Madrid"),
    City("Spain", "Valencia", 39.4699, -0.3763, "Europe/Madrid"),
    City("Spain", "Seville", 37.3891, -5.9845, "Europe/Madrid"),
    City("Spain", "Zaragoza", 41.6488, -0.8891, "Europe/Madrid"),
    City("Spain", "Málaga", 36.7213, -4.4214, "Europe/Madrid"),
    City("Spain", "Bilbao", 43.2630, -2.9350, "Europe/Madrid"),
    # Italy
    City("Italy", "Rome", 41.9028, 12.4964, "Europe/Rome"),
    City("Italy", "Milan", 45.4642, 9.1900, "Europe/Rome"),
    City("Italy", "Naples", 40.8518, 14.2681, "Europe/Rome"),
    City("Italy", "Turin", 45.0703, 7.6869, "Europe/Rome"),
    City("Italy", "Florence", 43.7696, 11.2558, "Europe/Rome"),
    City("Italy", "Bologna", 44.4949, 11.3426, "Europe/Rome"),
    City("Italy", "Venice", 45.4408, 12.3155, "Europe/Rome"),
    # Portugal
    City("Portugal", "Lisbon", 38.7223, -9.1393, "Europe/Lisbon"),
    City("Portugal", "Porto", 41.1579, -8.6291, "Europe/Lisbon"),
    # Switzerland / Austria / Belgium
    City("Switzerland", "Zurich", 47.3769, 8.5417, "Europe/Zurich"),
    City("Switzerland", "Geneva", 46.2044, 6.1432, "Europe/Zurich"),
    City("Switzerland", "Bern", 46.9481, 7.4474, "Europe/Zurich"),
    City("Austria", "Vienna", 48.2082, 16.3738, "Europe/Vienna"),
    City("Austria", "Salzburg", 47.8095, 13.0550, "Europe/Vienna"),
    City("Austria", "Graz", 47.0707, 15.4395, "Europe/Vienna"),
    City("Belgium", "Brussels", 50.8503, 4.3517, "Europe/Brussels"),
    City("Belgium", "Antwerp", 51.2194, 4.4025, "Europe/Brussels"),
    # Nordic
    City("Sweden", "Stockholm", 59.3293, 18.0686, "Europe/Stockholm"),
    City("Sweden", "Gothenburg", 57.7089, 11.9746, "Europe/Stockholm"),
    City("Sweden", "Malmö", 55.6050, 13.0038, "Europe/Stockholm"),
    City("Norway", "Oslo", 59.9139, 10.7522, "Europe/Oslo"),
    City("Norway", "Bergen", 60.3913, 5.3221, "Europe/Oslo"),
    City("Denmark", "Copenhagen", 55.6761, 12.5683, "Europe/Copenhagen"),
    City("Denmark", "Aarhus", 56.1629, 10.2039, "Europe/Copenhagen"),
    City("Finland", "Helsinki", 60.1699, 24.9384, "Europe/Helsinki"),
    City("Finland", "Tampere", 61.4978, 23.7610, "Europe/Helsinki"),
    # Eastern Europe
    City("Poland", "Warsaw", 52.2297, 21.0122, "Europe/Warsaw"),
    City("Poland", "Kraków", 50.0647, 19.9450, "Europe/Warsaw"),
    City("Poland", "Wrocław", 51.1079, 17.0385, "Europe/Warsaw"),
    City("Poland", "Poznań", 52.4064, 16.9252, "Europe/Warsaw"),
    City("Poland", "Gdańsk", 54.3520, 18.6466, "Europe/Warsaw"),
    City("Czech Republic", "Prague", 50.0755, 14.4378, "Europe/Prague"),
    City("Czech Republic", "Brno", 49.1951, 16.6068, "Europe/Prague"),
    City("Slovakia", "Bratislava", 48.1486, 17.1077, "Europe/Bratislava"),
    City("Hungary", "Budapest", 47.4979, 19.0402, "Europe/Budapest"),
    City("Romania", "Bucharest", 44.4268, 26.1025, "Europe/Bucharest"),
    City("Romania", "Cluj-Napoca", 46.7712, 23.6236, "Europe/Bucharest"),
    City("Bulgaria", "Sofia", 42.6977, 23.3219, "Europe/Sofia"),
    City("Greece", "Athens", 37.9838, 23.7275, "Europe/Athens"),
    City("Greece", "Thessaloniki", 40.6401, 22.9444, "Europe/Athens"),
    # Turkey / Russia / Ukraine
    City("Turkey", "Istanbul", 41.0082, 28.9784, "Europe/Istanbul"),
    City("Turkey", "Ankara", 39.9334, 32.8597, "Europe/Istanbul"),
    City("Turkey", "Izmir", 38.4192, 27.1287, "Europe/Istanbul"),
    City("Russia", "Moscow", 55.7558, 37.6173, "Europe/Moscow"),
    City("Russia", "Saint Petersburg", 59.9311, 30.3609, "Europe/Moscow"),
    City("Ukraine", "Kyiv", 50.4501, 30.5234, "Europe/Kyiv"),
    City("Ukraine", "Lviv", 49.8397, 24.0297, "Europe/Kyiv"),
    # Asia - East
    City("Japan", "Tokyo", 35.6762, 139.6503, "Asia/Tokyo"),
    City("Japan", "Osaka", 34.6937, 135.5023, "Asia/Tokyo"),
    City("Japan", "Yokohama", 35.4437, 139.6380, "Asia/Tokyo"),
    City("Japan", "Nagoya", 35.1815, 136.9066, "Asia/Tokyo"),
    City("Japan", "Sapporo", 43.0621, 141.3544, "Asia/Tokyo"),
    City("Japan", "Kyoto", 35.0116, 135.7681, "Asia/Tokyo"),
    City("Japan", "Fukuoka", 33.5904, 130.4017, "Asia/Tokyo"),
    City("South Korea", "Seoul", 37.5665, 126.9780, "Asia/Seoul"),
    City("South Korea", "Busan", 35.1796, 129.0756, "Asia/Seoul"),
    City("South Korea", "Incheon", 37.4563, 126.7052, "Asia/Seoul"),
    City("China", "Beijing", 39.9042, 116.4074, "Asia/Shanghai"),
    City("China", "Shanghai", 31.2304, 121.4737, "Asia/Shanghai"),
    City("China", "Guangzhou", 23.1291, 113.2644, "Asia/Shanghai"),
    City("China", "Shenzhen", 22.5431, 114.0579, "Asia/Shanghai"),
    City("China", "Chengdu", 30.5728, 104.0668, "Asia/Shanghai"),
    City("Hong Kong", "Hong Kong", 22.3193, 114.1694, "Asia/Hong_Kong"),
    City("Taiwan", "Taipei", 25.0330, 121.5654, "Asia/Taipei"),
    City("Taiwan", "Kaohsiung", 22.6273, 120.3014, "Asia/Taipei"),
    # Asia - South / SE
    City("India", "Mumbai", 19.0760, 72.8777, "Asia/Kolkata"),
    City("India", "Delhi", 28.6139, 77.2090, "Asia/Kolkata"),
    City("India", "Bangalore", 12.9716, 77.5946, "Asia/Kolkata"),
    City("India", "Hyderabad", 17.3850, 78.4867, "Asia/Kolkata"),
    City("India", "Chennai", 13.0827, 80.2707, "Asia/Kolkata"),
    City("India", "Kolkata", 22.5726, 88.3639, "Asia/Kolkata"),
    City("India", "Pune", 18.5204, 73.8567, "Asia/Kolkata"),
    City("India", "Ahmedabad", 23.0225, 72.5714, "Asia/Kolkata"),
    City("Pakistan", "Karachi", 24.8607, 67.0011, "Asia/Karachi"),
    City("Pakistan", "Lahore", 31.5497, 74.3436, "Asia/Karachi"),
    City("Pakistan", "Islamabad", 33.6844, 73.0479, "Asia/Karachi"),
    City("Bangladesh", "Dhaka", 23.8103, 90.4125, "Asia/Dhaka"),
    City("Sri Lanka", "Colombo", 6.9271, 79.8612, "Asia/Colombo"),
    City("Thailand", "Bangkok", 13.7563, 100.5018, "Asia/Bangkok"),
    City("Thailand", "Chiang Mai", 18.7883, 98.9853, "Asia/Bangkok"),
    City("Vietnam", "Hanoi", 21.0285, 105.8542, "Asia/Ho_Chi_Minh"),
    City("Vietnam", "Ho Chi Minh City", 10.8231, 106.6297, "Asia/Ho_Chi_Minh"),
    City("Philippines", "Manila", 14.5995, 120.9842, "Asia/Manila"),
    City("Philippines", "Cebu City", 10.3157, 123.8854, "Asia/Manila"),
    City("Indonesia", "Jakarta", -6.2088, 106.8456, "Asia/Jakarta"),
    City("Indonesia", "Surabaya", -7.2504, 112.7688, "Asia/Jakarta"),
    City("Indonesia", "Bali", -8.3405, 115.0920, "Asia/Makassar"),
    City("Malaysia", "Kuala Lumpur", 3.1390, 101.6869, "Asia/Kuala_Lumpur"),
    City("Malaysia", "George Town", 5.4141, 100.3288, "Asia/Kuala_Lumpur"),
    City("Singapore", "Singapore", 1.3521, 103.8198, "Asia/Singapore"),
    # Middle East
    City("United Arab Emirates", "Dubai", 25.2048, 55.2708, "Asia/Dubai"),
    City("United Arab Emirates", "Abu Dhabi", 24.4539, 54.3773, "Asia/Dubai"),
    City("Saudi Arabia", "Riyadh", 24.7136, 46.6753, "Asia/Riyadh"),
    City("Saudi Arabia", "Jeddah", 21.4858, 39.1925, "Asia/Riyadh"),
    City("Israel", "Tel Aviv", 32.0853, 34.7818, "Asia/Jerusalem"),
    City("Israel", "Jerusalem", 31.7683, 35.2137, "Asia/Jerusalem"),
    City("Egypt", "Cairo", 30.0444, 31.2357, "Africa/Cairo"),
    # Africa
    City("South Africa", "Johannesburg", -26.2041, 28.0473, "Africa/Johannesburg"),
    City("South Africa", "Cape Town", -33.9249, 18.4241, "Africa/Johannesburg"),
    City("South Africa", "Durban", -29.8587, 31.0218, "Africa/Johannesburg"),
    City("Nigeria", "Lagos", 6.5244, 3.3792, "Africa/Lagos"),
    City("Nigeria", "Abuja", 9.0765, 7.3986, "Africa/Lagos"),
    City("Kenya", "Nairobi", -1.2921, 36.8219, "Africa/Nairobi"),
    City("Morocco", "Casablanca", 33.5731, -7.5898, "Africa/Casablanca"),
    City("Morocco", "Marrakech", 31.6295, -7.9811, "Africa/Casablanca"),
    # Oceania
    City("Australia", "Sydney", -33.8688, 151.2093, "Australia/Sydney"),
    City("Australia", "Melbourne", -37.8136, 144.9631, "Australia/Melbourne"),
    City("Australia", "Brisbane", -27.4698, 153.0251, "Australia/Brisbane"),
    City("Australia", "Perth", -31.9505, 115.8605, "Australia/Perth"),
    City("Australia", "Adelaide", -34.9285, 138.6007, "Australia/Adelaide"),
    City("New Zealand", "Auckland", -36.8485, 174.7633, "Pacific/Auckland"),
    City("New Zealand", "Wellington", -41.2865, 174.7762, "Pacific/Auckland"),
    # Latin America
    City("Mexico", "Mexico City", 19.4326, -99.1332, "America/Mexico_City"),
    City("Mexico", "Guadalajara", 20.6597, -103.3496, "America/Mexico_City"),
    City("Mexico", "Monterrey", 25.6866, -100.3161, "America/Monterrey"),
    City("Mexico", "Tijuana", 32.5149, -117.0382, "America/Tijuana"),
    City("Brazil", "São Paulo", -23.5505, -46.6333, "America/Sao_Paulo"),
    City("Brazil", "Rio de Janeiro", -22.9068, -43.1729, "America/Sao_Paulo"),
    City("Brazil", "Brasília", -15.8267, -47.9218, "America/Sao_Paulo"),
    City("Brazil", "Salvador", -12.9714, -38.5014, "America/Bahia"),
    City("Argentina", "Buenos Aires", -34.6037, -58.3816, "America/Argentina/Buenos_Aires"),
    City("Argentina", "Córdoba", -31.4201, -64.1888, "America/Argentina/Cordoba"),
    City("Chile", "Santiago", -33.4489, -70.6693, "America/Santiago"),
    City("Colombia", "Bogotá", 4.7110, -74.0721, "America/Bogota"),
    City("Colombia", "Medellín", 6.2442, -75.5812, "America/Bogota"),
    City("Peru", "Lima", -12.0464, -77.0428, "America/Lima"),
    City("Venezuela", "Caracas", 10.4806, -66.9036, "America/Caracas"),
]


def cities_for(country: str) -> list[City]:
    """Return cities for a country (case-insensitive exact match)."""
    if not country:
        return []
    c = country.strip().casefold()
    return [x for x in _CITIES if x.country.casefold() == c]


def find_city(country: str, city: str) -> City | None:
    for x in cities_for(country):
        if x.name.casefold() == city.strip().casefold():
            return x
    return None


def all_countries() -> list[str]:
    return sorted({x.country for x in _CITIES})
