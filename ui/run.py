import sys,threading
import pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent.parent))
from liveclips.app import App,server
app=App(sys.argv[1]);app.store.setting('paused',False)
srv=server(app,int(sys.argv[2]) if len(sys.argv)>2 else 8765);print('serving',flush=True);srv.serve_forever()
