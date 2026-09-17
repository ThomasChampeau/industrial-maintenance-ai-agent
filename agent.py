from sqlalchemy import text, create_engine
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from pathlib import Path
from dotenv import load_dotenv
import re
import os
import json
from mistralai.client import Mistral

load_dotenv()

api_key = os.getenv("MISTRAL_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
os.environ.pop("SSL_CERT_FILE", None)

client = Mistral(api_key = api_key)
if not api_key:
    raise ValueError("MISTRAL_API_KEY manquante dans le fichier .env")

engine = create_engine(DATABASE_URL,
                       pool_pre_ping= True)
if not DATABASE_URL:
    raise ValueError("DATABASE_URL manquante dans le fichier .env")

def get_main_resolution(error_code):
    query = text("""
        SELECT resolution, COUNT(*) AS usage_count
        FROM incidents
        WHERE error_code = :error_code
        GROUP BY resolution
        ORDER BY usage_count DESC
        LIMIT 1;
    """)

    with engine.connect() as conn:
        result = conn.execute(query, {"error_code" : error_code})
        row = result.fetchone()
        return {
            "error_code" : error_code,
            "main_resolution" : row[0],
            "usage_count" : row[1]
        }
        
def get_incident_count_by_error(error_code):
    query = text("""
    select count(*)
    from incidents
    where error_code = :error_code;
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"error_code" : error_code})
        row = result.fetchone()
        return row
    
def get_avg_downtime_by_error(error_code):
    query = text("""
    select avg(downtime_minutes)
    from incidents
    where error_code = :error_code;
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"error_code" : error_code})
        row = result.fetchone()
        return {
            "error_code" : error_code,
            "avg_downtime_minutes" : round(float(row[0]), 2)
        }
    
def get_incidents_by_machine(machine_id):
    query = text("""
    select incident_id, error_code, severity, downtime_minutes, resolution
    from incidents
    where machine_id = :machine_id;
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"machine_id" : machine_id})
        rows = result.fetchall()
        return rows
    
def get_most_incident_machine():
    query = text("""
                SELECT machine_id, COUNT(*) AS nb_incidents
                FROM incidents
                GROUP BY machine_id
                ORDER BY nb_incidents DESC
                LIMIT 1;
                 """)
    with engine.connect() as conn:
        result = conn.execute(query)
        row = result.fetchone()
    
        return {
                "machine_id" : row[0],
                "incident_count" : row[1]
                }

def choose_tool(question):
    response = client.chat.complete(
        model = "ministral-3b-2512",
        messages = [
            {
            "role" : "system",
            "content" : """
            Tu es un agent de maintenance industrielle.

            Tu dois choisir UN outil parmi :

            get_most_incident_machine
            Arguments : {}
            
            get_avg_downtime_by_error
            Arguments : {"error_code" : "E104"}

            get_main_resolution
            Arguments : {"error_code": "E104"}
            
            get_incident_count_by_error
            Arguments : {"error_code": "E104"}
            
            get_incidents_by_machine
            Arguments : {"machine_id": "PH003"}

            answer_with_rag
            Arguments : {"question": "question utilisateur complète"}

            Réponds uniquement avec un JSON valide sous cette forme :

            {
                "tool": "nom_outil",
                "arguments": {}
            }

            N'ajoute aucun texte avant ou après le JSON.
            """
        },
        {
          "role" : "user",
          "content" : question 
        } 
        ]
    )
    
    response_text = response.choices[0].message.content.strip()
    
    response_text = response_text.replace("```json", "")
    response_text = response_text.replace("```", "")
    response_text = response_text.strip()
    
    return json.loads(response_text)

doc_folder = Path("data/documentation")

documents = []

for file_path in doc_folder.glob("*.txt"):
    texte = file_path.read_text(encoding = "utf-8")
    documents.append({
        "source" : file_path.name,
        "content" : texte
    })

chunks = []

for doc in documents:
    paragraphs = doc["content"].split("\n\n")
    
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        
        if paragraph:
            chunks.append({
                "source" : doc["source"],
                "content" : paragraph
            })

model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

texts = [chunk["content"] for chunk in chunks]

embeddings = model.encode(texts)

print(embeddings.shape)

def answer_with_rag(question):
    question_embedding = model.encode([question])
    scores = cosine_similarity(
        question_embedding,
        embeddings
    )[0]
    top_indices = scores.argsort()[-2:][::-1]
    context = "\n\n".join(chunks[idx]["content"] for idx in top_indices)
    
    response = client.chat.complete(
        model = "ministral-3b-2512", messages = [
            {"role" : "system",
             "content" : (
                "Tu es un assistant de maintenance industrielle. "
                "Réponds uniquement à partir de la documentation fournie. "
                "Si l'information n'est pas présente dans la documentation, "
                "dis-le clairement."
             )},
            {
                "role": "user",
                "content": f"""
                
                Documentation : {context}

                Question : {question}

                Réponds en français, de manière concise, en 2 à 4 étapes.
                """ 
            }
        ]
    )
    
    answer = response.choices[0].message.content
    sources = list({chunks[idx]["source"] for idx in top_indices})
    
    return {"response" : answer,
            "sources" : sources}
    
def answer_with_sql(question):
    q= question.lower()
    if "plus d'incidents" in q or "machine la plus" in q:
        row = get_most_incident_machine()
        return {
            "response" : f"La machine {row[0]} a eu le plus d'incients avec {row[1]} incidents.",
            "source" : "Neon PostgreSQL"
        }
    elif "temps d'arrêt moyen" in q:
        match = re.search(r"E\d{3}", question)
        
        if match:
            error_code = match.group()
            row = get_avg_downtime_by_error(error_code)
            return {
                "response" : f"Le temps d'arrêt moyen pour {error_code} est de {round(row[0], 1)} minutes.",
                "source" : "Neon PostgreSQL"
            }
            
    return {
        "response" : "Je ne sais pas encore traiter cette question SQL",
        "source" : "Neon PostgreSQL"
    }
    
    
error_catalog = {"E101" :  
                {"Machine_type" : ["Four industriel", "Robot d'assemblage", "Presse hydraulique"],
                "cause" : "surchauffe", 
                 "resolutions" : ["arrêt temporaire de la machine", 
                                  "remplacement thermo-regulateur", 
                                  "contrôle du système de refroidissement"],
                 "severity" : "High"},
                 "E102" : 
                {"Machine_type" : ["Presse hydraulique"],
                "cause" : "pression insuffisante",
                 "resolutions" : ["réglage de la pression", 
                                  "réinitialisation du système hydraulique", 
                                  "contrôle de la presse"],
                 "severity" : "Medium"},
                 "E103" :
                {"Machine_type" : ["Convoyeur", "Presse hydraulique", "Robot d'assemblage"],
                "cause" : "défaut moteur",
                "resolutions" : ["remplacement du moteur", 
                                 "arrêt du système", 
                                 "contrôle de l'alimentation moteur"],
                "severity" : "Critical"},
                "E104" : 
                {"Machine_type" : ["Robot d'assemblage"],
                "cause" : "capteur de position",
                "resolutions" : ["recalibrage du capteur", 
                                 "remplacement du capteur",
                                 "contrôle du câblage"],
                "severity" : "Low"},
                "E105" :
                {"Machine_type" : ["Convoyeur"],
                "cause" : "problème réseau",
                "resolutions" : ["vérification du câble réseau", 
                                 "redémarrage du routeur", 
                                 "intervention du support réseau"],
                "severity" : "Low"}
                }

machine_catalog = {"Presse hydraulique" : ["PH001", "PH002", "PH003"],
                   "Convoyeur" : ["CV001", "CV002", "CV003"],
                   "Four industriel" : ["FI001", "FI002"],
                   "Robot d'assemblage" : ["RA001", "RA002", "RA003"]}

tools = {
    "get_most_incident_machine": get_most_incident_machine,
    "get_avg_downtime_by_error": get_avg_downtime_by_error,
    "get_main_resolution": get_main_resolution,
    "get_incident_count_by_error": get_incident_count_by_error,
    "get_incidents_by_machine": get_incidents_by_machine,
    "answer_with_rag": answer_with_rag
}

tool_arguments = {
    "get_most_incident_machine": [],
    "get_avg_downtime_by_error": ["error_code"],
    "get_main_resolution": ["error_code"],
    "get_incident_count_by_error": ["error_code"],
    "get_incidents_by_machine": ["machine_id"],
    "answer_with_rag": ["question"]
}


def choose_tool(question):
    response = client.chat.complete(
        model = "ministral-3b-2512",
        messages = [
            {
            "role" : "system",
            "content" : """
            Tu es un agent de maintenance industrielle.

            Tu dois choisir UN outil parmi :

            get_most_incident_machine
            Arguments : {}
            
            get_avg_downtime_by_error
            Arguments : {"error_code" : "E104"}

            get_main_resolution
            Arguments : {"error_code": "E104"}
            
            get_incident_count_by_error
            Arguments : {"error_code": "E104"}
            
            get_incidents_by_machine
            Arguments : {"machine_id": "PH003"}

            answer_with_rag
            Arguments : {"question": "question utilisateur complète"}

            Réponds uniquement avec un JSON valide sous cette forme :

            {
                "tool": "nom_outil",
                "arguments": {}
            }

            N'ajoute aucun texte avant ou après le JSON.
            """
        },
        {
          "role" : "user",
          "content" : question 
        } 
        ]
    )
    
    response_text = response.choices[0].message.content.strip()
    
    response_text = response_text.replace("```json", "")
    response_text = response_text.replace("```", "")
    response_text = response_text.strip()
    
    return json.loads(response_text)

def validate_error_code(error_code):
    return error_code in error_catalog

valide_machine_ids = [
    machine_id 
    for machine_list in machine_catalog.values()
    for machine_id in machine_list
]
    
def validate_machine_id(machine_id):
    return machine_id in valide_machine_ids

def agent_answer(question):
    decision = choose_tool(question)
    
    tool_name = decision["tool"]
    arguments = decision["arguments"]
    
    if tool_name not in tools:
        return {
            "error" : f"Outil inconnu : {tool_name}"
        }
        
    expected_args = tool_arguments[tool_name]
        
    missing_args = [
        arg for arg in expected_args
        if arg not in arguments
    ]
    
    if missing_args:
        return {
            "error" : f"Arguments manquants : {missing_args}",
            "tool" : tool_name,
            "arguments" : arguments
        }
    
    if "error_code" in arguments:
        if not validate_error_code(arguments["error_code"]):
            return {
                "error": f"Code erreur inconnu : {arguments["error_code"]}",
                "tool" : tool_name,
                "arguments" : arguments
            }
            
    if "machine_id" in arguments:
        if not validate_machine_id(arguments["machine_id"]):
            return {
                "error" : f"Machine inconnue : {arguments["machine_id"]}",
                "tool" : tool_name,
                "arguments" : arguments
            }
    
    try :
        tool_result = tools[tool_name](**arguments)
    except Exception as e:
        return {
            "error" : str(e),
            "tool" : tool_name,
            "arguments" : arguments
        }
    
    response = client.chat.complete(
        model = "ministral-3b-2512",
        messages = [
            {
                "role" : "system",
                "content" : (
                    """
                    Tu es un assistant de maintenance industrielle.
                    Tu dois répondre à partir du résultat fourni par un outil.
                    N'invente aucune donnée absente du résultat.
                    """
                )
            },
            {
                "role" : "user",
                "content" : f"""
                Question utilisateur :
                {question}

                Outil utilisé :
                {tool_name}

                Résultat de l'outil :
                {tool_result}

                Respecte exactement les unités et les valeurs présentes dans le résultat de l'outil.
                Formule une réponse claire et concise en français.
                """
                
            }
        ]
    )
    
    clean_response = response.choices[0].message.content.replace("**", "")
    
    return {
        "tool" : tool_name,
        "arguments" : arguments,
        "tool_result" : tool_result,
        "response" : clean_response
    }