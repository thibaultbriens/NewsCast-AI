# Document de Spécifications Techniques — Daily Briefing Podcast (MVP)

## 1. Contexte & Objectif

**Produit** : Générateur automatisé de podcasts d'actualité quotidiens, exécuté sur serveur personnel, livré via webhook Discord et URL directe.  
**Public cible** : Usage personnel (MVP), puis application mobile grand public (V2).  
**Philosophie MVP** : Aucune interface graphique, aucune base de données distante, aucune gestion de charge, stockage filesystem uniquement.

---

## 2. Environnement Cible

| Ressource | Spécification |
|-----------|---------------|
| **Cloud Provider** | Oracle Cloud Infrastructure (OCI) — Free Tier |
| **Compute** | VM ARM64 (Ampere A1), 4 vCPU, 24 GB RAM |
| **OS** | Ubuntu Server 22.04 LTS ARM64 |
| **Runtime** | Python 3.11+ |
| **Accès réseau** | IP publique brute (pas de nom de domaine pour le MVP) |
| **Stockage** | Disque local de la VM uniquement |

---

## 3. Architecture Logicielle

### 3.1 Stack Technique

| Couche | Outil / Librairie | Version / Modèle | Justification |
|--------|-------------------|------------------|---------------|
| **Orchestration** | Python 3.11 | — | Logique métier principale |
| **Scheduling** | Systemd Timer | — | Plus fiable que cron (logs natifs, gestion d'erreurs) |
| **Sources Actu** | NewsAPI + RSS (feedparser) | NewsAPI (plan gratuit) | API structurée + fallback RSS |
| **LLM Local** | Ollama | `llama3.1:8b` (ou `gemma2:9b`) | Inférence 100% locale, API HTTP interne |
| **TTS Local** | Piper TTS | `fr_FR-siwis-medium` (défaut) | CPU-only, ARM64 natif, multilingue |
| **Traitement Audio** | FFmpeg | 4.4+ | Concaténation, normalisation, compression MP3 |
| **Delivery** | Discord Webhook + FastAPI | FastAPI 0.100+ | Webhook pour notification, FastAPI pour URL de téléchargement |
| **Config** | YAML + JSON | — | Aucune base de données |

### 3.2 Flux de Données (Data Flow)

```
[05:55] Systemd Timer déclenche main.py
    │
    ▼
┌─────────────────┐
│  NewsFetcher    │ ◄── NewsAPI (primaire) + RSS (fallback)
│  Récupération   │
└────────┬────────┘
         │ Liste d'articles (JSON)
         ▼
┌─────────────────┐
│  ScriptGenerator│ ◄── Ollama (llama3.1:8b)
│  Génération     │     Prompt structuré (narratif)
└────────┬────────┘
         │ Script texte brut (.txt)
         ▼
┌─────────────────┐
│  PiperTTS       │ ◄── Modèle voix (fr_FR-siwis-medium)
│  Synthèse vocale│     Découpage par paragraphes
└────────┬────────┘
         │ Segments audio WAV
         ▼
┌─────────────────┐
│  AudioAssembler │ ◄── FFmpeg
│  Assemblage     │     Normalisation + MP3 128kbps
└────────┬────────┘
         │ Fichier podcast final (.mp3)
         ▼
┌─────────────────┐
│  Delivery       │ ◄── Discord Webhook (multipart)
│  Livraison      │     + FastAPI (IP:8000/podcasts/)
└─────────────────┘
```

---

## 4. Spécifications Fonctionnelles Détaillées

### 4.1 Module `NewsFetcher`

**Responsabilité** : Récupérer les articles des dernières 24h selon le sujet et la région demandés.

**Entrée** : Configuration issue de `config.yaml` (sujet, région, langue).

**Sources (ordre de priorité)** :
1. **NewsAPI** (`newsapi.org`) — Plan gratuit (100 requêtes/jour).
   - Endpoint : `/v2/everything` (recherche par mot-clé) ou `/v2/top-headlines` (par pays).
   - Paramètres : `q`, `language`, `from`, `to`, `sortBy=publishedAt`, `pageSize=20`.
2. **RSS Fallback** — Fichier `sources.yaml` listant les flux par catégorie.
   - Format : `feedparser` pour parser les flux Atom/RSS.
   - Filtre temporel : articles publiés dans les dernières 24h uniquement.

**Traitement post-récupération** :
- **Dédoublonnage** : Par URL exacte (hash MD5 de l'URL).
- **Filtrage régional** : Si `region` est spécifié (ex: `fr`, `us`, `world`), filtrer via :
  - Code pays NewsAPI (`country` parameter) si disponible.
  - Sinon filtrage par mots-clés dans le titre/description (liste de mots-clés par pays dans `config.yaml`).
- **Nettoyage** : Supprimer le HTML des descriptions, tronquer à 500 caractères.
- **Sortie** : Fichier JSON `data/raw/YYYY-MM-DD/{topic}_articles.json`.

**Format de sortie (JSON)** :
```json
[
  {
    "title": "string",
    "description": "string",
    "url": "string",
    "published_at": "ISO-8601",
    "source": "string"
  }
]
```

---

### 4.2 Module `ScriptGenerator` (LLM)

**Responsabilité** : Transformer les articles en script de podcast narratif.

**Moteur** : Ollama (service local en background, port 11434 par défaut).

**Modèle cible** : `llama3.1:8b` (premier choix). Fallback acceptable : `gemma2:9b`.

**Prompt System (obligatoire)** :

```
Tu es un journaliste professionnel rédigeant le script d'un podcast d'actualité 
matinal de 5 à 6 minutes. Le public est un particulier curieux mais non spécialiste.

CONTRAINTES ABSOLUES :
- Langue : {langue} (ex: Français)
- Durée : 800 à 1000 mots (correspond à ~5-6 minutes de parole)
- Format : Texte brut, aucun markdown, aucun titre de section explicite
- Structure narrative obligatoire :
  1. INTRO (60-80 mots) : Date du jour, accroche, présentation des 3 sujets principaux
  2. DOSSIER 1 (200-250 mots) : Sujet le plus important. Contexte, fait clé, implication
  3. DOSSIER 2 (200-250 mots) : Deuxième sujet. Angle différent ou actualité complémentaire
  4. DOSSIER 3 (150-200 mots) : Troisième sujet ou actualité rapide
  5. CONCLUSION (60-80 mots) : Récap des points clés, transition vers la journée

TON : Professionnel mais accessible. Pas de jargon. Transitions naturelles entre sujets.
INTERDICTION : Ne mentionne pas que tu es une IA. Ne cite pas "selon les articles". 
Raconte l'actualité comme un journaliste le ferait à l'antenne.

ARTICLES SOURCE :
{articles_formattés}
```

**Appel API** : Requête HTTP POST sur `http://localhost:11434/api/generate` (format Ollama natif) ou via le client Python `ollama`.

**Paramètres d'inférence** :
- `temperature`: 0.7 (équilibre créativité/consistance)
- `num_predict`: 1500 (limite de tokens générés)
- `top_p`: 0.9

**Sortie** : Fichier texte `data/scripts/YYYY-MM-DD/{topic}_script.txt`.

---

### 4.3 Module `PiperTTS`

**Responsabilité** : Convertir le script texte en segments audio WAV.

**Moteur** : Piper TTS (binaire exécutable, pas de librairie Python native requise — appel via `subprocess`).

**Voix par défaut** : `fr_FR-siwis-medium` (féminine, claire, professionnelle).  
**Architecture voix** : Les fichiers `.onnx` et `.json` des voix sont stockés dans `piper-voices/`.

**Multilingue (préparation)** : La configuration `config.yaml` spécifie la langue cible. Le module charge la voix correspondante selon une table de mapping :
- `fr` → `fr_FR-siwis-medium`
- `en` → `en_US-lessac-medium`
- (Extensible pour V2)

**Découpage** : Le script est découpé en segments par paragraphes (délimités par `\n\n`). Cela permet :
- Une reprise sur erreur si un segment échoue.
- Une gestion de la mémoire (Piper charge/décharge le modèle).

**Paramètres d'exécution** :
- `--length_scale 1.0` (vitesse normale)
- `--noise_scale 0.667` (qualité par défaut)

**Sortie** : Fichiers WAV dans `data/audio/YYYY-MM-DD/segments/segment_001.wav`, `segment_002.wav`, etc.

---

### 4.4 Module `AudioAssembler`

**Responsabilité** : Assembler les segments WAV en un fichier MP3 final cohérent.

**Outil** : FFmpeg (appel ligne de commande via `subprocess`).

**Pipeline FFmpeg** :
1. Concaténation des segments WAV (liste fournie via fichier texte temporaire `concat_list.txt`).
2. Normalisation audio (loudness EBU R128 ou simple `dynaudnorm`).
3. Compression en MP3 :
   - Codec : `libmp3lame`
   - Bitrate : 128 kbps (équilibre qualité/taille)
   - Fréquence : 44100 Hz
   - Canal : Mono (suffisant pour de la parole)

**Pas de jingle** : Le fichier final ne contient que la voix synthétisée (spécification MVP).

**Sortie** : `output/YYYY-MM-DD/podcast.mp3`.

---

### 4.5 Module `Delivery`

**Responsabilité** : Livrer le fichier final à l'utilisateur.

#### A. Discord Webhook (canal privé)
- **Format** : Requête HTTP POST `multipart/form-data`.
- **Champs** :
  - `content`: Message texte court (ex: "📰 Votre briefing du {date} est prêt.")
  - `file`: Le fichier MP3 attaché.
- **Limite** : Discord impose 25 MB max par fichier. À 128 kbps, 10 min = ~10 MB. Pas de risque pour le MVP.
- **Gestion d'erreur** : Si le webhook échoue (HTTP != 204), logger l'erreur mais ne pas bloquer (le fichier reste accessible via URL).

#### B. Serveur FastAPI (URL locale)
- **Framework** : FastAPI + Uvicorn (1 worker suffisant).
- **Route** : `GET /podcasts/{date}.mp3`
  - `date` au format `YYYY-MM-DD`.
  - Retourne le fichier MP3 avec le bon `Content-Type: audio/mpeg`.
  - Si le fichier n'existe pas : 404.
- **Lancement** : Uvicorn bind sur `0.0.0.0:8000`.
- **Accès** : Depuis le téléphone, l'utilisateur saisit `http://{IP_PUBLIQUE_VM}:8000/podcasts/2026-04-19.mp3`.
- **Durée de rétention** : Les fichiers sont conservés 30 jours (nettoyage automatique via script ou `tmpwatch`).

---

### 4.6 Module `API` (FastAPI Minimal)

**Responsabilité** : Servir les fichiers MP3 historiques.

**Routes obligatoires** :

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/podcasts/{date}.mp3` | Téléchargement du podcast du jour |
| `GET` | `/health` | Healthcheck simple (vérifie qu'Ollama répond) |
| `GET` | `/latest` | Redirection 307 vers le dernier podcast disponible |

**Pas d'authentification** pour le MVP (l'IP publique + obscurité de l'URL suffisent).

---

## 5. Configuration & Fichiers

### 5.1 `config/config.yaml` (Fichier Principal)

```yaml
app:
  language: "fr"  # Code langue ISO 639-1
  timezone: "Europe/Paris"
  retention_days: 30

topics:
  tech_enterprises:
    name: "Actualité Tech"
    queries: ["Apple", "Google", "Microsoft", "NVIDIA", "OpenAI"]
    language: "fr"
    region: null  # null = monde entier
    max_articles: 15
    
  geopolitique:
    name: "Géopolitique Mondiale"
    queries: ["géopolitique", "diplomatie", "conflit", "ONU"]
    region: null
    max_articles: 15

  sport:
    name: "Actualité Sportive"
    queries: ["football", "NBA", "JO", "coupe du monde"]
    region: null
    max_articles: 10

  all_topics:
    name: "Briefing Complet"
    queries: ["actualité", "politique", "économie", "sport", "technologie"]
    region: null
    max_articles: 20

models:
  llm: "llama3.1:8b"
  tts_voice: "fr_FR-siwis-medium"

delivery:
  discord_webhook_url: "https://discord.com/api/webhooks/..."
  server_port: 8000
  server_host: "0.0.0.0"

newsapi:
  api_key: "${NEWSAPI_KEY}"  # Variable d'environnement
  base_url: "https://newsapi.org/v2"
```

### 5.2 `config/sources.yaml` (RSS Fallback)

```yaml
rss_feeds:
  tech:
    - "https://www.lemonde.fr/technologies/rss_full.xml"
    - "https://techcrunch.com/feed/"
  geopolitique:
    - "https://www.lemonde.fr/international/rss_full.xml"
    - "https://feeds.bbci.co.uk/news/world/rss.xml"
  sport:
    - "https://www.lequipe.fr/rss/actu_rss.xml"
```

### 5.3 Arborescence Fichiers (Runtime)

```
/opt/news-podcast/
├── config/
│   ├── config.yaml
│   └── sources.yaml
├── data/
│   ├── raw/YYYY-MM-DD/{topic}_articles.json
│   ├── scripts/YYYY-MM-DD/{topic}_script.txt
│   └── audio/YYYY-MM-DD/segments/segment_NNN.wav
├── output/YYYY-MM-DD/podcast.mp3
├── piper-voices/
│   ├── fr_FR-siwis-medium.onnx
│   ├── fr_FR-siwis-medium.onnx.json
│   └── en_US-lessac-medium.onnx
├── logs/
│   └── YYYY-MM-DD.log
├── src/
│   ├── __init__.py
│   ├── fetcher.py
│   ├── generator.py
│   ├── tts.py
│   ├── assembler.py
│   ├── delivery.py
│   ├── api.py
│   └── utils.py
├── main.py
└── requirements.txt
```

---

## 6. Orchestration & Scheduling

### 6.1 Script Principal (`main.py`)

**Fonction** : `run_pipeline(topic_key: str)`

**Gestion d'exécution unique** :
- Créer un fichier `.lock` (`/tmp/news-podcast.lock`) au démarrage.
- Si le fichier existe déjà, vérifier le PID. Si le processus est mort, supprimer le lock. Sinon, exit(1).
- Supprimer le lock en fin d'exécution (même en cas d'erreur — utiliser `try/finally`).

**Séquence d'exécution** :
1. Vérifier la connexion à Ollama (`GET http://localhost:11434`).
2. Récupérer les articles (`NewsFetcher`).
3. Si aucun article trouvé, logger et sortir.
4. Générer le script (`ScriptGenerator`).
5. Synthétiser la voix (`PiperTTS`).
6. Assembler l'audio (`AudioAssembler`).
7. Livrer (`Delivery`).
8. Logger le succès avec la durée totale du pipeline.

### 6.2 Systemd Timer

**Fichier `/etc/systemd/system/news-podcast.service`** :
```ini
[Unit]
Description=Daily News Podcast Generator
After=network.target ollama.service

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/opt/news-podcast
ExecStart=/usr/bin/python3 /opt/news-podcast/main.py
Environment="PYTHONPATH=/opt/news-podcast"
Environment="NEWSAPI_KEY=xxx"
StandardOutput=append:/var/log/news-podcast.log
StandardError=append:/var/log/news-podcast-error.log
```

**Fichier `/etc/systemd/system/news-podcast.timer`** :
```ini
[Unit]
Description=Run News Podcast daily at 5:55 AM

[Timer]
OnCalendar=*-*-* 05:55:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Remarque** : Le timer démarre à 5h55 pour garantir la disponibilité du fichier à 6h00.

---

## 7. Sécurité & Réseau

### 7.1 Firewall OCI (Cloud)

Règles de Security List / NSG obligatoires :

| Direction | Protocole | Port Source | Port Dest | Source | Action |
|-----------|-----------|-------------|-----------|--------|--------|
| Ingress | TCP | Any | 8000 | 0.0.0.0/0 | Allow |
| Ingress | TCP | Any | 22 | `<IP_ADMIN>/32` | Allow |
| Egress | All | Any | Any | 0.0.0.0/0 | Allow |

**Note** : Le port 8000 est exposé publiquement (pas de restriction IP pour le MVP, conformément aux choix produit).

### 7.2 Sécurité Application

- Aucune clé API en dur dans le code. Utiliser les variables d'environnement.
- Le dossier `data/` et `output/` doivent avoir des permissions `750` (user:group `ubuntu:ubuntu`).
- Pas de traitement de données utilisateur (pas de PII), donc pas de RGPD critique pour le MVP personnel.

---

## 8. Logging & Monitoring

**Niveau de log** : INFO minimum, DEBUG en option (configurable via `config.yaml`).

**Format** :
```
[YYYY-MM-DD HH:MM:SS] [LEVEL] [MODULE] Message
```

**Fichiers de log** :
- `/var/log/news-podcast.log` : Logs applicatifs (rotation via `logrotate` ou intégré Python `RotatingFileHandler`).
- `/var/log/news-podcast-error.log` : STDERR séparé (config Systemd).

**Métriques à logger** :
- Durée totale du pipeline
- Nombre d'articles récupérés
- Nombre de tokens générés par Ollama (si disponible dans la réponse)
- Taille du fichier MP3 final
- Statut de la livraison Discord (succès/échec)

---

## 9. Critères d'Acceptation (Definition of Done)

| ID | Critère | Validation |
|----|---------|------------|
| CA-01 | Le pipeline s'exécute automatiquement tous les jours à 5h55 sans intervention manuelle | Vérifier les logs Systemd sur 3 jours consécutifs |
| CA-02 | Le podcast généré fait entre 4 et 8 minutes (taille fichier ou durée FFmpeg) | Mesure via `ffprobe` |
| CA-03 | Le script suit la structure narrative (intro + 3 dossiers + conclusion) | Revue manuelle du fichier `.txt` |
| CA-04 | Le fichier MP3 est livré sur Discord avant 6h05 | Vérifier timestamp du message |
| CA-05 | Le fichier MP3 est téléchargeable via `http://IP:8000/podcasts/{date}.mp3` | Test HTTP 200 depuis un réseau externe |
| CA-06 | Le système fonctionne avec `region: null` (monde entier) et avec `region: "fr"` | Test A/B sur deux sujets |
| CA-07 | En cas d'indisponibilité de NewsAPI, le fallback RSS prend le relais | Simuler une panne (mauvaise clé API) |
| CA-08 | Deux exécutions simultanées sont impossibles (lock file) | Lancer manuellement deux instances |

---

## 10. Évolutivité & V2 (Non MVP)

Ces points sont hors scope mais l'architecture doit les supporter sans réécriture majeure :

| Feature V2 | Préparation dans MVP |
|------------|---------------------|
| Application mobile | L'API FastAPI servira de backend ; garder les routes REST stateless |
| Authentification utilisateur | Ajouter un middleware JWT sur FastAPI sans toucher au pipeline |
| Base de données | Remplacer les fichiers JSON par PostgreSQL ; les fonctions fetcher/generator restent inchangées |
| Cache CDN | Remplacer le dossier `output/` par un bucket Object Storage OCI |
| Génération de musique d'intro | Ajouter un segment avant `AudioAssembler` (module `JingleGenerator`) |
| Multi-utilisateur | Le fichier `config.yaml` devient une table `users`, le pipeline prend un `user_id` en paramètre |

---

## 11. Livrables Attendus du Développeur

1. **Code source** structuré selon l'arborescence §5.3.
2. **Fichiers Systemd** prêts à l'emploi (`news-podcast.service`, `news-podcast.timer`).
3. **Script d'installation** (`install.sh`) :
   - Installation d'Ollama + téléchargement du modèle `llama3.1:8b`.
   - Installation de Piper TTS + téléchargement des voix FR/EN.
   - Installation des dépendances Python (`requirements.txt`).
   - Création des dossiers et application des permissions.
4. **Documentation RUNBOOK** : Commandes pour vérifier l'état, relancer manuellement, consulter les logs.

---

**Document validé pour développement.**  
*Version 1.0 — MVP Local — Oracle Cloud ARM64*
