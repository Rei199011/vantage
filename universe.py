"""
Vantage — Universo de rastreo
--------------------------------
La lista amplia que el escáner revisa una vez al día.

Solo acciones. Las divisas, metales e índices se retiraron del universo
operable: Vantage ya no recomienda operarlos.

Los índices siguen descargándose, pero SOLO COMO CONTEXTO (ver CONTEXTO abajo).
Nunca generan señal. Sirven para que la revisión sepa en qué régimen está el
mercado: una compra en un valor aislado se lee distinto si el S&P viene
cayendo tres semanas.

Añadir o quitar es seguro. El coste es tiempo: unos 200 símbolos tardan
alrededor de un minuto porque se descargan por lotes.
"""

# --- Índices: NO se operan. Solo dan contexto de régimen de mercado. --------
CONTEXTO = [
    ("^GSPC", "S&P 500"),
    ("^NDX", "Nasdaq 100"),
    ("^DJI", "Dow Jones 30"),
    ("^RUT", "Russell 2000"),
    ("^VIX", "Índice de volatilidad"),
    ("^STOXX50E", "Euro Stoxx 50"),
    ("^IBEX", "IBEX 35"),
]

# --- Acciones de EE.UU.: grandes capitalizaciones y valores muy negociados -----
US_STOCKS = [
    ("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"),
    ("GOOGL", "Alphabet"), ("AMZN", "Amazon"), ("META", "Meta Platforms"),
    ("TSLA", "Tesla"), ("AVGO", "Broadcom"), ("AMD", "AMD"),
    ("INTC", "Intel"), ("QCOM", "Qualcomm"), ("TXN", "Texas Instruments"),
    ("MU", "Micron"), ("ARM", "Arm Holdings"), ("SMCI", "Super Micro"),
    ("PLTR", "Palantir"), ("SNOW", "Snowflake"), ("CRM", "Salesforce"),
    ("ORCL", "Oracle"), ("ADBE", "Adobe"), ("NOW", "ServiceNow"),
    ("SHOP", "Shopify"), ("UBER", "Uber"), ("ABNB", "Airbnb"),
    ("NFLX", "Netflix"), ("DIS", "Disney"), ("SPOT", "Spotify"),
    ("JPM", "JPMorgan"), ("BAC", "Bank of America"), ("GS", "Goldman Sachs"),
    ("MS", "Morgan Stanley"), ("WFC", "Wells Fargo"), ("V", "Visa"),
    ("MA", "Mastercard"), ("AXP", "American Express"), ("PYPL", "PayPal"),
    ("COIN", "Coinbase"), ("HOOD", "Robinhood"), ("BLK", "BlackRock"),
    ("BRK-B", "Berkshire Hathaway"), ("SCHW", "Charles Schwab"),
    ("JNJ", "Johnson & Johnson"), ("UNH", "UnitedHealth"), ("LLY", "Eli Lilly"),
    ("PFE", "Pfizer"), ("MRK", "Merck"), ("ABBV", "AbbVie"),
    ("TMO", "Thermo Fisher"), ("AMGN", "Amgen"), ("GILD", "Gilead"),
    ("XOM", "Exxon Mobil"), ("CVX", "Chevron"), ("COP", "ConocoPhillips"),
    ("SLB", "SLB"), ("OXY", "Occidental"), ("NEE", "NextEra Energy"),
    ("WMT", "Walmart"), ("COST", "Costco"), ("TGT", "Target"),
    ("HD", "Home Depot"), ("LOW", "Lowe's"), ("NKE", "Nike"),
    ("MCD", "McDonald's"), ("SBUX", "Starbucks"), ("KO", "Coca-Cola"),
    ("PEP", "PepsiCo"), ("PG", "Procter & Gamble"), ("PM", "Philip Morris"),
    ("BA", "Boeing"), ("CAT", "Caterpillar"), ("DE", "Deere"),
    ("GE", "GE Aerospace"), ("HON", "Honeywell"), ("LMT", "Lockheed Martin"),
    ("RTX", "RTX"), ("UPS", "UPS"), ("UNP", "Union Pacific"),
    ("RKLB", "Rocket Lab"), ("LUNR", "Intuitive Machines"), ("ASTS", "AST SpaceMobile"),
    ("T", "AT&T"), ("VZ", "Verizon"), ("CMCSA", "Comcast"),
    ("IBM", "IBM"), ("CSCO", "Cisco"), ("DELL", "Dell"),
    ("F", "Ford"), ("GM", "General Motors"), ("RIVN", "Rivian"),
    ("LCID", "Lucid"), ("NIO", "NIO"), ("MARA", "MARA Holdings"),
    ("RIOT", "Riot Platforms"), ("MSTR", "Strategy"), ("SOFI", "SoFi"),
    ("DKNG", "DraftKings"), ("RBLX", "Roblox"), ("U", "Unity"),
]

# --- Acciones europeas --------------------------------------------------------
EU_STOCKS = [
    ("ASML.AS", "ASML"), ("SAP.DE", "SAP"), ("SIE.DE", "Siemens"),
    ("ALV.DE", "Allianz"), ("BMW.DE", "BMW"), ("VOW3.DE", "Volkswagen"),
    ("MBG.DE", "Mercedes-Benz"), ("BAS.DE", "BASF"), ("DTE.DE", "Deutsche Telekom"),
    ("MC.PA", "LVMH"), ("OR.PA", "L'Oréal"), ("AIR.PA", "Airbus"),
    ("TTE.PA", "TotalEnergies"), ("SAN.PA", "Sanofi"), ("BNP.PA", "BNP Paribas"),
    ("SAN.MC", "Banco Santander"), ("BBVA.MC", "BBVA"), ("ITX.MC", "Inditex"),
    ("IBE.MC", "Iberdrola"), ("TEF.MC", "Telefónica"), ("REP.MC", "Repsol"),
    ("AMS.MC", "Amadeus"), ("FER.MC", "Ferrovial"), ("CABK.MC", "CaixaBank"),
    ("ISP.MI", "Intesa Sanpaolo"), ("ENI.MI", "Eni"), ("ENEL.MI", "Enel"),
    ("NESN.SW", "Nestlé"), ("NOVN.SW", "Novartis"), ("ROG.SW", "Roche"),
    ("SHEL.L", "Shell"), ("AZN.L", "AstraZeneca"), ("HSBA.L", "HSBC"),
    ("ULVR.L", "Unilever"), ("RIO.L", "Rio Tinto"), ("BP.L", "BP"),
]


def _rows(pairs, clase):
    return [(t, n, clase) for t, n in pairs]


UNIVERSE = _rows(US_STOCKS, "Acción") + _rows(EU_STOCKS, "Acción")

SYMBOLS = [row[0] for row in UNIVERSE]
META = {row[0]: (row[1], row[2]) for row in UNIVERSE}

CONTEXT_SYMBOLS = [row[0] for row in CONTEXTO]
CONTEXT_META = {row[0]: row[1] for row in CONTEXTO}


if __name__ == "__main__":
    from collections import Counter
    print(f"Universo operable: {len(SYMBOLS)} acciones")
    for clase, n in Counter(r[2] for r in UNIVERSE).most_common():
        print(f"  {clase:<16} {n}")
    print(f"\nContexto (no se opera): {len(CONTEXT_SYMBOLS)} índices")
    print("  " + ", ".join(CONTEXT_META.values()))
