"""
Vantage — Universo de rastreo
--------------------------------
La lista amplia que el escáner revisa una vez al día.

No son "todas las empresas del mundo": eso son más de 50.000 valores, y Yahoo
Finance corta el acceso mucho antes. Esto es el universo razonable — lo que
tiene liquidez suficiente para que los niveles técnicos signifiquen algo.

Añadir o quitar es seguro. El coste es tiempo: unos 250 símbolos tardan
alrededor de un minuto porque se descargan por lotes.
"""

# --- Divisas: los pares que realmente se mueven -------------------------------
FOREX = [
    ("EURUSD=X", "Euro / Dólar"), ("GBPUSD=X", "Libra / Dólar"),
    ("USDJPY=X", "Dólar / Yen"), ("USDCHF=X", "Dólar / Franco suizo"),
    ("AUDUSD=X", "Dólar australiano / Dólar"), ("NZDUSD=X", "Dólar neozelandés / Dólar"),
    ("USDCAD=X", "Dólar / Dólar canadiense"), ("EURGBP=X", "Euro / Libra"),
    ("EURJPY=X", "Euro / Yen"), ("GBPJPY=X", "Libra / Yen"),
    ("EURCHF=X", "Euro / Franco suizo"), ("AUDJPY=X", "Dólar australiano / Yen"),
    ("CHFJPY=X", "Franco suizo / Yen"), ("EURAUD=X", "Euro / Dólar australiano"),
    ("GBPAUD=X", "Libra / Dólar australiano"), ("EURCAD=X", "Euro / Dólar canadiense"),
    ("CADJPY=X", "Dólar canadiense / Yen"), ("NZDJPY=X", "Dólar neozelandés / Yen"),
    ("GBPCHF=X", "Libra / Franco suizo"), ("AUDNZD=X", "Australiano / Neozelandés"),
    ("USDMXN=X", "Dólar / Peso mexicano"), ("USDSEK=X", "Dólar / Corona sueca"),
    ("USDNOK=X", "Dólar / Corona noruega"), ("USDZAR=X", "Dólar / Rand"),
]

# --- Materias primas ----------------------------------------------------------
COMMODITIES = [
    ("GC=F", "Oro"), ("SI=F", "Plata"), ("HG=F", "Cobre"), ("PL=F", "Platino"),
    ("CL=F", "Petróleo WTI"), ("BZ=F", "Petróleo Brent"), ("NG=F", "Gas natural"),
    ("ZC=F", "Maíz"), ("ZW=F", "Trigo"), ("KC=F", "Café"),
]

# --- Índices ------------------------------------------------------------------
INDICES = [
    ("^GSPC", "S&P 500"), ("^NDX", "Nasdaq 100"), ("^DJI", "Dow Jones 30"),
    ("^RUT", "Russell 2000"), ("^VIX", "Índice de volatilidad"),
    ("^GDAXI", "DAX 40"), ("^FCHI", "CAC 40"), ("^IBEX", "IBEX 35"),
    ("^FTSE", "FTSE 100"), ("^STOXX50E", "Euro Stoxx 50"),
    ("^N225", "Nikkei 225"), ("^HSI", "Hang Seng"),
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


UNIVERSE = (
    _rows(FOREX, "Forex")
    + _rows(COMMODITIES, "Materia prima")
    + _rows(INDICES, "Índice")
    + _rows(US_STOCKS, "Acción")
    + _rows(EU_STOCKS, "Acción")
)

SYMBOLS = [row[0] for row in UNIVERSE]
META = {row[0]: (row[1], row[2]) for row in UNIVERSE}


if __name__ == "__main__":
    from collections import Counter
    print(f"Universo: {len(SYMBOLS)} símbolos")
    for clase, n in Counter(r[2] for r in UNIVERSE).most_common():
        print(f"  {clase:<16} {n}")
