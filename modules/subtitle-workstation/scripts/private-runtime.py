"""Private DLL bootstrap for approved local GPU model processes, with no global changes."""
import os,pathlib
_HANDLES=[]
def configure(root):
    root=pathlib.Path(root).resolve()
    paths=[root/'runtime/ffmpeg/ffmpeg-7.1.1-full_build-shared/bin',root/'envs/subtitle/Lib/site-packages/torch/lib']
    for p in paths:
        if not p.is_dir():raise RuntimeError('Private DLL directory missing: '+str(p))
        if os.name=='nt':_HANDLES.append(os.add_dll_directory(str(p)))
    os.environ['PATH']=os.pathsep.join(str(p) for p in paths)+os.pathsep+os.environ.get('PATH','')
    return [str(p) for p in paths]
