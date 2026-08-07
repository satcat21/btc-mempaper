"""Project root, resolved once.

Code that needs the repo root used to derive it from `__file__`, which is only
correct while the caller sits in the root directory. Splitting modules into
routes/ and services/ made every such path resolve one level too deep -
the display worker went looking for services/lib/display_worker.py.

Anchoring on this module instead keeps the answer the same wherever the caller
lives: utils/ is one level below the root, and that does not change.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
