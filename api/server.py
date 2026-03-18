# 하위 호환 shim - 실제 앱은 api.main에서 관리됩니다
from api.main import app

__all__ = ["app"]
