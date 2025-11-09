from flam.db.base import get_session
from flam.db.models import Config

#This code stores and retrieves simple configuration settings (key-value pairs) from a database. It allows saving values, and later retrieving them as string, integer, or float safely
def set_config(key, value):
    s = get_session()
    row = s.query(Config).filter_by(key=key).first()
    if row:
        row.value = str(value)
    else:
        s.add(Config(key=key, value=str(value)))
    s.commit()


def get_config(key, default=None):
    s = get_session()
    row = s.query(Config).filter_by(key=key).first()
    return row.value if row else default


def get_int(key, default):
    v = get_config(key)
    try:
        return int(v) if v is not None else default
    except:
        return default


def get_float(key, default):
    v = get_config(key)
    try:
        return float(v) if v is not None else default
    except:
        return default
