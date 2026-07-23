# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime, time
from pathlib import Path
import csv, hashlib, io, json, re
import pandas as pd
import streamlit as st

from constants import *
from lims_db import *
from experiment_engine import schema, initial_parameters, initial_rows, calculate_rows, dataframe, columns_for_editor
from record_word_engine import export_record
from business_record_engine import initialize_business_record, calculate_business_record, business_to_template_fields, business_completion_summary
from business_record_ui import render_readonly_summary, render_task_confirmations, render_equipment_confirmation, render_prechecks, render_parameters, render_sample_data, render_exception_and_summary, render_completion
from equipment_registry import EQUIPMENT_BINDING_ROLES
from experiment_schemas import SCHEMAS
from form_engine import commission_document, sample_register_document, loan_return_document, report_document
from report_rules import overall_conclusion, report_item
from trace_excel_engine import build_internal_trace_workbook

ROOT=Path(__file__).parent
TEMPLATE_DIR=ROOT/"templates"
SIG_DIR=ROOT/"data"/"signatures";SIG_DIR.mkdir(parents=True,exist_ok=True)

st.set_page_config(page_title="BPLab Trace",page_icon="🧪",layout="wide",initial_sidebar_state="expanded")
st.markdown("""
<style>
:root{--navy:#12364a;--blue:#176b87;--cyan:#3aa6b9;--line:#d7e3ea;--bg:#f6f9fb}
html,body,.stApp,[data-testid=stAppViewContainer]{background:var(--bg);color:#172a35}
.block-container{max-width:1580px;padding-top:1rem;padding-bottom:4rem}
[data-testid=stSidebar]{background:linear-gradient(180deg,#102f42,#174e66)}
[data-testid=stSidebar] *{color:white}
.hero{background:linear-gradient(135deg,#12364a,#176b87 65%,#3aa6b9);color:white;padding:24px 28px;border-radius:20px;margin-bottom:18px;box-shadow:0 14px 30px rgba(18,54,74,.2)}
.card{background:white;border:1px solid var(--line);padding:16px;border-radius:14px;box-shadow:0 5px 16px rgba(18,54,74,.06)}
.timeline{border-left:5px solid var(--blue);background:white;padding:12px 16px;margin:8px 0;border-radius:10px}
.notice{background:#fff8e1;border:1px solid #ead99a;padding:12px;border-radius:10px}
.stButton>button,.stDownloadButton>button{border-radius:10px;font-weight:700;min-height:42px}
[data-testid=stMetric]{background:white;border:1px solid var(--line);padding:14px;border-radius:14px;box-shadow:0 5px 16px rgba(18,54,74,.05)}
[data-baseweb=tab-list]{gap:8px;background:white;border:1px solid var(--line);padding:6px;border-radius:14px}
[data-baseweb=tab]{border-radius:9px;padding:8px 14px}
[data-baseweb=tab][aria-selected=true]{background:#e8f5f8;color:var(--navy)}
[data-testid=stExpander]{background:white;border-color:var(--line);border-radius:12px}
div[data-testid=stForm],div[data-testid=stVerticalBlockBorderWrapper]{border-color:var(--line)!important;border-radius:14px}
input,textarea{border-radius:9px!important}
</style>
""",unsafe_allow_html=True)


def header(title:str):
    st.markdown(f'<div class="hero"><h2>{COMPANY_CN}</h2><div>{COMPANY_EN}</div><h3>{title}</h3><small>{APP_VERSION}｜中国大陆时区 {TIMEZONE_NAME}（UTC+8）</small></div>',unsafe_allow_html=True)


def show_df(data,columns=None):
    if not data:
        st.info("暂无数据");return
    frame=pd.DataFrame(data)
    if columns:frame=frame[[x for x in columns if x in frame.columns]]
    st.dataframe(frame,hide_index=True,use_container_width=True)


def user_map():return {x["username"]:x["display_name"] for x in list_users()}
def display_user(username):return user_map().get(username,username or "")
def role_users(role):return [x for x in list_users() if x["role"]==role and x["enabled"]]

def increment_base(base,n):
    m=re.fullmatch(r"(BP\d{8})(\d{3})",base)
    return f"{m.group(1)}{int(m.group(2))+n:03d}" if m else base


def field_widget(field,value,key_prefix):
    key=f"{key_prefix}_{field['key']}";label=field["label"];typ=field.get("type","text")
    if field.get("readonly"):
        st.text_input(label,value=str(value or ""),disabled=True,key=key);return value
    if typ=="number":return st.number_input(label,value=float(value or 0),key=key)
    if typ=="select":
        opts=field.get("options",[]);idx=opts.index(value) if value in opts else 0
        return st.selectbox(label,opts,index=idx,key=key)
    if typ=="multiselect":return st.multiselect(label,field.get("options",[]),default=value or [],key=key)
    if typ=="checkbox":return st.checkbox(label,value=bool(value),key=key)
    if typ=="date":
        try:v=pd.to_datetime(value).date() if value else china_today()
        except:v=china_today()
        return str(st.date_input(label,v,key=key))
    if typ=="datetime":
        return st.text_input(label,value=str(value or now()),key=key,help="北京时间，格式建议 YYYY-MM-DD HH:MM:SS")
    if typ=="textarea":return st.text_area(label,value=str(value or ""),key=key)
    return st.text_input(label,value=str(value or ""),key=key)


def dataframe_editor(kind,rows0,key):
    cols=columns_for_editor(kind);frame=dataframe(kind,rows0)
    config={}
    for c in cols:
        typ=c["type"];label=c["label"]
        if typ=="calc":config[c["key"]]=st.column_config.NumberColumn(label,disabled=True)
        elif typ=="number":config[c["key"]]=st.column_config.NumberColumn(label,format="%.4f")
        elif typ.startswith("select:"):config[c["key"]]=st.column_config.SelectboxColumn(label,options=typ.split(":",1)[1].split("|"))
        else:config[c["key"]]=st.column_config.TextColumn(label,disabled=c["key"]=="sample_no")
    edited=st.data_editor(frame,column_config=config,hide_index=True,use_container_width=True,num_rows="fixed",key=key)
    return calculate_rows(kind,edited.to_dict("records"))


init_db()
for exp,cfg in EXPERIMENTS.items():
    seed_template(exp,"原始记录表",cfg.get("template"));seed_template(exp,"SOP",cfg.get("sop"))

if "user" not in st.session_state:
    restored=session_user(st.query_params.get("session",""))
    if restored:st.session_state.user=restored
if "user" not in st.session_state:
    header("系统登录");a,b,c=st.columns([1,1.15,1])
    with b:
        username=st.text_input("用户名");password=st.text_input("密码",type="password")
        if st.button("登录",type="primary",use_container_width=True):
            u=authenticate(username,password)
            if u:st.session_state.user=u;st.query_params["session"]=create_session(username);st.rerun()
            else:st.error("用户名或密码错误")
        st.caption("管理员 admin/admin123｜样品管理员 receiver/receive123 或 store/store123｜实验员 tester/test123｜复核员 reviewer/review123｜批准人 approver/approve123")
    st.stop()

user=st.session_state.user;role=user["role"];username=user["username"]
with st.sidebar:
    st.title("BPLab Trace");st.write(user["display_name"]);st.caption(role)
    page=st.radio("导航",ROLE_MENUS[role],label_visibility="collapsed")
    st.divider();st.caption("系统时间：中国大陆 UTC+8")
    if st.button("退出登录",use_container_width=True):delete_session(st.query_params.get("session",""));st.session_state.clear();st.query_params.clear();st.rerun()

if page=="首页看板":
    header("委托、样品、任务包和报告状态看板");counts=dashboard_counts();cols=st.columns(7)
    metrics=[("委托",counts["commissions"]),("在册样品",counts["samples"]),("待接收任务包",counts["packages"]),("检测中",counts["testing"]),("待复核",counts["reviews"]),("待回库",counts["returns"]),("待发布报告",counts["reports"])]
    for col,(label,value) in zip(cols,metrics):col.metric(label,value)
    show_df(list_samples(),["sample_no","commission_no","group_no","sample_name","model","material_name","status","current_location","current_holder","updated_at"])

elif page=="单位信息库":
    header("委托客户、生产单位和受委托生产企业信息库")
    if role not in ["管理员","样品管理员"]:st.stop()
    show_df(list_organizations(True),["org_code","org_name","short_name","is_client","is_manufacturer","is_contract_manufacturer","address","contact","phone","enabled"])
    with st.form("org_form",clear_on_submit=True):
        a,b,c=st.columns(3);code=a.text_input("单位编号");name=b.text_input("单位名称");short=c.text_input("单位简称")
        client=a.checkbox("委托客户");manufacturer=b.checkbox("生产单位");contract=c.checkbox("受委托生产企业")
        address=a.text_input("地址");contact=b.text_input("联系人");phone=c.text_input("联系电话");credit=a.text_input("统一社会信用代码");notes=st.text_area("备注")
        if st.form_submit_button("保存单位",type="primary"):
            try:add_organization({"org_code":code,"org_name":name,"short_name":short,"is_client":client,"is_manufacturer":manufacturer,"is_contract_manufacturer":contract,"address":address,"contact":contact,"phone":phone,"credit_code":credit,"notes":notes},username);st.rerun()
            except Exception as e:st.error(str(e))

elif page=="检测项目与方法库":
    header("动态检测项目与方法库")
    if role!="管理员":st.stop()
    methods=list_experiment_methods(True)
    show_df(methods,["experiment_name","method_code","standard","category","kind","enabled","sort_order","updated_at"])
    st.info("实验名称和检测方法可以继续增加、停用或调整；对正式任务生效前，应在“实验配置版本”中新建并发布配置。界面不显示内部实验标识。")
    names=["新增实验"]+[x["experiment_name"] for x in methods]
    selected=st.selectbox("新增或维护实验",names)
    current=experiment_method_by_name(selected) if selected!="新增实验" else {}
    with st.form("method_form"):
        a,b,c=st.columns(3)
        name=a.text_input("实验名称",current.get("experiment_name","") if current else "")
        method=b.text_input("检测方法",current.get("method_code","") if current else "",help="直接填写受控标准/方法名称，不设置“其他方法”选项")
        standard=c.text_input("检测依据/版本",current.get("standard","") if current else "")
        category=a.text_input("实验类别",current.get("category","") if current else "")
        kind_options=list(SCHEMAS.keys())
        current_kind=(current or {}).get("kind") or "generic"
        kind=b.selectbox("记录数据模板",kind_options,index=kind_options.index(current_kind) if current_kind in kind_options else kind_options.index("generic"),help="新增实验可先使用generic通用记录，收到SOP和原始记录表后再配置专用模板")
        order=c.number_input("排序",min_value=0,value=int((current or {}).get("sort_order",100) or 100),step=1)
        enabled=a.checkbox("启用",value=bool((current or {}).get("enabled",1)))
        if st.form_submit_button("保存检测项目与方法",type="primary"):
            try:
                save_experiment_method({"experiment_name":name,"method_code":method,"standard":standard,"category":category,"kind":kind,"sort_order":order,"enabled":enabled},username)
                st.success("已保存。新增或变更内容需建立配置版本并发布后，才用于新任务。")
                st.rerun()
            except Exception as e:st.error(str(e))

elif page=="样品资料库":
    header("样品名称、规格型号、材料和检测项目与方法资料库")
    if role not in ["管理员","样品管理员"]:st.stop()
    method_rows=list_experiment_methods();method_map={x["experiment_code"]:x for x in method_rows}
    catalog=list_catalog(True)
    for item in catalog:item["检测项目与方法"]="；".join(item.get("experiment_labels",[]))
    show_df(catalog,["sample_code","sample_name","model","material_name","category","unit","检测项目与方法","enabled"])
    with st.form("catalog_form",clear_on_submit=True):
        a,b,c=st.columns(3)
        code=a.text_input("样品资料编号");name=b.text_input("样品名称");model=c.text_input("规格型号")
        material=a.text_input("材料名称");category=b.text_input("类别");unit=c.text_input("单位",value="件")
        exp_codes=st.multiselect("检测项目与方法",[x["experiment_code"] for x in method_rows],
            format_func=lambda x:f"{method_map[x]['experiment_name']}｜{method_map[x]['method_code']}")
        notes=st.text_area("备注")
        if st.form_submit_button("保存样品资料",type="primary"):
            try:
                add_catalog({"sample_code":code,"sample_name":name,"model":model,"material_name":material,
                    "category":category,"unit":unit,"experiment_codes":exp_codes,"notes":notes},username)
                st.rerun()
            except Exception as e:st.error(str(e))

elif page=="新建委托与入库":
    header("一份委托统一选择生产单位，并同时录入多个不同样品组")
    if role not in ["管理员","样品管理员"]:st.stop()
    orgs=list_organizations();clients=[x for x in orgs if x["is_client"]]
    producers=[x for x in orgs if x["is_manufacturer"] or x["is_contract_manufacturer"]]
    catalog=list_catalog();method_rows=list_experiment_methods();method_map={x["experiment_code"]:x for x in method_rows}
    if not clients or not producers or not catalog:
        st.error("请先建立委托客户、生产单位/受委托生产企业和样品资料");st.stop()
    if "intake_groups" not in st.session_state:st.session_state.intake_groups=[]
    st.subheader("委托主单")
    a,b,c=st.columns(3)
    commission_no=a.text_input("检验委托编号（暂行规则）",value=next_commission_no())
    client_id=b.selectbox("委托客户",[x["id"] for x in clients],format_func=lambda x:next(y["org_name"] for y in clients if y["id"]==x))
    client=next(x for x in clients if x["id"]==client_id)
    producer_id=c.selectbox("生产单位/受委托生产企业",[x["id"] for x in producers],format_func=lambda x:next(y["org_name"] for y in producers if y["id"]==x))
    producer=next(x for x in producers if x["id"]==producer_id)
    relation=a.selectbox("单位关系",["生产单位","受委托生产企业"])
    commission_date=b.date_input("委托/接收日期",china_today())
    due=c.date_input("计划完成日期",add_months_to_date(commission_date,1))
    subcontract=a.selectbox("允许分包",["否","是"])
    report_medium=b.multiselect("报告载体",["纸质","电子档"],default=["电子档"])
    conformity=c.selectbox("符合性判定",["是","否"])
    uncertainty=a.selectbox("考虑不确定度",["否","是"])
    delivery=b.selectbox("递送方式",["Email","自取","快递"])
    cnas=c.selectbox("加盖CNAS章",["否","是"])
    capability=a.selectbox("检测能力评价",["完全满足","部分满足","不满足"])
    commission_notes=st.text_area("委托备注")
    st.info(f"本委托下所有样品统一使用：{producer['org_name']}（{relation}）")

    st.subheader("添加样品组")
    with st.form("add_group",clear_on_submit=False):
        a,b,c=st.columns(3)
        cat_id=a.selectbox("样品名称/规格型号",[x["id"] for x in catalog],
            format_func=lambda x:next(f"{y['sample_name']}｜{y['model']}｜{y['material_name']}" for y in catalog if y["id"]==x))
        cat=next(x for x in catalog if x["id"]==cat_id)
        base_default=increment_base(next_sample_base(),len(st.session_state.intake_groups))
        group_no=b.text_input("样品组基础编号",value=base_default)
        qty=int(c.number_input("接收数量（自动生成 -01～-0x）",1,99,1))
        product_no=a.text_input("产品编号/批号")
        condition=b.selectbox("样品状态",SAMPLE_CONDITIONS)
        storage=c.selectbox("入库区域",STORAGE_AREAS)
        unit=a.text_input("单位",value=cat["unit"])
        condition_note=b.text_input("状态备注")
        exp_codes=st.multiselect("检测项目与方法",[x["experiment_code"] for x in method_rows],
            default=[x for x in cat.get("experiment_codes_list",[]) if x in method_map],
            format_func=lambda x:f"{method_map[x]['experiment_name']}｜{method_map[x]['method_code']}")
        group_notes=st.text_area("样品组备注")
        if st.form_submit_button("加入本委托的样品明细"):
            normalized_group=group_no.strip().upper().replace(" ","")
            if not re.fullmatch(r"BP\d{11}",normalized_group):
                st.error("样品组基础编号必须符合BP年月日001，例如BP20260722001")
            elif any(g["group_no"]==normalized_group for g in st.session_state.intake_groups):
                st.error("当前委托草稿中已存在相同样品组编号")
            elif not exp_codes:
                st.error("请至少选择一个检测项目与方法")
            else:
                st.session_state.intake_groups.append({
                    "group_no":normalized_group,"catalog_id":cat_id,"sample_name":cat["sample_name"],
                    "model":cat["model"],"material_name":cat["material_name"],"quantity":qty,
                    "product_no":product_no,"unit":unit,"condition":condition,
                    "condition_note":condition_note,"storage_area":storage,
                    "experiment_codes":exp_codes,
                    "experiment_labels":[f"{method_map[x]['experiment_name']}｜{method_map[x]['method_code']}" for x in exp_codes],
                    "notes":group_notes,
                });st.rerun()
    if st.session_state.intake_groups:
        show_df(st.session_state.intake_groups,["group_no","sample_name","model","material_name","quantity","condition","storage_area","experiment_labels"])
        remove_index=st.selectbox("删除一条草稿明细",range(len(st.session_state.intake_groups)),
            format_func=lambda i:f"{i+1}. {st.session_state.intake_groups[i]['group_no']} {st.session_state.intake_groups[i]['sample_name']}")
        if st.button("删除所选草稿"):st.session_state.intake_groups.pop(remove_index);st.rerun()
        st.info("实体编号预览："+"；".join(
            f"{g['group_no']}-01～{g['group_no']}-{g['quantity']:02d}" if g['quantity']>1 else f"{g['group_no']}-01"
            for g in st.session_state.intake_groups))
        selected_methods=list(dict.fromkeys(method_map[c]["method_code"] for g in st.session_state.intake_groups for c in g["experiment_codes"]))
        st.info("委托单检测方法将自动勾选："+"、".join(selected_methods))
        if st.button("生成同一份委托单并完成全部样品入库",type="primary",use_container_width=True):
            data={"commission_no":commission_no,"client_org_id":client_id,"client_name":client["org_name"],
                "client_address":client["address"],"contact":client["contact"],"phone":client["phone"],
                "production_org_id":producer_id,"production_org_name":producer["org_name"],
                "production_relation":relation,"commission_date":commission_date,"due_date":due,
                "subcontract_allowed":subcontract,"report_medium":"、".join(report_medium),
                "conformity_judgment":conformity,"uncertainty":uncertainty,"delivery_method":delivery,
                "cnas_mark":cnas,"capability":capability,"notes":commission_notes}
            try:
                create_commission(data,st.session_state.intake_groups,username)
                st.session_state.intake_groups=[]
                st.success("委托和全部样品组已入库，实验名称和检测方法已自动绑定")
                st.rerun()
            except Exception as e:st.error(str(e))

elif page=="委托与样品管理":
    header("委托、样品组、实体样品和全过程时间轴");cs=list_commissions();show_df(cs,["commission_no","client_name","production_org_name","production_relation","commission_date","due_date","status","created_by"])
    if cs:
        cn=st.selectbox("选择委托",[x["commission_no"] for x in cs]);groups=commission_groups(cn,True);show_df(groups,["id","group_no","sample_name","model","material_name","quantity","status","is_void","void_reason"])
        active=[g for g in groups if not g["is_void"]]
        if active:
            gid=st.selectbox("查看样品组",[g["id"] for g in active],format_func=lambda x:next(f"{g['group_no']} {g['sample_name']}" for g in active if g["id"]==x));samples0=group_samples(gid);show_df(samples0,["sample_no","sample_name","model","material_name","status","current_location","current_holder"])
            sn=st.selectbox("查看实体样品时间轴",[x["sample_no"] for x in samples0]);
            for e in sample_events(sn):st.markdown(f'<div class="timeline"><b>{e["created_at"]} · {e["action"]}</b><br>{e["from_status"]} → {e["to_status"]}<br>{e["from_location"]} → {e["to_location"]}<br>操作人：{display_user(e["actor"])}<br>{e["details"]}</div>',unsafe_allow_html=True)
            reason=st.text_input("错误入库删除原因")
            if st.button("删除当前错误入库样品组"):
                try:void_group(gid,username,reason);st.rerun()
                except Exception as e:st.error(str(e))

elif page=="任务包分配":
    header("一个样品组多选实验，一次下发、一次领用、一次归还")
    groups=available_groups_for_assignment();show_df(groups,["id","commission_no","group_no","sample_name","model","material_name","pending_count","status"])
    if groups:
        gid=st.selectbox("样品组",[g["id"] for g in groups],format_func=lambda x:next(f"{g['group_no']} {g['sample_name']}" for g in groups if g["id"]==x))
        pending=[x for x in requested_tests(gid) if x["status"]=="待分配"]
        pending_map={x["experiment_code"]:x for x in pending}
        experiment_codes=st.multiselect("本次任务包包含的检测项目与方法",list(pending_map),default=list(pending_map),
            format_func=lambda x:f"{pending_map[x]['experiment']}｜{pending_map[x]['method_code']}")
        testers=role_users("实验人员");reviewers=role_users("复核实验员")
        a,b=st.columns(2)
        assignee=a.selectbox("实验员",[x["username"] for x in testers],format_func=display_user)
        reviewer=b.selectbox("复核员",[x["username"] for x in reviewers],format_func=display_user)
        if st.button("下发任务包并提醒实验员",type="primary"):
            try:
                package_no=create_task_package(gid,experiment_codes,assignee,reviewer,username)
                st.success("已下发："+package_no);st.rerun()
            except Exception as e:st.error(str(e))

elif page=="我的任务包":
    header("任务提醒、整组样品领用和多个实验子任务")
    packages=list_packages(None if role=="管理员" else role,None if role=="管理员" else username);show_df(packages,["package_no","commission_no","group_no","material_name","experiments","status","assigned_at","accepted_at","detection_location"])
    if packages:
        pn=st.selectbox("选择任务包",[x["package_no"] for x in packages]);p=package(pn);show_df(package_tasks(pn),["task_no","experiment","method_code","standard","material_name","status"])
        if p["status"]=="待接收" and username==p["assignee"]:
            result=st.radio("样品实物接收确认",["样品已收到，确认完好","样品已收到，但存在异常","尚未收到样品"])
            recommended=[device_preset(x).get("default_location","") for x in p["experiments_list"]]
            recommended=next((x for x in recommended if x in DETECTION_LOCATIONS),DETECTION_LOCATIONS[0])
            location=st.selectbox(
                "主要检测位置（由实验员确定）",
                DETECTION_LOCATIONS,
                index=DETECTION_LOCATIONS.index(recommended),
            )
            note=st.text_area("领用/异常备注")
            if st.button("确认整组样品领用",type="primary"):
                try:accept_package(pn,username,result,location,note);st.rerun()
                except Exception as e:st.error(str(e))

elif page=="实验记录":
    header("简洁实验流程记录")
    all_packages=list_packages(role,username,["检测中","待复核","退回修改","待归还","待回库确认","已回库"])
    task_list=[]
    for p in all_packages:
        task_list.extend([t for t in package_tasks(p["package_no"]) if t["status"] in ["检测中","退回修改","待复核","更正待复核","已完成"]])
    if not task_list:
        st.info("暂无可填写实验任务")
    else:
        tn=st.selectbox(
            "选择实验任务",
            [t["task_no"] for t in task_list],
            format_func=lambda x:next(f"{t['task_no']}｜{t['experiment']}" for t in task_list if t['task_no']==x),
        )
        t=task(tn);config_snapshot=task_config_snapshot(tn);latest=latest_record(tn)
        if latest and latest["status"]=="已锁定":
            st.warning("该记录已锁定。如需更正，请在修改追踪中创建新版本。")
            st.stop()
        version=latest["version"] if latest else 1
        prior=latest["payload"] if latest else {}
        compare=None
        if version>1:
            versions=record_versions(tn);compare=versions[-2]["payload"] if len(versions)>1 else None

        group0=group(t["group_id"]);commission0=commission(t["commission_no"]);package0=package(t["package_no"])
        sample_ids=t["sample_nos_list"]
        template_name=config_snapshot.get("record_template_file","") or EXPERIMENTS.get(t["experiment"],{}).get("template","")
        if not template_name or not (TEMPLATE_DIR/template_name).exists():
            st.error("该实验尚未配置有效的受控原始记录模板，不能提交正式记录。")
            st.stop()
        kind=config_snapshot.get("kind") or EXPERIMENTS.get(t["experiment"],{}).get("kind","generic")
        bound_devices=config_snapshot.get("equipment",[])
        production_unit=commission0.get("production_org_name","")
        if commission0.get("production_relation")=="受委托生产企业" and production_unit:
            production_unit += "（受委托生产企业）"
        context={
            "client_name":commission0.get("client_name",""),
            "client_address":commission0.get("client_address",""),
            "production_unit":production_unit,
            "product_no":group0.get("product_no",""),
            "sample_name":group0.get("sample_name",""),
            "model":group0.get("model",""),
            "material":t.get("material_name",""),
            "sample_nos":sample_ids,
            "sample_quantity":len(sample_ids),
            "received_date":commission0.get("commission_date",""),
            "report_no":t.get("commission_no",""),
            "task_no":tn,
            "test_date":str(china_today()),
            "detection_location":package0.get("detection_location",""),
            "standard":t.get("standard",""),
            "method_code":t.get("method_code",""),
            "operator":user["display_name"],
            "reviewer":display_user(t.get("reviewer","")),
        }
        business=initialize_business_record(kind,sample_ids,package0.get("detection_location",""),prior.get("business_record") or {})
        key_prefix=f"simple_{tn}_{version}"
        st.info(f"{t['experiment']}｜{t['method_code']}｜{len(sample_ids)}件样品。已知信息自动带入，正常选项已设置为默认值；实验员只需确认现场状态并填写实际测量数据。")
        tabs=st.tabs(["①任务确认","②设备与实验前检查","③环境与参数","④原始数据","⑤异常与附件","⑥保存提交"])
        with tabs[0]:
            render_readonly_summary(t,group0,commission0,package0,config_snapshot)
            business["task_confirmations"]=render_task_confirmations(business,key_prefix)
        with tabs[1]:
            business["equipment_checks"]=render_equipment_confirmation(bound_devices,business.get("equipment_checks") or [],key_prefix)
            business["prechecks"],business["precheck_note"]=render_prechecks(kind,business,key_prefix)
        with tabs[2]:
            business["parameters"],business["fixed_parameter_mode"]=render_parameters(kind,business,key_prefix)
        with tabs[3]:
            business["rows"]=render_sample_data(kind,business,key_prefix)
        with tabs[4]:
            business=render_exception_and_summary(kind,business,key_prefix)
            st.divider()
            st.subheader("附件追溯")
            attachments=list_attachments(task_no=tn)
            show_df(attachments,["attachment_id","sample_no","attachment_type","original_name","sha256","captured_at","uploader","description"])
            atype=st.selectbox("附件类型",ATTACHMENT_TYPES,key=f"{key_prefix}_atype")
            sample_no=st.selectbox("关联样品编号",[""]+sample_ids,key=f"{key_prefix}_attach_sample")
            captured=st.text_input("拍摄/生成时间（北京时间）",value=now(),key=f"{key_prefix}_captured")
            description=st.text_area("附件内容说明",key=f"{key_prefix}_attach_desc")
            files=st.file_uploader("上传电脑截图、实验照片、曲线或原始文件",accept_multiple_files=True,key=f"{key_prefix}_files")
            if files and st.button("保存附件",key=f"{key_prefix}_save_attach"):
                for f in files:
                    save_attachment({"commission_no":t["commission_no"],"package_no":t["package_no"],"task_no":tn,"sample_no":sample_no,"attachment_type":atype,"original_name":f.name,"captured_at":captured,"description":description,"is_original":True},f.getvalue(),username)
                st.success("附件已保存并计算SHA-256校验值");st.rerun()
            st.caption("附件不写入正式原始记录表；附件索引统一进入单据中心的内部实验数据追溯Excel。")
        with tabs[5]:
            business=calculate_business_record(kind,business)
            context["test_date"]=(business.get("parameters") or {}).get("test_date") or context["test_date"]
            attachments=list_attachments(task_no=tn)
            template_fields=business_to_template_fields(
                template_name,kind,context,bound_devices,business,attachments,prior.get("template_fields") or {}
            )
            summary0=business_completion_summary(kind,business,bound_devices)
            render_completion(summary0)
            st.caption("提交后，系统会把上述业务数据直接回填至受控Word母版的原位置；实验员界面不显示模板原文、表格坐标或无关选项。")
            reason=st.text_area("修改原因（首次记录可不填）",latest.get("change_reason","") if latest else "",key=f"{key_prefix}_reason")
            tm_version=config_snapshot.get("record_template_version","") or "A/0"
            sm_version=config_snapshot.get("sop_version","") or "A/0"
            payload={
                "common":{"record_no":tn,"task_no":tn,"commission_no":t["commission_no"],"report_no":t["commission_no"],"client":commission0["client_name"],"sample_name":group0["sample_name"],"sample_no":"、".join(sample_ids),"model":group0["model"],"material":t["material_name"],"method_code":t["method_code"],"standard":t["standard"],"test_date":context["test_date"],"operator":user["display_name"],"reviewer":display_user(t["reviewer"])},
                "business_record":business,
                "template_name":template_name,
                "template_fields":template_fields,
                "equipment_snapshot":bound_devices,
                "deviation":business.get("deviation",""),
                "retest":business.get("retest","否"),
                "report_summary":business.get("report_summary",""),
                "report_conclusion":business.get("report_conclusion",""),
                "configuration_snapshot":config_snapshot,
            }
            a,b=st.columns(2)
            if a.button("保存草稿",use_container_width=True,key=f"{key_prefix}_draft"):
                save_record(tn,version,payload,username,"草稿",tm_version,sm_version,reason,compare);st.success("草稿已保存")
            if b.button("提交复核",type="primary",use_container_width=True,disabled=not summary0["complete"],key=f"{key_prefix}_submit"):
                save_record(tn,version,payload,username,"更正待复核" if version>1 else "待复核",tm_version,sm_version,reason,compare);st.rerun()

elif page=="原始记录复核":
    header("按实验流程复核原始记录")
    rs=pending_reviews(None if role=="管理员" else username)
    show_df(rs,["record_no","version","package_no","group_no","experiment","owner","status","updated_at"])
    if rs:
        key=st.selectbox("选择记录",[f"{x['record_no']}|{x['version']}" for x in rs])
        rn,v=key.split("|");r=record(rn,int(v));snap=task_config_snapshot(rn);template_name=snap.get("record_template_file","") or r["payload"].get("template_name","")
        kind=snap.get("kind") or "generic";business=r["payload"].get("business_record") or {};summary0=business_completion_summary(kind,business,snap.get("equipment") or [])
        render_completion(summary0)
        t0=task(rn);g0=group(t0["group_id"]);c0=commission(t0["commission_no"]);p0=package(t0["package_no"])
        render_readonly_summary(t0,g0,c0,p0,snap)
        st.subheader("环境与实验参数");show_df([{"项目":k,"记录值":v0} for k,v0 in (business.get("parameters") or {}).items()],["项目","记录值"])
        st.subheader("原始测量数据");show_df(business.get("rows") or [])
        st.subheader("设备使用确认");show_df(business.get("equipment_checks") or [])
        st.subheader("异常与结果")
        st.write("实验状态：",business.get("overall_status",""));st.write("异常/偏离：",business.get("deviation","无"));st.write("复测/重制：",business.get("retest","否"));st.write("结果摘要：",business.get("report_summary",""));st.write("单项结论：",business.get("report_conclusion",""))
        if template_name:
            st.download_button("下载待复核原始记录预览",export_record(r,template_name,audit_logs(rn)),f"{rn}_V{v}_待复核原始记录.docx")
        st.subheader("附件索引（独立追溯）");show_df(list_attachments(task_no=rn),["attachment_id","attachment_type","original_name","sha256","description"])
        comment=st.text_area("复核意见")
        a,b=st.columns(2)
        if a.button("通过并锁定",type="primary",disabled=not summary0["complete"]):review_record(rn,int(v),username,"通过",comment);st.rerun()
        if b.button("退回修改"):review_record(rn,int(v),username,"退回",comment);st.rerun()

elif page=="样品归还":
    header("全部实验完成后整组样品一次归还")
    packages=return_candidates(username) if role!="管理员" else list_packages(statuses=["待归还"]);show_df(packages,["package_no","commission_no","group_no","experiments","status"])
    if packages:
        pn=st.selectbox("待归还任务包",[x["package_no"] for x in packages]);loans=package_loan_rows(pn);edit=pd.DataFrame([{"样品编号":x["sample_no"],"归还状态":"完好","归还备注":""} for x in loans]);edit=st.data_editor(edit,hide_index=True,use_container_width=True,column_config={"样品编号":st.column_config.TextColumn(disabled=True),"归还状态":st.column_config.SelectboxColumn(options=RETURN_CONDITIONS)})
        if st.button("提交整组归还",type="primary"):submit_package_return(pn,username,[{"sample_no":r["样品编号"],"condition":r["归还状态"],"note":r["归还备注"]} for _,r in edit.iterrows()]);st.rerun()

elif page=="回库确认":
    header("样品管理员逐个确认回库位置")
    packages=pending_return_packages();show_df(packages,["package_no","commission_no","group_no","assignee","return_submitted_at"])
    if packages:
        pn=st.selectbox("待回库任务包",[x["package_no"] for x in packages]);loans=[x for x in package_loan_rows(pn) if x["return_status"]=="待回库确认"];edit=pd.DataFrame([{"样品编号":x["sample_no"],"归还状态":x["return_condition"],"回库位置":"A区域"} for x in loans]);edit=st.data_editor(edit,hide_index=True,use_container_width=True,column_config={"样品编号":st.column_config.TextColumn(disabled=True),"归还状态":st.column_config.TextColumn(disabled=True),"回库位置":st.column_config.SelectboxColumn(options=STORAGE_AREAS)})
        if st.button("确认整组回库",type="primary"):confirm_package_return(pn,username,[{"sample_no":r["样品编号"],"location":r["回库位置"]} for _,r in edit.iterrows()]);st.rerun()

elif page=="附件与内部追溯":
    header("电脑截图、实验照片、曲线和原始文件独立追溯")
    cs=list_commissions();cn=st.selectbox("按委托筛选",[""]+[x["commission_no"] for x in cs])
    attachments=list_attachments(commission_no=cn or None)
    visible=attachments
    show_df(visible,["attachment_id","commission_no","package_no","task_no","sample_no","attachment_type","original_name","relative_path","sha256","captured_at","uploader","description"])
    st.caption("附件与原始记录通过委托编号、任务编号和样品编号关联；详细索引统一进入内部实验数据追溯Excel。")
    if visible:
        fieldnames=list(visible[0].keys())
        buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=fieldnames);writer.writeheader();writer.writerows(visible)
        st.download_button("下载当前附件索引CSV",buf.getvalue().encode("utf-8-sig"),"附件索引.csv","text/csv")
        aid=st.selectbox("预览/下载附件",[x["attachment_id"] for x in attachments]);meta=next(x for x in attachments if x["attachment_id"]==aid);path=attachment_file(meta)
        if path.exists():
            if path.suffix.lower() in [".png",".jpg",".jpeg",".webp"]:st.image(str(path),caption=meta["description"] or meta["original_name"])
            st.download_button("下载原始附件",path.read_bytes(),meta["original_name"])

elif page=="单据中心":
    header("检验委托单、样品登记、领用归还、原始记录和检验报告")
    cs=list_commissions();show_df(cs,["commission_no","client_name","commission_date","due_date","status"])
    if cs:
        cn=st.selectbox("选择委托",[x["commission_no"] for x in cs]);c0=commission(cn);groups=commission_groups(cn);samples0=commission_samples(cn);tests=commission_tests(cn);users0=user_map();st.download_button("下载检验委托单",commission_document(c0,groups,tests,display_user(c0["created_by"])),f"{cn}_检验委托单.docx");st.download_button("下载样品登记表",sample_register_document(c0,groups,samples0,tests,display_user(c0["created_by"])),f"{cn}_样品登记表.docx");st.download_button("下载样品领用归还登记表",loan_return_document(commission_loans(cn),users0),f"{cn}_样品领用归还登记表.docx")
        st.download_button("下载内部实验数据追溯Excel",build_internal_trace_workbook(cn),f"{cn}_内部实验数据追溯工作簿.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        locked=[]
        for t in commission_tasks(cn):locked.extend([r for r in record_versions(t["task_no"]) if r["status"]=="已锁定"])
        if locked:
            key=st.selectbox("下载锁定原始记录",[f"{r['record_no']}|{r['version']}" for r in locked]);rn,v=key.split("|");r=record(rn,int(v));t=task(rn);snap=task_config_snapshot(rn);r["kind"]=snap.get("kind") or "generic";template_name=snap.get("record_template_file","");changes=audit_logs(rn);st.download_button("下载选定原始记录表",export_record(r,template_name,changes),f"{rn}_V{v}_原始记录表.docx")
        rp=report(cn)
        if rp:
            tasks0=commission_tasks(cn);gmap={g["id"]:g for g in groups}
            for t in tasks0:t["kind"]=task_config_snapshot(t["task_no"]).get("kind") or "generic";t["sample_name"]=gmap[t["group_id"]]["sample_name"]
            sigs={u:signature(u) for u in users0};st.download_button("下载当前检验报告",report_document(c0,groups,samples0,tasks0,report_records(cn),rp,users0,sigs),f"{cn}_检验报告.docx")

elif page=="报告中心":
    header("同一委托全部实验汇总为一份报告并分级签署")
    rs=list_reports(role,username);show_df(rs,["report_no","commission_no","status","tester","verifier","approver","updated_at"])
    if rs:
        rn=st.selectbox("报告",[x["report_no"] for x in rs]);r=report(rn);st.info("当前状态："+r["status"])
        if role=="管理员":
            testers=role_users("实验人员");reviewers=role_users("复核实验员");approvers=role_users("批准人");a,b,c=st.columns(3);tester=a.selectbox("检测员",[x["username"] for x in testers],format_func=display_user);verifier=b.selectbox("核验员",[x["username"] for x in reviewers],format_func=display_user);approver=c.selectbox("批准人",[x["username"] for x in approvers],format_func=display_user)
            if st.button("保存报告签署人员"):update_report_roles(rn,tester,verifier,approver,username);st.rerun()
        if r["status"] in ["待检测员确认","退回检测员"] and username==r["tester"]:
            report_task_rows=commission_tasks(r["commission_no"]);report_record_rows=report_records(r["commission_no"]);auto_items=[]
            for report_task in report_task_rows:
                report_record=report_record_rows.get(report_task["task_no"])
                if not report_record:continue
                report_payload=report_record.get("payload") or {};report_business=report_payload.get("business_record") or {};report_snap=report_payload.get("configuration_snapshot") or {}
                auto_items.append(report_item(report_snap.get("kind") or "generic",report_business.get("rows") or []))
            auto_statement="；".join(f"{g['group_no']}：接收状态{g.get('condition','完好')}，共{g.get('quantity',1)}件" for g in commission_groups(r["commission_no"]))
            category=st.text_input("检验类别",r.get("report_category") or "委托检验");statement=st.text_area("样品情况说明",r.get("sample_statement") or auto_statement);conclusion=st.text_area("检验结论",r.get("conclusion") or overall_conclusion(auto_items));notes=st.text_area("需说明情况",r.get("notes") or "无")
            if st.button("检测员确认并签署",type="primary"):tester_submit_report(rn,username,category,statement,conclusion,notes);st.rerun()
        if r["status"]=="待核验" and username==r["verifier"]:
            comment=st.text_area("核验意见");a,b=st.columns(2)
            if a.button("核验通过",type="primary"):verifier_review_report(rn,username,"通过",comment);st.rerun()
            if b.button("退回检测员"):verifier_review_report(rn,username,"退回",comment);st.rerun()
        if r["status"]=="待批准" and username==r["approver"]:
            comment=st.text_area("批准意见");a,b=st.columns(2)
            if a.button("批准发布",type="primary"):approver_review_report(rn,username,"批准",comment);st.rerun()
            if b.button("退回检测员"):approver_review_report(rn,username,"退回",comment);st.rerun()
        show_df(report_actions(rn))

elif page=="修改追踪":
    header("原始记录版本和修改前后追踪")
    all_records=rows("SELECT * FROM records ORDER BY updated_at DESC");show_df(all_records,["record_no","version","experiment","owner","status","change_reason","updated_at"])
    if all_records:
        rn=st.selectbox("记录编号",list(dict.fromkeys(x["record_no"] for x in all_records)));show_df(record_versions(rn),["record_no","version","owner","status","change_reason","created_at","updated_at"]);show_df(audit_logs(rn),["action","field_name","old_value","new_value","reason","actor","created_at"]);reason=st.text_area("创建修改版原因")
        if st.button("创建新修改版",type="primary"):
            try:create_revision(rn,username,reason);st.success("已创建草稿版本，请回到实验记录修改");st.rerun()
            except Exception as e:st.error(str(e))

elif page=="SOP与模板版本":
    header("SOP和实验原始记录表受控版本")
    if role!="管理员":st.stop()
    show_df(all_template_versions(),["experiment","doc_type","version","effective_date","status","uploader","uploaded_at","note"])
    methods=list_experiment_methods(True)
    if not methods:st.info("请先建立检测项目");st.stop()
    exp=st.selectbox("实验项目",[x["experiment_name"] for x in methods])
    typ=st.selectbox("文件类型",["SOP","原始记录表"])
    ver=st.text_input("版本号","A/1")
    effective=st.date_input("生效日期",china_today())
    note=st.text_input("变更说明")
    f=st.file_uploader("上传DOCX",type=["docx"])
    if f and st.button("批准并启用文件版本",type="primary"):
        name=f"TPL_{hashlib.sha1((exp+typ+ver+f.name).encode()).hexdigest()[:12]}.docx"
        (TEMPLATE_DIR/name).write_bytes(f.getvalue())
        add_template(exp,typ,name,ver,str(effective),username,note)
        st.success("文件版本已启用。实验配置是否采用该版本，应在“实验配置版本”中确定。")
        st.rerun()

elif page=="实验配置版本":
    header("实验、方法、SOP、记录模板、地点和设备的动态版本配置")
    if role!="管理员":st.stop()
    methods=list_experiment_methods(True)
    method_map={x["experiment_code"]:x for x in methods}
    show_df(current_config_overview(),["experiment_name","method_code","config_version","kind","default_location","equipment_count","status","enabled"])
    if not methods:st.info("请先在检测项目与方法库中新建实验");st.stop()
    selected_code=st.selectbox("选择实验",[x["experiment_code"] for x in methods],format_func=lambda x:f"{method_map[x]['experiment_name']}｜{method_map[x]['method_code']}")
    configs=list_experiment_configs(selected_code)
    tabs=st.tabs(["①版本历史","②新建配置草稿","③编辑草稿信息","④配置设备关系","⑤批准发布"])
    with tabs[0]:
        show_df(configs,["version","experiment_name","method_code","standard","kind","default_location","sop_version","record_template_version","status","effective_date","created_by","approved_by","approved_at","note"])
        current=current_experiment_config(selected_code)
        if current:
            st.subheader(f"现行配置 {current['version']} 的设备关系")
            show_df(config_equipment(current["id"],True),["management_no","equipment_name","model","binding_role","required","lifecycle_status","calibration_time","sort_order","note"])
    with tabs[1]:
        version=st.text_input("新配置版本号","V1.1")
        copy_current=st.checkbox("复制现行配置及其设备关系",value=True)
        if st.button("建立配置草稿",type="primary"):
            try:
                cid=create_experiment_config_version(selected_code,version,username,copy_current)
                st.success(f"已建立草稿，配置ID：{cid}")
                st.rerun()
            except Exception as e:st.error(str(e))
    drafts=[x for x in configs if x["status"]=="草稿"]
    with tabs[2]:
        if not drafts:st.info("暂无草稿，请先新建配置草稿")
        else:
            cid=st.selectbox("选择草稿",[x["id"] for x in drafts],format_func=lambda x:next(f"{c['version']}｜{c['experiment_name']}" for c in drafts if c["id"]==x),key="edit_config")
            cfg=experiment_config(cid)
            sop_versions=[x for x in all_template_versions() if x["experiment"]==cfg["experiment_name"] and x["doc_type"]=="SOP"]
            record_versions0=[x for x in all_template_versions() if x["experiment"]==cfg["experiment_name"] and x["doc_type"]=="原始记录表"]
            with st.form("edit_config_form"):
                a,b,c=st.columns(3)
                exp_name=a.text_input("实验名称",cfg["experiment_name"])
                method=b.text_input("检测方法",cfg["method_code"])
                standard=c.text_input("检测依据/版本",cfg.get("standard","") or "")
                category=a.text_input("实验类别",cfg.get("category","") or "")
                kinds=list(SCHEMAS.keys());kind=b.selectbox("记录数据模板",kinds,index=kinds.index(cfg.get("kind") or "generic") if (cfg.get("kind") or "generic") in kinds else kinds.index("generic"))
                location=c.selectbox("推荐检测地点",[""]+DETECTION_LOCATIONS,index=([""]+DETECTION_LOCATIONS).index(cfg.get("default_location","") or "") if (cfg.get("default_location","") or "") in ([""]+DETECTION_LOCATIONS) else 0)
                sop_options=[""]+list(dict.fromkeys(x["version"] for x in sop_versions));sop=a.selectbox("SOP版本",sop_options,index=sop_options.index(cfg.get("sop_version","") or "") if (cfg.get("sop_version","") or "") in sop_options else 0)
                rec_options=[""]+list(dict.fromkeys(x["version"] for x in record_versions0));rec=b.selectbox("原始记录模板版本",rec_options,index=rec_options.index(cfg.get("record_template_version","") or "") if (cfg.get("record_template_version","") or "") in rec_options else 0)
                software=c.text_input("软件名称/版本",cfg.get("software","") or "")
                effective=a.date_input("计划生效日期",pd.to_datetime(cfg.get("effective_date") or china_today()).date())
                note=st.text_area("配置变更说明",cfg.get("note","") or "")
                if st.form_submit_button("保存配置草稿",type="primary"):
                    try:
                        save_experiment_config(cid,{"experiment_name":exp_name,"method_code":method,"standard":standard,"category":category,"kind":kind,"default_location":location,"sop_version":sop,"record_template_version":rec,"software":software,"effective_date":str(effective),"note":note},username)
                        st.rerun()
                    except Exception as e:st.error(str(e))
    with tabs[3]:
        if not drafts:st.info("暂无可编辑草稿")
        else:
            cid=st.selectbox("选择草稿配置",[x["id"] for x in drafts],format_func=lambda x:next(f"{c['version']}｜{c['experiment_name']}" for c in drafts if c["id"]==x),key="bind_config")
            current_items=config_equipment(cid,True)
            show_df(current_items,["management_no","equipment_name","model","binding_role","required","lifecycle_status","calibration_time","sort_order","note"])
            devices=list_equipment(True)
            dmap={x["management_no"]:x for x in devices}
            device_no=st.selectbox("选择设备/标准器/夹具",[x["management_no"] for x in devices],format_func=lambda x:f"{x}｜{dmap[x]['equipment_name']}｜{dmap[x].get('lifecycle_status','')}")
            existing=next((x for x in current_items if x["management_no"]==device_no),{})
            a,b,c=st.columns(3)
            roles=EQUIPMENT_BINDING_ROLES
            bind_role=a.selectbox("配置角色",roles,index=roles.index(existing.get("binding_role")) if existing.get("binding_role") in roles else 0)
            required=b.checkbox("必需设备",value=bool(existing.get("required",0)))
            order=c.number_input("排序",min_value=0,value=int(existing.get("sort_order",100) or 100))
            note=st.text_area("用途/绑定说明",existing.get("note","") or "")
            x,y=st.columns(2)
            if x.button("保存配置设备关系",type="primary",use_container_width=True):
                try:bind_config_equipment(cid,device_no,bind_role,required,order,note,username);st.rerun()
                except Exception as e:st.error(str(e))
            if y.button("从该草稿解除设备",use_container_width=True):
                try:unbind_config_equipment(cid,device_no,username);st.rerun()
                except Exception as e:st.error(str(e))
    with tabs[4]:
        if not drafts:st.info("暂无可发布草稿")
        else:
            cid=st.selectbox("选择待发布草稿",[x["id"] for x in drafts],format_func=lambda x:next(f"{c['version']}｜{c['experiment_name']}" for c in drafts if c["id"]==x),key="publish_config")
            cfg=experiment_config(cid);show_df([cfg]);show_df(config_equipment(cid,True),["management_no","equipment_name","binding_role","required","lifecycle_status","calibration_time","note"])
            reason=st.text_area("批准/变更原因")
            st.warning("发布后，新建任务将使用该版本；已经创建的任务继续使用原任务快照，不受影响。")
            if st.button("批准并发布为现行配置",type="primary"):
                try:publish_experiment_config(cid,username,reason);st.success("配置已发布");st.rerun()
                except Exception as e:st.error(str(e))

elif page=="设备库":
    header("DLBP-CX-P05-R10设备台账动态管理")
    if role!="管理员":st.stop()
    devices=list_equipment(True);dmap={x["management_no"]:x for x in devices}
    a,b,c,d=st.columns(4)
    a.metric("设备总数",len(devices));b.metric("启用",sum(1 for x in devices if x.get("lifecycle_status")=="启用"));c.metric("维修/停用",sum(1 for x in devices if x.get("lifecycle_status") in ["维修","停用"]));d.metric("报废",sum(1 for x in devices if x.get("lifecycle_status")=="报废"))
    tabs=st.tabs(["①设备台账","②维护已有设备","③新增设备","④使用关系与审计"])
    with tabs[0]:
        show_df(devices,["seq","equipment_name","model","measuring_range","manufacturer","serial_no","management_no","purchase_time","calibration_time","responsible","equipment_class","lifecycle_status","status_note","enabled"])
        master_df=pd.DataFrame(devices)
        st.download_button("下载当前设备台账CSV",master_df.to_csv(index=False).encode("utf-8-sig"),"equipment_master_current.csv","text/csv")
        binding_rows=[]
        for cfg in [x for x in list_experiment_configs() if x["status"]=="现行"]:
            for item in config_equipment(cfg["id"],True):
                binding_rows.append({"实验名称":cfg["experiment_name"],"配置版本":cfg["version"],"默认地点":cfg.get("default_location","") or "","管理编号":item["management_no"],"设备名称":item["equipment_name"],"角色":item["binding_role"],"是否必需":"是" if item["required"] else "否","设备状态":item.get("lifecycle_status","") or "","说明":item.get("note","") or ""})
        st.download_button("下载现行实验配置设备矩阵CSV",pd.DataFrame(binding_rows).to_csv(index=False).encode("utf-8-sig"),"current_experiment_equipment_matrix.csv","text/csv")
    with tabs[1]:
        selected=st.selectbox("选择设备",[x["management_no"] for x in devices],format_func=lambda x:f"{x}｜{dmap[x]['equipment_name']}")
        item=equipment_item(selected) or {}
        with st.form("equipment_edit"):
            a,b,c=st.columns(3)
            seq=a.number_input("序号",min_value=1,value=int(item.get("seq",1) or 1));name=b.text_input("名称",item.get("equipment_name","") or "");model=c.text_input("规格型号",item.get("model","") or "")
            rng=a.text_area("测量范围",item.get("measuring_range","") or "");manufacturer=b.text_input("生产厂家",item.get("manufacturer","") or "");serial=c.text_input("出厂编号",item.get("serial_no","") or "")
            management=a.text_input("管理编号",item.get("management_no","") or "",disabled=True);purchase=b.text_input("购置时间",item.get("purchase_time","") or "");calibration=c.text_input("校准时间",item.get("calibration_time","") or "")
            responsible=a.text_input("责任人",item.get("responsible","") or "");cls=b.selectbox("分类",["A类","B类","C类"],index=["A类","B类","C类"].index(item.get("equipment_class","A类")) if item.get("equipment_class") in ["A类","B类","C类"] else 0);status=c.selectbox("设备状态",EQUIPMENT_LIFECYCLE_STATUSES,index=EQUIPMENT_LIFECYCLE_STATUSES.index(item.get("lifecycle_status","启用")) if item.get("lifecycle_status") in EQUIPMENT_LIFECYCLE_STATUSES else 0)
            status_note=st.text_input("状态说明",item.get("status_note","") or "");notes=st.text_area("备注",item.get("notes","") or "")
            if st.form_submit_button("保存设备资料",type="primary"):
                save_equipment({"seq":seq,"equipment_name":name,"model":model,"measuring_range":rng,"manufacturer":manufacturer,"serial_no":serial,"management_no":management,"purchase_time":purchase,"calibration_time":calibration,"responsible":responsible,"equipment_class":cls,"lifecycle_status":status,"status_note":status_note,"enabled":status=="启用","notes":notes},username);st.rerun()
    with tabs[2]:
        with st.form("equipment_add"):
            a,b,c=st.columns(3)
            management=a.text_input("管理编号");name=b.text_input("名称");seq=c.number_input("序号",min_value=1,value=max([int(x.get("seq",0) or 0) for x in devices]+[0])+1)
            model=a.text_input("规格型号");rng=b.text_area("测量范围");manufacturer=c.text_input("生产厂家")
            serial=a.text_input("出厂编号");purchase=b.text_input("购置时间");calibration=c.text_input("校准时间")
            responsible=a.text_input("责任人");cls=b.selectbox("分类",["A类","B类","C类"]);status=c.selectbox("设备状态",EQUIPMENT_LIFECYCLE_STATUSES)
            status_note=st.text_input("状态说明");notes=st.text_area("备注")
            if st.form_submit_button("新增设备",type="primary"):
                try:save_equipment({"seq":seq,"equipment_name":name,"model":model,"measuring_range":rng,"manufacturer":manufacturer,"serial_no":serial,"management_no":management,"purchase_time":purchase,"calibration_time":calibration,"responsible":responsible,"equipment_class":cls,"lifecycle_status":status,"status_note":status_note,"enabled":status=="启用","notes":notes},username);st.rerun()
                except Exception as e:st.error(str(e))
    with tabs[3]:
        st.info("设备变化不会回写历史任务。历史任务保存的是创建任务时的设备、校准状态和配置版本快照。")
        show_df(audit_logs(),["entity_type","entity_id","action","old_value","new_value","reason","actor","created_at"])

elif page=="电子签名":
    header("电子签名库")
    if role!="管理员":st.stop()
    users0=list_users();u=st.selectbox("人员",[x["username"] for x in users0],format_func=display_user);f=st.file_uploader("上传PDF、PNG或JPG签名",type=["pdf","png","jpg","jpeg"])
    if f and st.button("保存签名",type="primary"):
        ext=Path(f.name).suffix.lower();source=SIG_DIR/f"{u}_source{ext}";source.write_bytes(f.getvalue());image=None
        if ext==".pdf":
            try:
                import fitz;doc=fitz.open(source);pix=doc[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=True);image=SIG_DIR/f"{u}_signature.png";pix.save(image)
            except Exception as e:st.error("PDF转换失败："+str(e));st.stop()
        else:image=SIG_DIR/f"{u}_signature{ext}";image.write_bytes(f.getvalue())
        save_signature(u,source.name,image.name if image else None,username);st.success("签名已保存")
    show_df([{**x,"签名状态":"已配置" if signature(x["username"]) else "未配置"} for x in users0],["username","display_name","role","签名状态"])

elif page=="用户与权限":
    header("用户与角色权限")
    if role!="管理员":st.stop()
    show_df(list_users());a,b=st.columns(2);u=a.text_input("用户名");name=b.text_input("姓名");pwd=a.text_input("初始密码",type="password");r=b.selectbox("角色",ROLES)
    if st.button("创建用户",type="primary"):
        try:add_user(u,name,pwd,r);st.rerun()
        except Exception as e:st.error(str(e))

elif page=="审计追踪":
    header("不可无痕修改的审计记录")
    if role!="管理员":st.stop()
    show_df(audit_logs(),["entity_type","entity_id","actor","action","field_name","old_value","new_value","reason","created_at"])
