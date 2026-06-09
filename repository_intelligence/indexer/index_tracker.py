import sys
import os

# Ensure the .agent directory is in sys.path
agent_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".agent"))
if agent_path not in sys.path:
    sys.path.insert(0, agent_path)

from retrieval.index_tracker import IndexTracker

