# -*- coding: utf-8 -*-

from __future__ import annotations
from datetime import date
from pathlib import Path
import pandas as pd
import streamlit as st

from constants import *
from lims_db import *
from experiment_engine import initial_dataframe,calculate
from word_engine import export_record

ROOT=Path(__file__).parent
TPL_DIR=ROOT/"templates"
st.set_page_config(page_title="BPLab Trace",page_icon="🧪",layout="wide",initial_sidebar_state="expanded")
st.markdown("""
<style>
:root{color-scheme:light!important;--bp-navy:#12364a;--bp-blue:#176b87;--bp-cyan:#3aa6b9;--bp-line:#dce7ee}
html,body,.stApp,[data-testid="stAppViewContainer"]{background:#f6f9fb!important;color:#1f2f38!important}
.block-container{padding-top:1rem;padding-bottom:3rem;max-width:1580px}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#102f42,#174e66)}[data-testid="stSidebar"] *{color:#f5fbff}
.bp-header{padding:24px 28px;border-radius:22px;background:linear-gradient(135deg,#12364a 0%,#176b87 58%,#3aa6b9 100%);color:white;box-shadow:0 16px 34px rgba(18,54,74,.22);margin-bottom:20px}
.bp-company{font-size:31px;font-weight:850}.bp-en{font-size:13px;letter-spacing:1.35px;opacity:.9}.bp-system{font-size:21px;font-weight:750;margin-top:12px}
.bp-section{font-size:19px;font-weight:800;color:var(--bp-navy);margin:22px 0 12px}
.bp-card{background:white;border:1px solid var(--bp-line);border-radius:17px;padding:18px 19px;box-shadow:0 7px 20px rgba(18,54,74,.07)}
.bp-current{border-left:5px solid #176b87;background:#fff;padding:12px 16px;border-radius:10px;margin:7px 0}
.bp-done{border-left:5px solid #2e7d32;background:#fff;padding:12px 16px;border-radius:10px;margin:7px 0}
.bp-wait{border-left:5px solid #ef9b19;background:#fff;padding:12px 16px;border-radius:10px;margin:7px 0}
.bp-change{background:#fff7f7;border:1px solid #efb9b9;border-radius:13px;padding:15px;margin:10px 0}
.stButton>button,.stDownloadButton>button{border-radius:10px;font-weight:700;min-height:42px}
.stTabs [data-baseweb="tab-list"]{gap:8px;background:#eaf2f6;border-radius:13px;padding:6px}.stTabs [aria-selected="true"]{background:white!important}
</style>
""",unsafe_allow_html=True)

def header(subtitle):
    st.markdown(f'<div class="bp-header"><div class="bp-company">{COMPANY_CN}</div><div class="bp-en">{COMPANY_EN}</div><div class="bp-system">{SYSTEM_CN}</div><div>{SYSTEM_EN} · {APP_VERSION} · {subtitle}</div></div>',unsafe_allow_html=True)
def section(title): st.markdown(f'<div class="bp-section">{title}</div>',unsafe_allow_html=True)

init_db()
for exp,conf in EXPERIMENTS.items():
    seed_template(exp,"原始记录表",conf.get("template"))
    seed_template(exp,"SOP",conf.get("sop"))

if "user" not in st.session_state:
    token=st.query_params.get("session","")
    restored=session_user(token)
    if restored: st.session_state.user=restored

if "user" not in st.session_state:
    header("账号登录")
    a,b,c=st.columns([1,1.15,1])
    with b:
        un=st.text_input("用户名")
        pw=st.text_input("密码",type="password")
        keep=st.checkbox("保持登录7天（刷新页面不会退出）",value=True)
        if st.button("登录",type="primary",use_container_width=True):
            u=authenticate(un,pw)
            if u:
                token=create_session(u["username"],7 if keep else 1)
                st.query_params["session"]=token
                st.session_state.user=u
                st.rerun()
            else: st.error("用户名或密码错误")
        st.caption("管理员 admin/admin123｜收样员 receiver/receive123｜实验员 tester/test123｜复核员 reviewer/review123｜样品管理员 store/store123")
    st.stop()

user=st.session_state.user
role,username=user["role"],user["username"]
nav=ROLE_MENUS[role]
with st.sidebar:
    st.markdown("## BPLab Trace")
    st.caption("样品全过程追溯系统")
    st.write(f"**{user['display_name']}**")
    st.caption(role)
    if role=="实验人员":
        n=pending_task_count(username)
        if n: st.warning(f"🔔 待接收任务：{n}")
    st.divider()
    page=st.radio("导航",nav,label_visibility="collapsed")
    st.divider()
    st.caption("登录状态：7天内刷新保持")
    if st.button("退出登录",use_container_width=True):
        delete_session(st.query_params.get("session",""))
        st.query_params.clear();st.session_state.clear();st.rerun()

if page=="首页看板":
    header("全员可见的样品状态看板")
    samples=list_samples()
    c1,c2,c3,c4,c5,c6=st.columns(6)
    c1.metric("样品总数",len(samples))
    c2.metric("待分配",sum(x["status"]=="待分配" for x in samples))
    c3.metric("待实验员接收",sum(x["status"]=="待实验员接收" for x in samples))
    c4.metric("检测中",sum(x["status"]=="检测中" for x in samples))
    c5.metric("待复核",sum(x["status"]=="待复核" for x in samples))
    c6.metric("待回库",sum(x["status"]=="待回库确认" for x in samples))
    if role=="实验人员" and pending_task_count(username):
        st.warning(f"🔔 你有 {pending_task_count(username)} 个检测任务等待接收。接收任务即表示样品已到手并完成状态核对。")
    section("样品实时状态")
    if samples:
        df=pd.DataFrame(samples)
        cols=["sample_no","base_no","client","sample_name","condition","status","location","owner","qty_current","unit","due_date","updated_at"]
        st.dataframe(df[[c for c in cols if c in df.columns]],hide_index=True,use_container_width=True)
    else: st.info("暂无样品，请由收样员执行样品入库")
    section("流程总览")
    st.markdown('<div class="bp-card">样品入库 → 待分配 → 任务下发并提醒 → 实验员接收并确认完好 → 检测 → 原始记录 → 复核 → 样品归还 → 回库确认 → 留样保存</div>',unsafe_allow_html=True)

elif page=="样品入库":
    header("样品接收、登记和首次入库")
    customers=list_customers(False);catalog=list_sample_catalog(False)
    if not customers or not catalog:
        st.error("请先在“基础资料”中录入至少一个客户和一个样品名称。")
    else:
        a,b=st.columns(2)
        customer_id=a.selectbox("客户名称",[x["id"] for x in customers],format_func=lambda x:next(c["name"] for c in customers if c["id"]==x))
        catalog_id=b.selectbox("样品名称",[x["id"] for x in catalog],format_func=lambda x:next(c["name"] for c in catalog if c["id"]==x))
        customer=next(x for x in customers if x["id"]==customer_id)
        cat=next(x for x in catalog if x["id"]==catalog_id)
        a,b,c=st.columns(3)
        received=a.date_input("接收日期",value=date.today())
        due=b.date_input("计划完成日期",value=date.today())
        location=c.selectbox("入库位置",STORAGE_AREAS)
        model=a.text_input("规格型号")
        batch_no=b.text_input("批号")
        unit=c.text_input("单位",value=cat.get("unit") or "件")
        condition=st.radio("样品状态",SAMPLE_CONDITIONS,horizontal=True)
        condition_note=st.text_area("样品状态备注",placeholder="选择“不完好”时必须说明破损、污染、数量异常等情况")
        notes=st.text_area("其他入库备注")
        split_count=st.number_input("同一产品独立样品数量",min_value=1,max_value=20,value=1,step=1,
                                    help="2个独立样品可编号为BP年月日001-1、BP年月日001-2")
        base=next_sample_no(received)
        st.caption("系统生成基础编号，允许手工修改；格式为BP年月日三位流水号，可增加-1、-2等后缀。")
        specimens=[]
        for i in range(int(split_count)):
            default=base if split_count==1 else f"{base}-{i+1}"
            x,y=st.columns([3,1])
            sn=x.text_input(f"样品编号 {i+1}",value=default,key=f"sn_{received}_{split_count}_{i}")
            qty=y.number_input(f"数量 {i+1}",min_value=0.0,value=1.0,key=f"qty_{received}_{split_count}_{i}")
            specimens.append({"sample_no":sn,"qty_received":qty})
        defaults=[x for x in cat.get("default_experiments_list",[]) if x in EXPERIMENTS]
        exps=st.multiselect("检测项目",list(EXPERIMENTS),default=defaults)
        if st.button("确认接收、入库并创建检测任务",type="primary",use_container_width=True):
            if condition=="不完好" and not condition_note.strip():
                st.error("样品状态为“不完好”时，样品状态备注必须填写")
            elif not exps:
                st.error("至少选择一个检测项目")
            else:
                try:
                    created=create_samples({
                      "customer_id":customer_id,"sample_catalog_id":catalog_id,"client":customer["name"],
                      "sample_name":cat["name"],"model":model,"batch_no":batch_no,"unit":unit,
                      "received_date":str(received),"due_date":str(due),"location":location,
                      "condition":condition,"condition_note":condition_note,"notes":notes
                    },specimens,exps,username)
                    st.success("已入库："+ "、".join(created))
                    st.rerun()
                except Exception as e: st.error(str(e))

elif page=="基础资料":
    header("客户信息和样品名称基础资料")
    tab1,tab2=st.tabs(["客户信息","样品名称"])
    with tab1:
        rows=list_customers(True)
        if rows: st.dataframe(pd.DataFrame(rows)[["id","customer_code","name","short_name","contact","phone","address","enabled","notes"]],hide_index=True,use_container_width=True)
        section("新增客户")
        a,b,c=st.columns(3)
        code=a.text_input("客户编号");name=b.text_input("客户名称");short=c.text_input("简称")
        contact=a.text_input("联系人");phone=b.text_input("联系电话");address=c.text_input("地址")
        note=st.text_area("客户备注")
        if st.button("保存客户",type="primary"):
            try: add_customer(code,name,short,contact,phone,address,note);st.success("客户已保存");st.rerun()
            except Exception as e: st.error(str(e))
        if rows:
            cid=st.selectbox("启用/停用客户",[x["id"] for x in rows],format_func=lambda x:next(c["name"] for c in rows if c["id"]==x))
            enabled=next(c["enabled"] for c in rows if c["id"]==cid)
            if st.button("停用客户" if enabled else "启用客户"):
                set_customer_enabled(cid,not enabled);st.rerun()
    with tab2:
        rows=list_sample_catalog(True)
        if rows: st.dataframe(pd.DataFrame(rows)[["id","sample_code","name","category","unit","enabled","notes"]],hide_index=True,use_container_width=True)
        section("新增样品名称")
        a,b,c=st.columns(3)
        code=a.text_input("样品名称编号");name=b.text_input("样品名称");category=c.text_input("类别")
        unit=st.text_input("默认单位",value="件")
        defaults=st.multiselect("默认检测项目",list(EXPERIMENTS))
        note=st.text_area("样品名称备注")
        if st.button("保存样品名称",type="primary"):
            try: add_sample_catalog(code,name,category,unit,defaults,note);st.success("样品名称已保存");st.rerun()
            except Exception as e: st.error(str(e))
        if rows:
            sid=st.selectbox("启用/停用样品名称",[x["id"] for x in rows],format_func=lambda x:next(c["name"] for c in rows if c["id"]==x))
            enabled=next(c["enabled"] for c in rows if c["id"]==sid)
            if st.button("停用样品名称" if enabled else "启用样品名称"):
                set_sample_catalog_enabled(sid,not enabled);st.rerun()

elif page=="样品全流程":
    header("样品当前位置、当前流程和全生命周期")
    samples=list_samples()
    if not samples: st.info("暂无样品")
    else:
        selected=st.selectbox("选择样品",[x["sample_no"] for x in samples],
          format_func=lambda x:f'{x}｜{next(s["sample_name"] for s in samples if s["sample_no"]==x)}')
        s=sample(selected)
        a,b,c,d=st.columns(4)
        a.metric("当前状态",s["status"]);b.metric("当前位置",s["location"]);c.metric("当前负责人",s["owner"] or "未指定");d.metric("样品状态",s.get("condition") or "未记录")
        section("样品基本信息")
        cols=["sample_no","base_no","client","sample_name","model","batch_no","qty_received","qty_current","unit","received_date","due_date","location","condition","condition_note","notes"]
        st.dataframe(pd.DataFrame([s])[[c for c in cols if c in s]],hide_index=True,use_container_width=True)
        section("流程时间轴")
        events=sample_events(selected)
        for i,e in enumerate(events):
            css="bp-current" if i==len(events)-1 else "bp-done"
            st.markdown(f'<div class="{css}"><b>{e["created_at"]} · {e["action"]}</b><br>{e["from_status"] or "起点"} → {e["to_status"]}<br>位置：{e["from_location"] or "—"} → {e["to_location"] or "—"}<br>操作人：{e["actor"]}<br>{e["details"] or ""}</div>',unsafe_allow_html=True)
        section("关联检测任务")
        ts=[x for x in list_tasks() if x["sample_no"]==selected]
        if ts:
            cols=["task_no","experiment","assignee","reviewer","status","assigned_at","notified_at","accepted_at","acceptance_result","room","updated_at"]
            st.dataframe(pd.DataFrame(ts)[[c for c in cols if c in ts[0]]],hide_index=True,use_container_width=True)
        if role in ["管理员","收样员"]:
            section("删除错误入库记录")
            ok,msg=can_delete_sample(selected)
            st.info(msg)
            reason=st.text_area("删除原因",key=f"del_reason_{selected}")
            confirm=st.checkbox(f"确认删除样品 {selected}",key=f"del_confirm_{selected}")
            if st.button("删除错误入库记录",disabled=not ok,type="secondary"):
                if not reason.strip() or not confirm: st.error("必须填写删除原因并勾选确认")
                elif role=="收样员" and s["received_by"]!=username: st.error("收样员只能删除本人录入且尚未接收的样品")
                else:
                    try: soft_delete_sample(selected,username,reason);st.success("已删除并保留审计记录");st.rerun()
                    except Exception as e: st.error(str(e))

elif page=="任务分配":
    header("检测任务下发与提醒")
    tasks=list_tasks(statuses=["待分配","待接收"])
    if not tasks: st.info("暂无待分配或待接收任务")
    else:
        cols=["task_no","sample_no","sample_name","experiment","assignee","status","assigned_at","notified_at"]
        st.dataframe(pd.DataFrame(tasks)[[c for c in cols if c in tasks[0]]],hide_index=True,use_container_width=True)
        task_no=st.selectbox("任务编号",[x["task_no"] for x in tasks])
        testers=[u for u in users() if u["role"]=="实验人员" and u["enabled"]]
        reviewers=[u for u in users() if u["role"]=="复核实验员" and u["enabled"]]
        a,b,c=st.columns(3)
        assignee=a.selectbox("实验人员",[u["username"] for u in testers],format_func=lambda x:next(u["display_name"] for u in testers if u["username"]==x))
        reviewer=b.selectbox("复核实验员",[u["username"] for u in reviewers],format_func=lambda x:next(u["display_name"] for u in reviewers if u["username"]==x))
        room=c.text_input("样品交接后的检测位置",value="检测室")
        if st.button("下发任务并生成提醒",type="primary",use_container_width=True):
            assign_task(task_no,assignee,reviewer,room,username)
            st.success("任务已下发；下发时间和提醒时间已写入样品时间轴")
            st.rerun()

elif page=="我的检测任务":
    header("任务提醒、样品接收确认和检测")
    n=pending_task_count(username)
    if n: st.warning(f"🔔 当前有 {n} 个任务等待接收")
    tasks=list_tasks(assignee=username)
    if not tasks: st.info("暂无分配给你的任务")
    else:
        cols=["task_no","sample_no","sample_name","experiment","status","assigned_at","notified_at","accepted_at","room","sample_condition"]
        st.dataframe(pd.DataFrame(tasks)[[c for c in cols if c in tasks[0]]],hide_index=True,use_container_width=True)
        selected=st.selectbox("选择任务",[x["task_no"] for x in tasks])
        t=task(selected);s=sample(t["sample_no"])
        if t["status"]=="待接收":
            st.info(f'任务下发时间：{t.get("assigned_at") or "—"}｜提醒生成时间：{t.get("notified_at") or "—"}｜样品当前位置：{s["location"]}｜入库状态：{s.get("condition") or "未记录"}')
            result=st.radio("任务接收结果",["样品已收到，确认完好","样品已收到，但存在异常","尚未收到样品"])
            note=st.text_area("接收备注/异常说明")
            if st.button("提交任务接收确认",type="primary",use_container_width=True):
                try: accept_task(selected,username,result,note);st.success("接收结果已记录，时间轴已更新");st.rerun()
                except Exception as e: st.error(str(e))
        elif t["status"]=="接收异常":
            st.error(f'样品接收异常：{t.get("acceptance_note") or "未说明"}。异常处理前不能填写实验记录。')
        if t["status"] in ["检测中","退回修改"]:
            if st.button("进入实验记录填写",use_container_width=True):
                st.session_state.active_task=selected
                st.success("任务已载入，请进入“实验记录”")
        if t["status"]=="已完成": st.success("该检测任务已复核完成")
        if s["status"]=="待归还":
            st.markdown("### 样品归还")
            a,b=st.columns(2)
            used=a.number_input("实验消耗数量",min_value=0.0,value=0.0,key=f"used{selected}")
            returned=b.number_input("实际归还数量",min_value=0.0,value=float(s["qty_current"]),key=f"ret{selected}")
            condition=st.selectbox("归还状态",["完好","部分消耗","已破坏","全部消耗"])
            proposed=st.selectbox("建议回库位置",STORAGE_AREAS)
            note=st.text_area("归还备注")
            if st.button("提交样品归还",type="primary",use_container_width=True):
                submit_return(s["sample_no"],selected,username,used,returned,condition,proposed,note)
                st.success("已提交回库确认");st.rerun()

elif page=="实验记录":
    header("受控实验记录填写")
    active=st.session_state.get("active_task")
    available=list_tasks(assignee=username,statuses=["检测中","退回修改","待复核","已完成"])
    if role=="管理员":available=list_tasks()
    if not available:st.info("暂无可填写任务")
    else:
        options=[x["task_no"] for x in available]
        if active not in options:active=options[0]
        task_no=st.selectbox("检测任务",options,index=options.index(active))
        t=task(task_no);s=sample(t["sample_no"]);conf=EXPERIMENTS[t["experiment"]]
        existing=latest_record_by_task(task_no)
        if existing and existing["status"]=="已锁定":
            st.warning("该记录已锁定。如需修改，请进入“修改追踪”创建修订版。")
            st.stop()
        prior=existing["payload"] if existing else {}
        common_prior=prior.get("common",{})
        record_no=existing["record_no"] if existing else next_record_no()
        version=existing["version"] if existing else 1
        compare=None
        if version>1:
            prev=record_versions(record_no)[-2];compare=prev["payload"]
        st.info(f"样品：{s['sample_no']} {s['sample_name']}｜项目：{t['experiment']}｜记录：{record_no} V{version}")
        tab1,tab2,tab3,tab4,tab5=st.tabs(["①样品信息","②环境设备","③过程确认","④原始数据","⑤保存提交"])
        with tab1:
            a,b,c=st.columns(3)
            report_no=a.text_input("报告编号",common_prior.get("report_no",""))
            client=b.text_input("委托单位",common_prior.get("client",s["client"]))
            sample_name=c.text_input("样品名称",common_prior.get("sample_name",s["sample_name"]))
            sample_no=a.text_input("样品编号/批号",common_prior.get("sample_no",s["sample_no"]))
            model=b.text_input("规格型号",common_prior.get("model",s["model"]))
            material=c.text_input("材料名称",common_prior.get("material",""))
            test_date=a.date_input("检测日期",value=date.fromisoformat(common_prior["test_date"]) if common_prior.get("test_date") else date.today())
            location=b.text_input("检测地点",common_prior.get("location",t["room"]))
        with tab2:
            a,b,c=st.columns(3)
            temperature=a.number_input("环境温度℃",value=float(common_prior.get("temperature",23.0)))
            humidity=b.number_input("相对湿度%RH",value=float(common_prior.get("humidity",50.0)))
            equipment=c.text_input("设备名称/编号",common_prior.get("equipment",""))
            software=a.text_input("软件/版本",common_prior.get("software",""))
            calibration=b.text_input("校准有效期",common_prior.get("calibration",""))
            data_path=c.text_input("数据保存路径",common_prior.get("data_path",""))
            tm=active_version(t["experiment"],"原始记录表");sm=active_version(t["experiment"],"SOP")
            st.info(f"绑定原始记录表：{tm['version'] if tm else '未配置'}｜SOP：{sm['version'] if sm else '未配置'}")
        with tab3:
            checks={}
            for item in CHECK_ITEMS[conf["kind"]]:
                checks[item]=st.checkbox(item,value=prior.get("checks",{}).get(item,False))
            deviation=st.text_area("异常/偏离说明",prior.get("deviation",""))
        with tab4:
            source=pd.DataFrame(prior["data"]) if prior.get("data") else initial_dataframe(conf["kind"],conf["n"])
            edited=st.data_editor(source,use_container_width=True,num_rows="fixed",key=f"data_{record_no}_{version}")
            result=calculate(conf["kind"],edited)
            st.markdown("**自动计算结果**")
            st.dataframe(result,hide_index=True,use_container_width=True)
        with tab5:
            reason=st.text_area("本次修改原因",value=existing.get("change_reason","") if existing else "")
            common={"record_no":record_no,"report_no":report_no,"task_no":task_no,
              "client":client,"sample_name":sample_name,"sample_no":sample_no,"model":model,
              "material":material,"test_date":str(test_date),"location":location,
              "temperature":temperature,"humidity":humidity,"equipment":equipment,
              "software":software,"calibration":calibration,"data_path":data_path,
              "operator":user["display_name"],"reviewer":t["reviewer"]}
            payload={"common":common,"checks":checks,"deviation":deviation,"data":result.to_dict("records")}
            a,b=st.columns(2)
            if a.button("保存草稿",use_container_width=True):
                save_record(record_no,task_no,s["sample_no"],t["experiment"],version,payload,username,"草稿",
                  tm["version"] if tm else "A/0",sm["version"] if sm else "A/0",reason,compare)
                st.success("草稿已保存")
            if b.button("提交复核",type="primary",use_container_width=True):
                status="更正待复核" if version>1 else "待复核"
                save_record(record_no,task_no,s["sample_no"],t["experiment"],version,payload,username,status,
                  tm["version"] if tm else "A/0",sm["version"] if sm else "A/0",reason,compare)
                set_task_status(task_no,"待复核")
                update_sample(s["sample_no"],username,"原始记录提交复核",status="待复核",details=f"{record_no} V{version}")
                st.success("提交成功，待复核页面和样品状态看板已立即更新")
                st.rerun()

elif page=="待复核":
    header("待复核记录")
    rows=pending_reviews(None if role=="管理员" else username)
    if not rows:st.info("暂无待复核记录")
    else:
        st.dataframe(pd.DataFrame(rows)[["record_no","version","sample_no","experiment","owner","status","updated_at"]],hide_index=True,use_container_width=True)
        keys=[f"{r['record_no']}|{r['version']}" for r in rows]
        key=st.selectbox("选择记录",keys)
        rn,ver=key.split("|");r=record(rn,int(ver))
        st.write(f"**{r['experiment']}｜{r['sample_no']}｜{r['record_no']} V{r['version']}**")
        if r["version"]>1:
            changes=[x for x in audit_logs(rn,r["version"]) if x["action"]=="字段修改"]
            st.markdown("### 本次修改对照")
            if changes:st.dataframe(pd.DataFrame(changes)[["field_name","old_value","new_value","reason","actor","created_at"]],hide_index=True,use_container_width=True)
        st.dataframe(pd.DataFrame(r["payload"]["data"]),hide_index=True,use_container_width=True)
        comment=st.text_area("复核意见")
        a,b=st.columns(2)
        if a.button("复核通过并锁定",type="primary",use_container_width=True):
            review_record(rn,int(ver),username,"通过",comment);st.rerun()
        if b.button("退回修改",use_container_width=True):
            review_record(rn,int(ver),username,"退回",comment);st.rerun()

elif page=="样品回库":
    header("样品回库确认")
    rows=returns_pending()
    if not rows:st.info("暂无待回库样品")
    else:
        st.dataframe(pd.DataFrame(rows)[["id","sample_no","returned_by","qty_used","qty_returned","condition","proposed_location","return_time"]],hide_index=True,use_container_width=True)
        rid=st.selectbox("选择归还单",[x["id"] for x in rows])
        rr=next(x for x in rows if x["id"]==rid)
        location=st.selectbox("确认回库位置",STORAGE_AREAS,index=STORAGE_AREAS.index(rr["proposed_location"]) if rr["proposed_location"] in STORAGE_AREAS else 0)
        if st.button("确认回库并进入留样保存",type="primary",use_container_width=True):
            confirm_return(rid,username,location);st.rerun()

elif page=="原始记录表下载":
    header("原始记录表下载中心")
    rows=latest_records(statuses=["已锁定"])
    if role=="实验人员":rows=[r for r in rows if r["owner"]==username]
    if not rows:st.info("暂无已复核锁定的原始记录")
    else:
        query=st.text_input("搜索记录编号/样品编号/实验项目")
        if query:
            rows=[r for r in rows if query in r["record_no"] or query in r["sample_no"] or query in r["experiment"]]
        st.dataframe(pd.DataFrame(rows)[["record_no","version","sample_no","experiment","owner","status","updated_at"]],hide_index=True,use_container_width=True)
        opts=[]
        for r in rows:
            for v in record_versions(r["record_no"]):
                if v["status"]=="已锁定":opts.append(f"{v['record_no']}|{v['version']}")
        if opts:
            key=st.selectbox("选择可下载版本",opts)
            rn,ver=key.split("|");r=record(rn,int(ver))
            conf=EXPERIMENTS[r["experiment"]]
            changes=[x for x in audit_logs(rn,int(ver)) if x["action"]=="字段修改"]
            data=export_record(r,conf.get("template"),changes)
            label="下载红色修改痕迹版原始记录表" if r["version"]>1 else "下载正式原始记录表"
            st.download_button(f"📄 {label}",data,file_name=f"{rn}_V{ver}_原始记录表.docx",
              mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
              type="primary",use_container_width=True)
            if r["version"]>1:
                st.error("本版本含原始数据修改：修改位置已使用红色字体，并附修改说明页。")

elif page=="修改追踪":
    header("专业修改追踪")
    rows=latest_records()
    if role=="实验人员":rows=[x for x in rows if x["owner"]==username]
    if not rows:st.info("暂无记录")
    else:
        summary=[]
        for r in rows:
            vs=record_versions(r["record_no"])
            summary.append({"记录编号":r["record_no"],"样品编号":r["sample_no"],"实验项目":r["experiment"],
              "版本数":len(vs),"当前版本":f"V{r['version']}","当前状态":r["status"],"最后更新时间":r["updated_at"]})
        st.dataframe(pd.DataFrame(summary),hide_index=True,use_container_width=True)
        rn=st.selectbox("查看记录",[x["record_no"] for x in rows])
        versions=record_versions(rn)
        section("版本时间线")
        for v in versions:
            css="bp-current" if v==versions[-1] else "bp-done"
            st.markdown(f'<div class="{css}"><b>V{v["version"]} · {v["status"]}</b><br>{v["created_at"]}｜创建人：{v["owner"]}<br>原因：{v["change_reason"] or "首次记录"}</div>',unsafe_allow_html=True)
        selected_ver=st.selectbox("查看版本",[v["version"] for v in versions],format_func=lambda x:f"V{x}")
        v=record(rn,selected_ver)
        changes=[x for x in audit_logs(rn,selected_ver) if x["action"]=="字段修改"]
        section("修改前后对照")
        if changes:
            for ch in changes:
                st.markdown(f'<div class="bp-change"><b>{ch["field_name"]}</b><br><span style="color:#7d858a;text-decoration:line-through">原值：{ch["old_value"]}</span><br><span style="color:#d00000;font-weight:800">修改后：{ch["new_value"]}</span><br>原因：{ch["reason"] or v["change_reason"]}<br>修改人：{ch["actor"]}　时间：{ch["created_at"]}</div>',unsafe_allow_html=True)
        else:st.info("该版本无字段修改")
        if role in ["实验人员","管理员"] and versions[-1]["status"]=="已锁定":
            section("创建新修改版")
            reason=st.text_area("必须填写修改原因")
            if st.button("创建修改版原始记录",type="primary"):
                if not reason:st.error("请填写修改原因")
                else:
                    nv=create_revision(rn,username,reason)
                    latest=record(rn,nv)
                    st.session_state.active_task=latest["task_no"]
                    st.success(f"已创建V{nv}草稿，请进入“实验记录”修改并重新提交复核")
                    st.rerun()


elif page=="已删除样品":
    header("已删除样品审计记录")
    rows=deleted_samples()
    if not rows:
        st.info("暂无已删除样品")
    else:
        st.warning("这里保留错误入库记录、删除人、删除时间和删除原因；样品编号不会被自动重复使用。")
        st.dataframe(pd.DataFrame(rows)[["sample_no","base_no","client","sample_name","received_by","deleted_by","deleted_at","delete_reason"]],hide_index=True,use_container_width=True)

elif page=="SOP与模板版本":
    header("SOP和原始记录表版本管理")
    rows=all_template_versions()
    if rows:st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    section("启用新版本")
    a,b,c=st.columns(3)
    exp=a.selectbox("实验项目",list(EXPERIMENTS));doctype=b.selectbox("文件类型",["SOP","原始记录表"]);version=c.text_input("版本号","A/1")
    effective=st.date_input("生效日期")
    note=st.text_input("变更说明")
    uploaded=st.file_uploader("上传DOCX",type=["docx"])
    if st.button("批准并启用",type="primary"):
        if not uploaded:st.error("请上传文件")
        else:
            filename=f"{exp}_{doctype}_{version.replace('/','-')}_{uploaded.name}"
            (TPL_DIR/filename).write_bytes(uploaded.getvalue())
            add_template(exp,doctype,filename,version,str(effective),username,note)
            st.success("新版本已启用，历史记录仍绑定原版本")
            st.rerun()

elif page=="用户与权限":
    header("账号与角色权限")
    st.dataframe(pd.DataFrame(users()),hide_index=True,use_container_width=True)
    section("新增账号")
    a,b=st.columns(2)
    un=a.text_input("用户名");dn=b.text_input("显示姓名")
    pw=a.text_input("初始密码",type="password");r=b.selectbox("角色",ROLES)
    if st.button("创建账号",type="primary"):
        try:add_user(un,dn,pw,r);st.success("账号已创建");st.rerun()
        except Exception as e:st.error(str(e))
