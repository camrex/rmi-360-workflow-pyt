# Lightweight version helper used for dynamic versioning via setuptools_scm

try:
    from setuptools_scm import get_version
    __version__ = get_version(root='..', relative_to=__file__)
except (ImportError, LookupError):
    __version__ = "dev"
