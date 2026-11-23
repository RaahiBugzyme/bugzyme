import sys
from pathlib import Path

# make `import dating_ml_model` work when pytest runs from anywhere
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
