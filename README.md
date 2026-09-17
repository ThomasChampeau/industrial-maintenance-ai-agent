# Industrial Maintenance AI Agent

Prototype d’assistant IA dédié à la maintenance industrielle, combinant **données structurées, recherche documentaire, RAG, SQL et agent outillé**.

L’objectif du projet est de permettre à un utilisateur de poser une question en langage naturel sur des incidents industriels ou des procédures de maintenance, puis de laisser l’agent choisir automatiquement la source et l’outil les plus adaptés pour produire une réponse contextualisée et traçable.

## Objectif du projet

Le système doit être capable de répondre à deux grandes catégories de questions :

**Questions basées sur l’historique des incidents**

* Quelle machine a eu le plus d’incidents ?
* Quel est le temps d’arrêt moyen pour l’erreur E104 ?
* Combien de fois l’erreur E103 est-elle apparue ?
* Quelle résolution est la plus fréquemment utilisée pour E102 ?

Ces questions sont traitées à partir d’une base PostgreSQL hébergée sur Neon.

**Questions basées sur la documentation technique**

* Que vérifier si une presse hydraulique manque de pression ?
* Que faire lorsqu’un moteur de convoyeur s’arrête ?
* Comment réagir à un problème de capteur de position ?

Ces questions passent par un pipeline **RAG — Retrieval-Augmented Generation** utilisant une recherche sémantique dans la documentation de maintenance.

## Architecture générale

```text
Question utilisateur
        │
        ▼
     Agent IA
        │
        ├───────────────► Outils SQL
        │                    │
        │                    ▼
        │              PostgreSQL / Neon
        │
        └───────────────► Outil RAG
                             │
                             ▼
                  Recherche sémantique
                             │
                             ▼
                     Documentation
                             │
                             ▼
                         Mistral
                             │
                             ▼
                     Réponse finale
```

L’agent utilise un LLM pour sélectionner l’outil le plus pertinent et générer les arguments nécessaires à son exécution.

Python exécute ensuite réellement la fonction choisie.

Le LLM ne simule donc pas une requête SQL ou une recherche documentaire : il orchestre des outils réels.

## Fonctionnement du RAG

RAG signifie **Retrieval-Augmented Generation**, ou génération augmentée par récupération d’information.

Le pipeline fonctionne en plusieurs étapes :

```text
Documents techniques
        ↓
Découpage en chunks
        ↓
Embeddings
        ↓
Recherche par similarité cosinus
        ↓
Sélection des passages pertinents
        ↓
Construction du contexte
        ↓
Appel du LLM Mistral
        ↓
Réponse basée sur la documentation
```

Les embeddings sont générés avec :

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

Le choix d’un modèle multilingue permet d’obtenir une meilleure recherche sémantique sur les documents et questions en français.

## Agent et Tool Calling

L’agent dispose de plusieurs outils métier :

```text
get_most_incident_machine
get_avg_downtime_by_error
get_main_resolution
get_incident_count_by_error
get_incidents_by_machine
answer_with_rag
```

Pour chaque question, le LLM produit une décision structurée en JSON.

Exemple :

```json
{
  "tool": "get_avg_downtime_by_error",
  "arguments": {
    "error_code": "E104"
  }
}
```

Python récupère ensuite le nom de l’outil et ses arguments puis exécute réellement :

```python
tools[tool_name](**arguments)
```

Le résultat de l’outil est ensuite renvoyé au LLM afin de produire une réponse utilisateur claire.

## Robustesse et validation

Plusieurs contrôles ont été ajoutés afin d’éviter qu’une mauvaise décision du modèle provoque une erreur applicative :

* validation du nom de l’outil ;
* contrôle des arguments obligatoires ;
* validation des codes erreur ;
* validation des identifiants machines ;
* gestion des exceptions ;
* nettoyage des réponses JSON ;
* contrôle des unités et valeurs retournées par les outils ;
* gestion des codes erreur inconnus.

Par exemple, une demande concernant :

```text
E999
```

est rejetée comme code erreur inconnu avant l’exécution d’une requête SQL.

## Routage des requêtes

Plusieurs stratégies de routage ont été expérimentées au cours du projet :

### Routage par mots-clés

Première approche simple basée sur la présence de termes comme :

```text
combien
moyenne
historique
temps d'arrêt
```

Cette méthode est facile à implémenter mais peu flexible.

### Routage par embeddings

Les questions sont transformées en vecteurs puis comparées à des exemples de questions SQL et RAG.

Une seconde approche utilise des **centroïdes**, représentant le profil sémantique moyen de chaque catégorie.

### Routage par LLM

Le LLM classe directement l’intention de la question entre :

```text
sql
rag
```

Cette approche a obtenu 100 % de bonnes classifications sur le jeu de test construit pour le prototype.

Ce résultat correspond uniquement au jeu de tests utilisé et ne constitue pas une mesure générale de performance.

## Dataset

Un dataset synthétique de **200 incidents industriels** a été généré en Python.

Chaque incident contient notamment :

```text
incident_id
machine_id
machine_type
error_code
cause
resolution
severity
downtime_minutes
date
status
```

Les incidents sont générés à partir de règles métier afin de conserver une cohérence entre :

```text
code erreur
→ type de machine
→ cause
→ résolution
→ criticité
→ durée d'arrêt
```

Exemples de codes erreur :

```text
E101 → surchauffe
E102 → pression insuffisante
E103 → défaut moteur
E104 → capteur de position
E105 → problème réseau
```

Les données sont ensuite chargées dans une base **PostgreSQL hébergée sur Neon**.

## Interface

Une interface utilisateur a été réalisée avec **Streamlit**.

Elle permet :

* de poser une question en langage naturel ;
* d'afficher la réponse de l’agent ;
* d’identifier l’outil utilisé ;
* de visualiser les arguments transmis ;
* de consulter le résultat brut de l’outil ;
* d’afficher les sources documentaires utilisées par le RAG.

Cette traçabilité permet de mieux comprendre comment la réponse a été produite.

## Stack technique

**Langage**

* Python

**Data**

* pandas
* PostgreSQL
* Neon
* SQLAlchemy
* psycopg2

**IA / NLP**

* Sentence Transformers
* scikit-learn
* cosine similarity
* Mistral API

**Application**

* Streamlit

**Configuration**

* python-dotenv

## Structure du projet

```text
industrial-maintenance-ai-agent/
│
├── app.py
├── agent.py
├── requirements.txt
├── README.md
├── .gitignore
│
├── data/
│   ├── incidents.csv
│   │
│   └── documentation/
│       ├── maintenance_capteurs.txt
│       ├── maintenance_hydraulique.txt
│       ├── maintenance_moteurs.txt
│       ├── maintenance_reseau.txt
│       └── surchauffe.txt
│
└── notebooks/
    └── prototype.ipynb
```

## Installation

Cloner le repository :

```bash
git clone <URL_DU_REPOSITORY>
cd industrial-maintenance-ai-agent
```

Installer les dépendances :

```bash
pip install -r requirements.txt
```

Créer un fichier `.env` :

```text
MISTRAL_API_KEY=votre_cle_api
DATABASE_URL=votre_url_postgresql
```

Le fichier `.env` n’est pas versionné et doit rester local.

Lancer l’application :

```bash
streamlit run app.py
```

## Exemples de questions

```text
Quelle machine a eu le plus d'incidents ?

Quel est le temps d'arrêt moyen pour E104 ?

Quelle résolution est la plus utilisée pour E102 ?

Montre-moi l'historique de la machine PH003.

Que dois-je vérifier si une presse manque de pression ?

Que faire si le moteur du convoyeur s'arrête ?

Comment réagir à une erreur de capteur de position ?
```

## Expérimentations réalisées

Plusieurs approches ont été testées au cours du développement.

Pour la génération, différents modèles locaux ont notamment été expérimentés :

* FLAN-T5 Base ;
* FLAN-T5 Large ;
* Qwen 2.5 Instruct ;
* versions quantifiées GGUF avec llama.cpp.

Les contraintes matérielles de l’environnement local ont finalement conduit à découpler la génération du reste du pipeline et à utiliser l’API Mistral.

Cette architecture permet de conserver localement :

```text
embeddings
recherche documentaire
logique métier
SQL
orchestration
```

tout en externalisant uniquement la génération du LLM.

## Limites actuelles

Ce projet reste un prototype.

Les principales limites identifiées sont :

* dataset synthétique ;
* documentation volontairement limitée ;
* nombre restreint d’outils disponibles ;
* absence de mémoire conversationnelle ;
* pas d’authentification utilisateur ;
* absence de monitoring avancé du LLM ;
* évaluation du routage réalisée sur un petit jeu de tests ;
* dépendance à une API externe pour la génération.

## Évolutions possibles

Le projet pourrait être prolongé avec :

* ajout de nouveaux outils métier ;
* génération automatique de tickets de maintenance ;
* intégration d’un véritable système de gestion d’incidents ;
* stockage des embeddings dans une base vectorielle ;
* évaluation automatisée des réponses du RAG ;
* monitoring des appels au LLM ;
* mémoire conversationnelle ;
* gestion de plusieurs sources documentaires ;
* authentification et gestion des rôles ;
* modèle local ou hébergé selon les contraintes d’infrastructure.

## Ce que ce projet m’a permis d’explorer

Ce projet m’a permis de mettre en pratique plusieurs concepts liés aux architectures Data & IA :

* génération et structuration de données ;
* SQL et PostgreSQL ;
* embeddings ;
* recherche sémantique ;
* RAG ;
* LLM ;
* routage d’intention ;
* tool calling ;
* agents IA ;
* validation et gestion des erreurs ;
* traçabilité des décisions d’un agent ;
* intégration d’une application IA avec Streamlit.

L’objectif principal était de comprendre chaque composant de l’architecture plutôt que d’utiliser directement un framework agentique abstrait.

Cela permet notamment de mieux distinguer les rôles respectifs de la base SQL, de la recherche documentaire, du LLM et de l’orchestrateur.
