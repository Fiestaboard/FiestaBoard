"""FiestaPanel output plugin: a full-screen board FiestaBoard draws itself.

FiestaBoard's first-party output for TVs and browsers. Frames are pulled by
the panel's viewer from FiestaBoard's last-frame store; nothing is pushed.
It depends on FiestaBoard only through the output-plugin author API
(:mod:`src.plugins`).
"""

from .output import FiestaPanelOutput

__all__ = ["FiestaPanelOutput"]
