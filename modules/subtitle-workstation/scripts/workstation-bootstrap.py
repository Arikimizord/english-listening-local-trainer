"""Explicit private-module path under isolated Python; never imports the caller cwd."""
import pathlib,sys,runpy
scripts=pathlib.Path(__file__).resolve().parent
sys.path.insert(0,str(scripts))
runpy.run_path(str(scripts/'workstation-core.py'),run_name='__main__')
