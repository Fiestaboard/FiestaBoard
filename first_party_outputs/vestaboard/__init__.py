"""Vestaboard output plugin: drive a Vestaboard Flagship, Note or Note array.

FiestaBoard's first-party output for Vestaboard hardware, over the Local
API, the RW Cloud API, the note-array Cloud API, or a local note array's
per-Note fan-out. It depends on FiestaBoard only through the output-plugin
author API (:mod:`src.plugins`).
"""

from .output import VestaboardOutput

__all__ = ["VestaboardOutput"]
