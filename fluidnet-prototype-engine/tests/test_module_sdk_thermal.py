import math
import pytest
from fn_sdk import heat_exchanger_effectiveness


def test_independent_equal_capacity_and_parallel_flow_limits():
    assert heat_exchanger_effectiveness(ua_w_k=200,capacity_a_w_k=100,capacity_b_w_k=100)==pytest.approx(2/3)
    assert heat_exchanger_effectiveness(ua_w_k=200,capacity_a_w_k=100,capacity_b_w_k=200,counterflow=False)==pytest.approx((1-math.exp(-3))/1.5)
    assert heat_exchanger_effectiveness(ua_w_k=0,capacity_a_w_k=100,capacity_b_w_k=200)==0
    assert heat_exchanger_effectiveness(ua_w_k=200,capacity_a_w_k=0,capacity_b_w_k=200)==0
    assert heat_exchanger_effectiveness(ua_w_k=1e300,capacity_a_w_k=1e-300,capacity_b_w_k=1e-300)==1


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,True,'bad',10**1000])
def test_invalid_capacity_and_ua_rejected(value):
    for key in ['ua_w_k','capacity_a_w_k','capacity_b_w_k']:
        args={'ua_w_k':200,'capacity_a_w_k':100,'capacity_b_w_k':200}
        args[key]=value
        with pytest.raises(ValueError):heat_exchanger_effectiveness(**args)
    with pytest.raises(ValueError):heat_exchanger_effectiveness(ua_w_k=100,capacity_a_w_k=100,capacity_b_w_k=200,counterflow='bad')
