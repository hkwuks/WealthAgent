"""FundQuant 策略引擎"""
# 导入所有策略模块以触发注册
from . import base
from . import fusion
from .timing import valuation_deviation
from .timing import momentum
from .timing import interest_rate
from .timing import fx_momentum
from .timing import smart_dca
from .timing import commodity
from .selection import multi_factor
from .selection import rating_enhanced
from .allocation import risk_parity
from .allocation import black_litterman
