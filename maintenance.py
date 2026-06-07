import os
_FLAG = "/tmp/maintenance.flag"

def is_maintenance() -> bool:
    return os.path.exists(_FLAG)

def set_maintenance(active: bool):
    if active:
        open(_FLAG, "w").close()
    else:
        try: os.remove(_FLAG)
        except FileNotFoundError: pass
