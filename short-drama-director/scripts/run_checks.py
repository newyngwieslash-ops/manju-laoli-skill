#!/usr/bin/env python3
"""Reproducible offline suite; runs no models, installation or network operations."""
import os
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]

def main():
    env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
    commands=[['-m','unittest','discover','-s','short-drama-director/tests','-v'],
              ['short-drama-director/scripts/model_contract.py'],
              ['short-drama-director/scripts/check_package.py'],
              ['short-drama-director/scripts/validate_prompt.py','--self-test'],
              ['short-drama-director/scripts/sd_core.py','--self-test'],
              ['short-drama-director/scripts/compile_feed.py','--self-test'],
              ['short-drama-director/scripts/audit_contract.py','--self-test']]
    for command in commands:
        result=subprocess.run([sys.executable,'-X','utf8',*command],cwd=ROOT,env=env)
        if result.returncode:return result.returncode
    print('Offline structure/logic checks PASS; human semantics and video acceptance NOT RUN')
    return 0
if __name__=='__main__':sys.exit(main())
