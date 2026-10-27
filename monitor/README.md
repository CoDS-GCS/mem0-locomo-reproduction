# Memory Journey

Read-only local web app that follows LOCOMO messages and questions through every stage of a Mem0g experiment
(dataset → add → memory state → search → answer → judge). It never writes to, stops or modifies the experiment
folder, Qdrant or Neo4j, and never opens a Kuzu file. Binds to 127.0.0.1 only.

    ./run.sh                                        # live Neo4j run  -> http://127.0.0.1:8731
    ./run.sh ~/mem0-repro/paper-eval-gemini 8732    # finished Kuzu run -> http://127.0.0.1:8732

Own venv (Python 3.12, Flask + neo4j driver + jinja2) in `.venv`; nothing is installed into the experiment venvs.
Cytoscape.js, dagre and cytoscape-dagre are vendored (pinned) in `static/vendor`, so the page works offline.
The About page explains every linking rule and every heuristic.

Layout: `server.py` (Flask API) · `core/` (indexer, linking, analysis, views) · `static/` (pages).
