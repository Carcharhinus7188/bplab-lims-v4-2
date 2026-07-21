# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime,timedelta,date
from zoneinfo import ZoneInfo
from pathlib import Path
import sqlite3,hashlib,secrets,json,re,calendar
ROOT=Path(__file__).parent;DB_PATH=ROOT/"data"/"bplab_trace.db";CHINA_TZ=ZoneInfo("Asia/Shanghai")
def china_now():return datetime.now(CHINA_TZ).replace(tzinfo=None)
def china_today():return china_now().date()
def now():return china_now().isoformat(timespec="seconds")
def add_months_to_date(v,m=1):
    if isinstance(v,str):v=date.fromisoformat(v)
    q=v.year*12+v.month-1+m;y,mi=divmod(q,12);mo=mi+1
    return v.replace(year=y,month=mo,day=min(v.day,calendar.monthrange(y,mo)[1]))
def phash(x):return hashlib.sha256(x.encode()).hexdigest()
def con():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(DB_PATH);c.row_factory=sqlite3.Row;return c
def init_db():
 with con() as c:
  c.executescript("""
CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,display_name TEXT,password_hash TEXT,role TEXT,enabled INTEGER,created_at TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,username TEXT,expires_at TEXT);
CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY,code TEXT UNIQUE,name TEXT UNIQUE,address TEXT,contact TEXT,phone TEXT,notes TEXT,enabled INTEGER,created_at TEXT);
CREATE TABLE IF NOT EXISTS sample_catalog(id INTEGER PRIMARY KEY,code TEXT UNIQUE,name TEXT,model TEXT,production_unit TEXT,category TEXT,unit TEXT,default_experiments TEXT,notes TEXT,enabled INTEGER,created_at TEXT);
CREATE TABLE IF NOT EXISTS commissions(commission_no TEXT PRIMARY KEY,customer_id INTEGER,customer_name TEXT,address TEXT,contact TEXT,phone TEXT,commission_date TEXT,condition TEXT,condition_note TEXT,subcontract TEXT,confidential TEXT,report_medium TEXT,conformity TEXT,uncertainty TEXT,delivery TEXT,cnas TEXT,capability TEXT,due_date TEXT,notes TEXT,created_by TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS samples(sample_no TEXT PRIMARY KEY,base_no TEXT,commission_no TEXT,catalog_id INTEGER,sample_name TEXT,model TEXT,product_no TEXT,production_unit TEXT,unit TEXT,condition TEXT,condition_note TEXT,location TEXT,status TEXT,owner TEXT,is_deleted INTEGER DEFAULT 0,deleted_by TEXT,deleted_at TEXT,delete_reason TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,sample_no TEXT,actor TEXT,action TEXT,from_status TEXT,to_status TEXT,from_location TEXT,to_location TEXT,details TEXT,created_at TEXT);
CREATE TABLE IF NOT EXISTS tasks(task_no TEXT PRIMARY KEY,commission_no TEXT,sample_no TEXT,experiment TEXT,standard TEXT,assignee TEXT,reviewer TEXT,status TEXT,assigned_by TEXT,assigned_at TEXT,notified_at TEXT,accepted_at TEXT,detection_location TEXT,acceptance_result TEXT,acceptance_note TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY,record_no TEXT,task_no TEXT,version INTEGER,owner TEXT,status TEXT,payload TEXT,reason TEXT,created_at TEXT,updated_at TEXT,UNIQUE(record_no,version));
CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY,record_no TEXT,version INTEGER,reviewer TEXT,decision TEXT,comment TEXT,reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS loans(id INTEGER PRIMARY KEY,task_no TEXT UNIQUE,sample_no TEXT,borrower TEXT,borrowed_at TEXT,purpose TEXT,detection_location TEXT,issue_note TEXT,returned_at TEXT,returned_by TEXT,return_condition TEXT,return_note TEXT,return_status TEXT,confirmed_by TEXT,confirmed_at TEXT,confirmed_location TEXT);
CREATE TABLE IF NOT EXISTS reports(report_no TEXT PRIMARY KEY,commission_no TEXT UNIQUE,status TEXT,tester TEXT,verifier TEXT,approver TEXT,tester_signed_at TEXT,verifier_signed_at TEXT,approver_signed_at TEXT,publish_date TEXT,sample_statement TEXT,conclusion TEXT,notes TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE IF NOT EXISTS signatures(username TEXT PRIMARY KEY,file_name TEXT,image_name TEXT,uploaded_at TEXT);
CREATE TABLE IF NOT EXISTS template_versions(id INTEGER PRIMARY KEY,experiment TEXT,doc_type TEXT,file_name TEXT,version TEXT,effective_date TEXT,status TEXT,uploader TEXT,uploaded_at TEXT,note TEXT);
""")
  users=[("admin","系统管理员","admin123","管理员"),("receiver","收样员王工","receive123","收样员"),("tester","实验员张工","test123","实验人员"),("reviewer","核验员李工","review123","复核实验员"),("store","样品管理员赵工","store123","样品管理员"),("approver","批准人刘工","approve123","批准人")]
  for u,n,p,r in users:c.execute("INSERT OR IGNORE INTO users VALUES(?,?,?,?,1,?)",(u,n,phash(p),r,now()))
  c.execute("INSERT OR IGNORE INTO customers(code,name,address,contact,phone,notes,enabled,created_at) VALUES('C-DEFAULT','默认客户','','','','入库默认预设',1,?)",(now(),))
  c.execute("INSERT OR IGNORE INTO sample_catalog(code,name,model,production_unit,category,unit,default_experiments,notes,enabled,created_at) VALUES('S-DEFAULT','默认样品','默认规格','','未分类','件','[]','入库默认预设',1,?)",(now(),))
def auth(u,p):
 with con() as c:r=c.execute("SELECT username,display_name,role FROM users WHERE username=? AND password_hash=? AND enabled=1",(u,phash(p))).fetchone()
 return dict(r) if r else None
def make_session(u):
 t=secrets.token_urlsafe(24)
 with con() as c:c.execute("INSERT INTO sessions VALUES(?,?,?)",(t,u,(china_now()+timedelta(days=7)).isoformat(timespec="seconds")))
 return t
def session_user(t):
 with con() as c:r=c.execute("SELECT u.username,u.display_name,u.role FROM sessions s JOIN users u ON u.username=s.username WHERE s.token=? AND s.expires_at>?",(t,now())).fetchone()
 return dict(r) if r else None
def rows(sql,args=()):
 with con() as c:return [dict(x) for x in c.execute(sql,args).fetchall()]
def one(sql,args=()):
 with con() as c:r=c.execute(sql,args).fetchone()
 return dict(r) if r else None
def next_no(prefix):
 d=china_now().strftime("%Y%m%d");p=f"{prefix}{d}"
 with con() as c:r=c.execute("SELECT commission_no FROM commissions WHERE commission_no LIKE ? ORDER BY commission_no DESC LIMIT 1",(p+"%",)).fetchone()
 return f"{p}{(int(r[0][-3:])+1 if r else 1):03d}"
def next_sample_no():
 d=china_now().strftime("%Y%m%d");p=f"BP{d}"
 with con() as c:
  vals=[x[0] for x in c.execute("SELECT base_no FROM samples WHERE base_no LIKE ?", (p+"%",)).fetchall()]
 n=max([int(re.search(r'(\d{3})$',v).group(1)) for v in vals if re.search(r'(\d{3})$',v)] or [0])+1
 return f"{p}{n:03d}"
def customers():return rows("SELECT * FROM customers WHERE enabled=1 ORDER BY name")
def catalogs():return rows("SELECT * FROM sample_catalog WHERE enabled=1 ORDER BY name,model")
def add_customer(code,name,address="",contact="",phone="",notes=""):
 with con() as c:c.execute("INSERT INTO customers(code,name,address,contact,phone,notes,enabled,created_at) VALUES(?,?,?,?,?,?,1,?)",(code or None,name,address,contact,phone,notes,now()))
def add_catalog(code,name,model,production_unit="",category="",unit="件",defaults=None,notes=""):
 with con() as c:c.execute("INSERT INTO sample_catalog(code,name,model,production_unit,category,unit,default_experiments,notes,enabled,created_at) VALUES(?,?,?,?,?,?,?,?,1,?)",(code or None,name,model,production_unit,category,unit,json.dumps(defaults or [],ensure_ascii=False),notes,now()))
def add_event(sn,actor,action,fs,ts,fl,tl,details=""):
 with con() as c:c.execute("INSERT INTO events(sample_no,actor,action,from_status,to_status,from_location,to_location,details,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(sn,actor,action,fs,ts,fl,tl,details,now()))
def create_intake(d,experiments,actor):
 commission=d["commission_no"];base=d["base_no"].strip().upper().replace(" ","");qty=int(d["qty"])
 sns=[base] if qty==1 else [f"{base}-{i}" for i in range(1,qty+1)]
 with con() as c:
  c.execute("INSERT INTO commissions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(commission,d["customer_id"],d["customer_name"],d["address"],d["contact"],d["phone"],d["commission_date"],d["condition"],d["condition_note"],d["subcontract"],d["confidential"],d["report_medium"],d["conformity"],d["uncertainty"],d["delivery"],d["cnas"],d["capability"],d["due_date"],d["notes"],actor,now()))
  for sn in sns:
   c.execute("INSERT INTO samples(sample_no,base_no,commission_no,catalog_id,sample_name,model,product_no,production_unit,unit,condition,condition_note,location,status,owner,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(sn,base,commission,d["catalog_id"],d["sample_name"],d["model"],d["product_no"],d["production_unit"],d["unit"],d["condition"],d["condition_note"],d["storage"],"待分配",actor,now(),now()))
   for j,e in enumerate(experiments,1):
    tn=f"{sn}-T{j:02d}";std=d["standards"].get(e,"")
    c.execute("INSERT INTO tasks(task_no,commission_no,sample_no,experiment,standard,status,created_at,updated_at) VALUES(?,?,?,?,?,'待分配',?,?)",(tn,commission,sn,e,std,now(),now()))
 for sn in sns:add_event(sn,actor,"样品入库","","待分配","",d["storage"],f"委托单:{commission};状态:{d['condition']}")
 return sns
def samples(include_deleted=False):return rows("SELECT * FROM samples WHERE is_deleted=? ORDER BY updated_at DESC",(0 if not include_deleted else 1,))
def sample(sn):return one("SELECT * FROM samples WHERE sample_no=?",(sn,))
def events(sn):return rows("SELECT * FROM events WHERE sample_no=? ORDER BY id",(sn,))
def tasks(statuses=None,assignee=None,reviewer=None):
 q="SELECT t.*,s.sample_name,s.model,s.location,s.status sample_status FROM tasks t JOIN samples s ON s.sample_no=t.sample_no WHERE s.is_deleted=0";a=[]
 if statuses:q+=" AND t.status IN ("+",".join("?"*len(statuses))+")";a+=statuses
 if assignee is not None:q+=" AND t.assignee=?";a.append(assignee)
 if reviewer is not None:q+=" AND t.reviewer=?";a.append(reviewer)
 return rows(q+" ORDER BY t.updated_at DESC",a)
def task(tn):return one("SELECT * FROM tasks WHERE task_no=?",(tn,))
def assign(tn,a,r,actor):
 t=task(tn);ts=now()
 with con() as c:c.execute("UPDATE tasks SET assignee=?,reviewer=?,status='待接收',assigned_by=?,assigned_at=?,notified_at=?,updated_at=? WHERE task_no=?",(a,r,actor,ts,ts,ts,tn))
 s=sample(t["sample_no"]);add_event(t["sample_no"],actor,"任务下发",s["status"],"等待实验员接收",s["location"],s["location"],f"{tn};实验员:{a}")
def accept(tn,actor,result,location,note):
 t=task(tn);s=sample(t["sample_no"]);ts=now();ok=result=="样品已收到，确认完好";st="检测中" if ok else "接收异常"
 with con() as c:
  c.execute("UPDATE tasks SET status=?,accepted_at=?,detection_location=?,acceptance_result=?,acceptance_note=?,updated_at=? WHERE task_no=?",(st,ts,location,result,note,ts,tn))
  if ok:
   c.execute("INSERT OR REPLACE INTO loans(task_no,sample_no,borrower,borrowed_at,purpose,detection_location,issue_note,return_status) VALUES(?,?,?,?,?,?,?,'未归还')",(tn,t["sample_no"],actor,ts,t["experiment"],location,note))
   c.execute("UPDATE samples SET status='检测中',location=?,owner=?,updated_at=? WHERE sample_no=?",(location,actor,ts,t["sample_no"]))
 add_event(t["sample_no"],actor,"实验员领用",s["status"],st,s["location"],location,f"{result};{note}")
def latest_record(tn):
 r=one("SELECT * FROM records WHERE task_no=? ORDER BY version DESC LIMIT 1",(tn,))
 if r:r["payload"]=json.loads(r["payload"])
 return r
def save_record(tn,version,payload,owner,status,reason=""):
 ts=now()
 with con() as c:c.execute("INSERT OR REPLACE INTO records(record_no,task_no,version,owner,status,payload,reason,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(tn,tn,version,owner,status,json.dumps(payload,ensure_ascii=False,default=str),reason,ts,ts))
def pending_reviews(user=None):
 q="SELECT r.*,t.experiment,t.sample_no FROM records r JOIN tasks t ON t.task_no=r.task_no WHERE r.status IN('待复核','更正待复核')";a=[]
 if user:q+=" AND t.reviewer=?";a.append(user)
 z=rows(q,a)
 for x in z:x["payload"]=json.loads(x["payload"])
 return z
def review(tn,v,user,decision,comment):
 st="已锁定" if decision=="通过" else "退回修改";ts=now()
 with con() as c:
  c.execute("UPDATE records SET status=?,updated_at=? WHERE record_no=? AND version=?",(st,ts,tn,v))
  c.execute("INSERT INTO reviews(record_no,version,reviewer,decision,comment,reviewed_at) VALUES(?,?,?,?,?,?)",(tn,v,user,decision,comment,ts))
  c.execute("UPDATE tasks SET status=?,updated_at=? WHERE task_no=?",("已完成" if decision=="通过" else "退回修改",ts,tn))
 t=task(tn);s=sample(t["sample_no"]);add_event(s["sample_no"],user,"原始记录复核"+decision,s["status"],s["status"],s["location"],s["location"],tn)
 if decision=="通过":ensure_report(t["commission_no"])
def ensure_report(cn):
 pending=one("SELECT COUNT(*) n FROM tasks WHERE commission_no=? AND status!='已完成'",(cn,))["n"]
 if pending==0:
  ts=now();t=one("SELECT assignee,reviewer FROM tasks WHERE commission_no=? ORDER BY task_no LIMIT 1",(cn,))
  with con() as c:c.execute("INSERT OR IGNORE INTO reports(report_no,commission_no,status,tester,verifier,approver,created_at,updated_at) VALUES(?,?,'待检测员签署',?,?, 'approver',?,?)",(cn,cn,t["assignee"],t["reviewer"],ts,ts))
def return_candidates(user):return rows("SELECT l.*,t.experiment FROM loans l JOIN tasks t ON t.task_no=l.task_no WHERE l.borrower=? AND t.status='已完成' AND l.return_status='未归还'",(user,))
def submit_return(tn,user,condition,note):
 l=one("SELECT * FROM loans WHERE task_no=?",(tn,));s=sample(l["sample_no"]);ts=now()
 with con() as c:
  c.execute("UPDATE loans SET returned_at=?,returned_by=?,return_condition=?,return_note=?,return_status='待回库确认' WHERE task_no=?",(ts,user,condition,note,tn))
  c.execute("UPDATE samples SET status='待回库确认',location='回库交接区',owner='',updated_at=? WHERE sample_no=?",(ts,l["sample_no"]))
 add_event(l["sample_no"],user,"样品归还",s["status"],"待回库确认",s["location"],"回库交接区",condition+";"+note)
def pending_returns():return rows("SELECT l.*,t.experiment FROM loans l JOIN tasks t ON t.task_no=l.task_no WHERE l.return_status='待回库确认'")
def confirm_return(tn,user,loc):
 l=one("SELECT * FROM loans WHERE task_no=?",(tn,));s=sample(l["sample_no"]);ts=now()
 with con() as c:
  c.execute("UPDATE loans SET return_status='已回库',confirmed_by=?,confirmed_at=?,confirmed_location=? WHERE task_no=?",(user,ts,loc,tn))
  c.execute("UPDATE samples SET status='留样保存',location=?,owner=?,updated_at=? WHERE sample_no=?",(loc,user,ts,l["sample_no"]))
 add_event(l["sample_no"],user,"回库确认",s["status"],"留样保存",s["location"],loc,tn)
def commissions():return rows("SELECT * FROM commissions ORDER BY created_at DESC")
def commission(cn):return one("SELECT * FROM commissions WHERE commission_no=?",(cn,))
def commission_samples(cn):return rows("SELECT * FROM samples WHERE commission_no=? AND is_deleted=0 ORDER BY sample_no",(cn,))
def commission_tasks(cn):return rows("SELECT * FROM tasks WHERE commission_no=? ORDER BY task_no",(cn,))
def loans_by_commission(cn):return rows("SELECT l.*,t.commission_no,t.experiment FROM loans l JOIN tasks t ON t.task_no=l.task_no WHERE t.commission_no=? ORDER BY l.borrowed_at",(cn,))
def report(rn):return one("SELECT * FROM reports WHERE report_no=?",(rn,))
def reports_for(role,user):
 if role=="实验人员":return rows("SELECT * FROM reports WHERE tester=? ORDER BY updated_at DESC",(user,))
 if role=="复核实验员":return rows("SELECT * FROM reports WHERE verifier=? ORDER BY updated_at DESC",(user,))
 if role=="批准人":return rows("SELECT * FROM reports WHERE approver=? ORDER BY updated_at DESC",(user,))
 return rows("SELECT * FROM reports ORDER BY updated_at DESC")
def sign_report(rn,stage,user,sample_statement="",conclusion="",notes=""):
 r=report(rn);ts=now()
 with con() as c:
  if stage=="检测员":
   c.execute("UPDATE reports SET status='待核验',tester_signed_at=?,sample_statement=?,conclusion=?,notes=?,updated_at=? WHERE report_no=?",(ts,sample_statement,conclusion,notes,ts,rn))
  elif stage=="核验员":c.execute("UPDATE reports SET status='待批准',verifier_signed_at=?,updated_at=? WHERE report_no=?",(ts,ts,rn))
  elif stage=="批准人":c.execute("UPDATE reports SET status='已发布',approver_signed_at=?,publish_date=?,updated_at=? WHERE report_no=?",(ts,str(china_today()),ts,rn))
def user_info(u):return one("SELECT username,display_name,role FROM users WHERE username=?",(u,))
def all_users():return rows("SELECT username,display_name,role,enabled,created_at FROM users ORDER BY username")
def add_user(u,n,p,r):
 with con() as c:c.execute("INSERT INTO users VALUES(?,?,?,?,1,?)",(u,n,phash(p),r,now()))
def save_signature(u,file_name,image_name):
 with con() as c:c.execute("INSERT OR REPLACE INTO signatures VALUES(?,?,?,?)",(u,file_name,image_name,now()))
def signature(u):return one("SELECT * FROM signatures WHERE username=?",(u,))
def soft_delete(sn,user,reason):
 s=sample(sn)
 if one("SELECT COUNT(*) n FROM tasks WHERE sample_no=? AND status NOT IN('待分配','待接收')",(sn,))["n"]:raise ValueError("已领用或已有检测记录，不能删除")
 with con() as c:
  c.execute("UPDATE samples SET is_deleted=1,deleted_by=?,deleted_at=?,delete_reason=? WHERE sample_no=?",(user,now(),reason,sn))
  c.execute("DELETE FROM tasks WHERE sample_no=?",(sn,))

def record_versions(tn):
 z=rows("SELECT * FROM records WHERE record_no=? ORDER BY version",(tn,))
 for x in z:x["payload"]=json.loads(x["payload"])
 return z

def _flat(v,p=""):
 out={}
 if isinstance(v,dict):
  for k,x in v.items():out.update(_flat(x,f"{p}.{k}" if p else k))
 elif isinstance(v,list):
  for i,x in enumerate(v):out.update(_flat(x,f"{p}[{i}]"))
 else:out[p]=v
 return out

def record_changes(tn,version):
 vs=record_versions(tn)
 cur=next((x for x in vs if x["version"]==version),None)
 prev=next((x for x in vs if x["version"]==version-1),None)
 if not cur or not prev:return []
 a,b=_flat(prev["payload"]),_flat(cur["payload"]);out=[]
 for k in sorted(set(a)|set(b)):
  if str(a.get(k,""))!=str(b.get(k,"")):out.append({"action":"字段修改","field_name":k,"old_value":str(a.get(k,"")),"new_value":str(b.get(k,"")),"reason":cur.get("reason","")})
 return out
