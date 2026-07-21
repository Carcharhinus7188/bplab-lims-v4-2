
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
import hashlib, json, secrets, sqlite3

ROOT = Path(__file__).parent
DB_PATH = ROOT / "data" / "bplab_lims_demo.db"

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def now():
    return datetime.now().isoformat(timespec="seconds")

def phash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          username TEXT PRIMARY KEY, display_name TEXT, password_hash TEXT,
          role TEXT, enabled INTEGER DEFAULT 1, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS auth_sessions(
          token TEXT PRIMARY KEY, username TEXT, expires_at TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS samples(
          sample_no TEXT PRIMARY KEY, client TEXT, sample_name TEXT, model TEXT,
          batch_no TEXT, qty_received REAL, qty_current REAL, unit TEXT,
          received_date TEXT, received_by TEXT, status TEXT, location TEXT,
          owner TEXT, due_date TEXT, notes TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sample_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, sample_no TEXT, actor TEXT,
          action TEXT, from_status TEXT, to_status TEXT, from_location TEXT,
          to_location TEXT, details TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS tasks(
          id INTEGER PRIMARY KEY AUTOINCREMENT, task_no TEXT UNIQUE, sample_no TEXT,
          experiment TEXT, assignee TEXT, reviewer TEXT, status TEXT,
          room TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS records(
          id INTEGER PRIMARY KEY AUTOINCREMENT, record_no TEXT, task_no TEXT,
          sample_no TEXT, version INTEGER, experiment TEXT, owner TEXT,
          status TEXT, payload TEXT, template_version TEXT, sop_version TEXT,
          change_reason TEXT, created_at TEXT, updated_at TEXT,
          UNIQUE(record_no,version)
        );
        CREATE TABLE IF NOT EXISTS reviews(
          id INTEGER PRIMARY KEY AUTOINCREMENT, record_no TEXT, version INTEGER,
          reviewer TEXT, decision TEXT, comment TEXT, reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_logs(
          id INTEGER PRIMARY KEY AUTOINCREMENT, record_no TEXT, version INTEGER,
          actor TEXT, action TEXT, field_name TEXT, old_value TEXT, new_value TEXT,
          reason TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS template_versions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, experiment TEXT, doc_type TEXT,
          file_name TEXT, version TEXT, effective_date TEXT, status TEXT,
          uploader TEXT, uploaded_at TEXT, change_note TEXT
        );
        CREATE TABLE IF NOT EXISTS sample_returns(
          id INTEGER PRIMARY KEY AUTOINCREMENT, sample_no TEXT, task_no TEXT,
          returned_by TEXT, qty_used REAL, qty_returned REAL, condition TEXT,
          proposed_location TEXT, status TEXT, confirmed_by TEXT,
          confirmed_location TEXT, return_time TEXT, confirm_time TEXT, note TEXT
        );
        """)
        users = [
          ("admin","系统管理员",phash("admin123"),"管理员",1,now()),
          ("receiver","收样员王工",phash("receive123"),"收样员",1,now()),
          ("tester","实验员张工",phash("test123"),"实验人员",1,now()),
          ("reviewer","复核员李工",phash("review123"),"复核实验员",1,now()),
          ("store","样品管理员赵工",phash("store123"),"样品管理员",1,now()),
        ]
        c.executemany("INSERT OR IGNORE INTO users VALUES(?,?,?,?,?,?)", users)

def get_user(username):
    with connect() as c:
        r = c.execute("SELECT username,display_name,role,enabled FROM users WHERE username=?", (username,)).fetchone()
    return dict(r) if r else None

def authenticate(username,password):
    with connect() as c:
        r = c.execute(
            "SELECT username,display_name,role FROM users WHERE username=? AND password_hash=? AND enabled=1",
            (username.strip(),phash(password))
        ).fetchone()
    return dict(r) if r else None

def create_session(username, days=7):
    token = secrets.token_urlsafe(28)
    expires = (datetime.now()+timedelta(days=days)).isoformat(timespec="seconds")
    with connect() as c:
        c.execute("INSERT INTO auth_sessions VALUES(?,?,?,?)",(token,username,expires,now()))
    return token

def session_user(token):
    if not token: return None
    with connect() as c:
        r = c.execute("""
          SELECT u.username,u.display_name,u.role,s.expires_at
          FROM auth_sessions s JOIN users u ON u.username=s.username
          WHERE s.token=? AND s.expires_at>? AND u.enabled=1
        """,(token,now())).fetchone()
    return dict(r) if r else None

def delete_session(token):
    with connect() as c:
        c.execute("DELETE FROM auth_sessions WHERE token=?",(token,))

def add_event(sample_no,actor,action,from_status,to_status,from_location,to_location,details=""):
    with connect() as c:
        c.execute("""
          INSERT INTO sample_events(sample_no,actor,action,from_status,to_status,
          from_location,to_location,details,created_at) VALUES(?,?,?,?,?,?,?,?,?)
        """,(sample_no,actor,action,from_status,to_status,from_location,to_location,details,now()))

def next_sample_no():
    prefix = datetime.now().strftime("BP-S%Y%m%d-")
    with connect() as c:
        r=c.execute("SELECT sample_no FROM samples WHERE sample_no LIKE ? ORDER BY sample_no DESC LIMIT 1",(prefix+"%",)).fetchone()
    seq=int(r["sample_no"].split("-")[-1])+1 if r else 1
    return f"{prefix}{seq:03d}"

def create_sample(data, experiments, actor):
    with connect() as c:
        c.execute("""
          INSERT INTO samples(sample_no,client,sample_name,model,batch_no,qty_received,
          qty_current,unit,received_date,received_by,status,location,owner,due_date,
          notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,(data["sample_no"],data["client"],data["sample_name"],data["model"],
        data["batch_no"],data["qty_received"],data["qty_received"],data["unit"],
        data["received_date"],actor,"待分配",data["location"],actor,data["due_date"],
        data["notes"],now(),now()))
        for i,exp in enumerate(experiments,1):
            task_no=f"{data['sample_no']}-T{i:02d}"
            c.execute("""INSERT INTO tasks(task_no,sample_no,experiment,assignee,reviewer,
              status,room,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)""",
              (task_no,data["sample_no"],exp,"","","待分配","",now(),now()))
    add_event(data["sample_no"],actor,"样品接收并入库","", "待分配","",data["location"],f"检测项目：{', '.join(experiments)}")

def list_samples():
    with connect() as c:
        rows=c.execute("SELECT * FROM samples ORDER BY updated_at DESC").fetchall()
    return [dict(x) for x in rows]

def sample(sample_no):
    with connect() as c:
        r=c.execute("SELECT * FROM samples WHERE sample_no=?",(sample_no,)).fetchone()
    return dict(r) if r else None

def sample_events(sample_no):
    with connect() as c:
        rows=c.execute("SELECT * FROM sample_events WHERE sample_no=? ORDER BY id",(sample_no,)).fetchall()
    return [dict(x) for x in rows]

def update_sample(sample_no, actor, action, status=None, location=None, owner=None, details="", qty_current=None):
    old=sample(sample_no)
    ns=status if status is not None else old["status"]
    nl=location if location is not None else old["location"]
    no=owner if owner is not None else old["owner"]
    q=qty_current if qty_current is not None else old["qty_current"]
    with connect() as c:
        c.execute("UPDATE samples SET status=?,location=?,owner=?,qty_current=?,updated_at=? WHERE sample_no=?",
                  (ns,nl,no,q,now(),sample_no))
    add_event(sample_no,actor,action,old["status"],ns,old["location"],nl,details)

def list_tasks(statuses=None,assignee=None,reviewer=None):
    q="SELECT t.*,s.sample_name,s.location,s.status AS sample_status FROM tasks t JOIN samples s ON s.sample_no=t.sample_no WHERE 1=1"
    args=[]
    if statuses:
        q += " AND t.status IN (%s)" % ",".join("?"*len(statuses)); args.extend(statuses)
    if assignee is not None:
        q += " AND t.assignee=?"; args.append(assignee)
    if reviewer is not None:
        q += " AND t.reviewer=?"; args.append(reviewer)
    q += " ORDER BY t.updated_at DESC"
    with connect() as c: rows=c.execute(q,args).fetchall()
    return [dict(x) for x in rows]

def assign_task(task_no,assignee,reviewer,room,actor):
    with connect() as c:
        t=c.execute("SELECT * FROM tasks WHERE task_no=?",(task_no,)).fetchone()
        c.execute("UPDATE tasks SET assignee=?,reviewer=?,room=?,status='已分配',updated_at=? WHERE task_no=?",
                  (assignee,reviewer,room,now(),task_no))
    update_sample(t["sample_no"],actor,"任务分配",status="已分配",owner=assignee,
                  details=f"{t['experiment']}分配给{assignee}，复核员{reviewer}")

def task(task_no):
    with connect() as c:
        r=c.execute("SELECT * FROM tasks WHERE task_no=?",(task_no,)).fetchone()
    return dict(r) if r else None

def set_task_status(task_no,status):
    with connect() as c:
        c.execute("UPDATE tasks SET status=?,updated_at=? WHERE task_no=?",(status,now(),task_no))

def next_record_no():
    prefix=datetime.now().strftime("BP-R%Y%m%d-")
    with connect() as c:
        r=c.execute("SELECT record_no FROM records WHERE record_no LIKE ? ORDER BY record_no DESC LIMIT 1",(prefix+"%",)).fetchone()
    seq=int(r["record_no"].split("-")[-1])+1 if r else 1
    return f"{prefix}{seq:03d}"

def flatten(value,prefix=""):
    out={}
    if isinstance(value,dict):
        for k,v in value.items():
            out.update(flatten(v,f"{prefix}.{k}" if prefix else k))
    elif isinstance(value,list):
        for i,v in enumerate(value):
            out.update(flatten(v,f"{prefix}[{i}]"))
    else:
        out[prefix]=value
    return out

def latest_record_by_task(task_no):
    with connect() as c:
        r=c.execute("SELECT * FROM records WHERE task_no=? ORDER BY version DESC LIMIT 1",(task_no,)).fetchone()
    if not r:return None
    d=dict(r);d["payload"]=json.loads(d["payload"]);return d

def record_versions(record_no):
    with connect() as c:
        rows=c.execute("SELECT * FROM records WHERE record_no=? ORDER BY version",(record_no,)).fetchall()
    out=[]
    for r in rows:
        d=dict(r);d["payload"]=json.loads(d["payload"]);out.append(d)
    return out

def latest_records(owner=None,statuses=None):
    q="""SELECT r.* FROM records r WHERE r.version=(
      SELECT MAX(x.version) FROM records x WHERE x.record_no=r.record_no)"""
    args=[]
    if owner is not None:q+=" AND r.owner=?";args.append(owner)
    if statuses:
        q+=" AND r.status IN (%s)"%(",".join("?"*len(statuses)));args.extend(statuses)
    q+=" ORDER BY r.updated_at DESC"
    with connect() as c:rows=c.execute(q,args).fetchall()
    out=[]
    for r in rows:
        d=dict(r);d["payload"]=json.loads(d["payload"]);out.append(d)
    return out

def record(record_no,version):
    with connect() as c:
        r=c.execute("SELECT * FROM records WHERE record_no=? AND version=?",(record_no,version)).fetchone()
    if not r:return None
    d=dict(r);d["payload"]=json.loads(d["payload"]);return d

def save_record(record_no,task_no,sample_no,experiment,version,payload,owner,status,
                template_version,sop_version,reason="",compare_payload=None):
    t=now()
    with connect() as c:
        c.execute("""
          INSERT INTO records(record_no,task_no,sample_no,version,experiment,owner,status,
          payload,template_version,sop_version,change_reason,created_at,updated_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(record_no,version) DO UPDATE SET status=excluded.status,
          payload=excluded.payload,change_reason=excluded.change_reason,updated_at=excluded.updated_at
        """,(record_no,task_no,sample_no,version,experiment,owner,status,
        json.dumps(payload,ensure_ascii=False,default=str),template_version,sop_version,
        reason,t,t))
        old=flatten(compare_payload or {})
        new=flatten(payload)
        for f in sorted(set(old)|set(new)):
            ov,nv=old.get(f,""),new.get(f,"")
            if str(ov)!=str(nv):
                c.execute("""INSERT INTO audit_logs(record_no,version,actor,action,
                  field_name,old_value,new_value,reason,created_at)
                  VALUES(?,?,?,?,?,?,?,?,?)""",
                  (record_no,version,owner,"字段修改",f,str(ov),str(nv),reason,t))
        c.execute("""INSERT INTO audit_logs(record_no,version,actor,action,reason,created_at)
                     VALUES(?,?,?,?,?,?)""",
                  (record_no,version,owner,"提交复核" if "待复核" in status else "保存记录",reason,t))

def pending_reviews(reviewer=None):
    q="SELECT * FROM records WHERE status IN ('待复核','更正待复核')"
    args=[]
    if reviewer:
        q+=" AND task_no IN (SELECT task_no FROM tasks WHERE reviewer=?)";args.append(reviewer)
    q+=" ORDER BY updated_at DESC"
    with connect() as c:rows=c.execute(q,args).fetchall()
    out=[]
    for r in rows:
        d=dict(r);d["payload"]=json.loads(d["payload"]);out.append(d)
    return out

def review_record(record_no,version,reviewer,decision,comment):
    r=record(record_no,version)
    status="已锁定" if decision=="通过" else "退回修改"
    with connect() as c:
        c.execute("UPDATE records SET status=?,updated_at=? WHERE record_no=? AND version=?",
                  (status,now(),record_no,version))
        c.execute("INSERT INTO reviews(record_no,version,reviewer,decision,comment,reviewed_at) VALUES(?,?,?,?,?,?)",
                  (record_no,version,reviewer,decision,comment,now()))
        c.execute("""INSERT INTO audit_logs(record_no,version,actor,action,reason,created_at)
                     VALUES(?,?,?,?,?,?)""",
                  (record_no,version,reviewer,"复核"+decision,comment,now()))
    if decision=="通过":
        set_task_status(r["task_no"],"已完成")
        open_tasks=list_tasks(statuses=["待分配","已分配","检测中","待复核"],assignee=None)
        unfinished=[x for x in open_tasks if x["sample_no"]==r["sample_no"]]
        if not unfinished:
            update_sample(r["sample_no"],reviewer,"全部检测完成",status="待归还",details="全部原始记录已复核通过")
    else:
        set_task_status(r["task_no"],"退回修改")

def audit_logs(record_no,version=None):
    q="SELECT * FROM audit_logs WHERE record_no=?";args=[record_no]
    if version is not None:q+=" AND version=?";args.append(version)
    q+=" ORDER BY id"
    with connect() as c:rows=c.execute(q,args).fetchall()
    return [dict(x) for x in rows]

def create_revision(record_no,actor,reason):
    versions=record_versions(record_no)
    base=versions[-1]
    new_version=base["version"]+1
    save_record(record_no,base["task_no"],base["sample_no"],base["experiment"],new_version,
                base["payload"],actor,"草稿",base["template_version"],base["sop_version"],
                reason,base["payload"])
    return new_version

def returns_pending():
    with connect() as c:
        rows=c.execute("SELECT * FROM sample_returns WHERE status='待回库确认' ORDER BY id DESC").fetchall()
    return [dict(x) for x in rows]

def submit_return(sample_no,task_no,actor,qty_used,qty_returned,condition,location,note):
    with connect() as c:
        c.execute("""INSERT INTO sample_returns(sample_no,task_no,returned_by,qty_used,
          qty_returned,condition,proposed_location,status,return_time,note)
          VALUES(?,?,?,?,?,?,?,'待回库确认',?,?)""",
          (sample_no,task_no,actor,qty_used,qty_returned,condition,location,now(),note))
    update_sample(sample_no,actor,"样品归还申请",status="待回库确认",location="回库交接区",
                  owner="",details=f"使用{qty_used}，归还{qty_returned}，状态：{condition}")

def confirm_return(return_id,actor,location):
    with connect() as c:
        r=c.execute("SELECT * FROM sample_returns WHERE id=?",(return_id,)).fetchone()
        c.execute("""UPDATE sample_returns SET status='已回库',confirmed_by=?,
          confirmed_location=?,confirm_time=? WHERE id=?""",(actor,location,now(),return_id))
    update_sample(r["sample_no"],actor,"样品回库确认",status="留样保存",location=location,
                  owner=actor,qty_current=r["qty_returned"],details=f"确认回库，样品状态：{r['condition']}")

def active_version(experiment,doc_type):
    with connect() as c:
        r=c.execute("""SELECT * FROM template_versions WHERE experiment=? AND doc_type=?
          AND status='现行' ORDER BY id DESC LIMIT 1""",(experiment,doc_type)).fetchone()
    return dict(r) if r else None

def seed_template(experiment,doc_type,file_name,version="A/0"):
    if not file_name:return
    with connect() as c:
        e=c.execute("SELECT 1 FROM template_versions WHERE experiment=? AND doc_type=? AND version=?",
                    (experiment,doc_type,version)).fetchone()
        if not e:
            c.execute("""INSERT INTO template_versions(experiment,doc_type,file_name,version,
              effective_date,status,uploader,uploaded_at,change_note)
              VALUES(?,?,?,?,?,'现行','system',?,'系统初始化')""",
              (experiment,doc_type,file_name,version,datetime.now().date().isoformat(),now()))

def all_template_versions():
    with connect() as c:rows=c.execute("SELECT * FROM template_versions ORDER BY experiment,doc_type,id DESC").fetchall()
    return [dict(x) for x in rows]

def add_template(experiment,doc_type,file_name,version,effective,uploader,note):
    with connect() as c:
        c.execute("UPDATE template_versions SET status='停用' WHERE experiment=? AND doc_type=? AND status='现行'",
                  (experiment,doc_type))
        c.execute("""INSERT INTO template_versions(experiment,doc_type,file_name,version,
          effective_date,status,uploader,uploaded_at,change_note)
          VALUES(?,?,?,?,?,'现行',?,?,?)""",
          (experiment,doc_type,file_name,version,effective,uploader,now(),note))

def users():
    with connect() as c:rows=c.execute("SELECT username,display_name,role,enabled,created_at FROM users ORDER BY username").fetchall()
    return [dict(x) for x in rows]

def add_user(username,display_name,password,role):
    with connect() as c:
        c.execute("INSERT INTO users VALUES(?,?,?,?,1,?)",(username,display_name,phash(password),role,now()))
