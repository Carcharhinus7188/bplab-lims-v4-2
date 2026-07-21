# -*- coding: utf-8 -*-

from __future__ import annotations
import io, re
import pandas as pd

def initial_dataframe(kind,n):
    ids=[f"S{i+1}" for i in range(n)]
    if kind=="rough":return pd.DataFrame({"试样编号":ids,"Ra1/μm":[0.0]*n,"Ra2/μm":[0.0]*n,"Ra3/μm":[0.0]*n})
    if kind=="mc":return pd.DataFrame({"试样编号":ids,"宽度/mm":[0.0]*n,"dM1/mm":[0.0]*n,"dM2/mm":[0.0]*n,"dM3/mm":[0.0]*n,"EM/GPa":[0.0]*n,"K/mm⁻²":[0.0]*n,"Ffail/N":[0.0]*n})
    if kind=="xray":return pd.DataFrame({"试样编号":ids,"ROI1":[0.0]*n,"ROI2":[0.0]*n,"ROI3":[0.0]*n,"图像有效":["是"]*n,"异常":["无"]*n})
    if kind=="warp":return pd.DataFrame({"试样编号":ids,"H1/mm":[0.0]*n,"H2/mm":[0.0]*n})
    if kind=="cte":return pd.DataFrame({"试样编号":ids,"起始温度/℃":[25.0]*n,"终止温度/℃":[550.0]*n,"L0/mm":[0.0]*n,"ΔL/μm":[0.0]*n})
    if kind=="shock":return pd.DataFrame({"样品编号/位置":ids,"裂纹":["无"]*n,"崩瓷":["无"]*n,"破裂/裂开":["无"]*n})
    if kind=="bend":return pd.DataFrame({"试样编号":ids,"长度/mm":[25.0]*n,"宽度/mm":[2.0]*n,"高度/mm":[2.0]*n,"Fmax/N":[0.0]*n,"0.2%规定非比例弯曲应力/MPa":[0.0]*n})
    if kind=="hv":return pd.DataFrame([{"样品编号":sid,"测试面":face,"压痕1/HV":0.0,"压痕2/HV":0.0,"压痕3/HV":0.0} for sid in ids for face in ["面1","面2"]])
    if kind=="thickness":return pd.DataFrame({"试样编号":ids,"固定端1/mm":[0.0]*n,"固定端2/mm":[0.0]*n,"中点1/mm":[0.0]*n,"中点2/mm":[0.0]*n,"自由端1/mm":[0.0]*n,"自由端2/mm":[0.0]*n})
    if kind=="color":return pd.DataFrame({"试样编号":ids,"L0*":[0.0]*n,"a0*":[0.0]*n,"b0*":[0.0]*n,"L1*":[0.0]*n,"a1*":[0.0]*n,"b1*":[0.0]*n})
    return pd.DataFrame({"试样编号":ids})

def calculate(kind,df):
    df=df.copy()
    if kind=="rough":
        df["平均值/μm"]=df[["Ra1/μm","Ra2/μm","Ra3/μm"]].mean(axis=1).round(3)
        df["判定"]=df["平均值/μm"].apply(lambda x:"符合" if x<=15 else "不符合")
    elif kind=="mc":
        df["dM平均/mm"]=df[["dM1/mm","dM2/mm","dM3/mm"]].mean(axis=1).round(4)
        df["τb/MPa"]=(df["K/mm⁻²"]*df["Ffail/N"]).round(2)
        df["判定"]=df["τb/MPa"].apply(lambda x:"符合" if x>25 else "不符合")
    elif kind=="xray":
        df["ROI平均灰度"]=df[["ROI1","ROI2","ROI3"]].mean(axis=1).round(2)
        df["判定"]=df.apply(lambda r:"需复检" if r["图像有效"]!="是" else ("符合" if r["异常"]=="无" else "不符合"),axis=1)
    elif kind=="warp":
        df["ΔH/mm"]=(df["H1/mm"]-df["H2/mm"]).round(4)
        df["判定"]=df["ΔH/mm"].apply(lambda x:"符合" if abs(x)<=0.5 else "不符合")
    elif kind=="cte":
        df["ΔT/℃"]=df["终止温度/℃"]-df["起始温度/℃"]
        df["α/(10⁻⁶/K)"]=df.apply(lambda r:round((r["ΔL/μm"]/1000)/(r["L0/mm"]*r["ΔT/℃"])*1e6,3) if r["L0/mm"] and r["ΔT/℃"] else 0,axis=1)
        df["判定"]="仅记录"
    elif kind=="shock":
        df["判定"]=df.apply(lambda r:"符合" if r["裂纹"]=="无" and r["崩瓷"]=="无" and r["破裂/裂开"]=="无" else "不符合",axis=1)
    elif kind=="bend":
        df["判定"]=df["0.2%规定非比例弯曲应力/MPa"].apply(lambda x:"符合" if x>=800 else "不符合")
    elif kind=="hv":
        df["测试面平均/HV"]=df[["压痕1/HV","压痕2/HV","压痕3/HV"]].mean(axis=1).round(1)
        df["判定"]="仅记录"
    elif kind=="thickness":
        cols=[c for c in df.columns if c.endswith("/mm")]
        df["平均厚度/mm"]=df[cols].mean(axis=1).round(4)
        df["判定"]="仅记录"
    elif kind=="color":
        df["ΔE*"]=(((df["L1*"]-df["L0*"])**2+(df["a1*"]-df["a0*"])**2+(df["b1*"]-df["b0*"])**2)**0.5).round(3)
        df["判定"]="按限值判定"
    return df
