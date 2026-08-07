"""Route registration, split out of MempaperApp._setup_routes.

Every module exposes register(self), taking the MempaperApp instance. The
parameter is named `self` so the moved bodies, decorators included, read
exactly as they did inside the class.
"""
