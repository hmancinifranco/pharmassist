"""
Reference data: specialty-to-product mapping and cadencia intervals.

Used by visit generation, SLA calculation, and product suggestion tools.
"""

ESPECIALIDAD_PRODUCTOS: dict[str, list[str]] = {
    "Gastroenterología": ["ALACIR", "CIRUELAX MINITABS"],
    "Psiquiatría": ["APSICO", "PAMOXET"],
    "Dermatología": ["PANCUTAN NF", "TRIMACREM PLUS", "MENCOGRIN AP", "SUTRICO TAR", "TRICOPLUS"],
    "Ginecología": ["TRICOFIN", "TANVIMIL ACD"],
    "Clínica Médica": ["TANDIUR", "TIOCTAN", "CO-TIOCTAN", "TANVIMIL B1 B6 B12"],
    "Endocrinología": ["TIOCTAN", "CO-TIOCTAN", "TANVIMIL AMINOÁCIDOS"],
    "Neurología": ["APSICO", "PAMOXET", "ONEFIN"],
    "Urología": ["ONEFIN", "TACNA"],
    "Pediatría": ["TANVIMIL ACD", "TANVIMIL ACD FLUOR", "AEROGAL"],
    "Nutrición": ["TANVIMIL AMINOÁCIDOS", "TANVIMIL PLUS", "TANVIMIL B1 B6 B12"],
    "Infectología": ["TRICOFIN", "TACNA"],
    "Traumatología": ["TIOCTAN", "TANVIMIL B1 B6 B12"],
}

CADENCIA_DIAS: dict[str, int] = {
    "Mensual": 30,
    "Trimestral": 90,
    "Semestral": 180,
    "Anual": 365,
    "Digital": 60,
}
