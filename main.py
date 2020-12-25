import datetime
import time
import statistics
import threading

## ---
# Stockage données
## ---
# Base de données type SQL stockée dans un fichier
import sqlite3
lock = threading.Lock()
def write_to_sql(statement, data = ()):
    with lock:
        cursor = CONN.cursor()
        cursor.execute(statement, data)
        CONN.commit()

def read_from_sql(statement, data = ()):
    with lock:
        cursor = CONN.cursor()
        cursor.execute(statement, data)
        return cursor.fetchall()

# Insère un point de données
def insert_data(raw, computed):
    now = datetime.datetime.now()
    write_to_sql("INSERT INTO measures (time, raw, computed) VALUES (?, ?, ?);", (now, raw, computed))

# Sauvegarde les paramètres
def insert_parameters(offset, factor):
    now = datetime.datetime.now()
    write_to_sql("INSERT INTO parameters (time, offset, factor) VALUES (?, ?, ?);", (now, offset, factor))

# Se connecte, créée le fichier s'il n'existe pas encore
CONN = sqlite3.connect("data.db", detect_types = sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread = False)
# Créée les tables si elles n'existent pas
write_to_sql("CREATE TABLE IF NOT EXISTS measures(time TIMESTAMP PRIMARY KEY, raw REAL, computed REAL);")
write_to_sql("CREATE TABLE IF NOT EXISTS parameters(time TIMESTAMP PRIMARY KEY, offset REAL, factor REAL);")

## ---
# Acquisition données
## ---
# Variables pour faire une fonction aléatoire à la place du hx711. Pas utile à terme.
import random
VAL_MIN = 30000
VAL_MAX = 50000
VAL_CURRENT = random.randrange(VAL_MIN, VAL_MAX)
def get_raw_value_random():
    global VAL_CURRENT
    new = VAL_CURRENT + random.randrange(-100, 100)
    VAL_CURRENT = max(min(new, VAL_MAX), VAL_MIN)
    return VAL_CURRENT


def get_raw_value_hx():
    pass
    # TODO!

def get_smoothed_value():
    values = []
    for i in range(0, 11):
        values.append(get_raw_value_random())
    values.sort()
    # Ecarter les deux valeurs minimales et maximales
    values = values[2:-2]
    return statistics.mean(values)


## ---
# Traitement des données
## ---
# Valeurs moyennée sur N mesures (déjà smoothées) ; utilisé uniquement pour les tares
def get_averaged_value(n):
    values = []
    for i in range(0, n):
        values.append(get_smoothed_value())
        time.sleep(0.1)
    return statistics.mean(values)

# Facteurs de tare et de facteur multiplicatif pour avoir des grammes ; réglables avec les fonctions de tare
CURRENT_OFFSET = 0
CURRENT_FACTOR = 1
def tare_zero():
    global CURRENT_OFFSET
    CURRENT_OFFSET = get_averaged_value(10)
    save_parameters_to_sql()

def tare_grams(weight_in_grams):
    global CURRENT_FACTOR
    raw = get_averaged_value(10)
    CURRENT_FACTOR = weight_in_grams / raw
    save_parameters_to_sql()

# Récupère la valeur brute, et fait le calcul avec l"offset et le facteur multiplicatif
def get_computed():
    raw_smoothed = get_smoothed_value()
    computed = (raw_smoothed - CURRENT_OFFSET) * CURRENT_FACTOR
    print("Raw: %f, offset: %f, factor: %f, computed: %f" % (raw_smoothed, CURRENT_OFFSET, CURRENT_FACTOR, computed))
    return (
        raw_smoothed,
        computed
    )

# Récupère une valeur avec les différents paramètres et appelle l"insertion en base de données
def get_insert_data():
    (raw, computed) = get_computed()
    insert_data(raw, computed)
    return computed

# Récupère les derniers paramètres (offset et facteur) dans la DB
def set_parameters_from_sql():
    global CURRENT_OFFSET
    global CURRENT_FACTOR
    rows = read_from_sql("SELECT offset, factor FROM parameters ORDER BY time DESC LIMIT 1;")

    if rows:
        (CURRENT_OFFSET, CURRENT_FACTOR) = rows[0]
        print("Found previous parameters: offset: %f, factor: %f" % (CURRENT_OFFSET, CURRENT_FACTOR))
    else:
        print("Not found any parameters in database")

def save_parameters_to_sql():
    insert_parameters(CURRENT_OFFSET, CURRENT_FACTOR)

## ---
# Serveur WEB
## ---
from bottle import get, post, run, static_file

# Static files
@get("/")
def index():
    return static_file("static/index.html", root = "/root/")
@get("/static/<filename>")
def server_static(filename):
    return static_file(filename, root="/root/static/")


@get("/history/<days:int>")
def get_history_data(days):
    timedelta = datetime.timedelta(days = days)
    from_date = datetime.datetime.now() - timedelta
    rows = read_from_sql("SELECT time, computed FROM measures WHERE time > ?;", (from_date, ))
    return {
        "data": list(map(lambda x: {"x": str(x[0]), "y": x[1]}, rows)),
    }

@get("/realtime")
def get_realtime():
    current_value = get_insert_data() 
    return {
        "data": {"x": str(datetime.datetime.now()), "y": current_value},
    }

@post("/tare_zero")
def post_tare_zero():
    tare_zero()

@post("/tare_grams/<grams:int>")
def post_tare_grams(grams):
    tare_grams(grams)


@post("/delete_measures")
def post_delete_measures():
    write_to_sql("DELETE FROM measures;")



## ---
# Execution principale
## ---
# Au lancement du programme, on récupère les derniers paramètres (offset, facteur) sauvegardés
set_parameters_from_sql()

# Tâche de fond : un nouveau point toutes les 5 minutes
def run_background():
    while True:
        val = get_insert_data()
        print("From background job: inserted data: %f" % (val, ))
        time.sleep(300)

threading.Thread(target = run_background).start()


# Lancer le serveur WEB
run(host = "0.0.0.0", port = 80)