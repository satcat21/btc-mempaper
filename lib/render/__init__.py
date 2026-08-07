"""ImageRenderer method groups, split out as mixins.

Each module holds one cohesive area of rendering. ImageRenderer inherits
them all, so every method keeps the same `self` and the same call sites.
"""
