# security/api/views/whoami.py
from .me import MeView  # reutiliza

whoami = MeView.as_view()
