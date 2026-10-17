"""Local browser preview. Always loopback; public downloads remain disabled."""
import argparse
import os
from pathlib import Path
import sys

BACKEND=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(BACKEND))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8090)
    parser.add_argument('--offline-workflow',action='store_true',help='Enable the fixed local sample queue; public URLs remain disabled')
    parser.add_argument('--demo-downloads',action='store_true',help='Serve bundled sample files so the download flow can be exercised locally')
    parser.add_argument('--state',type=Path,default=BACKEND/'clipora_v8_web_runtime')
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Use a port between 1024 and 65535')
    if args.offline_workflow and args.demo_downloads:
        parser.error('--demo-downloads serves sample files on the product preview; run it without --offline-workflow')
    os.environ['CLIPORA_WEB_ORIGIN']=f'http://127.0.0.1:{args.port}'
    os.environ['CLIPORA_WEB_STATE']=str(args.state.resolve())
    os.environ['CLIPORA_DEMO_DOWNLOADS']='1' if args.demo_downloads else '0'
    import uvicorn
    target='clipora_v8_web.main:app_factory';factory=True
    if args.offline_workflow:
        from clipora_v8_local_workflow.app import create_local_app
        target=create_local_app(os.environ['CLIPORA_WEB_ORIGIN'],args.state.resolve());factory=False
    uvicorn.run(target,factory=factory,host='127.0.0.1',port=args.port,
                proxy_headers=False,access_log=False,limit_concurrency=32,timeout_keep_alive=5)


if __name__=='__main__':main()
