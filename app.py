# -*- coding: utf-8 -*-
from datetime import date
from pathlib import Path
import json,streamlit as st,pandas as pd
from constants import *
from lims_db import *
from experiment_engine import initial_dataframe,calculate
from word_engine import export_record
from document_engine import commission_doc,register_doc,loan_doc,report_doc
ROOT=Path(__file__).parent;SIGDIR=ROOT/"data"/"signatures";SIGDIR.mkdir(parents=True,exist_ok=True)
st.set_page_config(page_title="BPLab Trace",page_icon="🧪",layout="wide")
st.markdown("""<style>.block-container{max-width:1550px;padding-top:1rem}.hero{background:linear-gradient(135deg,#12364a,#176b87);color:white;padding:24px;border-radius:20px}.card{background:white;border:1px solid #dce7ee;padding:15px;border-radius:14px}[data-testid=stSidebar]{background:#12364a}[data-testid=stSidebar] *{color:white}</style>""",unsafe_allow_html=True)
def head(x):st.markdown(f'<div class="hero"><h2>{COMPANY_CN}</h2><div>{SYSTEM_CN}</div><h3>{x}</h3><small>{APP_VERSION}｜北京时间 Asia/Shanghai UTC+8</small></div>',unsafe_allow_html=True)
init_db()
if "user" not in st.session_state:
 t=st.query_params.get("session","");u=session_user(t)
 if u:st.session_state.user=u
if "user" not in st.session_state:
 head("登录");u=st.text_input("用户名");p=st.text_input("密码",type="password")
 if st.button("登录",type="primary"):
  x=auth(u,p)
  if x:
   st.session_state.user=x;st.query_params["session"]=make_session(u);st.rerun()
  else:st.error("账号或密码错误")
 st.caption("admin/admin123；receiver/receive123；tester/test123；reviewer/review123；store/store123；approver/approve123");st.stop()
user=st.session_state.user;role=user["role"];username=user["username"]
with st.sidebar:
 st.title("BPLab Trace");st.write(user["display_name"]);page=st.radio("导航",ROLE_MENUS[role],label_visibility="collapsed")
 if st.button("退出"):st.session_state.clear();st.query_params.clear();st.rerun()
if page=="首页看板":
 head("全过程状态看板");ss=samples();ts=tasks()
 a,b,c,d=st.columns(4);a.metric("在册样品",len(ss));b.metric("待接收任务",sum(x["status"]=="待接收" for x in ts));c.metric("待复核",sum(x["status"]=="待复核" for x in ts));d.metric("待回库",len(pending_returns()))
 if ss:st.dataframe(pd.DataFrame(ss)[["sample_no","sample_name","model","status","location","owner","commission_no"]],hide_index=True,use_container_width=True)
elif page=="基础资料":
 head("客户与样品名称资料")
 if role not in["管理员","收样员"]:st.stop()
 t1,t2=st.tabs(["客户信息","样品名称/规格型号"])
 with t1:
  st.dataframe(pd.DataFrame(customers()),hide_index=True,use_container_width=True)
  c1,c2=st.columns(2);code=c1.text_input("客户编号");name=c2.text_input("客户名称");addr=c1.text_input("地址");contact=c2.text_input("联系人");phone=c1.text_input("联系电话");note=c2.text_input("备注")
  if st.button("添加客户"):
   add_customer(code,name,addr,contact,phone,note);st.rerun()
 with t2:
  st.dataframe(pd.DataFrame(catalogs()),hide_index=True,use_container_width=True)
  c1,c2,c3=st.columns(3);code=c1.text_input("样品资料编号");name=c2.text_input("样品名称");model=c3.text_input("规格型号");prod=c1.text_input("生产单位");cat=c2.text_input("类别");unit=c3.text_input("单位",value="件");defs=st.multiselect("默认检测项目",list(EXPERIMENTS));note=st.text_input("样品资料备注")
  if st.button("添加样品名称"):
   add_catalog(code,name,model,prod,cat,unit,defs,note);st.rerun()
elif page=="样品入库":
 head("新建检验委托单并完成样品入库")
 cs=customers();cats=catalogs()
 ci=st.selectbox("委托客户",range(len(cs)),format_func=lambda i:cs[i]["name"]);ca=cs[ci]
 si=st.selectbox("样品名称/规格型号",range(len(cats)),format_func=lambda i:f'{cats[i]["name"]}｜{cats[i]["model"]}');sc=cats[si]
 c1,c2,c3=st.columns(3);commission_no=c1.text_input("检验委托单编号（暂行）",value=next_no("WT"));base=c2.text_input("样品基础编号",value=next_sample_no());qty=int(c3.number_input("接收数量",1,100,1))
 preview=[base] if qty==1 else[f"{base}-{i}" for i in range(1,qty+1)];st.caption("自动生成："+ "、".join(preview))
 product_no=c1.text_input("产品编号/批号");storage=c2.selectbox("入库区域",STORAGE_AREAS);condition=c3.selectbox("样品状态",SAMPLE_CONDITIONS);condition_note=st.text_input("样品状态备注")
 received=c1.date_input("委托/接收日期",china_today());due=c2.date_input("计划完成日期",add_months_to_date(received));experiments=st.multiselect("检测项目",list(EXPERIMENTS),default=json.loads(sc["default_experiments"] or "[]"))
 st.subheader("委托及报告要求");subcontract=c1.selectbox("允许分包",["否","是"]);confidential=c2.selectbox("保密要求",["无要求","是"]);medium=c3.multiselect("报告载体",["纸质","电子档"],default=["电子档"]);conformity=c1.selectbox("符合性判定",["是","否"]);uncertainty=c2.selectbox("考虑不确定度",["否","是"]);delivery=c3.selectbox("递送方式",["Email","自取","快递"]);cnas=c1.selectbox("加盖CNAS章",["否","是"]);capability=c2.selectbox("检测能力",["完全满足","部分满足","不满足"]);notes=st.text_area("委托备注")
 if st.button("生成委托单、样品登记并入库",type="primary"):
  d={"commission_no":commission_no,"base_no":base,"qty":qty,"customer_id":ca["id"],"customer_name":ca["name"],"address":ca["address"],"contact":ca["contact"],"phone":ca["phone"],"catalog_id":sc["id"],"sample_name":sc["name"],"model":sc["model"],"production_unit":sc["production_unit"],"unit":sc["unit"],"product_no":product_no,"condition":condition,"condition_note":condition_note,"storage":storage,"commission_date":str(received),"due_date":str(due),"subcontract":subcontract,"confidential":confidential,"report_medium":"、".join(medium),"conformity":conformity,"uncertainty":uncertainty,"delivery":delivery,"cnas":cnas,"capability":capability,"notes":notes,"standards":{e:EXPERIMENTS[e]["std"] for e in experiments}}
  create_intake(d,experiments,username);st.session_state.last_commission=commission_no;st.success("入库完成，委托单和样品登记表已生成");st.rerun()
elif page=="样品全流程":
 head("样品全过程")
 ss=samples()
 if ss:
  sn=st.selectbox("样品", [x["sample_no"] for x in ss]);s=sample(sn)
  st.write(s);st.dataframe(pd.DataFrame(events(sn)),hide_index=True,use_container_width=True)
  st.dataframe(pd.DataFrame([x for x in tasks() if x["sample_no"]==sn]),hide_index=True,use_container_width=True)
  if role in["管理员","收样员"]:
   reason=st.text_input("错误入库删除原因")
   if st.button("删除错误入库"):
    try:soft_delete(sn,username,reason);st.rerun()
    except Exception as e:st.error(str(e))
elif page=="任务分配":
 head("任务分配")
 ts=tasks(["待分配","待接收"])
 if ts:
  tn=st.selectbox("任务", [x["task_no"] for x in ts]);us=all_users();testers=[x for x in us if x["role"]=="实验人员"];revs=[x for x in us if x["role"]=="复核实验员"]
  a=st.selectbox("实验员",[x["username"] for x in testers],format_func=lambda x:next(y["display_name"] for y in testers if y["username"]==x));r=st.selectbox("核验员",[x["username"] for x in revs],format_func=lambda x:next(y["display_name"] for y in revs if y["username"]==x))
  if st.button("下发任务并提醒"):assign(tn,a,r,username);st.rerun()
elif page=="我的检测任务":
 head("任务提醒与样品领用")
 ts=tasks(assignee=username)
 if ts:
  st.dataframe(pd.DataFrame(ts),hide_index=True,use_container_width=True);tn=st.selectbox("任务",[x["task_no"] for x in ts]);t=task(tn)
  if t["status"]=="待接收":
   result=st.radio("样品接收确认",["样品已收到，确认完好","样品已收到，但存在异常","尚未收到样品"]);loc=st.text_input("检测位置（由实验员确定）",value="力学实验室");note=st.text_area("领用/异常备注")
   if st.button("确认领用"):accept(tn,username,result,loc,note);st.rerun()
  if t["status"] in["检测中","退回修改"] and st.button("进入实验记录"):st.session_state.active_task=tn;st.info("请切换到实验记录")
elif page=="实验记录":
 head("实验原始记录")
 av=tasks(assignee=username) if role!="管理员" else tasks()
 av=[x for x in av if x["status"] in["检测中","退回修改","待复核","已完成"]]
 if av:
  tn=st.selectbox("任务/原始记录编号",[x["task_no"] for x in av],index=0);t=task(tn);s=sample(t["sample_no"]);old=latest_record(tn);v=(old["version"] if old and old["status"]!="已锁定" else (old["version"]+1 if old else 1));prior=old["payload"] if old else {}
  st.info(f"编号统一为任务编号：{tn}｜版本V{v}")
  c1,c2,c3=st.columns(3);temp=c1.number_input("温度℃",value=float(prior.get("common",{}).get("temperature",23)));hum=c2.number_input("湿度%RH",value=float(prior.get("common",{}).get("humidity",50)));eq=c3.text_input("设备名称/编号",prior.get("common",{}).get("equipment",""));cal=c1.text_input("校准/证书信息",prior.get("common",{}).get("calibration",""));material=c2.text_input("材料名称",prior.get("common",{}).get("material",""));deviation=st.text_area("异常/偏离",prior.get("deviation",""))
  conf=EXPERIMENTS[t["experiment"]];src=pd.DataFrame(prior["data"]) if prior.get("data") else initial_dataframe(conf["kind"],conf["n"]);ed=st.data_editor(src,use_container_width=True);res=calculate(conf["kind"],ed);st.dataframe(res,hide_index=True,use_container_width=True)
  payload={"common":{"record_no":tn,"task_no":tn,"report_no":t["commission_no"],"client":commission(t["commission_no"])["customer_name"],"sample_name":s["sample_name"],"sample_no":s["sample_no"],"model":s["model"],"material":material,"test_date":str(china_today()),"location":t["detection_location"],"temperature":temp,"humidity":hum,"equipment":eq,"calibration":cal,"operator":user["display_name"],"reviewer":t["reviewer"]},"deviation":deviation,"data":res.to_dict("records")}
  reason=st.text_area("修改原因（首次记录可留空）",value="" if v==1 else "原始记录更正")
  if st.button("提交复核",type="primary"):
   save_record(tn,v,payload,username,"待复核" if v==1 else "更正待复核",reason)
   with con() as c:c.execute("UPDATE tasks SET status='待复核',updated_at=? WHERE task_no=?",(now(),tn))
   st.success("已提交复核");st.rerun()
elif page=="待复核":
 head("原始记录复核")
 rs=pending_reviews(None if role=="管理员" else username)
 if rs:
  k=st.selectbox("任务/记录编号",[f'{x["record_no"]}|{x["version"]}' for x in rs]);tn,v=k.split("|");r=next(x for x in rs if x["record_no"]==tn and x["version"]==int(v));st.dataframe(pd.DataFrame(r["payload"]["data"]),hide_index=True,use_container_width=True);comment=st.text_area("复核意见")
  c1,c2=st.columns(2)
  if c1.button("通过并锁定"):review(tn,int(v),username,"通过",comment);st.rerun()
  if c2.button("退回"):review(tn,int(v),username,"退回",comment);st.rerun()
elif page=="样品归还":
 head("实验员样品归还")
 rs=return_candidates(username)
 if rs:
  tn=st.selectbox("待归还任务",[x["task_no"] for x in rs]);condition=st.selectbox("归还状态",["完好","部分消耗","已破坏","全部消耗"]);note=st.text_area("归还备注")
  if st.button("提交归还"):submit_return(tn,username,condition,note);st.rerun()
 else:st.info("暂无可归还样品")
elif page=="回库确认":
 head("样品管理员回库确认")
 rs=pending_returns()
 if rs:
  tn=st.selectbox("归还任务",[x["task_no"] for x in rs]);loc=st.selectbox("确认回库位置",STORAGE_AREAS)
  if st.button("确认回库"):confirm_return(tn,username,loc);st.rerun()
elif page=="单据中心":
 head("受控单据中心")
 cs=commissions()
 if cs:
  cn=st.selectbox("检验委托单",[x["commission_no"] for x in cs]);c=commission(cn);ss=commission_samples(cn);ts=commission_tasks(cn);ls=loans_by_commission(cn)
  st.download_button("下载检验委托单",commission_doc(c,ss,ts),f"{cn}_检验委托单.docx")
  st.download_button("下载样品登记表",register_doc(c,ss,ts),f"{cn}_样品登记表.docx")
  st.download_button("下载样品领用归还登记表",loan_doc(ls),f"{cn}_样品领用归还登记表.docx")
  locked=[]
  for tx in ts:
   rr=latest_record(tx["task_no"])
   if rr and rr["status"]=="已锁定":locked.append((tx,rr))
  if locked:
   pick=st.selectbox("选择原始记录",range(len(locked)),format_func=lambda i:f'{locked[i][0]["task_no"]}｜{locked[i][0]["experiment"]}')
   tx,rr=locked[pick];robj={"record_no":tx["task_no"],"task_no":tx["task_no"],"sample_no":tx["sample_no"],"version":rr["version"],"experiment":tx["experiment"],"owner":rr["owner"],"status":rr["status"],"payload":rr["payload"],"change_reason":rr.get("reason","")}
   st.download_button("下载实验原始记录表",export_record(robj,EXPERIMENTS[tx["experiment"]].get("template"),record_changes(tx["task_no"],rr["version"])),f'{tx["task_no"]}_V{rr["version"]}_原始记录表.docx')
  rp=report(cn)
  if rp:
   recs={}; 
   for t in ts:
    r=latest_record(t["task_no"])
    if r:recs[t["task_no"]]=r
   us={x["username"]:x for x in all_users()};sigs={u:(SIGDIR/signature(u)["image_name"] if signature(u) else None) for u in us}
   st.download_button("下载半成品/正式检验报告",report_doc(c,ss,ts,rp,recs,us,sigs),f"{cn}_检验报告.docx")
elif page=="报告中心":
 head("半成品报告与三级签署")
 rs=reports_for(role,username)
 if rs:
  st.dataframe(pd.DataFrame(rs),hide_index=True,use_container_width=True);rn=st.selectbox("报告",[x["report_no"] for x in rs]);r=report(rn);st.info("当前状态："+r["status"])
  if role in["实验人员","管理员"] and r["status"]=="待检测员签署":
   statement=st.text_area("样品情况说明");conclusion=st.text_area("检验结论");notes=st.text_area("报告说明")
   if st.button("检测员确认并签署"):sign_report(rn,"检测员",username,statement,conclusion,notes);st.rerun()
  if role in["复核实验员","管理员"] and r["status"]=="待核验" and st.button("核验通过并签署"):sign_report(rn,"核验员",username);st.rerun()
  if role in["批准人","管理员"] and r["status"]=="待批准" and st.button("批准并发布"):sign_report(rn,"批准人",username);st.rerun()
elif page=="签名中心":
 head("电子签名库")
 if role!="管理员":st.stop()
 u=st.selectbox("人员",[x["username"] for x in all_users()],format_func=lambda x:user_info(x)["display_name"]);f=st.file_uploader("上传签名PDF或PNG/JPG",type=["pdf","png","jpg","jpeg"])
 if f and st.button("保存签名"):
  raw=SIGDIR/(u+"_"+f.name);raw.write_bytes(f.getvalue());img=raw
  if f.type=="application/pdf":
   try:
    import fitz
    doc=fitz.open(raw);pix=doc[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=True);img=SIGDIR/(u+"_signature.png");pix.save(img)
   except Exception as e:st.error(str(e));st.stop()
  save_signature(u,raw.name,img.name);st.success("签名已保存")
elif page=="SOP与模板版本":
 head("SOP与实验原始记录表版本")
 if role!="管理员":st.stop()
 exp=st.selectbox("实验项目",list(EXPERIMENTS));typ=st.selectbox("文件类型",["SOP","原始记录表"]);ver=st.text_input("版本","A/1");f=st.file_uploader("上传DOCX",type=["docx"])
 if f and st.button("启用新版本"):
  name=f"{exp}_{typ}_{ver.replace('/','-')}.docx";(ROOT/"templates"/name).write_bytes(f.getvalue())
  with con() as c:c.execute("INSERT INTO template_versions(experiment,doc_type,file_name,version,effective_date,status,uploader,uploaded_at,note) VALUES(?,?,?,?,?,'现行',?,?,?)",(exp,typ,name,ver,str(china_today()),username,now(),""))
  st.success("已启用")
elif page=="用户与权限":
 head("用户与权限");st.dataframe(pd.DataFrame(all_users()),hide_index=True,use_container_width=True)
 u=st.text_input("用户名");n=st.text_input("姓名");p=st.text_input("密码",type="password");r=st.selectbox("角色",ROLES)
 if st.button("新增用户"):add_user(u,n,p,r);st.rerun()
elif page=="修改追踪":
 head("原始记录版本与修改追踪")
 allr=rows("SELECT record_no,version,owner,status,reason,created_at,updated_at FROM records ORDER BY record_no,version")
 st.dataframe(pd.DataFrame(allr),hide_index=True,use_container_width=True)
 if allr:
  rn=st.selectbox("记录编号",sorted(set(x["record_no"] for x in allr)));vs=record_versions(rn);ver=st.selectbox("版本",[x["version"] for x in vs]);chs=record_changes(rn,ver)
  if chs:st.dataframe(pd.DataFrame(chs),hide_index=True,use_container_width=True)
  else:st.info("该版本无字段修改或为首次版本")
elif page=="已删除样品":
 head("已删除样品");st.dataframe(pd.DataFrame(rows("SELECT * FROM samples WHERE is_deleted=1")),hide_index=True,use_container_width=True)
