import subprocess
import sys
import json
from subprocess import TimeoutExpired
from fastmcp import FastMCP

mcp = FastMCP("mcp_tools_swebench")

# NOTES DE CONCEPTION (30/10, à condenser en anglais avant le rendu)
#
# TESTBED_PATH : variable d'environnement = « le dépôt à étudier est ici ».
#   - Pendant le run de l'agent : le dépôt est dans le conteneur Docker,
#     toujours à /testbed.
#   - Pendant le test isolé des tools : la moulinette met le dépôt où elle
#     veut, règle TESTBED_PATH et démarre ce serveur elle-même. Elle ne
#     promet RIEN d'autre (pas d'id de conteneur).
#   => Ne jamais écrire /testbed en dur : toujours partir de TESTBED_PATH.
#
# Architecture choisie : sandbox sur l'hôte, les tools passent par
# 'docker exec' pour agir dans le conteneur.
#
# CONTAINER_ID : variable d'environnement donnée par l'agent.
#   - Présente  -> les commandes tournent dans le conteneur :
#                  docker exec -w $TESTBED_PATH <id> <commande>
#   - Absente   -> mode local (cas du test isolé de la moulinette) :
#                  <commande> lancée avec cwd=$TESTBED_PATH
#   Lire les deux variables une seule fois, en constantes de module.
#
# Comment l'id arrive ici :
#   Agent -> Sandbox(..., env={"CONTAINER_ID": id, "TESTBED_PATH": "/testbed"})
#         -> MCPClient(..., env=env) -> StdioTransport(cmd, args, env=env)
#   PIÈGE (testé) : le SDK MCP ne transmet au serveur que HOME, LOGNAME,
#   PATH, SHELL, TERM, USER. Un os.environ[...] côté agent n'arrive PAS ici :
#   il faut passer env= explicitement. (PATH est gardé -> docker trouvé.)
#   En HTTP (--mcp-server), le client ne peut rien passer : lancer le
#   serveur avec les variables (CONTAINER_ID=... python mcp_tools_swebench.py)


# _run : fonction interne (pas de @mcp.tool, donc invisible pour le LLM).
# Chaque tool construit sa commande, appelle _run, puis formate la sortie ;
# seul _run sait OÙ la commande s'exécute (conteneur ou local).
#   - Commande en LISTE, jamais en chaîne avec shell=True : les arguments
#     viennent du LLM (pattern "x; rm -rf /testbed" = injection).
#     Seule exception voulue : run_command -> ["bash", "-c", command].
#   - Paramètres à prévoir : workdir (défaut TESTBED_PATH, pour
#     run_command), input pour stdin (edit_file : écrire dans le conteneur
#     via docker exec -i ... sh -c 'cat > fichier'), timeout (run_tests,
#     run_command).
#   - Renvoie stdout, stderr, code retour (CompletedProcess les a déjà).
def _run(cmd: list[str]):


@mcp.tool()
def read_file(file_path: str, start_line: int, end_line: int):
    cmd: list = ["sed", "-n", f"{start_line}", f"{end_line}p", f"{file_path}"]


if __name__ == "__main__":
    mcp.run(show_banner=False, log_level="WARNING")
