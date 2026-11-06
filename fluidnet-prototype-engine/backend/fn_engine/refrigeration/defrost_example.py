"""One cooler defrosts while a second cooler keeps a valid pumped-flow branch open."""
from ..catalog import catalog_map
from ..models import ScheduleEvent
from .multi_cooler_example import multi_cooler_example


def defrost_example():
    project=multi_cooler_example()
    cooler=next(i for i in project.instances if i.id=='CoolerB')
    cooler.module_id, cooler.name='defrost_air_cooler','独立电融霜冷风机'
    cooler.parameters.update(defrost_duration_s=120.,drip_duration_s=60.,defrost_room_fraction=.6)
    project.modules=[m for key,m in catalog_map().items() if key in {i.module_id for i in project.instances}]
    project.events=[ScheduleEvent(id='request',type='set_variable',time_s=60.,key='CoolerB.param.defrost_request',value=1.)]
    project.id,project.name='modular-electric-defrost','模块组装 · 同库冷风机独立电融霜'
    project.description='60s请求一台冷风机电融霜120s、滴水60s，另一台保持供液；请求不重复触发。显式加热份额入库房/制冷剂，不模拟霜量。'
    return project
