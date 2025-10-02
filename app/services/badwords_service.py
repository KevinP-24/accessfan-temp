# app/services/badwords_service.py
from app import db
from sqlalchemy import Column, Integer, String

# --- MODELO FUTURO (para migrar a DB) ---
class BadWord(db.Model):
    __tablename__ = "badwords"
    id = Column(Integer, primary_key=True, autoincrement=True)
    palabra = Column(String(100), nullable=False, unique=True)
    categoria = Column(String(50), nullable=False)  # sexual o violento

    def __repr__(self):
        return f"<BadWord {self.palabra} ({self.categoria})>"

# --- LISTA LOCAL (hardcode inicial) ---
BADWORDS = {
    "sexual": [
        # === Genitales y órganos ===
        "pene", "vergón", "verga", "falo", "pito", "nepe", "polla",
        "vagina", "coño", "chocho", "concha", "conchita", "chochito",
        "clítoris", "ano", "culo", "orto", "nalgas", "trasero", "poto",
        "testículos", "huevos", "pelotas", "bolas", "escroto", "panocha",
        "tetas", "senos", "pechos", "pezón", "ubres", "melones",
        "chichi", "chichis", "chichona", "boobies",

        # === Actos sexuales ===
        "sexo", "sexo oral", "sexo anal", "sexo grupal", "hacer el amor",
        "follar", "coger", "chingar", "tirar", "acostarse", "fornicar",
        "coito", "orgía", "trío", "gangbang", "deepthroat", "garganta profunda",
        "felación", "mamando", "chuparla", "chuparla toda", "chupar pito",
        "chupapollas", "pajearse", "masturbarse", "hacerse una paja",
        "corrida", "eyacular", "eyaculación", "sodomía", "penetrar",
        "penetración", "desvirgar", "virginar", "desflorar", "sodomizar",

        # === Porno y variantes ===
        "porno", "pornografía", "porn", "xvideos", "pornhub", "xnxx",
        "redtube", "brazzers", "hentai", "jav", "camgirl", "cam boy",
        "webcam porno", "sexcam", "pornovideo", "video porno", "película porno",

        # === Prostitución y fetiches ===
        "puta", "ramera", "prostituta", "escort", "sexo servicio", "sexo pago",
        "prepago", "trabajadora sexual", "putero", "burdel", "lupanar", "casa de citas",
        "sadomasoquismo", "sado", "bdsm", "bondage", "dominatrix", "fetiche",
        "zoofilia", "bestialismo", "incesto", "pederasta", "pedofilia",
        "abuso sexual", "abusar sexualmente", "violación", "violador",
        "exhibicionismo", "voyeurismo", "orgasmo", "climax", "placer sexual",
        "sexo explícito", "sexo duro", "sexo salvaje",

        # === Juguetes / objetos ===
        "dildo", "vibrador", "consolador", "plug anal", "bolas chinas",
        "juguete sexual", "aceite sexual", "lubricante", "condón", "preservativo",
        "pornotube", "porno casero", "porno amateur",

        # === Jerga y variaciones coloquiales ===
        "fiesta de salchichas", "maciza", "macizorra", "tía buena", "marica",
        "maricón", "mariconazo", "travesti", "transexual", "transgénero",
        "bollera", "lesbiana", "gay", "homosexual", "lameculo", "ninfómana",
        "pervertido", "sádico", "caliente", "ardiente", "horny", "sexy"
    ],

    "violento": [
        # === Homicidio y asesinato ===
        "matar", "asesinar", "asesinato", "homicidio", "homicida",
        "degollar", "decapitar", "ejecución", "linchar", "lapidar",
        "descuartizar", "exterminar", "aniquilar", "masacrar", "genocidio",
        "aniquilación", "carnicería", "matanza", "fusilar", "fusilamiento",

        # === Violencia física ===
        "golpear", "pegar", "apalear", "patear", "ahorcar", "estrangular",
        "ahogar", "quemar vivo", "torturar", "flagelar", "aplastar",
        "apuñalar", "acuchillar", "clavar cuchillo", "destripar",
        "envenenar", "ahogar con agua", "electrocutar", "estrangulación",
        "ahorcamiento",

        # === Armas ===
        "arma", "armamento", "pistola", "revólver", "rifle", "escopeta",
        "fusil", "metralleta", "ak47", "kalashnikov", "subfusil",
        "ametrallar", "arma blanca", "navaja", "cuchillo", "machete",
        "guillotina", "martillo", "granada", "explosivo", "c4", "dinamita",
        "molotov", "bomba", "bombardeo", "misil", "cohete", "bazuca",
        "minas antipersona",

        # === Guerra / violencia organizada ===
        "guerra", "batalla", "combate", "conflicto armado", "frente de batalla",
        "terrorismo", "terrorista", "dictadura", "represión", "campos de concentración",
        "campos de exterminio", "holocausto", "violencia", "represalia",
        "conspiración armada", "ejército armado", "golpe de estado",

        # === Abuso / violencia sexual ===
        "abuso", "abuso sexual", "acoso sexual", "violencia sexual", "violador",
        "violar", "violación", "forzar", "forzamiento", "coerción sexual",
        "heroína", "cocaína", "metanfetamina", "crack", "drogas duras",
        "narcotráfico", "cartel", "narco", "sicario", "sicariato",
        "ajuste de cuentas"
    ]
}


# --- DETECTOR ---
def load_badwords(source="file"):
    """
    Carga las badwords (por ahora solo desde código).
    En el futuro se puede cambiar a DB.
    """
    return BADWORDS

def detect_badwords(text: str, source="file") -> dict:
    """
    Detecta palabras problemáticas en un texto.
    Devuelve todas encontradas y clasificadas.
    """
    text_low = text.lower()
    badwords = load_badwords(source)
    found = {cat: [] for cat in badwords.keys()}

    for categoria, palabras in badwords.items():
        for palabra in palabras:
            if palabra in text_low:
                found[categoria].append(palabra)

    all_found = sum(found.values(), [])
    return {"found": all_found, "categories": found}
