"""S5-4 explicit dry-coil geometry design. Coefficients supplied with provenance, no hidden fit."""
import math
from pydantic import Field, model_validator
from .models import StrictModel

class CoilGeometryRequest(StrictModel):
    tube_inner_diameter_m:float=Field(default=.010,gt=0,le=1)
    tube_outer_diameter_m:float=Field(default=.012,gt=0,le=1)
    tube_length_m:float=Field(default=1.,gt=0,le=100)
    parallel_tubes:int=Field(default=20,ge=1,le=10000,strict=True)
    face_width_m:float=Field(default=.6,gt=0,le=100)
    face_height_m:float=Field(default=.5,gt=0,le=100)
    fins:int=Field(default=100,ge=0,le=10000,strict=True)
    fin_thickness_m:float=Field(default=.0001,ge=0,le=.1)
    fin_efficiency:float=Field(default=.8,gt=0,le=1)
    air_film_w_m2_k:float=Field(default=30.,gt=0,le=1e6)
    water_film_w_m2_k:float=Field(default=1500.,gt=0,le=1e7)
    wall_conductivity_w_m_k:float=Field(default=200.,gt=0,le=1e5)
    air_free_area_m2:float=Field(default=.2,gt=0,le=10000)
    air_loss_coefficient:float=Field(default=3.,ge=0,le=1e5)
    water_darcy_friction_factor:float=Field(default=.03,gt=0,le=1)
    water_minor_loss_coefficient:float=Field(default=2.,ge=0,le=1e5)
    source:str=Field(default='教学指定h/摩阻/K/翅片效率，未经厂家或全Re关联标定',min_length=1,max_length=1000)
    @model_validator(mode='after')
    def geometry(self):
        if self.tube_outer_diameter_m<=self.tube_inner_diameter_m:raise ValueError('外径必须大于内径')
        if self.fins*self.fin_thickness_m>=self.tube_length_m:raise ValueError('翅片总厚度须小于管长')
        if self.parallel_tubes*math.pi*self.tube_outer_diameter_m**2/4>=self.face_width_m*self.face_height_m:raise ValueError('管孔面积超过迎风面积')
        if self.air_free_area_m2>self.face_width_m*self.face_height_m:raise ValueError('净通风面积不能超过迎风面积')
        if not self.source.strip():raise ValueError('必须注明系数来源')
        return self
class CoilGeometryResponse(StrictModel):
    parameters:dict[str,float]
    areas:dict[str,float]
    effective_ua_w_k:float
    source:str
    assumptions:list[str]

def design(p):
    n=p.parallel_tubes;di=p.tube_inner_diameter_m;do=p.tube_outer_diameter_m;length=p.tube_length_m
    water_area=n*math.pi*di*length
    bare=n*math.pi*do*(length-p.fins*p.fin_thickness_m)
    fins=2*p.fins*(p.face_width_m*p.face_height_m-n*math.pi*do*do/4)
    air_area=bare+p.fin_efficiency*fins
    air_ua=p.air_film_w_m2_k*air_area
    wall=math.log(do/di)/(2*math.pi*p.wall_conductivity_w_m_k*length*n)
    water_ua=1/(1/(p.water_film_w_m2_k*water_area)+wall)
    parameters={'air_side_ua_w_k':air_ua,'water_side_ua_w_k':water_ua,
        'diameter_m':math.sqrt(4*p.air_free_area_m2/math.pi),'loss_coefficient':p.air_loss_coefficient,
        'secondary_diameter_m':math.sqrt(n)*di,
        'secondary_loss_coefficient':p.water_darcy_friction_factor*length/di+p.water_minor_loss_coefficient}
    return CoilGeometryResponse(parameters=parameters,areas={'water_wetted_m2':water_area,'bare_air_m2':bare,'fin_m2':fins,'effective_air_m2':air_area},
        effective_ua_w_k=1/(1/air_ua+1/water_ua),source=p.source,
        assumptions=['相同并联圆管、平整翅片、均匀流动；无集管不均流/翅片接触热阻/管壁热容',
            '指定膜系数、Darcy摩阻、局部K与翅片效率，适用设计点；未自动推断Re相关性',
            '仅干盘管几何设计；实际水盘管运行仍按原双回路物性与干湿能力检查，湿面/结霜需另验证',
            '水侧等效直径保存总流通面积；单管L/di摩阻保持原速度基准'])
