# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import date
from pathlib import Path
import hashlib,json,re
import pandas as pd
import streamlit as st
from constants import *
from lims_db import *
from experiment_engine import initial_dataframe_for_samples,calculate
from record_word_engine import export_record
from form_engine import commission_document,sample_register_document,loan_return_document,report_document
ROOT=Path(__file__).parent;SIG=ROOT/'data'/'signatures';SIG.mkdir(parents=True,exist_ok=True)
st.set_page_config(page_title='BPLab Trace',page_icon='🧪',layout='wide')
st.markdown('''<style>.block-container{max-width:1580px;padding-top:1rem}.hero{background:linear-gradient(135deg,#12364a,#176b87);color:white;padding:24px;border-radius:20px;margin-bottom:18px}.card{background:white;border:1px solid #dce7ee;border-radius:15px;padding:16px}[data-testid="stSidebar"]{background:#12364a}[data-testid="stSidebar"] *{color:white}.timeline{border-left:5px solid #176b87;background:white;padding:12px;margin:8px 0;border-radius:10px}</style>''',unsafe_allow_html=True)
def header(x):st.markdown(f'<div class="hero"><h2>{COMPANY_CN}</h2><div>{COMPANY_EN}</div><h3>{x}</h3><small>{APP_VERSION}｜北京时间 {TIMEZONE_NAME}（UTC+8）</small></div>',unsafe_allow_html=True)
def df(rows,cols=None):
 if not rows:return st.info('暂无数据')
 d=pd.DataFrame(rows);st.dataframe(d[[c for c in (cols or d.columns) if c in d.columns]],hide_index=True,use_container_width=True)
def usernames(role=None):return [u for u in users() if (not role or u['role']==role) and u['enabled']]
def uname(u):
 x=next((v for v in users() if v['username']==u),None);return x['display_name'] if x else u
init_db()
for exp,cfg in EXPERIMENTS.items():seed_template(exp,'原始记录表',cfg.get('template'));seed_template(exp,'SOP',cfg.get('sop'))
if 'user' not in st.session_state:
 u=session_user(st.query_params.get('session',''))
 if u:st.session_state.user=u
if 'user' not in st.session_state:
 header('系统登录');a,b,c=st.columns([1,1.2,1])
 with b:
  user=st.text_input('用户名');pwd=st.text_input('密码',type='password')
  if st.button('登录',type='primary',use_container_width=True):
   u=authenticate(user,pwd)
   if u:st.session_state.user=u;st.query_params['session']=create_session(user);st.rerun()
   else:st.error('用户名或密码错误')
  st.caption('admin/admin123｜receiver/receive123｜tester/test123｜reviewer/review123｜store/store123｜approver/approve123')
 st.stop()
user=st.session_state.user;role=user['role'];username=user['username']
with st.sidebar:
 st.title('BPLab Trace');st.write(user['display_name']);st.caption(role);page=st.radio('导航',ROLE_MENUS[role],label_visibility='collapsed')
 if st.button('退出登录',use_container_width=True):delete_session(st.query_params.get('session',''));st.session_state.clear();st.query_params.clear();st.rerun()
if page=='首页看板':
 header('样品全过程状态看板');c=dashboard_counts();cols=st.columns(6)
 for col,(k,n) in zip(cols,[('在册样品',c['samples']),('待接收任务',c['pending_tasks']),('检测中',c['testing']),('待复核',c['reviews']),('待回库',c['returns']),('待发布报告',c['reports'])]):col.metric(k,n)
 df(list_samples(),['sample_no','commission_no','sample_name','model','status','current_location','current_holder','updated_at'])
elif page=='基础资料':
 header('客户与样品名称基础资料')
 if role not in ['管理员','收样员']:st.stop()
 t1,t2=st.tabs(['客户信息','样品名称/规格型号'])
 with t1:
  df(list_customers(True));a,b,c=st.columns(3);code=a.text_input('客户编号');name=b.text_input('客户名称');short=c.text_input('简称');addr=a.text_input('地址');contact=b.text_input('联系人');phone=c.text_input('电话');note=st.text_area('备注')
  if st.button('保存客户',type='primary'):
   try:add_customer(code,name,short,addr,contact,phone,note);st.rerun()
   except Exception as e:st.error(str(e))
 with t2:
  df(list_sample_catalog(True));a,b,c=st.columns(3);code=a.text_input('样品资料编号');name=b.text_input('样品名称');model=c.text_input('规格型号');prod=a.text_input('生产单位');cat=b.text_input('类别');unit=c.text_input('单位',value='件');defaults=st.multiselect('默认检测项目',list(EXPERIMENTS));note=st.text_area('样品资料备注')
  if st.button('保存样品名称',type='primary'):
   try:add_sample_catalog(code,name,model,prod,cat,unit,defaults,note);st.rerun()
   except Exception as e:st.error(str(e))
elif page=='检验委托与入库':
 header('新建检验委托单并完成样品入库');cs=list_customers();cats=list_sample_catalog()
 ci=st.selectbox('委托客户',range(len(cs)),format_func=lambda i:cs[i]['name']);ca=cs[ci];si=st.selectbox('样品名称/规格型号',range(len(cats)),format_func=lambda i:f"{cats[i]['name']}｜{cats[i]['model']}");sc=cats[si]
 a,b,c=st.columns(3);commission_no=a.text_input('检验委托单编号（暂行规则）',value=next_commission_no());base=b.text_input('样品基础编号',value=next_sample_base());qty=int(c.number_input('接收数量',1,100,1));preview=[base] if qty==1 else[f'{base}-{i}' for i in range(1,qty+1)];st.info('将生成：'+'、'.join(preview))
 product_no=a.text_input('产品编号/批号');storage=b.selectbox('入库区域',STORAGE_AREAS);condition=c.selectbox('样品状态',SAMPLE_CONDITIONS);condition_note=st.text_input('样品状态备注');received=a.date_input('委托/接收日期',china_today());due=b.date_input('计划完成日期',add_months_to_date(received,1));experiments=st.multiselect('检测项目',list(EXPERIMENTS),default=sc['default_experiments_list'])
 st.subheader('委托及报告要求');sub=a.selectbox('允许分包',['否','是']);secret=b.selectbox('保密要求',['无要求','是']);medium=c.multiselect('报告载体',['纸质','电子档'],default=['电子档']);conform=a.selectbox('符合性判定',['是','否']);unc=b.selectbox('考虑不确定度',['否','是']);delivery=c.selectbox('递送方式',['Email','自取','快递']);cnas=a.selectbox('加盖CNAS章',['否','是']);cap=b.selectbox('检测能力',['完全满足','部分满足','不满足']);notes=st.text_area('委托备注')
 if st.button('生成委托单、样品登记并入库',type='primary',use_container_width=True):
  data={'commission_no':commission_no,'base_no':base,'qty':qty,'customer_id':ca['id'],'customer_name':ca['name'],'customer_address':ca['address'],'contact':ca['contact'],'phone':ca['phone'],'commission_date':received,'due_date':due,'condition':condition,'condition_note':condition_note,'subcontract_allowed':sub,'confidentiality':secret,'report_medium':'、'.join(medium),'conformity_judgment':conform,'uncertainty':unc,'delivery_method':delivery,'cnas_mark':cnas,'capability':cap,'notes':notes,'sample_catalog_id':sc['id'],'sample_name':sc['name'],'model':sc['model'],'product_no':product_no,'production_unit':sc['production_unit'],'unit':sc['unit'],'storage_area':storage}
  try:create_commission_and_samples(data,experiments,username);st.success('入库完成，检验委托单和样品登记表已可在单据中心下载');st.rerun()
  except Exception as e:st.error(str(e))
elif page=='样品全流程':
 header('样品全过程追溯');ss=list_samples()
 if ss:
  sn=st.selectbox('样品编号',[x['sample_no'] for x in ss]);s=sample(sn);a,b,c,d=st.columns(4);a.metric('状态',s['status']);b.metric('位置',s['current_location']);c.metric('持有人',s['current_holder'] or '—');d.metric('委托单',s['commission_no']);df(sample_events(sn),['created_at','action','actor','from_status','to_status','from_location','to_location','details'])
  if role in ['管理员','收样员']:
   reason=st.text_input('错误入库删除原因');
   if st.button('删除错误入库记录'):
    try:soft_delete_sample(sn,username,reason);st.rerun()
    except Exception as e:st.error(str(e))
elif page=='任务分配':
 header('检测任务分配');items=pending_test_items();df(items,['id','commission_no','customer_name','experiment','standard','due_date'])
 if items:
  iid=st.selectbox('待分配检测项目',[x['id'] for x in items],format_func=lambda i:next(f"{x['commission_no']}｜{x['experiment']}" for x in items if x['id']==i));it=next(x for x in items if x['id']==iid);ss=commission_samples(it['commission_no']);sns=st.multiselect('选择本任务使用的样品',[x['sample_no'] for x in ss],default=[x['sample_no'] for x in ss]);tests=usernames('实验人员');revs=usernames('复核实验员');a=st.selectbox('实验员',[x['username'] for x in tests],format_func=uname);r=st.selectbox('复核实验员',[x['username'] for x in revs],format_func=uname)
  if st.button('下发任务并生成提醒',type='primary'):
   try:tn=assign_test_item(iid,sns,a,r,username);st.success('已下发：'+tn);st.rerun()
   except Exception as e:st.error(str(e))
elif page=='我的检测任务':
 header('任务提醒与样品领用');n=pending_task_count(username)
 if n:st.warning(f'🔔 有 {n} 个任务等待接收')
 ts=list_tasks(assignee=username);df(ts,['task_no','commission_no','sample_nos','experiment','status','assigned_at','notified_at','accepted_at','detection_location'])
 if ts:
  tn=st.selectbox('任务编号',[x['task_no'] for x in ts]);t=task(tn)
  if t['status']=='待接收':
   result=st.radio('接收确认',['样品已收到，确认完好','样品已收到，但存在异常','尚未收到样品']);loc0=st.selectbox('检测位置（由实验员决定）',DETECTION_LOCATIONS);loc=st.text_input('其他检测位置') if loc0=='其他' else loc0;note=st.text_area('领用/异常备注')
   if st.button('确认领用',type='primary'):
    try:accept_task(tn,username,result,loc,note);st.rerun()
    except Exception as e:st.error(str(e))
  elif t['status']=='接收异常':st.error(t.get('acceptance_note') or '样品接收异常')
  elif t['status'] in ['检测中','退回修改']:st.success('可进入“实验记录”填写')
elif page=='实验记录':
 header('受控实验原始记录');av=list_tasks(assignee=username) if role!='管理员' else list_tasks();av=[x for x in av if x['status'] in ['检测中','退回修改','待复核','已完成']]
 if av:
  tn=st.selectbox('任务/原始记录/复核编号',[x['task_no'] for x in av]);t=task(tn);latest=latest_record_by_task(tn)
  if latest and latest['status'] in ['待复核','更正待复核']:st.warning('记录正在复核，不能继续编辑');st.stop()
  if latest and latest['status']=='已锁定':st.warning('记录已锁定；需修改请进入“修改追踪”创建新版本');st.stop()
  version=latest['version'] if latest else 1;prior=latest['payload'] if latest else {};compare=record_versions(tn)[-2]['payload'] if version>1 and len(record_versions(tn))>1 else None;cfg=EXPERIMENTS[t['experiment']];samples0=task_samples(tn);sample_ids=[x['sample_no'] for x in samples0];c0=commission(t['commission_no']);common0=prior.get('common',{})
  st.info(f'统一编号：{tn}｜V{version}｜样品：'+ '、'.join(sample_ids));tabs=st.tabs(['样品信息','环境设备','过程确认','原始数据','保存提交'])
  with tabs[0]:material=st.text_input('材料名称',common0.get('material',''));test_date=st.date_input('检测日期',date.fromisoformat(common0['test_date']) if common0.get('test_date') else china_today())
  with tabs[1]:
   a,b,c=st.columns(3);temp=a.number_input('温度℃',value=float(common0.get('temperature',23)));hum=b.number_input('相对湿度%RH',value=float(common0.get('humidity',50)));equipment=c.text_input('设备名称/编号',common0.get('equipment',''));equipment_model=a.text_input('设备型号规格',common0.get('equipment_model',''));cal=b.text_input('校准证书编号',common0.get('calibration',''));cal_due=c.text_input('校准有效期至',common0.get('calibration_due',''));software=a.text_input('软件/版本',common0.get('software',''));data_path=b.text_input('数据保存路径',common0.get('data_path',''))
  with tabs[2]:checks={x:st.checkbox(x,value=prior.get('checks',{}).get(x,False)) for x in CHECK_ITEMS[cfg['kind']]};deviation=st.text_area('异常/偏离说明',prior.get('deviation',''))
  with tabs[3]:src=pd.DataFrame(prior['data']) if prior.get('data') else initial_dataframe_for_samples(cfg['kind'],sample_ids);edited=st.data_editor(src,use_container_width=True,num_rows='fixed',key=f'{tn}-{version}');result=calculate(cfg['kind'],edited);st.dataframe(result,hide_index=True,use_container_width=True)
  with tabs[4]:
   reason=st.text_area('修改原因（首次记录可不填）',latest.get('change_reason','') if latest else '');tm=active_version(t['experiment'],'原始记录表');sm=active_version(t['experiment'],'SOP');payload={'common':{'record_no':tn,'task_no':tn,'report_no':t['commission_no'],'client':c0['customer_name'],'sample_name':'、'.join(dict.fromkeys(x['sample_name'] for x in samples0)),'sample_no':'、'.join(sample_ids),'model':'、'.join(dict.fromkeys(x['model'] for x in samples0)),'material':material,'test_date':str(test_date),'location':t['detection_location'],'temperature':temp,'humidity':hum,'equipment':equipment,'equipment_model':equipment_model,'calibration':cal,'calibration_due':cal_due,'software':software,'data_path':data_path,'operator':user['display_name'],'reviewer':uname(t['reviewer'])},'checks':checks,'deviation':deviation,'data':result.to_dict('records')};a,b=st.columns(2)
   if a.button('保存草稿',use_container_width=True):save_record(tn,version,payload,username,'草稿',tm['version'] if tm else 'A/0',sm['version'] if sm else 'A/0',reason,compare);st.success('已保存')
   if b.button('提交复核',type='primary',use_container_width=True):save_record(tn,version,payload,username,'更正待复核' if version>1 else '待复核',tm['version'] if tm else 'A/0',sm['version'] if sm else 'A/0',reason,compare);st.rerun()
elif page=='原始记录复核':
 header('原始记录复核');rs=pending_reviews(None if role=='管理员' else username);df(rs,['record_no','version','commission_no','sample_nos','experiment','owner','status','updated_at'])
 if rs:
  key=st.selectbox('记录',[f"{x['record_no']}|{x['version']}" for x in rs]);rn,v=key.split('|');r=record(rn,int(v));st.dataframe(pd.DataFrame(r['payload']['data']),hide_index=True,use_container_width=True);comment=st.text_area('复核意见');a,b=st.columns(2)
  if a.button('通过并锁定',type='primary'):review_record(rn,int(v),username,'通过',comment);st.rerun()
  if b.button('退回修改'):review_record(rn,int(v),username,'退回',comment);st.rerun()
elif page=='样品归还':
 header('实验员样品归还');rs=return_candidates(username);df(rs)
 if rs:
  tn=st.selectbox('待归还任务',[x['task_no'] for x in rs]);loans=task_loan_rows(tn);ed=pd.DataFrame([{'样品编号':x['sample_no'],'归还状态':'完好','归还备注':''} for x in loans]);ed=st.data_editor(ed,hide_index=True,use_container_width=True,column_config={'归还状态':st.column_config.SelectboxColumn(options=RETURN_CONDITIONS),'样品编号':st.column_config.TextColumn(disabled=True)})
  if st.button('提交归还',type='primary'):submit_return(tn,username,[{'sample_no':r['样品编号'],'condition':r['归还状态'],'note':r['归还备注']} for _,r in ed.iterrows()]);st.rerun()
elif page=='回库确认':
 header('样品回库确认');rs=pending_return_tasks();df(rs)
 if rs:
  tn=st.selectbox('待回库任务',[x['task_no'] for x in rs]);loans=task_loan_rows(tn);ed=pd.DataFrame([{'样品编号':x['sample_no'],'归还状态':x['return_condition'],'回库位置':'A区域'} for x in loans if x['return_status']=='待回库确认']);ed=st.data_editor(ed,hide_index=True,use_container_width=True,column_config={'样品编号':st.column_config.TextColumn(disabled=True),'归还状态':st.column_config.TextColumn(disabled=True),'回库位置':st.column_config.SelectboxColumn(options=STORAGE_AREAS)})
  if st.button('确认回库',type='primary'):confirm_return(tn,username,[{'sample_no':r['样品编号'],'location':r['回库位置']} for _,r in ed.iterrows()]);st.rerun()
elif page=='单据中心':
 header('受控单据中心');cs=list_commissions();df(cs,['commission_no','customer_name','commission_date','due_date','status'])
 if cs:
  cn=st.selectbox('检验委托单',[x['commission_no'] for x in cs]);c0=commission(cn);ss=commission_samples(cn);tests=commission_tests(cn);receiver=uname(c0['created_by']);us={x['username']:x['display_name'] for x in users()};st.download_button('下载检验委托单',commission_document(c0,ss,tests,receiver),f'{cn}_commission.docx');st.download_button('下载样品登记表',sample_register_document(c0,ss,tests,receiver),f'{cn}_sample_register.docx');st.download_button('下载样品领用归还登记表',loan_return_document(commission_loans(cn),us),f'{cn}_loan_return.docx')
  recs=[]
  for tx in commission_tasks(cn):recs.extend([r for r in record_versions(tx['task_no']) if r['status']=='已锁定'])
  if recs:
   k=st.selectbox('原始记录版本',[f"{r['record_no']}|{r['version']}" for r in recs]);rn,v=k.split('|');r=record(rn,int(v));meta=template_for_version(r['experiment'],'原始记录表',r.get('template_version'));changes=[x for x in audit_logs(rn,int(v)) if x['action']=='字段修改'];st.download_button('下载选定原始记录',export_record(r,meta['file_name'] if meta else EXPERIMENTS[r['experiment']]['template'],changes),f'{rn}_V{v}.docx')
  rp=report(cn)
  if rp:
   sigs={u:signature(u) for u in us};st.download_button('下载当前检验报告',report_document(c0,ss,commission_tasks(cn),report_records(cn),rp,us,sigs),f'{cn}_report.docx')
elif page=='报告中心':
 header('半成品报告与分级签署');rs=list_reports(role,username);df(rs,['report_no','commission_no','status','tester','verifier','approver','updated_at'])
 if rs:
  rn=st.selectbox('报告编号',[x['report_no'] for x in rs]);r=report(rn);st.info('当前状态：'+r['status'])
  if role=='管理员':
   tests=usernames('实验人员');revs=usernames('复核实验员');apps=usernames('批准人');a=st.selectbox('检测员',[x['username'] for x in tests],index=next((i for i,x in enumerate(tests) if x['username']==r['tester']),0),format_func=uname);v=st.selectbox('核验员',[x['username'] for x in revs],index=next((i for i,x in enumerate(revs) if x['username']==r['verifier']),0),format_func=uname);p=st.selectbox('批准人',[x['username'] for x in apps],index=next((i for i,x in enumerate(apps) if x['username']==r['approver']),0),format_func=uname)
   if st.button('保存签署人员'):update_report_roles(rn,a,v,p,username);st.rerun()
  if r['status']=='待检测员确认' and username==r['tester']:
   cat=st.text_input('检验类别',r.get('report_category') or '委托检验');statement=st.text_area('样品情况说明',r.get('sample_statement') or '');conclusion=st.text_area('检验结论',r.get('conclusion') or '');notes=st.text_area('需说明情况',r.get('notes') or '')
   if st.button('检测员确认并签署',type='primary'):tester_submit_report(rn,username,cat,statement,conclusion,notes);st.rerun()
  if r['status']=='待核验' and username==r['verifier']:
   comment=st.text_area('核验意见');a,b=st.columns(2)
   if a.button('核验通过',type='primary'):verifier_review_report(rn,username,'通过',comment);st.rerun()
   if b.button('退回检测员'):verifier_review_report(rn,username,'退回',comment);st.rerun()
  if r['status']=='待批准' and username==r['approver']:
   comment=st.text_area('批准意见');a,b=st.columns(2)
   if a.button('批准发布',type='primary'):approver_review_report(rn,username,'批准',comment);st.rerun()
   if b.button('退回检测员'):approver_review_report(rn,username,'退回',comment);st.rerun()
  df(report_actions(rn))
elif page=='修改追踪':
 header('原始记录修改追踪');rows0=latest_records();df(rows0,['record_no','version','experiment','owner','status','updated_at'])
 if rows0:
  rn=st.selectbox('记录编号',[x['record_no'] for x in rows0]);vs=record_versions(rn);df(vs,['record_no','version','owner','status','change_reason','created_at','updated_at']);v=st.selectbox('版本',[x['version'] for x in vs]);df(audit_logs(rn,v),['field_name','old_value','new_value','reason','actor','created_at']);reason=st.text_area('创建新修改版的原因')
  if role in ['管理员','实验人员'] and st.button('创建修改版'):
   try:create_revision(rn,username,reason);st.success('已创建新版本，请到实验记录修改');st.rerun()
   except Exception as e:st.error(str(e))
elif page=='已删除样品':header('已删除样品');df(list_samples(True))
elif page=='SOP与模板版本':
 header('SOP与实验原始记录表版本管理')
 if role!='管理员':st.stop()
 df(all_template_versions());exp=st.selectbox('实验项目',list(EXPERIMENTS));typ=st.selectbox('文件类型',['SOP','原始记录表']);ver=st.text_input('版本号','A/1');eff=st.date_input('生效日期',china_today());note=st.text_input('变更说明');f=st.file_uploader('上传DOCX',type=['docx'])
 if f and st.button('批准并启用',type='primary'):
  name=f"TPL_{hashlib.sha1((exp+typ+ver+f.name).encode()).hexdigest()[:12]}.docx";(ROOT/'templates'/name).write_bytes(f.getvalue());add_template(exp,typ,name,ver,str(eff),username,note);st.rerun()
elif page=='电子签名':
 header('电子签名库')
 if role!='管理员':st.stop()
 us=users();u=st.selectbox('签名人员',[x['username'] for x in us],format_func=uname);f=st.file_uploader('上传PDF、PNG或JPG',type=['pdf','png','jpg','jpeg'])
 if f and st.button('保存签名',type='primary'):
  ext=Path(f.name).suffix.lower();src=SIG/f'{u}_source{ext}';src.write_bytes(f.getvalue());image=None
  if ext=='.pdf':
   try:
    import fitz;doc=fitz.open(src);pix=doc[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=True);image=SIG/f'{u}_signature.png';pix.save(image)
   except Exception as e:st.error('PDF转换失败：'+str(e));st.stop()
  else:image=SIG/f'{u}_signature{ext}';image.write_bytes(f.getvalue())
  save_signature(u,src.name,image.name if image else None,username);st.success('签名已保存')
 df([{**x,'签名状态':'已配置' if signature(x['username']) else '未配置'} for x in us],['username','display_name','role','签名状态'])
elif page=='用户与权限':
 header('用户与权限');df(users());a,b=st.columns(2);u=a.text_input('用户名');n=b.text_input('姓名');p=a.text_input('初始密码',type='password');r=b.selectbox('角色',ROLES)
 if st.button('创建账号',type='primary'):
  try:add_user(u,n,p,r);st.rerun()
  except Exception as e:st.error(str(e))
