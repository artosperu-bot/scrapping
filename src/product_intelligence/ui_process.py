from dataclasses import dataclass,field
from datetime import datetime
from itertools import count

@dataclass
class ProcessSession:
    session_id:str; kind:str; label:str; total:int=1; state:str='running'; stage:str='queued'; product_percent:int=0; overall_percent:int=0; completed:int=0; started_at:str=field(default_factory=lambda:datetime.now().isoformat()); summary:dict=field(default_factory=dict); logs:list[str]=field(default_factory=list)

class ProcessRegistry:
    def __init__(self): self._ids=count(1); self._sessions={}
    def start(self,kind,label,total=1):
        s=ProcessSession(f"{str(kind).lower()}-{next(self._ids):03d}",kind,label,max(1,int(total or 1))); self._sessions[s.session_id]=s; return s
    def get(self,session_id): return self._sessions.get(session_id)
    def apply(self,session_id,event):
        s=self._sessions[session_id]
        if event.get('stage'): s.stage=str(event['stage'])
        if event.get('product_percent') is not None: s.product_percent=max(0,min(100,int(event['product_percent'])))
        if event.get('overall_percent') is not None: s.overall_percent=max(0,min(100,int(event['overall_percent'])))
        if event.get('completed') is not None: s.completed=max(0,int(event['completed'] or 0))
        if isinstance(event.get('summary'),dict): s.summary.update(event['summary'])
        if event.get('type') in {'done','batch_done'}: s.state='complete'; s.stage='done'; s.product_percent=100
        elif event.get('type') in {'fatal','error'}: s.state='error'; s.stage='error'
        return s
    def log(self,session_id,message): self._sessions[session_id].logs.append(str(message))
