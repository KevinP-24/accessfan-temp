# app/services/badwords_service.py
from app import db
from sqlalchemy import Column, Integer, String

# --- Listos para migrar a base de datos---
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
    # — Masculinos (ES / LATAM, coloquial y jerga) —
        "pija", "pijita", "pijón", "poronga", "porongón", "garompa", "garcha",
        "pichula", "pichulita", "pichulón", "pico", "tula", "tulita", "tulón",
        "chota", "chotita", "chotón", "riata","camote", "monda", "mondá",
        "bicho", "pajarito", "pájaro", "miembro", "miembro viril", "manguera",
        "tranca", "manguaco", "verguilla", "verguita", "vergota", "capullo", "glande",

        # — Femeninos (anatómicos / coloquiales) —
        "vulva", "pubis", "monte de venus", "labios", "labios vaginales",
        "labios mayores", "labios menores", "himen",
        "chocha", "chochona", "chumino", "cuca", "totona", "toto", "pucha",
        "coñito", "conchota", "panochita", "panochón", "cosita", "chucha",

        # — Ano / trasero (sin duplicar los ya presentes) —
        "ojete", "culito", "culazo", "culos", "colita",
        "pompis", "pompas", "glúteos", "gluteos", "traserito", "traserote",
        "traserazo", "nalguita", "nalgón", "nalgotas", "nalga", "orificio anal",
        "recto",

        # — Mamas / pezones (variantes y términos médicos) —
        "mamas", "areola", "areolas", "pezones", "pezoncito",

        # — Términos anatómicos adicionales —
        "periné", "perineo", "uretra", "próstata", "prostata", "anus", "perineum",

        # — Inglés (muy usados en textos/etiquetas) —
        "penis", "dick", "cock", "willy", "pecker", "schlong", "shaft", "johnson", "dong",
        "balls", "ball sack", "ballsack", "nuts", "nads", "gonads", "testicles", "scrotum",
        "sack", "nutsack", "pussy", "vulva", "labia", "clit", "clitoris", "coochie", "coochy", "cooch", "cootchie",
        "cunt", "beaver", "snatch", "vajayjay", "kitty", "ass", "butt", "buttocks", "booty", "arse", "asshole", "butthole", 
        "backside", "rear", "bum", "bumhole", "boob", "tits", "titties", "breasts", "nipples", "areolae", "areola"

        # === Actos sexuales ===
        "sexo", "sexo oral", "sexo anal", "sexo grupal", "hacer el amor",
        "follar", "coger", "chingar", "tirar", "acostarse", "fornicar",
        "coito", "orgía", "trío", "gangbang", "deepthroat", "garganta profunda",
        "felación", "mamando", "chuparla", "chuparla toda", "chupar pito",
        "chupapollas", "pajearse", "masturbarse", "hacerse una paja",
        "corrida", "eyacular", "eyaculación", "sodomía", "penetrar",
        "penetración", "desvirgar", "virginar", "desflorar", "sodomizar", "violar", 
        "violado", "violada", "violando", "violó", "violaron", 
        "me violó", "me violaron", "fue violada", "fue violado", 
        "ha sido violada", "ha sido violado", "violador", "violadores", 
        "violadora", "violadoras", "violación", "violaciones", 
        "intento de violación", "fue víctima de violación", "violamos" 
        "abusó de ella", "abusó sexualmente", "agredió sexualmente", 
        "ataque sexual", "abuso sexual", "delito sexual", 
        "forzar sexualmente", "fue forzada", "fue forzado"
        "violo", "violas", "viola", "violamos", "violáis", "violen",
        "violé", "violaste", "violasteis",
        "violaba", "violabas", "violábamos", "violabais", "violaban",
        "violaré", "violarás", "violará", "violaremos", "violaréis", "violarán",
        "violaría", "violarías", "violaríamos", "violaríais", "violarían",
        "viole", "violes", "violemos", "violéis", "violen",
        "violara", "violaras", "violáramos", "violarais", "violaran",
        "violase", "violases", "violásemos", "violaseis", "violasen",
        "viola", "violad", "no violes", "no viole", "no violéis", "no violen",
        "violándose", "se violó", "se violaron"

        # — Verbos comunes con conjugaciones y derivados —
        "cogiendo", "cogió", "follando", "folló", "tirando", "tiró",
        "chingando", "chingó", "acostándome", "acostándose", "acostó",
        "fornicando", "fornicó", "penetrando", "penetró", "desvirgó",
        "desfloró", "sodomizó", "eyaculando", "eyaculó", "acabando", "acabó",
        "correrse", "me corrí", "se corrió", "acabarse", "acabarse encima", "acabarse dentro",
        "metiendo", "meterla", "meterlo", "la metió", "le metió", "meterla toda",
        "encular", "enculó", "enculando", "tragarla", "tragársela", "me la tragué",
        "mamar", "mamó", "mamada", "mamando rico", "lamerla", "lamer", "lamiendo",
        "fingering", "masturbando", "tocándome", "tocándose", "tocarte", "tocarlo", "tocarla",
        "manosear", "manoseando", "manoseó", "acariciar", "acariciando", "acarició",
        "hacerlo", "lo hicimos", "lo hiciste", "haciendo el amor", "teniendo sexo",
        "mantener relaciones", "mantuvimos relaciones", "tener relaciones", "relaciones sexuales",
        "polvo", "echar un polvo", "echamos un polvo", "tiramos", "tiradita", "traca traca",
        
        # — Actos y categorías de porno o fetiche —
        "sexo interracial", "sexo lésbico", "sexo gay", "sexo entre hombres", "sexo entre mujeres",
        "sexo con animales", "bestialismo", "zoofilia", "fisting", "anal fisting", "spanking",
        "bondage", "sadomasoquismo", "dominación", "sumisión", "orgasmo múltiple",
        "69", "sesenta y nueve", "doggystyle", "posición perrito", "misionero", "cowgirl", "reverse cowgirl",
        "tragar semen", "eyaculación facial", "facial", "bukkake", "cumshot", "creampie", "handjob", "blowjob",
        "licking", "rimming", "twerking sexual", "dry hump", "grinding", "sexo virtual", "sexting", "videollamada caliente",

        # — Español coloquial / jerga —
        "echar pata", "echar un palo", "darle duro", "dándole", "dándosela", "dándomelo", "romperle la cama",
        "vacilarse", "tirar un polvo", "hacer cochinadas", "hacer marranadas", "meter mano", "toquetear",
        "darle placer", "calentarse", "calentando", "estoy caliente", "estás caliente", "me prendí", "me encendí",
        "me vine", "te viniste", "venirse", "venirse adentro", "venirse en la cara",
        
        # — En inglés (muy comunes en contenido etiquetado NSFW) —
        "sex", "oral sex", "anal sex", "group sex", "threesome", "orgy", "fuck", "fucking",
        "suck", "sucking", "lick", "licking", "deep throat", "hand job", "handjob", "blow job",
        "cum", "cumshot", "cumming", "ejaculation", "ejaculate", "penetration", "humping",
        "making love", "bang", "banging", "bangs", "spitroast", "twerk", "grind", "grinding",
        "intercourse", "lovemaking", "anal play", "foreplay", "strip tease", "lap dance",
        "masturbate", "masturbating", "masturbation", "jerk off", "jerking off", "self pleasure",
        "follo", "follas", "folla", "follamos", "folláis", "follan",
        "follé", "follaste", "follamos", "follasteis", "follaron",
        "follaba", "follabas", "follábamos", "follabais", "follaban",
        "follaré", "follarás", "follará", "follaremos", "follaréis", "follarán",
        "follaría", "follarías", "follaríamos", "follaríais", "follarían",
        "folle", "folles", "follemos", "folléis", "follen",
        "follara", "follaras", "folláramos", "follarais", "follaran",
        "follease", "folleases", "follésemos", "folleaseis", "folleasen",
        "folla", "follad", "no folles", "no folle", "no folléis", "no follen",
        "follado",
        "te voy a follar", "me la follé", "nos follamos", "se lo folló", "se la folló"

        "cojo", "coges", "coge", "cogemos", "cogéis", "cogen",
        "cogí", "cogiste", "cogimos", "cogisteis", "cogieron",
        "cogía", "cogías", "cogíamos", "cogíais", "cogían",
        "cogeré", "cogerás", "cogerá", "cogeremos", "cogeréis", "cogerán",
        "cogería", "cogerías", "cogeríamos", "cogeríais", "cogerían",
        "coja", "cojas", "cojamos", "cojáis", "cojan",
        "cogiera", "cogieras", "cogiéramos", "cogierais", "cogieran",
        "cogiese", "cogieses", "cogiésemos", "cogieseis", "cogiesen",
        "coge", "coged", "no cojas", "no coja", "no cojáis", "no cojan",
        "cogido",
        "te voy a coger", "me la cogí", "nos cogimos", "la cogieron", "lo cogieron"
        # — Otros términos asociados —
        "placer", "placer sexual", "clímax", "orgasmo", "preliminares", "fantasías sexuales",
        "encuentro íntimo", "encuentro sexual", "relación íntima", "relación carnal", "acto sexual",
        "coqueteo fuerte", "insinuación sexual", "comportamiento lascivo", "contacto sexual"

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
        # === Homicidio y asesinato (verbos, acciones y sustantivos) ===
        "matar", "matando", "matado", "mato", "mataron",
        "maté", "mataste", "matamos", "mata", "maten", "matad",
        "me mató", "lo mató", "la mató", "los mató", "las mató",
        "me mataron", "lo mataron", "la mataron", "los mataron", "las mataron",
        "quiero matar", "va a matar", "va a matarte", "te voy a matar", "te mato",
        "te voy a matar hijo de puta", "lo voy a matar", "la voy a matar",
        "podría matar", "quiso matar", "intentó matar", "trató de matar",
        "mataré", "matarás", "mataría", "matarías", "matara", "mataran", "matase", "matasen",
        "asesinar", "asesinó", "asesinaron", "asesinando", "asesinado",
        "asesinada", "asesinados", "asesinadas",
        "asesino", "asesina", "asesinos", "asesinas",
        "me asesinó", "lo asesinó", "la asesinó", "los asesinaron", "las asesinaron",
        "fue asesinado", "fue asesinada", "ha sido asesinado", "ha sido asesinada",
        "intentó asesinar", "intento de asesinato", "quiso asesinar", "planeó asesinar",
        "va a asesinar", "voy a asesinar", "te voy a asesinar",
        "asesinato", "asesinatos", "homicidio", "homicida",
        "sicario", "sicarios", "contrató un sicario", "lo mandó a matar", "la mandó a matar",
        "ejecutar", "ejecución", "ejecuciones", "fue ejecutado", "fue ejecutada",
        "abatir", "abatió", "abatidos", "ajusticiar", "ajusticiado", "ultimar",
        "liquidar", "eliminar", "acabar con", "destruir", "degollar", "decapitar",
        "descuartizar", "exterminar", "aniquilar", "masacrar", "genocidio",
        "aniquilación", "carnicería", "matanza", "fusilar", "fusilamiento",

        # === Violencia física / agresiones (verbos, golpes y derivados) ===
        "golpear", "golpeó", "golpearon", "golpeando", "golpeado", "golpeada",
        "golpeados", "golpeadas", "golpes", "golpe",
        "me golpeó", "te golpeó", "lo golpeó", "la golpeó",
        "los golpearon", "las golpearon", "fue golpeado", "fue golpeada",
        "ha sido golpeado", "ha sido golpeada", "lo golpearon", "la golpearon",
        "pegar", "pegó", "pegaron", "pegarle", "me pegó", "me pegaron",
        "apalear", "apaleó", "apalearon", "apalizando", "dar una paliza",
        "le dio una paliza", "le dieron una paliza",
        "le metió un golpe", "le metió una piña",
        "puñetazo", "puñetazos", "cachetada", "cachetadas",
        "bofetada", "bofetadas", "trompada", "trompadas",
        "patada", "patadas", "golpeó brutalmente", "golpe brutal",
        "golpiza", "golpizas", "fue golpeado brutalmente",
        "agresión física", "violencia física",
        "lo agredió", "me agredió", "fue agredido", "fue agredida", "agredieron",
        "apuñalar", "apuñaló", "apuñalaron", "apuñalado", "apuñalada",
        "acuchillar", "acuchilló", "acuchillado", "acuchillaron",
        "clavar cuchillo", "destripar", "aplastar",
        "ahorcar", "ahorcó", "ahorcamiento",
        "estrangular", "estranguló", "estrangulación",
        "ahogar", "ahogó", "ahogar con agua",
        "quemar vivo", "torturar", "torturó", "flagelar", "electrocutar",

        # === Amenazas típicas (expresiones directas) ===
        "te voy a matar", "los vamos a matar", "la vamos a matar", "te vamos a matar",
        "vas a morir", "te voy a romper", "te reviento", "te voy a cagar a palos",
        "te voy a hacer mierda", "te voy a reventar", "te va a ir mal", "cuídate o te mato",

        # === Armas (objetos y acciones relacionadas) ===
        "arma", "armamento", "arma de fuego", "arma blanca",
        "pistola", "revólver", "rifle", "escopeta", "fusil", "metralleta", "subfusil",
        "ak47", "kalashnikov", "uZI", "glock", "ar-15",
        "navaja", "cuchillo", "machete", "puñal", "guillotina", "martillo",
        "granada", "explosivo", "c4", "dinamita", "molotov", "bomba", "cohete", "misil", "bazuca",
        "bombardeo", "minas antipersona",
        "ametrallar", "tirotear", "balear",
        "tiroteo", "balacera", "tiros", "disparos",
        "lo balearon", "fue baleado", "fue tiroteado", "disparó", "dispararon",

        # === Guerra / violencia organizada ===
        "guerra", "batalla", "combate", "conflicto armado", "frente de batalla",
        "terrorismo", "terrorista", "represión", "dictadura",
        "campos de concentración", "campos de exterminio", "holocausto",
        "violencia", "represalia",
        "conspiración armada", "ejército armado", "golpe de estado",
        "ataque", "ataque armado", "ataque físico", "emboscada",

        # === Abuso / violencia sexual (términos de violencia, no eróticos) ===
        "abuso", "abuso sexual", "acoso sexual", "violencia sexual",
        "violador", "violar", "violación",
        "forzar", "forzó", "forzamiento", "coerción sexual",
        "agresión sexual", "ataque sexual",
        "fue violado", "fue violada", "me violó", "me violaron",
        "intento de violación", "abusó sexualmente",

        # === Crimen organizado / drogas relacionadas a violencia ===
        "heroína", "cocaína", "metanfetamina", "crack", "drogas duras",
        "narcotráfico", "cartel", "narco", "sicariato", "ajuste de cuentas",

        # === Odio / insultos (lenguaje violento o de odio) ===
        "hijo de puta", "perra", "zorra", "puta", "maricón", "marica", "puto", "putazo",
        "negro de mierda", "india de mierda", "sudaca", "panchito", "gringo de mierda",
        "moro de mierda", "gallego bruto", "mongólico", "retrasado", "subnormal",
        "discapacitado mental", "minusválido de mierda", "parguela", "tarado", "imbécil",
        "idiota", "inútil", "basura", "escoria", "asqueroso", "repugnante", "apestoso",
        "cerdo", "cerda", "cochino", "marrano", "malparido", "culiao", "culiá", "carepija",
        "careverga", "caremonda", "pajuo", "gonorrea", "hijueputa", "hp", "maldito", "maldita",
        "mierda", "de mierda", "muérete", "ojalá te mueras", "te odio", "te detesto",
        "odio a los gays", "odio a las mujeres", "odio a los hombres", "odio a los negros",
        "odio a los pobres", "odio a los ricos", "mátate", "suicídate", "vete a la mierda",
        "vete al infierno", "malnacido", "nazi", "facha", "comunista de mierda",
        "feminazi", "homofóbico", "homófobo", "racista", "clasista", "machista",
        "violento", "intolerante", "asesino", "criminal", "degenerado", "asquerosa",
        "puta asquerosa", "negro mugroso", "indio ignorante", "maricón de mierda",
        "peruano de mierda", "mierda", "argentino de mierda", "mexicano de mierda",
        "ecuatoriano de mierda", "veneco de mierda", "venezolano de mierda", "paraguayo de mierda",
        "judío de mierda", "árabe terrorista", "moraco", "cabecita negra",
        "simio", "mono", "animal", "bestia", "cerdo humano", "puerco", "inmigrante de mierda",
        "extranjero de mierda", "negra sucia", "maricón asqueroso", "lesbiana de mierda",
        "travesti de mierda", "trans de mierda", "marimacho", "nenaza", "poco hombre", "mariposón",
        "depravado", "sidoso", "enfermo", "apestoso", "feo de mierda", "forro", "forros" 
    ]
}


# --- DETECTOR ---
def load_badwords(source="file"):
    """
    Carga las badwords por ahora solo desde código.
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
